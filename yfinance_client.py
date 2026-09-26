"""
yfinance_client.py
------------------
Yahoo Finance (yfinance) を使った株価データ取得クライアント。
J-Quants AsyncJQuantsClient の以下メソッドと同じインターフェースを提供：

  - get_prices_daily_quotes()         : 1銘柄・期間指定取得
  - get_prices_daily_quotes_by_date() : 全銘柄・日付指定一括取得（FixCB互換）
  - is_trading_day()                  : 取引日チェック

戻り値のDataFrame列は J-Quants 形式と同一:
  1銘柄取得: Date, Open, High, Low, Close, Volume
  一括取得:  Code, Date, Open, High, Low, Close, Volume

切り替え方法:
  daily_data_collection.py の DATA_SOURCE を変更するだけ
    DATA_SOURCE = "yfinance"  # Yahoo Finance（16:00 JST頃にデータ確定）
    DATA_SOURCE = "jquants"   # J-Quants（23:30 JST頃にデータ確定）
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def code_to_ticker(code: str) -> str:
    """jQuantsの銘柄コード → yfinanceティッカーに変換。
    例: "7203" → "7203.T" / "72030" → "7203.T"
    """
    c = str(code).strip()
    if len(c) == 5 and c.endswith('0'):
        c = c[:-1]
    return f"{c}.T"


def ticker_to_code(ticker: str) -> str:
    """yfinanceティッカー → jQuants銘柄コードに変換。
    例: "7203.T" → "7203"
    """
    return ticker.replace(".T", "")


def _yyyymmdd_to_ymd(date_str: str, offset_days: int = 0) -> str:
    """YYYYMMDD → YYYY-MM-DD 変換（offset_days日後）。"""
    dt = datetime.strptime(date_str, '%Y%m%d') + timedelta(days=offset_days)
    return dt.strftime('%Y-%m-%d')


def _normalize_single(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """yfinanceのDataFrameをjQuants互換形式に正規化（Codeなし版）。"""
    try:
        df = df.reset_index()
        date_col = df.columns[0]
        if hasattr(df[date_col].dtype, 'tz') or 'tz' in str(df[date_col].dtype):
            df[date_col] = df[date_col].dt.tz_localize(None)
        df = df.rename(columns={date_col: 'Date'})
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['Volume'] = pd.to_numeric(df.get('Volume', 0), errors='coerce').fillna(0).astype(int)
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Close'])
        return df if not df.empty else None
    except Exception as e:
        logger.debug(f"DataFrame正規化エラー: {e}")
        return None


def _fetch_single_sync(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """1銘柄のOHLCVを同期取得。"""
    try:
        t = yf.Ticker(ticker)
        df = t.history(start=start, end=end, auto_adjust=False)
        if df is None or df.empty:
            return None
        return _normalize_single(df)
    except Exception as e:
        logger.debug(f"yfinance 1銘柄取得エラー [{ticker}]: {e}")
        return None


def _fetch_bulk_sync(tickers: list, start: str, end: str) -> Optional[pd.DataFrame]:
    """複数銘柄を yf.download で一括取得。Code列付きDataFrameを返す。"""
    try:
        raw = yf.download(
            tickers, start=start, end=end,
            auto_adjust=False, progress=False,
            group_by='ticker', threads=True,
        )
        if raw is None or raw.empty:
            return None

        frames = []
        if len(tickers) == 1:
            df_single = _normalize_single(raw)
            if df_single is not None:
                df_single['Code'] = ticker_to_code(tickers[0])
                frames.append(df_single)
        else:
            for ticker in tickers:
                try:
                    if ticker not in raw.columns.get_level_values(0):
                        continue
                    df_t = raw[ticker].copy().dropna(how='all')
                    if df_t.empty:
                        continue
                    df_norm = _normalize_single(df_t)
                    if df_norm is None:
                        continue
                    df_norm['Code'] = ticker_to_code(ticker)
                    frames.append(df_norm)
                except Exception as e:
                    logger.debug(f"一括取得 個別処理エラー [{ticker}]: {e}")

        if not frames:
            return None

        result = pd.concat(frames, ignore_index=True)
        return result[['Code', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']]

    except Exception as e:
        logger.warning(f"yfinance 一括取得エラー: {e}")
        return None


class YFinanceClient:
    """yfinanceを使った株価データ取得クライアント。
    AsyncJQuantsClientの価格取得メソッドと同じインターフェース。
    """

    def __init__(self):
        logger.info("📡 YFinanceClient 初期化（Yahoo Finance・無料・16:00 JST頃データ確定）")

    async def get_prices_daily_quotes(
        self, session, code: str, from_date: str, to_date: str, retry: int = 0
    ) -> Optional[pd.DataFrame]:
        """日次株価データを取得（jQuantsの同名メソッドと同じ戻り値形式）。"""
        ticker = code_to_ticker(code)
        start = _yyyymmdd_to_ymd(from_date)
        end = _yyyymmdd_to_ymd(to_date, offset_days=1)
        try:
            df = await asyncio.to_thread(_fetch_single_sync, ticker, start, end)
            return df
        except Exception as e:
            if retry < 2:
                await asyncio.sleep(1.0)
                return await self.get_prices_daily_quotes(session, code, from_date, to_date, retry + 1)
            logger.warning(f"yfinance取得失敗 [{code}]: {e}")
            return None

    async def get_prices_daily_quotes_by_date(
        self, session, date: str, retry: int = 0, stock_codes: Optional[list] = None
    ) -> Optional[pd.DataFrame]:
        """指定日の全銘柄分の株価データを一括取得（FixCB互換）。
        bulk_update_from_snapshot() にそのまま渡せる形式で返す。

        Args:
            session:     未使用（互換）
            date:        YYYYMMDD形式
            stock_codes: 取得する銘柄コードのリスト（必須）
        """
        if not stock_codes:
            logger.warning("get_prices_daily_quotes_by_date: stock_codesが空です")
            return None

        tickers = [code_to_ticker(c) for c in stock_codes]
        start = _yyyymmdd_to_ymd(date)
        end = _yyyymmdd_to_ymd(date, offset_days=1)

        logger.info(f"📡 yfinance一括取得開始: {date} ({len(tickers)}銘柄)")

        try:
            BATCH_SIZE = 500
            all_frames = []

            for i in range(0, len(tickers), BATCH_SIZE):
                batch = tickers[i:i + BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                total = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
                logger.info(f"  バッチ {batch_num}/{total}: {len(batch)}銘柄取得中...")

                df_batch = await asyncio.to_thread(_fetch_bulk_sync, batch, start, end)
                if df_batch is not None and not df_batch.empty:
                    all_frames.append(df_batch)

                if i + BATCH_SIZE < len(tickers):
                    await asyncio.sleep(2.0)

            if not all_frames:
                logger.warning(f"yfinance一括取得: {date}のデータが空でした（休日の可能性）")
                return None

            result = pd.concat(all_frames, ignore_index=True)
            logger.info(f"✅ yfinance一括取得完了: {len(result)}行 ({result['Code'].nunique()}銘柄)")
            return result

        except Exception as e:
            if retry < 2:
                await asyncio.sleep(3.0)
                return await self.get_prices_daily_quotes_by_date(
                    session, date, retry + 1, stock_codes
                )
            logger.warning(f"yfinance一括取得失敗 [{date}]: {e}")
            return None

    async def is_trading_day(self, session, date: str) -> bool:
        """指定日が取引日かどうか確認（jQuantsClientとの互換）。"""
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            if dt.weekday() >= 5:
                return False
            start = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
            end = (dt + timedelta(days=1)).strftime('%Y-%m-%d')
            df = await asyncio.to_thread(_fetch_single_sync, "7203.T", start, end)
            if df is None or df.empty:
                return False
            return date in df['Date'].values
        except Exception as e:
            logger.warning(f"yfinance 取引日チェック失敗: {e}")
            return True

    async def authenticate(self, session):
        """jQuantsClientとの互換のためのダミーメソッド（認証不要）。"""
        pass


if __name__ == "__main__":
    async def test():
        client = YFinanceClient()
        print("=== yfinanceクライアント動作確認 ===\n")

        print("① トヨタ(7203) 過去5日データ取得...")
        end = datetime.now()
        start = end - timedelta(days=10)
        df = await client.get_prices_daily_quotes(
            None, "7203", start.strftime('%Y%m%d'), end.strftime('%Y%m%d')
        )
        if df is not None:
            print(f"   ✅ {len(df)}行 / 最新日: {df['Date'].iloc[-1]} / 終値: {df['Close'].iloc[-1]}")
        else:
            print("   ❌ 取得失敗")

        print("\n② 一括取得テスト（10銘柄）...")
        codes = ["7203", "6758", "9984", "6367", "8306", "6861", "7974", "9432", "8058", "6501"]
        date_str = (datetime.now() - timedelta(days=3)).strftime('%Y%m%d')
        bulk_df = await client.get_prices_daily_quotes_by_date(None, date_str, stock_codes=codes)
        if bulk_df is not None:
            print(f"   ✅ {len(bulk_df)}行 / {bulk_df['Code'].nunique()}銘柄")
            print(bulk_df.to_string())
        else:
            print("   ❌ 一括取得失敗")

    asyncio.run(test())
