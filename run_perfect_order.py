#!/usr/bin/env python3
"""パーフェクトオーダースクリーニング専用スクリプト"""

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
    """パーフェクトオーダーのみを実行"""
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
        
        # パーフェクトオーダースクリーニングのみ実行
        logger.info("=" * 80)
        logger.info("🎯 パーフェクトオーダースクリーニング開始")
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 80)
        
        po_start = datetime.now()
        perfect_order = await screener.process_stocks_batch(
            stocks, screener.screen_stock_perfect_order, "パーフェクトオーダー"
        )
        po_time = int((datetime.now() - po_start).total_seconds() * 1000)
        logger.info(f"✅ パーフェクトオーダー検出: {len(perfect_order)}銘柄 ({po_time}ms)")
        
        # 最新取引日を取得（検出銘柄の有無に関わらず）
        target_date = await screener.get_latest_trading_date()
        logger.info(f"📅 最新取引日: {target_date}")
        
        # 間引き処理
        perfect_order_sampled = sample_stocks_balanced(perfect_order, max_per_range=10)
        logger.info(f"📊 間引き後: {len(perfect_order_sampled)}銘柄")
        
        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "perfect_order", target_date,
            len(perfect_order), po_time
        )
        if screening_id:
            screener.sb_client.save_detected_stocks(screening_id, perfect_order_sampled)
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
        
        logger.info("✅ パーフェクトオーダースクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
