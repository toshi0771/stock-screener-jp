#!/usr/bin/env python3
"""ブレイクアウト（持ち合い上放れ）スクリーニング専用スクリプト"""

import asyncio
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from daily_data_collection import (
    StockScreener, 
    sample_stocks_balanced,
    logger,
    CONCURRENT_REQUESTS
)

async def main():
    """ブレイクアウトのみを実行"""
    screener = StockScreener()
    
    try:
        # 仮の実行日（後で最新取引日に更新）
        target_date = datetime.now().strftime('%Y-%m-%d')
        logger.info("=" * 80)
        logger.info(f"日次株式スクリーニングデータ収集開始 (並列処理・全銘柄対応・オプション機能付き)")
        logger.info("=" * 80)
        
        # 実行トリガーを判定
        trigger = os.environ.get('GITHUB_EVENT_NAME', 'unknown')
        is_manual = (trigger == 'workflow_dispatch')
        
        # 営業日チェック
        logger.info("🔍 営業日チェック中...")
        import aiohttp
        async with aiohttp.ClientSession() as session:
            is_trading = await screener.client.is_trading_day(session, target_date)
            
            if not is_trading:
                if is_manual:
                    logger.warning(f"⚠️  {target_date}は休日ですが、手動実行のため処理を続行します")
                else:
                    return
        
        logger.info(f"✅ 実行日: {target_date}")
        
        # Supabase接続成功
        logger.info("📊 Supabase接続成功")
        
        # 銘柄一覧取得
        logger.info("🔍 jQuants API V1認証開始...")
        stocks = await screener.get_stocks_list()
        
        if not stocks:
            logger.error("❌ 銘柄一覧の取得に失敗しました")
            sys.exit(1)
        
        logger.info(f"✅ 銘柄一覧取得完了: {len(stocks)}銘柄")
        
        # 🔧 FIX: 最新取引日を事前に取得してキャッシュ（スクリーニング前に実行）
        screener.latest_trading_date = await screener.get_latest_trading_date()
        logger.info(f"📅 最新取引日（スクリーニング用）: {screener.latest_trading_date}")
        
        # ブレイクアウトスクリーニングのみ実行
        logger.info("=" * 80)
        logger.info("🎯 ブレイクアウト（持ち合い上放れ）スクリーニング開始")
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 80)
        
        bo_start = datetime.now()
        breakout = await screener.process_stocks_batch(
            stocks, screener.screen_stock_breakout, "ブレイクアウト"
        )
        bo_time = int((datetime.now() - bo_start).total_seconds() * 1000)
        logger.info(f"✅ ブレイクアウト検出: {len(breakout)}銘柄 ({bo_time}ms)")

        # 詳細統計を出力
        if hasattr(screener, 'perfect_order_stats'):
            s = screener.perfect_order_stats
            logger.info("=" * 60)
            logger.info("📊 ブレイクアウト スクリーニング 詳細統計")
            logger.info("=" * 60)
            logger.info(f"  処理対象:         {s['total']:,}銘柄")
            logger.info(f"  データ取得成功:   {s['has_data']:,}銘柄")
            logger.info(f"  ボックス幅OK:     {s['passed_box']:,}銘柄 （幅20%以内）")
            logger.info(f"  ブレイクアウトOK: {s['passed_breakout']:,}銘柄 （直近5日で高値更新）")
            logger.info(f"  ATRブレイクOK:    {s['passed_volume']:,}銘柄 （ATR1.5倍以上の値動き）")
            logger.info(f"  EMA50超OK:        {s['passed_ema']:,}銘柄 （EMA50より上）")
            logger.info(f"  3EMA収束OK:       {s['passed_convergence']:,}銘柄 （ブレイク前にEMA収束）")
            logger.info(f"  最終検出:         {s['final_detected']:,}銘柄")
            logger.info("=" * 60)
        
        # 🔧 FIX: 既に取得済みなので再取得不要（datetimeを文字列に変換）
        target_date = screener.latest_trading_date.strftime('%Y-%m-%d')
        logger.info(f"📅 最新取引日（保存用）: {target_date}")
        
        # 間引き処理
        breakout_sampled = sample_stocks_balanced(breakout, max_per_range=10)
        logger.info(f"📊 間引き後: {len(breakout_sampled)}銘柄")
        
        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "breakout", target_date,
            len(breakout), bo_time
        )
        if screening_id:
            screener.sb_client.save_detected_stocks(screening_id, breakout_sampled)
            logger.info(f"💾 Supabase保存完了 (screening_id: {screening_id})")
        
        # キャッシュ統計を出力
        logger.info("=" * 80)
        logger.info("メモリキャッシュ統計:")
        screener.cache.log_stats()
        
        # 永続キャッシュ統計を出力
        persistent_stats = screener.persistent_cache.get_stats()
        logger.info("\n永続キャッシュ統計:")
        logger.info(f"  ファイル数: {persistent_stats['files']}件")
        logger.info(f"  合計サイズ: {persistent_stats['size_mb']}MB")
        logger.info(f"  ヒット数: {persistent_stats['hits']}回")
        logger.info(f"  ミス数: {persistent_stats['misses']}回")
        logger.info(f"  ヒット率: {persistent_stats['hit_rate']}%")
        logger.info("=" * 80)
        
        logger.info("✅ ブレイクアウトスクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
