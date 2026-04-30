#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日次株式スクリーニングデータ収集スクリプト（並列処理・全銘柄対応・オプション機能付き）
asyncio + aiohttpによる高速並列処理で全銘柄をスクリーニング
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
import pandas as pd
from typing import List, Dict, Any, Optional
import pytz
import math
import psutil
from price_cache import get_cache
from persistent_cache import PersistentPriceCache
from trading_day_helper import get_latest_trading_day, get_date_range_for_screening

# ============================================================
# スクリーニングオプション設定
# ============================================================

# ブレイクアウト（持ち合い上放れ）オプション
# BREAKOUT_BOX_WIDTH_PCT = 15  # ボックス幅の最大値（%）

# 200日新高値押し目オプション
PULLBACK_EMA_FILTER = "all"  # "10ema", "20ema", "50ema", "all" (いずれか)
PULLBACK_STOCHASTIC_FILTER = False  # True: ストキャス売られすぎのみ, False: 全て

# ============================================================

# スクリプトのディレクトリを基準とした相対パス
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログ設定
log_file = LOG_DIR / f"daily_collection_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 設定
CONCURRENT_REQUESTS = 1  # 同時実行数（レート制限対応: 60件/分 = 1件/秒）
HISTORY_DAYS = 90
RETRY_COUNT = 3
RETRY_DELAY = 2
API_CALL_DELAY = 2.0  # APIコール間の待機時間（秒）（レート制限対応: 1.1→2.0秒）


def safe_float(value, default=None):
    """安全にfloatに変換（NaN, Infを回避）"""
    if value is None or value == "" or value == "NaN":
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default

def safe_int(value, default=None):
    """安全にintに変換"""
    if value is None or value == "":
        return default
    try:
        return int(float(value))  # float経由でintに変換
    except (ValueError, TypeError):
        return default


class SupabaseClient:
    """Supabase クライアント"""
    
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_ANON_KEY')
        self.enabled = bool(self.url and self.key)
        self.client = None
        
        if self.enabled:
            try:
                from supabase import create_client
                self.client = create_client(self.url, self.key)
                logger.info("Supabase接続成功")
            except Exception as e:
                logger.error(f"Supabase接続失敗: {e}")
                self.enabled = False
    
    def save_screening_result(self, screening_type, date, total_stocks, execution_time_ms=0):
        """スクリーニング結果の概要を保存"""
        if not self.enabled:
            return None
        
        try:
            data = {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "screening_type": screening_type,
                "screening_date": date,
                "market_filter": "all",
                "total_stocks_found": total_stocks,
                "execution_time_ms": execution_time_ms
            }
            
            result = self.client.table("screening_results").insert(data).execute()
            logger.info(f"Supabase保存成功: {screening_type} - {total_stocks}銘柄")
            return result.data[0]["id"] if result.data else None
            
        except Exception as e:
            logger.error(f"Supabase保存エラー ({screening_type}): {e}")
            return None
    
    def save_detected_stocks(self, screening_result_id, stocks):
        """検出された銘柄の詳細を保存（バッチINSERT）"""
        if not self.enabled or not screening_result_id:
            return False
        
        if not stocks or len(stocks) == 0:
            logger.warning("保存する銘柄がありません（0銘柄）")
            # 0銘柄の場合も、screening_result_idに紐づく古いデータを削除
            try:
                self.client.table("detected_stocks").delete().eq("screening_result_id", screening_result_id).execute()
                logger.info(f"古いdetected_stocksデータを削除しました (screening_result_id={screening_result_id})")
            except Exception as e:
                logger.error(f"古いデータ削除エラー: {e}")
            return True  # 0銘柄でも成功とみなす
        
        try:
            # バッチ用データリストを作成
            data_list = []
            for stock in stocks:
                data = {
                    "screening_result_id": screening_result_id,
                    "stock_code": str(stock.get("code", "")),
                    "company_name": str(stock.get("name", "")),
                    "market": str(stock.get("market", "")),
                    "close_price": safe_float(stock.get("price") or stock.get("close"), 0),
                    "volume": safe_int(stock.get("volume"), 0),
                    "ema_10": safe_float(stock.get("ema10") or stock.get("ema_10")),
                    "ema_20": safe_float(stock.get("ema20") or stock.get("ema_20")),
                    "ema_50": safe_float(stock.get("ema50") or stock.get("ema_50")),
                    "week52_high": safe_float(stock.get("high_200day")),
                    "touch_ema": str(stock.get("touched_emas") or stock.get("ema_touch") or "") if (stock.get("touched_emas") or stock.get("ema_touch")) else None,
                    "pullback_percentage": safe_float(stock.get("pullback_pct")),
                    "bollinger_upper": safe_float(stock.get("upper_3sigma")),
                    "bollinger_lower": safe_float(stock.get("lower_3sigma")),
                    "bollinger_middle": safe_float(stock.get("sma20")),
                    "touch_direction": str(stock.get("touch_direction", "upper")),
                    "stochastic_k": safe_float(stock.get("stochastic_k")),
                    "stochastic_d": safe_float(stock.get("stochastic_d"))
                }
                data_list.append(data)
            
            # バッチINSERT（一括保存）
            self.client.table("detected_stocks").insert(data_list).execute()
            
            logger.info(f"Supabase詳細保存成功: {len(stocks)}銘柄")
            return True
            
        except Exception as e:
            logger.error(f"Supabase詳細保存エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


class AsyncJQuantsClient:
    """非同期jQuants APIクライアント（V2 API対応）"""
    
    def __init__(self):
        # V2 API: APIキーを使用
        self.api_key = os.getenv('JQUANTS_API_KEY')
        
        # V1 API互換性（フォールバック）
        self.refresh_token = os.getenv('JQUANTS_REFRESH_TOKEN')
        self.id_token = None
        
        # V2 APIを優先する
        if self.api_key:
            self.api_version = "v2"
            self.base_url = "https://api.jquants.com/v2"
            logger.info("✅ J-Quants API V2を使用します（APIキー認証）")
            logger.info(f"✅ API Key: {self.api_key[:10]}...{self.api_key[-4:]}")
        elif self.refresh_token:
            self.api_version = "v1"
            self.base_url = "https://api.jquants.com/v1"
            logger.warning("⚠️ J-Quants API V1を使用します（Refresh Token認証）")
            logger.warning("⚠️ V2 APIへの移行を推奨します。JQUANTS_API_KEYを設定してください。")
            self._check_refresh_token_expiry()
        else:
            raise ValueError("JQUANTS_API_KEY または JQUANTS_REFRESH_TOKEN が設定されていません")
    
    def _check_refresh_token_expiry(self):
        """Refresh Token有効期限をチェック"""
        token_created_date = os.getenv('JQUANTS_TOKEN_CREATED_DATE')
        
        if not token_created_date:
            logger.warning("⚠️ JQUANTS_TOKEN_CREATED_DATE が設定されていません。Refresh Token取得日を環境変数に設定することを推奨します。")
            return
        
        try:
            created = datetime.strptime(token_created_date, "%Y-%m-%d")
            days_since_created = (datetime.now() - created).days
            
            if days_since_created >= 7:
                logger.error(f"🚨 Refresh Tokenの有効期限が切れています！（{days_since_created}日経過）")
                logger.error("🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得し、環境変数を更新してください。")
            elif days_since_created >= 6:
                logger.warning(f"⚠️ Refresh Tokenの有効期限が明日切れます！（{days_since_created}日経過）")
                logger.warning("🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得してください。")
            elif days_since_created >= 5:
                logger.warning(f"⚠️ Refresh Tokenの有効期限が近づいています（{days_since_created}日経過、残り{7-days_since_created}日）")
            else:
                logger.info(f"✅ Refresh Token有効期限: あと{7-days_since_created}日（{days_since_created}日経過）")
        except ValueError as e:
            logger.error(f"❌ JQUANTS_TOKEN_CREATED_DATE の形式が不正です（正しい形式: YYYY-MM-DD）: {e}")
    
    async def authenticate(self, session: aiohttp.ClientSession):
        """認証処理（V2はAPIキー、V1はRefresh Token）"""
        # V2 API: 認証不要（APIキーをヘッダーに追加するだけ）
        if self.api_version == "v2":
            logger.info("✅ J-Quants API V2: 認証不要（APIキー使用）")
            return True
        
        # V1 API: Refresh TokenでID Tokenを取得
        try:
            url = f"{self.base_url}/token/auth_refresh"
            params = {"refreshtoken": self.refresh_token}
            
            logger.info("🔐 jQuants API V1認証開始...")
            logger.info(f"🔑 Refresh Token長: {len(self.refresh_token) if self.refresh_token else 0}文字")
            logger.info(f"🔑 Refresh Token先頭: {self.refresh_token[:50] if self.refresh_token else 'None'}...")
            
            async with session.post(url, params=params) as response:
                status_code = response.status
                
                if status_code == 200:
                    data = await response.json()
                    self.id_token = data["idToken"]
                    logger.info("✅ jQuants API V1認証成功（ID Token取得完了）")
                    return True
                elif status_code == 400:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API V1認証失敗 [400 Bad Request]: Refresh Tokenの形式が不正です")
                    logger.error(f"詳細: {error_text}")
                    return False
                elif status_code == 401:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API V1認証失敗 [401 Unauthorized]: Refresh Tokenが無効または期限切れです")
                    logger.error(f"詳細: {error_text}")
                    logger.error("🔧 対処方法: V2 APIへの移行を推奨します。JQUANTS_API_KEYを設定してください。")
                    return False
                else:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API V1認証失敗 [{status_code}]: {error_text}")
                    return False
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ jQuants API V1認証失敗（ネットワークエラー）: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ jQuants API V1認証失敗（予期しないエラー）: {e}")
            logger.error(f"エラータイプ: {type(e).__name__}")
            return False
    
    def _get_headers(self):
        """バージョンに応じたヘッダーを返す"""
        if self.api_version == "v2":
            return {"x-api-key": self.api_key}
        else:
            return {"Authorization": f"Bearer {self.id_token}"}
    
    async def get_listed_info(self, session: aiohttp.ClientSession, date: str = None):
        """上場銘柄一覧を取得（V1/V2対応）
        
        Args:
            session: aiohttp セッション
            date: 基準日（YYYYMMDD形式、V2のみ有効）
        """
        if self.api_version == "v1" and not self.id_token:
            await self.authenticate(session)
        
        try:
            # V2 API: /equities/master
            if self.api_version == "v2":
                url = f"{self.base_url}/equities/master"
            # V1 API: /listed/info
            else:
                url = f"{self.base_url}/listed/info"
            
            headers = self._get_headers()
            
            # V2 APIでdateパラメータを追加
            params = {}
            if date and self.api_version == "v2":
                params["date"] = date
            
            async with session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                # レート制限対応: APIコール後に待機
                await asyncio.sleep(API_CALL_DELAY)
                
                # V2 API: dataキーを使用
                if self.api_version == "v2":
                    result = data.get("data", [])
                    logger.info(f"🔍 銘柄一覧APIレスポンス: {len(result)}銘柄 (date={params.get('date', 'None')})")
                    if len(result) == 0:
                        logger.warning(f"⚠️ 銘柄データが0件です。レスポンス: {data}")
                    return result
                # V1 API: infoキーを使用
                else:
                    return data.get("info", [])
        except Exception as e:
            logger.error(f"銘柄一覧取得失敗: {e}")
            return None
    
    async def get_trading_calendar(self, session: aiohttp.ClientSession, from_date: str, to_date: str):
        """取引カレンダーを取得（V1/V2対応）"""
        if self.api_version == "v1" and not self.id_token:
            await self.authenticate(session)
        
        try:
            # V2 API: /markets/calendar (V1から名称変更)
            # V1: /markets/trading_calendar, V2: /markets/calendar
            endpoint = "/markets/calendar" if self.api_version == "v2" else "/markets/trading_calendar"
            url = f"{self.base_url}{endpoint}"
            headers = self._get_headers()
            params = {"from": from_date, "to": to_date}
            
            async with session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                # レート制限対応: APIコール後に待機
                await asyncio.sleep(API_CALL_DELAY)
                
                # V2 API: dataキーを使用
                if self.api_version == "v2":
                    return data.get("data", [])
                # V1 API: trading_calendarキーを使用
                else:
                    return data.get("trading_calendar", [])
        except Exception as e:
            logger.error(f"取引カレンダー取得失敗: {e}")
            return None
    
    async def is_trading_day(self, session: aiohttp.ClientSession, date: str) -> bool:
        """指定日が営業日かどうかを確認
        
        Args:
            session: aiohttp.ClientSession
            date: 日付文字列（YYYY-MM-DD形式）
        
        Returns:
            bool: 営業日ならTrue、休場日ならFalse
        """
        try:
            # 日付をYYYYMMDD形式に変換
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_yyyymmdd = date_obj.strftime("%Y%m%d")
            
            # 取引カレンダーを取得（指定日のみ）
            calendar = await self.get_trading_calendar(session, date_yyyymmdd, date_yyyymmdd)
            
            if not calendar:
                logger.warning(f"取引カレンダーの取得に失敗しました: {date}")
                return False
            
            # V2 API: HolDiv が "1" なら営業日、"0" なら休場日
            # V1 API: HolidayDivision が "0" なら営業日、"1" なら休場日
            for day in calendar:
                # 日付フィールドの取得（V2: Date, V1: Date or D）
                day_date = day.get("Date", "").replace("-", "")  # YYYY-MM-DD -> YYYYMMDD
                if not day_date:
                    day_date = day.get("D", "")
                
                if day_date == date_yyyymmdd:
                    # V2 API: HolDiv
                    hol_div = day.get("HolDiv")
                    if hol_div:
                        if hol_div == "1":
                            return True
                        else:
                            return False
                    
                    # V1 API: HolidayDivision or HD
                    holiday_division = day.get("HolidayDivision") or day.get("HD")
                    if holiday_division:
                        if holiday_division == "0":
                            return True
                        else:
                            return False
            
            logger.warning(f"取引カレンダーに {date} のデータがありません")
            return False
            
        except Exception as e:
            logger.error(f"営業日チェックエラー: {e}")
            return False
    
    async def get_prices_daily_quotes(self, session: aiohttp.ClientSession, code: str, 
                                     from_date: str, to_date: str, retry: int = 0):
        """日次株価データを取得（V1/V2対応、リトライ機能付き）"""
        if self.api_version == "v1" and not self.id_token:
            await self.authenticate(session)
        
        try:
            # V2 API: /equities/bars/daily
            if self.api_version == "v2":
                url = f"{self.base_url}/equities/bars/daily"
            # V1 API: /prices/daily_quotes
            else:
                url = f"{self.base_url}/prices/daily_quotes"
            
            headers = self._get_headers()
            params = {
                "code": code,
                "from": from_date,
                "to": to_date
            }
            
            async with session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                # レート制限対応: APIコール後に待機
                await asyncio.sleep(API_CALL_DELAY)
                
                # V2 API: dataキーを使用
                if self.api_version == "v2":
                    if "data" in data and data["data"]:
                        df = pd.DataFrame(data["data"])
                        # V2 APIのカラム名をV1形式に変換
                        column_mapping = {
                            "D": "Date",
                            "O": "Open",
                            "H": "High",
                            "L": "Low",
                            "C": "Close",
                            "V": "Volume"
                        }
                        df = df.rename(columns=column_mapping)
                        return df
                    return None
                # V1 API: daily_quotesキーを使用
                else:
                    if "daily_quotes" in data and data["daily_quotes"]:
                        df = pd.DataFrame(data["daily_quotes"])
                        return df
                    return None
                
        except Exception as e:
            if retry < RETRY_COUNT:
                await asyncio.sleep(RETRY_DELAY)
                return await self.get_prices_daily_quotes(session, code, from_date, to_date, retry + 1)
            logger.warning(f"株価データ取得失敗 [{code}]: {e}")
            return None


def sample_stocks_balanced(stocks, max_per_range=10):
    """
    銘柄コード帯別・市場別の銘柄数に応じた割合でランダムサンプリング
    
    Args:
        stocks: 検出銘柄のリスト
        max_per_range: 各銘柄コード帯から抽出する最大銘柄数
    
    Returns:
        サンプリングされた銘柄のリスト
    
    ロジック:
        1. 各銘柄コード帯（1000-1999, 2000-2999など）内で市場別に分類
        2. 各市場の銘柄数を集計
        3. 最大剰余法（Largest Remainder Method）で抽出数を決定
        4. 各市場からランダムに抽出
    """
    import random
    
    if not stocks or len(stocks) <= 100:
        return stocks  # 100銘柄以下ならそのまま返す
    
    # 銘柄コード帯別・市場別に分類
    ranges = {}
    
    for stock in stocks:
        code = str(stock.get('code', '0000'))
        # 銘柄コードの先頭1桁を取得（1000番台、2000番台...）
        if len(code) >= 4:
            range_key = f"{code[0]}000"
        else:
            range_key = "other"
        
        market = stock.get('market', 'プライム')
        
        if range_key not in ranges:
            ranges[range_key] = {}
        if market not in ranges[range_key]:
            ranges[range_key][market] = []
        
        ranges[range_key][market].append(stock)
    
    # 各帯から市場別の銘柄数に応じてランダム抽出
    sampled = []
    
    for range_key, markets in sorted(ranges.items()):
        # 各市場の銘柄数を集計
        market_counts = {market: len(stocks_list) for market, stocks_list in markets.items()}
        total_in_range = sum(market_counts.values())
        
        # この帯から抽出する銘柄数（最大max_per_range）
        target_count = min(max_per_range, total_in_range)
        
        # 最大剰余法で各市場の抽出数を計算
        market_samples = {}
        quotas = {}  # 比例配分の商
        remainders = {}  # 比例配分の余り
        
        # ステップ1: 比例配分の商と余りを計算
        for market, count in market_counts.items():
            quota = (count / total_in_range) * target_count
            quotas[market] = int(quota)  # 整数部分
            remainders[market] = quota - int(quota)  # 小数部分（余り）
        
        # ステップ2: 商の合計を計算
        allocated = sum(quotas.values())
        
        # ステップ3: 残りの議席を余りが大きい順に配分
        remaining_seats = target_count - allocated
        if remaining_seats > 0:
            # 余りが大きい順にソート
            sorted_markets = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
            for i in range(remaining_seats):
                market = sorted_markets[i][0]
                quotas[market] += 1
        
        # 実際の銘柄数を超えないように調整
        for market, sample_count in quotas.items():
            market_samples[market] = min(sample_count, market_counts[market])
        
        # 各市場からランダムに抽出
        for market, sample_count in market_samples.items():
            if sample_count > 0:
                stocks_in_market = markets[market]
                # ランダムにサンプリング
                sampled_stocks = random.sample(stocks_in_market, min(sample_count, len(stocks_in_market)))
                sampled.extend(sampled_stocks)
    
    logger.info(f"📊 間引きロジック: {len(stocks)}銘柄 → {len(sampled)}銘柄")
    
    # 各帯の内訳をログ出力
    for range_key, markets in sorted(ranges.items()):
        market_summary = ", ".join([f"{m}:{len(s)}" for m, s in markets.items()])
        logger.info(f"   {range_key}番台: {market_summary}")
    
    return sampled


class StockScreener:
    """株式スクリーニングクラス"""
    
    def __init__(self):
        self.jq_client = AsyncJQuantsClient()
        self.client = self.jq_client  # ラッパースクリプトとの互換性のため
        self.sb_client = SupabaseClient()
        self.session = None
        self.progress = {"total": 0, "processed": 0, "detected": 0}
        self.cache = get_cache()  # メモリキャッシュインスタンス
        self.persistent_cache = PersistentPriceCache()  # 永続キャッシュインスタンス
        self.latest_trading_date = None  # 最新の取引日（キャッシュ）
    
    async def get_latest_trading_date(self):
        """最新の取引日を取得（検出銘柄の有無に関わらず）"""
        from trading_day_helper import get_latest_trading_day
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            latest_date = await get_latest_trading_day(self.jq_client, session)
            return latest_date  # datetimeオブジェクトのまま返す（各run_*.pyでstrftime変換）
    
    def calculate_ema(self, series, period):
        """EMAを計算"""
        return series.ewm(span=period, adjust=False).mean()
    
    def calculate_sma(self, series, period):
        """SMAを計算"""
        return series.rolling(window=period).mean()
    
    def calculate_stochastic(self, df, k_period=14, d_period=3):
        """ストキャスティクスを計算"""
        if df is None or len(df) < k_period:
            return None, None
        
        # 過去N日間の最高値・最安値
        highest_high = df['High'].rolling(window=k_period).max()
        lowest_low = df['Low'].rolling(window=k_period).min()
        
        # %K計算
        stoch_k = ((df['Close'] - lowest_low) / (highest_high - lowest_low)) * 100
        
        # %D計算（%Kの移動平均）
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        return stoch_k.iloc[-1], stoch_d.iloc[-1]
    
    def _market_code_to_name(self, code):
        """市場コードを市場名に変換"""
        market_map = {
            "0111": "プライム",
            "0112": "スタンダード",
            "0113": "グロース"
        }
        return market_map.get(code, code)
    
    async def get_stocks_list(self):
        """銘柄リストを取得してフィルタリング"""
        today = datetime.now().strftime('%Y-%m-%d')
        target_date_str = today.replace("-", "")
        
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            await self.jq_client.authenticate(session)
            all_stocks_data = await self.jq_client.get_listed_info(session, date=target_date_str)
            
            if not all_stocks_data:
                return []
            
            market_field = "Mkt" if self.jq_client.api_version == "v2" else "MarketCode"
            market_codes = {"0111": "プライム", "0112": "スタンダード", "0113": "グロース"}
            return [s for s in all_stocks_data if s.get(market_field) in market_codes]

    async def screen_stock_breakout(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄のボックスブレイク（持ち合い上放れ）スクリーニング
        
        ハブ(3030)のような長期持ち合い後の急上昇銘柄を検出する。
        検出条件:
          1. 直近60営業日の値動きがボックス幅20%以内（持ち合い確認）
          2. 直近5営業日以内に60日高値を更新（上放れ確認）
          3. 直近5日の値幅がATR20日平均の1.5倍以上（大きな値動き確認）
          4. 現在株価がEMA50より上（トレンド転換確認）
        """
        code = stock["Code"]
        name = stock.get("CoName", stock.get("CompanyName", f"銘柄{code}"))
        market = stock.get("Mkt", stock.get("MarketCode", ""))

        # 統計情報を初期化（初回のみ）
        if not hasattr(self, 'perfect_order_stats'):
            self.perfect_order_stats = {
                "total": 0,
                "has_data": 0,
                "data_insufficient": 0,
                "passed_box": 0,        # ボックス幅条件通過
                "passed_breakout": 0,   # 高値ブレイク条件通過
                "passed_volume": 0,     # ATR条件通過
                "passed_ema": 0,        # EMA50条件通過
                "passed_convergence": 0, # 3EMA収束条件通過
                "final_detected": 0
            }

        self.perfect_order_stats["total"] += 1

        try:
            end_date = self.latest_trading_date

            # 60営業日 + バッファのため約100日分取得
            start_str, end_str = get_date_range_for_screening(end_date, 100)

            # 永続キャッシュから取得
            df = await self.persistent_cache.get(code, start_str, end_str, max_age_days=120)

            if df is None:
                df = await self.cache.get_or_fetch(
                    code, start_str, end_str,
                    self.jq_client.get_prices_daily_quotes,
                    session, code, start_str, end_str
                )
                if df is not None:
                    await self.persistent_cache.set(code, start_str, end_str, df)

            if df is None or len(df) < 30:
                return None

            self.perfect_order_stats["has_data"] += 1

            # 直近60営業日分（足りない場合は全データ）を使用
            lookback = min(60, len(df))
            df_box = df.iloc[-lookback:].copy()
            latest = df.iloc[-1]
            current_price = float(latest['Close'])
            current_volume = float(latest.get('Volume', 0))

            # ── 条件1: ボックス幅チェック（持ち合い確認）──────────────────
            # ブレイク直前の持ち合いを確認するため、直近5日を除いた期間で判定
            df_range = df.iloc[-(lookback):-5] if len(df) > (lookback + 5) else df.iloc[:-5]
            if len(df_range) < 10:
                return None

            box_high = float(df_range['High'].max())
            box_low = float(df_range['Low'].min())
            if box_low <= 0:
                return None

            box_width_pct = (box_high - box_low) / box_low * 100

            # ボックス幅が20%超 → 持ち合いではなくトレンド相場とみなしてスキップ
            if box_width_pct > 20:
                logger.debug(f"[{code}] ボックス幅超過: {box_width_pct:.1f}% > 20%")
                return None

            self.perfect_order_stats["passed_box"] += 1

            # ── 条件2: 高値ブレイクアウト確認（直近5日以内）──────────────
            recent_high = float(df.iloc[-5:]['High'].max())
            if recent_high <= box_high:
                logger.debug(f"[{code}] ブレイクなし: 直近高値={recent_high:.0f} <= ボックス高値={box_high:.0f}")
                return None

            # ブレイク率（何%上抜けたか）
            breakout_pct = (recent_high - box_high) / box_high * 100

            self.perfect_order_stats["passed_breakout"] += 1

            # ── 条件3: ATRブレイク確認（普段より大きな値動き）──────────────
            # ATR（Average True Range）= 過去20日の真値幅の平均
            # 真値幅 = max(High-Low, |High-前日Close|, |Low-前日Close|)
            df_atr = df.iloc[-lookback:].copy()
            df_atr['prev_close'] = df_atr['Close'].shift(1)
            df_atr['tr'] = df_atr[['High', 'prev_close']].max(axis=1) - df_atr[['Low', 'prev_close']].min(axis=1)
            atr_20 = float(df_atr['tr'].iloc[-20:].mean())

            # 直近5日の最大値幅
            recent_range = float(df.iloc[-5:]['High'].max()) - float(df.iloc[-5:]['Low'].min())
            atr_ratio = recent_range / atr_20 if atr_20 > 0 else 0

            if atr_ratio < 1.5:
                logger.debug(f"[{code}] ATR不足: {atr_ratio:.2f}倍 < 1.5倍")
                return None

            self.perfect_order_stats["passed_volume"] += 1

            # ── 条件4: EMA50より上（トレンド転換確認）───────────────────
            df['EMA50'] = self.calculate_ema(df['Close'], 50)
            df['EMA20'] = self.calculate_ema(df['Close'], 20)
            df['EMA10'] = self.calculate_ema(df['Close'], 10)
            latest = df.iloc[-1]  # EMA計算後に再取得

            if current_price < float(latest['EMA50']):
                logger.debug(f"[{code}] EMA50未満: Close={current_price:.0f} < EMA50={latest['EMA50']:.0f}")
                return None

            self.perfect_order_stats["passed_ema"] += 1

            # ── 条件5: 直近でEMAが収束していたか確認（3EMA収束後の上放れ）──
            # EMA10とEMA50は既に計算済み（latest取得前に計算されている）
            # ブレイク直前5〜15日前の間でEMA10-EMA50の差が株価の5%以内ならOK
            convergence_detected = False
            try:
                for i in range(5, 16):
                    if len(df) > i + 1:
                        past_row = df.iloc[-(i + 1)]
                        past_ema10 = float(past_row['EMA10'])
                        past_ema50 = float(past_row['EMA50'])
                        past_price = float(past_row['Close'])
                        if past_price > 0 and not (pd.isna(past_ema10) or pd.isna(past_ema50)):
                            ema_diff_pct = abs(past_ema10 - past_ema50) / past_price * 100
                            if ema_diff_pct <= 5.0:
                                convergence_detected = True
                                break
            except Exception as e:
                logger.debug(f"[{code}] 3EMA収束チェックエラー: {e}")
                convergence_detected = False

            if not convergence_detected:
                logger.debug(f"[{code}] 3EMA収束なし: ブレイク前5〜15日間でEMA10-EMA50差が5%超")
                return None

            self.perfect_order_stats["passed_convergence"] += 1
            self.perfect_order_stats["final_detected"] += 1

            logger.debug(
                f"[{code}] ✅ ボックスブレイク検出: "
                f"ボックス幅={box_width_pct:.1f}%, ブレイク率={breakout_pct:.1f}%, "
                f"ATR倍率={atr_ratio:.2f}倍"
            )

            return {
                "code": code,
                "name": name,
                "price": current_price,
                "ema10": float(latest['EMA10']),
                "ema20": float(latest['EMA20']),
                "ema50": float(latest['EMA50']),
                "market": self._market_code_to_name(market),
                "volume": int(current_volume),
                "pullback_pct": round(box_width_pct, 2),   # ボックス幅
                "week52_high": round(box_high, 2),          # ボックス高値
                "stochastic_k": round(breakout_pct, 2),     # ブレイク率
                "stochastic_d": round(atr_ratio, 2),        # ATR倍率
            }

        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def screen_stock_bollinger_band(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄のボリンジャーバンドスクリーニング"""
        code = stock["Code"]
        # V2 APIでは "CoName"、V1 APIでは "CompanyName"
        name = stock.get("CoName", stock.get("CompanyName", f"銘柄{code}"))
        # V2 APIでは "Mkt" フィールド、V1 APIでは "MarketCode" フィールド
        market = stock.get("Mkt", stock.get("MarketCode", ""))
        
        try:
            # キャッシュされた最新の取引日を使用
            end_date = self.latest_trading_date
            
            # 日付範囲を取得（50日分、20SMAのみ必要）
            start_str, end_str = get_date_range_for_screening(end_date, 50)
            
            # 永続キャッシュから取得を試みる（50日分のデータが必要）
            df = await self.persistent_cache.get(code, start_str, end_str, max_age_days=60)
            
            # 永続キャッシュになければメモリキャッシュ経由でAPIから取得
            if df is None:
                df = await self.cache.get_or_fetch(
                    code, start_str, end_str,
                    self.jq_client.get_prices_daily_quotes,
                    session, code, start_str, end_str
                )
                # 取得したデータを永続キャッシュに保存
                if df is not None:
                    await self.persistent_cache.set(code, start_str, end_str, df)
            
            if df is None or len(df) < 20:
                return None
            
            # 🔧 日付チェックを一時的に無効化（データ蓄積まで）
            # latest = df.iloc[-1]
            # latest_data_date = pd.to_datetime(latest['Date']).date()
            # end_date_obj = datetime.strptime(end_str, '%Y%m%d').date()
            # 
            # # キャッシュの最新データが実行日より3日以上古い場合は除外
            # if (end_date_obj - latest_data_date).days > 3:
            #     logger.debug(f"キャッシュデータが古すぎる [{code}]: 最新={latest_data_date}, 実行日={end_date_obj}")
            #     return None
            
            # ボリンジャーバンド計算
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['STD20'] = df['Close'].rolling(window=20).std()
            df['Upper3'] = df['SMA20'] + (df['STD20'] * 3)
            df['Lower3'] = df['SMA20'] - (df['STD20'] * 3)
            
            latest = df.iloc[-1]
            
            # ±3σタッチ判定
            if latest['Close'] >= latest['Upper3'] or latest['Close'] <= latest['Lower3']:
                touch_direction = "upper" if latest['Close'] >= latest['Upper3'] else "lower"
                
                return {
                    "code": code,
                    "name": name,
                    "price": float(latest['Close']),
                    "sma20": float(latest['SMA20']),
                    "upper_3sigma": float(latest['Upper3']),
                    "lower_3sigma": float(latest['Lower3']),
                    "touch_direction": touch_direction,
                    "market": self._market_code_to_name(market),
                    "volume": int(latest.get('Volume', 0))
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def screen_stock_200day_pullback(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄の200日新高値押し目スクリーニング（EMAタッチ・ストキャスオプション付き）"""
        # 統計情報用のカウンターを初期化（初回のみ）
        if not hasattr(self, 'pullback_stats'):
            self.pullback_stats = {
                'total': 0,
                'has_data': 0,
                'recent_high': 0,
                'within_30pct': 0,
                'ema10_touch': 0,
                'ema20_touch': 0,
                'ema50_touch': 0,
                'any_ema_touch': 0,
                'ema50_rising': 0,  # EMA50上昇トレンド条件通過
                'passed_all': 0
            }
        
        self.pullback_stats['total'] += 1
        
        code = stock["Code"]
        # V2 APIでは "CoName"、V1 APIでは "CompanyName"
        name = stock.get("CoName", stock.get("CompanyName", f"銘柄{code}"))
        # V2 APIでは "Mkt" フィールド、V1 APIでは "MarketCode" フィールド
        market = stock.get("Mkt", stock.get("MarketCode", ""))
        
        # デバッグモード
        debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        debug_stock_code = os.getenv('DEBUG_STOCK_CODE', '')
        # 文字列比較を確実にするため、両方を文字列に変換
        is_debug_target = debug_mode and str(code) == str(debug_stock_code)
        
        # 6954の場合は必ずログ出力（デバッグモード関係なく）
        if code == "6954":
            logger.info(f"⚡⚡⚡ 6954検出！ screen_stock_200day_pullback() 開始 - {name}({code})")
            logger.info(f"⚡ debug_mode={debug_mode}, debug_stock_code='{debug_stock_code}', code='{code}'")
            logger.info(f"⚡ is_debug_target={is_debug_target}")
        
        # デバッグ：関数に入ったことを確認
        if is_debug_target:
            logger.info(f"⚡ DEBUG: screen_stock_200day_pullback() 開始 - {name}({code})")
            logger.info(f"⚡ DEBUG: debug_mode={debug_mode}, debug_stock_code={debug_stock_code}")
        
        try:
            # キャッシュされた最新の取引日を使用
            end_date = self.latest_trading_date
            
            # 日付範囲を取得（200日分、キャッシュ範囲内に収める）
            start_str, end_str = get_date_range_for_screening(end_date, 200)
            
            # 永続キャッシュから取得を試みる（200日分のデータが必要）
            df = await self.persistent_cache.get(code, start_str, end_str, max_age_days=220)
            
            # 永続キャッシュになければメモリキャッシュ経由でAPIから取得
            if df is None:
                df = await self.cache.get_or_fetch(
                    code, start_str, end_str,
                    self.jq_client.get_prices_daily_quotes,
                    session, code, start_str, end_str
                )
                # 取得したデータを永続キャッシュに保存
                if df is not None:
                    await self.persistent_cache.set(code, start_str, end_str, df)
            
            if df is None or len(df) < 20:  # 営業日20日分あればOK（最低限の判定可能）
                return None
            
            # 🔧 日付チェックを一時的に無効化（データ蓄積まで）
            # latest = df.iloc[-1]
            # latest_data_date = pd.to_datetime(latest['Date']).date()
            # end_date_obj = datetime.strptime(end_str, '%Y%m%d').date()
            # 
            # # キャッシュの最新データが実行日より3日以上古い場合は除外
            # if (end_date_obj - latest_data_date).days > 3:
            #     logger.debug(f"キャッシュデータが古すぎる [{code}]: 最新={latest_data_date}, 実行日={end_date_obj}")
            #     return None
            
            self.pullback_stats['has_data'] += 1
            
            # EMA計算
            df['EMA10'] = self.calculate_ema(df['Close'], 10)
            df['EMA20'] = self.calculate_ema(df['Close'], 20)
            df['EMA50'] = self.calculate_ema(df['Close'], 50)
            
            # 200日最高値（利用可能なデータの範囲内で計算、最大200日）
            lookback_days = min(200, len(df))
            high_200d = df['High'].tail(lookback_days).max()
            latest = df.iloc[-1]
            current_price = latest['Close']
            
            # 200日新高値を記録した日を特定
            high_200d_date_idx = df['High'].tail(lookback_days).idxmax()
            days_since_high = len(df) - 1 - high_200d_date_idx
            
            # 条件1: 過去60日以内に200日新高値を更新していること
            if days_since_high <= 60:
                self.pullback_stats['recent_high'] += 1
            else:
                return None
            
            # 新高値からの下落率
            pullback_pct = ((high_200d - current_price) / high_200d) * 100
            
            # 条件2: 200日新高値から30%以内の押し目
            if pullback_pct <= 30:
                self.pullback_stats['within_30pct'] += 1
            else:
                return None
            
            # EMAタッチ判定（4本値のいずれかがEMAにタッチ）
            touched_emas = []
            
            # 当日の4本値を取得
            open_price = latest['Open']
            high_price = latest['High']
            low_price = latest['Low']
            close_price = latest['Close']
            
            # デバッグログ
            if is_debug_target:
                logger.info(f"\n{'='*60}")
                logger.info(f"🔍 デバッグ詳細: {name}({code})")
                logger.info(f"日付: {latest['Date']}")
                logger.info(f"4本値:")
                logger.info(f"  始値: {open_price:,.0f}円")
                logger.info(f"  高値: {high_price:,.0f}円")
                logger.info(f"  安値: {low_price:,.0f}円")
                logger.info(f"  終値: {close_price:,.0f}円")
                logger.info(f"EMA:")
                logger.info(f"  EMA10: {latest['EMA10']:,.2f}円")
                logger.info(f"  EMA20: {latest['EMA20']:,.2f}円")
                logger.info(f"  EMA50: {latest['EMA50']:,.2f}円")
                logger.info(f"200日新高値: {high_200d:,.0f}円")
                logger.info(f"200日新高値更新日: {df.iloc[high_200d_date_idx]['Date']} ({days_since_high}日前)")
                logger.info(f"下落率: {pullback_pct:.2f}%")
            
            # EMA10タッチ判定：ローソク足の範囲内にEMAがあるか
            if low_price <= latest['EMA10'] <= high_price:
                touched_emas.append("10EMA")
                self.pullback_stats['ema10_touch'] += 1
            
            # EMA20タッチ判定
            if low_price <= latest['EMA20'] <= high_price:
                touched_emas.append("20EMA")
                self.pullback_stats['ema20_touch'] += 1
            
            # EMA50タッチ判定
            if low_price <= latest['EMA50'] <= high_price:
                touched_emas.append("50EMA")
                self.pullback_stats['ema50_touch'] += 1
            
            if is_debug_target:
                logger.info(f"\nタッチ判定:")
                logger.info(f"  EMA10タッチ: {low_price} <= {latest['EMA10']:.2f} <= {high_price} → {'✅' if '10EMA' in touched_emas else '❌'}")
                logger.info(f"  EMA20タッチ: {low_price} <= {latest['EMA20']:.2f} <= {high_price} → {'✅' if '20EMA' in touched_emas else '❌'}")
                logger.info(f"  EMA50タッチ: {low_price} <= {latest['EMA50']:.2f} <= {high_price} → {'✅' if '50EMA' in touched_emas else '❌'}")
                logger.info(f"タッチしたEMA: {touched_emas if touched_emas else 'なし'}")
                logger.info(f"{'='*60}\n")
            
            if touched_emas:
                self.pullback_stats['any_ema_touch'] += 1
            else:
                return None
            
            # EMAフィルター適用
            if PULLBACK_EMA_FILTER != "all":
                if PULLBACK_EMA_FILTER == "10ema" and "10EMA" not in touched_emas:
                    return None
                elif PULLBACK_EMA_FILTER == "20ema" and "20EMA" not in touched_emas:
                    return None
                elif PULLBACK_EMA_FILTER == "50ema" and "50EMA" not in touched_emas:
                    return None
            
            # ストキャスティクス計算
            stoch_k, stoch_d = self.calculate_stochastic(df)
            
            # ストキャスティクスフィルター適用
            if PULLBACK_STOCHASTIC_FILTER:
                if stoch_k is None or stoch_k > 20:  # 売られすぎ閾値
                    return None
            
            # 条件: EMA50が20日前より上（上昇トレンド中のみ）
            if len(df) >= 20:
                ema50_20days_ago = float(df['EMA50'].iloc[-20])
                ema50_now = float(latest['EMA50'])
                if ema50_now <= ema50_20days_ago:
                    logger.debug(f"[{code}] EMA50下降中: 現在{ema50_now:.0f} <= 20日前{ema50_20days_ago:.0f}")
                    return None
            self.pullback_stats['ema50_rising'] += 1
            
            # 全条件通過！
            self.pullback_stats['passed_all'] += 1
            
            return {
                "code": code,
                "name": name,
                "price": float(current_price),
                "high_200day": float(high_200d),
                "pullback_pct": round(pullback_pct, 2),
                "touched_emas": ",".join(touched_emas),
                "ema_10": float(latest['EMA10']),
                "ema_20": float(latest['EMA20']),
                "ema_50": float(latest['EMA50']),
                "stochastic_k": round(stoch_k, 2) if stoch_k is not None else None,
                "stochastic_d": round(stoch_d, 2) if stoch_d is not None else None,
                "market": self._market_code_to_name(market),
                "volume": int(latest.get('Volume', 0))
            }
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def screen_stock_squeeze(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄のスクイーズ（価格収縮）スクリーニング"""
        # 統計情報用のカウンターを初期化（初回のみ）
        if not hasattr(self, 'squeeze_stats'):
            self.squeeze_stats = {
                'total': 0,
                'has_data': 0,
                'bbw_failed': 0,
                'deviation_failed': 0,
                'atr_failed': 0,
                'duration_failed': 0,
                'ema50_flat_failed': 0,  # EMA50平坦条件不通過
                'passed_all': 0
            }
        
        self.squeeze_stats['total'] += 1
        
        code = stock["Code"]
        # V2 APIでは "CoName"、V1 APIでは "CompanyName"
        name = stock.get("CoName", stock.get("CompanyName", f"銘柄{code}"))
        # V2 APIでは "Mkt" フィールド、V1 APIでは "MarketCode" フィールド
        market = stock.get("Mkt", stock.get("MarketCode", ""))
        
        try:
            # キャッシュされた最新の取引日を使用
            end_date = self.latest_trading_date
            
            # 日付範囲を取得（200日分）
            start_str, end_str = get_date_range_for_screening(end_date, 200)
            
            # 永続キャッシュから取得を試みる（200日分のデータが必要）
            df = await self.persistent_cache.get(code, start_str, end_str, max_age_days=220)
            
            # 永続キャッシュになければメモリキャッシュ経由でAPIから取得
            if df is None:
                df = await self.cache.get_or_fetch(
                    code, start_str, end_str,
                    self.jq_client.get_prices_daily_quotes,
                    session, code, start_str, end_str
                )
                # 取得したデータを永続キャッシュに保存
                if df is not None:
                    await self.persistent_cache.set(code, start_str, end_str, df)
            
            if df is None or len(df) < 20:
                return None
            
            # 🔧 日付チェックを一時的に無効化（データ蓄積まで）
            # latest = df.iloc[-1]
            # latest_data_date = pd.to_datetime(latest['Date']).date()
            # end_date_obj = datetime.strptime(end_str, '%Y%m%d').date()
            # 
            # # キャッシュの最新データが実行日より3日以上古い場合は除外
            # if (end_date_obj - latest_data_date).days > 3:
            #     logger.debug(f"キャッシュデータが古すぎる [{code}]: 最新={latest_data_date}, 実行日={end_date_obj}")
            #     return None
            
            self.squeeze_stats['has_data'] += 1
            
            # 最新100日分を取得
            df = df.tail(100)
            
            # 各指標を計算
            prices = df['Close']
            high = df['High']
            low = df['Low']
            
            # ボリンジャーバンド幅（BBW）
            sma20 = prices.rolling(window=20).mean()
            std20 = prices.rolling(window=20).std()
            upper = sma20 + (std20 * 2)
            lower = sma20 - (std20 * 2)
            bbw = (upper - lower) / sma20 * 100
            
            # 50EMA
            ema50 = prices.ewm(span=50, adjust=False).mean()
            
            # 乖離率
            deviation = abs(prices - ema50) / ema50 * 100
            
            # ATR
            tr1 = high - low
            tr2 = abs(high - prices.shift(1))
            tr3 = abs(low - prices.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.ewm(span=14, adjust=False).mean()
            
            # 最新の値
            current_bbw = bbw.iloc[-1]
            current_deviation = deviation.iloc[-1]
            current_atr = atr.iloc[-1]
            current_price = prices.iloc[-1]
            current_ema50 = ema50.iloc[-1]
            
            # 過去60日間の最小値
            bbw_min_60d = bbw.iloc[-60:].min()
            atr_min_60d = atr.iloc[-60:].min()
            
            # 検出条件
            bbw_threshold = 1.2  # ボリンジャーバンド幅
            deviation_threshold = 3.0  # 50EMAからの乖離率
            atr_threshold = 1.3
            min_duration = 7  # 継続期間（固定値）
            
            # 条件1: BBWが狭い
            bbw_condition = current_bbw <= bbw_min_60d * bbw_threshold
            
            # 条件2: 株価がEMAに近い
            deviation_condition = current_deviation <= deviation_threshold
            
            # 条件3: ATRが低い
            atr_condition = current_atr <= atr_min_60d * atr_threshold
            
            # 各条件をチェックして統計を記録
            if not bbw_condition:
                self.squeeze_stats['bbw_failed'] += 1
                return None
            
            if not deviation_condition:
                self.squeeze_stats['deviation_failed'] += 1
                return None
            
            if not atr_condition:
                self.squeeze_stats['atr_failed'] += 1
                return None
            
            # 継続日数を計算
            duration = 0
            for i in range(1, min(len(prices), 30)):  # 最大30日まで遡る
                idx = -i
                if (bbw.iloc[idx] <= bbw_min_60d * bbw_threshold and
                    deviation.iloc[idx] <= deviation_threshold * 1.4 and
                    atr.iloc[idx] <= atr_min_60d * atr_threshold):
                    duration += 1
                else:
                    break
            
            # 最小継続期間を満たすか確認
            if duration < min_duration:
                self.squeeze_stats['duration_failed'] += 1
                return None
            
            # 条件5: EMA50が平坦（凪状態の確認）
            # 20日前のEMA50との差が株価の2%以内 → 上昇中・下落中を除外
            if len(ema50) >= 20:
                ema50_now = float(ema50.iloc[-1])
                ema50_20d_ago = float(ema50.iloc[-20])
                ema50_change_pct = abs(ema50_now - ema50_20d_ago) / ema50_20d_ago * 100
                if ema50_change_pct > 2.0:
                    self.squeeze_stats['ema50_flat_failed'] += 1
                    logger.debug(f"[{code}] EMA50が平坦でない: 20日変化率={ema50_change_pct:.1f}% > 2%")
                    return None
            
            # すべての条件を満たした
            self.squeeze_stats['passed_all'] += 1
            logger.info(f"✅ スクイーズ検出 [{code}]: 継続{duration}日")
            
            # 検出結果を返す
            return {
                "code": code,
                "name": name,
                "price": float(current_price),
                "market": self._market_code_to_name(market),
                "current_bbw": float(current_bbw),
                "bbw_min_60d": float(bbw_min_60d),
                "bbw_ratio": float(current_bbw / bbw_min_60d) if bbw_min_60d > 0 else None,
                "deviation_from_ema": float(current_deviation),
                "current_atr": float(current_atr),
                "atr_min_60d": float(atr_min_60d),
                "atr_ratio": float(current_atr / atr_min_60d) if atr_min_60d > 0 else None,
                "duration_days": int(duration),
                "ema_50": float(current_ema50),
                "volume": int(df.iloc[-1].get('Volume', 0))
            }
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def process_stocks_batch(self, stocks: List[Dict], screening_func, method_name: str):
        """銘柄のバッチ処理"""
        self.progress["total"] = len(stocks)
        self.progress["processed"] = 0
        self.progress["detected"] = 0
        
        # 開始時のメモリ使用量をログ
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024
        vm = psutil.virtual_memory()
        logger.info(f"💾 {method_name} 開始時メモリ: プロセス {mem_mb:.2f}MB / システム {vm.used/1024/1024/1024:.2f}GB ({vm.percent}%)")
        
        connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 認証
            await self.jq_client.authenticate(session)
            
            # セマフォで同時実行数を制限
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            
            async def process_with_semaphore(stock):
                async with semaphore:
                    result = await screening_func(stock, session)
                    self.progress["processed"] += 1
                    
                    if self.progress["processed"] % 100 == 0:
                        # メモリ使用量をログ
                        mem_info = process.memory_info()
                        mem_mb = mem_info.rss / 1024 / 1024
                        logger.info(f"{method_name}: {self.progress['processed']}/{self.progress['total']} 処理完了 "
                                  f"({self.progress['detected']}銘柄検出) - 💾 メモリ: {mem_mb:.2f}MB")
                    
                    if result:
                        self.progress["detected"] += 1
                    
                    # レート制限対応: APIコール後に待機
                    await asyncio.sleep(API_CALL_DELAY)
                    
                    return result
            
            # 順次実行（レート制限対応）
            results = []
            for stock in stocks:
                result = await process_with_semaphore(stock)
                if result:
                    results.append(result)
            
            # 終了時のメモリ使用量をログ
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            vm = psutil.virtual_memory()
            logger.info(f"💾 {method_name} 終了時メモリ: プロセス {mem_mb:.2f}MB / システム {vm.used/1024/1024/1024:.2f}GB ({vm.percent}%)")
            
            # Noneを除外
            return [r for r in results if r is not None]
    
    async def run_screening(self, stocks: List[Dict]):
        """全スクリーニング手法を並列実行"""
        logger.info(f"並列スクリーニング開始: {len(stocks)}銘柄")
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 60)
        logger.info("スクリーニングオプション設定:")
        logger.info(f"  - 200日新高値押し目 EMAフィルター: {PULLBACK_EMA_FILTER}")
        logger.info(f"  - 200日新高値押し目 ストキャスティクス: {'ON' if PULLBACK_STOCHASTIC_FILTER else 'OFF'}")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        # ブレイクアウト（持ち合い上放れ）
        logger.info("ブレイクアウト（持ち合い上放れ）スクリーニング開始")
        po_start = datetime.now()
        breakout = await self.process_stocks_batch(
            stocks, self.screen_stock_breakout, "ブレイクアウト"
        )
        po_time = int((datetime.now() - po_start).total_seconds() * 1000)
        logger.info(f"ブレイクアウト検出: {len(breakout)}銘柄 ({po_time}ms)")
        
        # 統計情報を表示
        if hasattr(self, 'perfect_order_stats'):
            stats = self.perfect_order_stats
            logger.info("📊 ブレイクアウトスクリーニング 詳細統計")
            logger.info("="*60)
            logger.info(f"📄 処理対象: {stats['total']:,}銘柄")
            
            if stats['total'] > 0:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄 ({stats['has_data']/stats['total']*100:.1f}%)")
                logger.info(f"❌ データ不足: {stats['data_insufficient']:,}銘柄 ({stats['data_insufficient']/stats['total']*100:.1f}%)")
            
            logger.info(f"\n🔹 条件別通過状況:")
            
            if stats['has_data'] > 0:
                logger.info(f"  1️⃣ ボックス幅15%以内: {stats.get('passed_box', 0):,}銘柄 ({stats.get('passed_box', 0)/stats['has_data']*100:.2f}%)")
                logger.info(f"  2️⃣ 高値ブレイクアウト: {stats.get('passed_breakout', 0):,}銘柄")
                logger.info(f"  3️⃣ 出来高急増1.5倍以上: {stats.get('passed_volume', 0):,}銘柄")
                logger.info(f"  4️⃣ EMA50以上: {stats.get('passed_ema', 0):,}銘柄")
            
            logger.info(f"\n⭐ 全条件通過: {stats['final_detected']:,}銘柄")
            logger.info("="*60 + "\n")
        
        # 間引き処理
        breakout_sampled = sample_stocks_balanced(breakout, max_per_range=10)
        
        # Supabase保存（元の検出数を保持）
        screening_id = self.sb_client.save_screening_result(
            "breakout", datetime.now().strftime('%Y-%m-%d'),
            len(breakout), po_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, breakout_sampled)
        
        # ボリンジャーバンド
        logger.info("=" * 60)
        logger.info("ボリンジャーバンド±3σスクリーニング開始")
        bb_start = datetime.now()
        bollinger_band = await self.process_stocks_batch(
            stocks, self.screen_stock_bollinger_band, "ボリンジャーバンド"
        )
        bb_time = int((datetime.now() - bb_start).total_seconds() * 1000)
        logger.info(f"ボリンジャーバンド検出: {len(bollinger_band)}銘柄 ({bb_time}ms)")
        
        # 間引き処理
        bollinger_band_sampled = sample_stocks_balanced(bollinger_band, max_per_range=10)
        
        screening_id = self.sb_client.save_screening_result(
            "bollinger_band", datetime.now().strftime('%Y-%m-%d'),
            len(bollinger_band), bb_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, bollinger_band_sampled)
        
        # 200日新高値押し目
        logger.info("=" * 60)
        logger.info("200日新高値押し目スクリーニング開始")
        pb_start = datetime.now()
        week52_pullback = await self.process_stocks_batch(
            stocks, self.screen_stock_200day_pullback, "200日新高値押し目"
        )
        pb_time = int((datetime.now() - pb_start).total_seconds() * 1000)
        logger.info(f"200日新高値押し目検出: {len(week52_pullback)}銘柄 ({pb_time}ms)")
        
        # 間引き処理
        week52_pullback_sampled = sample_stocks_balanced(week52_pullback, max_per_range=10)
        
        # 統計情報を表示
        if hasattr(self, 'pullback_stats'):
            stats = self.pullback_stats
            logger.info("\n" + "="*60)
            logger.info("📊 200日新高値押し目スクリーニング 詳細統計")
            logger.info("="*60)
            logger.info(f"📄 処理対象: {stats['total']:,}銘柄")
            
            if stats['total'] > 0:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄 ({stats['has_data']/stats['total']*100:.1f}%)")
            else:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄")
            
            logger.info(f"\n🔹 条件別通過状況:")
            
            if stats['has_data'] > 0:
                logger.info(f"  1️⃣ 60日以内に200日新高値更新: {stats['recent_high']:,}銘柄 ({stats['recent_high']/stats['has_data']*100:.2f}%)")
            else:
                logger.info(f"  1️⃣ 60日以内に200日新高値更新: {stats['recent_high']:,}銘柄")
            
            if stats['recent_high'] > 0:
                logger.info(f"  2️⃣ 30%以内の押し目: {stats['within_30pct']:,}銘柄 ({stats['within_30pct']/stats['recent_high']*100:.2f}% of 条件1通過)")
            else:
                logger.info(f"  2️⃣ 30%以内の押し目: {stats['within_30pct']:,}銘柄 (条件1通過が0のため計算不可)")
            
            logger.info(f"\n🔹 EMAタッチ別統計:")
            logger.info(f"  🔸 10EMAタッチ: {stats['ema10_touch']:,}銘柄")
            logger.info(f"  🔸 20EMAタッチ: {stats['ema20_touch']:,}銘柄")
            logger.info(f"  🔸 50EMAタッチ: {stats['ema50_touch']:,}銘柄")
            
            if stats['within_30pct'] > 0:
                logger.info(f"  ✅ いずれかのEMAタッチ: {stats['any_ema_touch']:,}銘柄 ({stats['any_ema_touch']/stats['within_30pct']*100:.2f}% of 条件2通過)")
            else:
                logger.info(f"  ✅ いずれかのEMAタッチ: {stats['any_ema_touch']:,}銘柄 (条件2通過が0のため計算不可)")
            
            logger.info(f"\n⭐ 全条件通過: {stats['passed_all']:,}銘柄")
            logger.info("="*60 + "\n")
        
        screening_id = self.sb_client.save_screening_result(
            "200day_pullback", datetime.now().strftime('%Y-%m-%d'),
            len(week52_pullback), pb_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, week52_pullback_sampled)
        
        # スクイーズ（価格収縮）
        logger.info("=" * 60)
        logger.info("スクイーズ（価格収縮）スクリーニング開始")
        sq_start = datetime.now()
        squeeze = await self.process_stocks_batch(
            stocks, self.screen_stock_squeeze, "スクイーズ"
        )
        sq_time = int((datetime.now() - sq_start).total_seconds() * 1000)
        logger.info(f"スクイーズ検出: {len(squeeze)}銘柄 ({sq_time}ms)")
        
        # 間引き処理
        squeeze_sampled = sample_stocks_balanced(squeeze, max_per_range=10)
        
        screening_id = self.sb_client.save_screening_result(
            "squeeze", datetime.now().strftime('%Y-%m-%d'),
            len(squeeze), sq_time  # 元の検出数
        )
        if screening_id:
            # duration_daysをstochastic_kカラムに保存（additional_dataカラム非存在のため）
            stocks_with_duration = []
            for s in squeeze_sampled:
                stock_data = {
                    "code": s["code"],
                    "name": s["name"],
                    "price": s["price"],
                    "market": s["market"],
                    "volume": s.get("volume", 0),
                    "ema_50": s.get("ema_50"),
                    "stochastic_k": s["duration_days"],  # duration_daysをstochastic_kに流用
                }
                stocks_with_duration.append(stock_data)
            
            self.sb_client.save_detected_stocks(screening_id, stocks_with_duration)
        
        total_time = (datetime.now() - start_time).total_seconds()
        logger.info("=" * 60)
        # キャッシュ統計を出力
        logger.info("メモリキャッシュ統計:")
        self.cache.log_stats()
        
        # 永続キャッシュ統計を出力
        persistent_stats = self.persistent_cache.get_stats()
        logger.info("\n永続キャッシュ統計:")
        logger.info(f"  ファイル数: {persistent_stats['files']}件")
        logger.info(f"  合計サイズ: {persistent_stats['size_mb']}MB")
        logger.info(f"  ヒット数: {persistent_stats['hits']}回")
        logger.info(f"  ミス数: {persistent_stats['misses']}回")
        logger.info(f"  ヒット率: {persistent_stats['hit_rate']}%")
        logger.info("=" * 60)
        
        logger.info(f"全スクリーニング完了: {total_time:.1f}秒")
        
        return {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "timestamp": datetime.now().isoformat(),
            "total_stocks": len(stocks),
            "execution_time_seconds": round(total_time, 1),
            "options": {
                "pullback_ema": PULLBACK_EMA_FILTER,
                "pullback_stochastic": PULLBACK_STOCHASTIC_FILTER
            },
            "breakout": breakout,
            "bollinger_band": bollinger_band,
            "200day_pullback": week52_pullback,
            "squeeze": squeeze
        }


class HistoryManager:
    """履歴管理クラス"""
    
    def __init__(self):
        self.history_file = DATA_DIR / "screening_history.json"
        self.max_days = HISTORY_DAYS
    
    def load_history(self):
        if not self.history_file.exists():
            return {}
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"履歴読み込みエラー: {e}")
            return {}
    
    def save_history(self, data):
        history = self.load_history()
        today = datetime.now().strftime('%Y-%m-%d')
        
        history[today] = data
        
        # 90日以前のデータを削除
        cutoff_date = (datetime.now() - timedelta(days=self.max_days)).strftime('%Y-%m-%d')
        history = {k: v for k, v in history.items() if k >= cutoff_date}
        
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.info(f"履歴保存完了: {self.history_file}")
        except Exception as e:
            logger.error(f"履歴保存エラー: {e}")
    
    def get_statistics(self):
        history = self.load_history()
        
        if not history:
            return None
        
        stats = {
            "total_days": len(history),
            "date_range": {
                "from": min(history.keys()),
                "to": max(history.keys())
            },
            "avg_detections": {
                "breakout": 0,
                "bollinger_band": 0,
                "200day_pullback": 0
            }
        }
        
        for data in history.values():
            stats["avg_detections"]["breakout"] += len(data.get("breakout", []))
            stats["avg_detections"]["bollinger_band"] += len(data.get("bollinger_band", []))
            stats["avg_detections"]["200day_pullback"] += len(data.get("200day_pullback", []))
        
        days = len(history)
        for key in stats["avg_detections"]:
            stats["avg_detections"][key] = round(stats["avg_detections"][key] / days, 2)
        
        return stats


async def main():
    """メイン処理"""
    logger.info("=" * 60)
    logger.info("日次株式スクリーニングデータ収集開始（並列処理・全銘柄対応・オプション機能付き）")
    logger.info("=" * 60)
    
    try:
        screener = StockScreener()
        
        # コマンドライン引数から日付を取得（指定がない場合は今日）
        import sys
        if len(sys.argv) > 1:
            target_date = sys.argv[1]
            # YYYYMMDD形式をYYYY-MM-DD形式に変換
            if len(target_date) == 8 and target_date.isdigit():
                target_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
            today = target_date
        else:
            today = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"📅 実行日: {today}")
        logger.info("🔍 営業日チェック中...")
        
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            await screener.jq_client.authenticate(session)
            
            # 営業日かどうかを確認
            is_trading = await screener.jq_client.is_trading_day(session, today)
            
            if not is_trading:
                logger.info("=" * 60)
                logger.info("🚫 本日は休場日のため、スクリーニングをスキップします")
                logger.info("=" * 60)
                return 0
            
            # 最新の取引日を取得してキャッシュ（1回だけ）
            from trading_day_helper import get_latest_trading_day
            base_date = datetime.strptime(today, '%Y-%m-%d')
            screener.latest_trading_date = await get_latest_trading_day(screener.jq_client, session, base_date)
            logger.info(f"✅ 取引日確定: {screener.latest_trading_date.strftime('%Y-%m-%d')} ({['月', '火', '水', '木', '金', '土', '日'][screener.latest_trading_date.weekday()]})")
            logger.info("=" * 60)
            
            # 銘柄リスト取得
            logger.info("銘柄リスト取得中...")
            # V2 APIでは対象日の銘柄情報を取得
            # todayは既にYYYY-MM-DD形式の文字列
            target_date_str = today.replace("-", "")  # YYYYMMDD形式に変換
            all_stocks_data = await screener.jq_client.get_listed_info(session, date=target_date_str)
        
        if not all_stocks_data:
            logger.error("銘柄リスト取得失敗")
            return 1
        
        # 市場コードでフィルタ
        # V2 APIでは "Mkt" フィールド、V1 APIでは "MarketCode" フィールド
        market_field = "Mkt" if screener.jq_client.api_version == "v2" else "MarketCode"
        market_codes = {"0111": "プライム", "0112": "スタンダード", "0113": "グロース"}
        all_stocks = [s for s in all_stocks_data if s.get(market_field) in market_codes]
        
        # 市場別統計
        for code, name in market_codes.items():
            count = len([s for s in all_stocks if s.get(market_field) == code])
            logger.info(f"{name}市場: {count}銘柄")
        
        logger.info(f"合計: {len(all_stocks)}銘柄")
        
        # 6954が銘柄リストに含まれているか確認
        stock_6954 = next((s for s in all_stocks if s.get("Code") == "6954"), None)
        if stock_6954:
            logger.info(f"⚡⚡⚡ 6954が銘柄リストに存在: {stock_6954}")
        else:
            logger.error(f"❌ 6954が銘柄リストに存在しません！")
            # 全銘柄リストから検索
            stock_6954_all = next((s for s in all_stocks_data if s.get("Code") == "6954"), None)
            if stock_6954_all:
                logger.info(f"⚡ 6954は全銘柄リストに存在: {stock_6954_all}")
                logger.info(f"⚡ {market_field}: {stock_6954_all.get(market_field)}")
            else:
                logger.error(f"❌ 6954は全銘柄リストにも存在しません！")
        
        # スクリーニング実行
        results = await screener.run_screening(all_stocks)
        
        # ローカル履歴に保存
        history_manager = HistoryManager()
        history_manager.save_history(results)
        
        # 統計情報を表示
        stats = history_manager.get_statistics()
        if stats:
            logger.info("=" * 60)
            logger.info("統計情報")
            logger.info(f"履歴日数: {stats['total_days']}日")
            logger.info(f"期間: {stats['date_range']['from']} ~ {stats['date_range']['to']}")
            logger.info(f"平均検出数:")
            logger.info(f"  - ブレイクアウト: {stats['avg_detections']['breakout']}銘柄/日")
            logger.info(f"  - ボリンジャーバンド: {stats['avg_detections']['bollinger_band']}銘柄/日")
            logger.info(f"  - 200日新高値押し目: {stats['avg_detections']['200day_pullback']}銘柄/日")
        
        logger.info("=" * 60)
        logger.info("日次データ収集完了")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))

