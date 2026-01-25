#!/usr/bin/env python3
"""
0銘柄検出問題のデバッグスクリプト

このスクリプトは以下を確認します：
1. キャッシュの状態（ファイル数、サイズ、日付範囲）
2. サンプル銘柄のデータ取得と条件判定
3. 日付調整ロジックの動作確認
"""

import os
import sys
import asyncio
import logging
import pickle
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import aiohttp

# プロジェクトのモジュールをインポート
from jquants_client import JQuantsClient
from persistent_cache import PersistentPriceCache

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_cache_status():
    """キャッシュの状態を確認"""
    logger.info("=" * 80)
    logger.info("1. キャッシュ状態の確認")
    logger.info("=" * 80)
    
    cache_dir = Path("~/.cache/stock_prices").expanduser()
    
    if not cache_dir.exists():
        logger.warning(f"キャッシュディレクトリが存在しません: {cache_dir}")
        return
    
    cache_files = list(cache_dir.glob("*.pkl"))
    logger.info(f"キャッシュファイル数: {len(cache_files)}")
    
    if len(cache_files) == 0:
        logger.warning("キャッシュファイルが0個です！")
        return
    
    # 総サイズ計算
    total_size_mb = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)
    logger.info(f"キャッシュ総サイズ: {total_size_mb:.2f} MB")
    
    # サンプルファイルを確認（最初の5個）
    logger.info("\nサンプルキャッシュファイル（最初の5個）:")
    for i, cache_file in enumerate(cache_files[:5]):
        try:
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
            
            if isinstance(data, dict) and 'df' in data and 'last_date' in data:
                df = data['df']
                last_date = data['last_date']
                logger.info(f"  {cache_file.name}: {len(df)}行, 最終日={last_date}")
                
                # 日付範囲を確認
                if 'Date' in df.columns and len(df) > 0:
                    df['Date'] = pd.to_datetime(df['Date'])
                    first_date = df['Date'].iloc[0].strftime('%Y%m%d')
                    last_date_actual = df['Date'].iloc[-1].strftime('%Y%m%d')
                    logger.info(f"    日付範囲: {first_date} ～ {last_date_actual}")
            else:
                logger.info(f"  {cache_file.name}: 旧形式または不正なデータ")
        
        except Exception as e:
            logger.error(f"  {cache_file.name}: 読み込みエラー - {e}")
    
    logger.info("")


async def check_date_adjustment():
    """日付調整ロジックの動作確認"""
    logger.info("=" * 80)
    logger.info("2. 日付調整ロジックの確認")
    logger.info("=" * 80)
    
    # J-Quants クライアント初期化
    refresh_token = os.getenv("JQUANTS_REFRESH_TOKEN")
    if not refresh_token:
        logger.error("JQUANTS_REFRESH_TOKEN環境変数が設定されていません")
        return None
    
    jq_client = JQuantsClient(refresh_token=refresh_token)
    
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        await jq_client.authenticate(session)
        
        # 現在日時から前営業日を取得
        end_date = datetime.now()
        logger.info(f"現在日時: {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"曜日: {['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]}")
        
        # 週末チェック
        original_date = end_date
        while end_date.weekday() >= 5:  # 5=土曜, 6=日曜
            end_date = end_date - timedelta(days=1)
            logger.info(f"  週末スキップ: {end_date.strftime('%Y-%m-%d')} ({['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]})")
        
        # 祝日チェック
        max_attempts = 10
        attempts = 0
        while attempts < max_attempts:
            date_str = end_date.strftime("%Y-%m-%d")
            is_trading = await jq_client.is_trading_day(session, date_str)
            logger.info(f"  {date_str} ({['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]}): {'✅ 取引日' if is_trading else '❌ 休場日'}")
            
            if is_trading:
                break
            
            end_date = end_date - timedelta(days=1)
            # 週末をスキップ
            while end_date.weekday() >= 5:
                end_date = end_date - timedelta(days=1)
            
            attempts += 1
        
        if attempts >= max_attempts:
            logger.error(f"⚠️ {max_attempts}回試行しても取引日が見つかりませんでした")
            return None
        
        logger.info(f"\n✅ 最終的な取引日: {end_date.strftime('%Y-%m-%d')} ({['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]})")
        logger.info(f"   元の日付からの差: {(original_date - end_date).days}日")
        logger.info("")
        
        return end_date


async def test_sample_stock(end_date):
    """サンプル銘柄でデータ取得と条件判定をテスト"""
    logger.info("=" * 80)
    logger.info("3. サンプル銘柄のデータ取得と条件判定")
    logger.info("=" * 80)
    
    # テスト銘柄（トヨタ自動車）
    test_code = "7203"
    logger.info(f"テスト銘柄: {test_code} (トヨタ自動車)")
    
    # J-Quants クライアント初期化
    refresh_token = os.getenv("JQUANTS_REFRESH_TOKEN")
    if not refresh_token:
        logger.error("JQUANTS_REFRESH_TOKEN環境変数が設定されていません")
        return
    
    jq_client = JQuantsClient(refresh_token=refresh_token)
    persistent_cache = PersistentPriceCache()
    
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        await jq_client.authenticate(session)
        
        # 日付範囲設定（200-Day Pullback用）
        if end_date is None:
            end_date = datetime.now()
        
        start_date = end_date - timedelta(days=300)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        logger.info(f"データ取得期間: {start_str} ～ {end_str}")
        
        # キャッシュから取得
        df = await persistent_cache.get(test_code, start_str, end_str)
        
        if df is None:
            logger.info("キャッシュミス - APIから取得します")
            df = await jq_client.get_prices_daily_quotes(session, test_code, start_str, end_str)
            
            if df is not None:
                await persistent_cache.set(test_code, start_str, end_str, df)
                logger.info(f"✅ データ取得成功: {len(df)}行")
            else:
                logger.error("❌ データ取得失敗")
                return
        else:
            logger.info(f"✅ キャッシュヒット: {len(df)}行")
        
        # データの内容を確認
        if len(df) > 0:
            logger.info(f"\nデータ概要:")
            logger.info(f"  行数: {len(df)}")
            logger.info(f"  列: {list(df.columns)}")
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                logger.info(f"  日付範囲: {df['Date'].iloc[0].strftime('%Y-%m-%d')} ～ {df['Date'].iloc[-1].strftime('%Y-%m-%d')}")
                logger.info(f"  最新データ:")
                latest = df.iloc[-1]
                logger.info(f"    日付: {latest['Date']}")
                logger.info(f"    終値: {latest['Close']:,.0f}円")
                logger.info(f"    出来高: {latest.get('Volume', 0):,.0f}")
        
        # 200-Day Pullback条件チェック
        if len(df) >= 200:
            logger.info(f"\n200-Day Pullback条件チェック:")
            
            # EMA計算
            df['EMA10'] = df['Close'].ewm(span=10, adjust=False).mean()
            df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
            
            # 52週最高値
            lookback_days = min(260, len(df))
            high_52w = df['High'].tail(lookback_days).max()
            latest = df.iloc[-1]
            current_price = latest['Close']
            
            # 52週新高値を記録した日を特定
            high_52w_date_idx = df['High'].tail(lookback_days).idxmax()
            days_since_high = len(df) - 1 - high_52w_date_idx
            
            # 新高値からの下落率
            pullback_pct = ((high_52w - current_price) / high_52w) * 100
            
            logger.info(f"  52週高値: {high_52w:,.0f}円")
            logger.info(f"  現在価格: {current_price:,.0f}円")
            logger.info(f"  高値更新からの経過日数: {days_since_high}日")
            logger.info(f"  下落率: {pullback_pct:.2f}%")
            
            # 条件判定
            logger.info(f"\n  条件1（60日以内に52週新高値）: {'✅ PASS' if days_since_high <= 60 else '❌ FAIL'}")
            logger.info(f"  条件2（30%以内の押し目）: {'✅ PASS' if pullback_pct <= 30 else '❌ FAIL'}")
            
            # EMAタッチ判定
            open_price = latest['Open']
            high_price = latest['High']
            low_price = latest['Low']
            
            ema10_touch = low_price <= latest['EMA10'] <= high_price
            ema20_touch = low_price <= latest['EMA20'] <= high_price
            ema50_touch = low_price <= latest['EMA50'] <= high_price
            
            logger.info(f"  条件3（EMAタッチ）:")
            logger.info(f"    EMA10タッチ: {'✅' if ema10_touch else '❌'} (EMA10={latest['EMA10']:,.2f}円)")
            logger.info(f"    EMA20タッチ: {'✅' if ema20_touch else '❌'} (EMA20={latest['EMA20']:,.2f}円)")
            logger.info(f"    EMA50タッチ: {'✅' if ema50_touch else '❌'} (EMA50={latest['EMA50']:,.2f}円)")
            
            any_ema_touch = ema10_touch or ema20_touch or ema50_touch
            logger.info(f"    いずれかのEMAにタッチ: {'✅ PASS' if any_ema_touch else '❌ FAIL'}")
            
            # 総合判定
            all_pass = (days_since_high <= 60 and pullback_pct <= 30 and any_ema_touch)
            logger.info(f"\n  総合判定: {'✅ 検出対象' if all_pass else '❌ 非検出'}")
        else:
            logger.warning(f"⚠️ データ不足: {len(df)}行 < 200行")
        
        logger.info("")


async def main():
    """メイン処理"""
    logger.info("0銘柄検出問題のデバッグを開始します\n")
    
    # 1. キャッシュ状態確認
    await check_cache_status()
    
    # 2. 日付調整ロジック確認
    end_date = await check_date_adjustment()
    
    # 3. サンプル銘柄テスト
    await test_sample_stock(end_date)
    
    logger.info("=" * 80)
    logger.info("デバッグ完了")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
