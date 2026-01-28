#!/usr/bin/env python3
"""200日新高値押し目スクリーニング専用スクリプト"""

import asyncio
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from daily_data_collection import (
    StockScreener, 
    sample_stocks_balanced,
    logger,
    CONCURRENT_REQUESTS,
    PULLBACK_EMA_FILTER,
    PULLBACK_STOCHASTIC_FILTER
)

async def main():
    """200日新高値押し目のみを実行"""
    screener = StockScreener()
    
    try:
        # 仮の実行日（後で最新取引日に更新）
        target_date = datetime.now().strftime('%Y-%m-%d')
        logger.info("=" * 80)
        logger.info(f"200日新高値押し目スクリーニング開始")
        logger.info("=" * 80)
        
        # 実行トリガーを判定
        trigger = os.environ.get('GITHUB_EVENT_NAME', 'unknown')
        is_manual = (trigger == 'workflow_dispatch')
        
        # 営業日チェック
        import aiohttp
        async with aiohttp.ClientSession() as session:
            is_trading = await screener.client.is_trading_day(session, target_date)
            
            if not is_trading:
                if is_manual:
                    # 手動実行：警告を表示して続行
                    logger.warning(f"⚠️  {target_date}は休日ですが、手動実行のため処理を続行します")
                else:
                    # 自動実行：静かに終了
                    return
        
        logger.info(f"✅ 実行日: {target_date}")
        logger.info("📊 Supabase接続成功")
        
        # 銘柄一覧取得
        stocks = await screener.get_stocks_list()
        
        if not stocks:
            logger.error("❌ 銘柄一覧の取得に失敗しました")
            sys.exit(1)
        
        logger.info(f"✅ 銘柄一覧取得完了: {len(stocks)}銘柄")
        
        # 🔧 FIX: 最新取引日を事前に取得してキャッシュ（スクリーニング前に実行）
        screener.latest_trading_date = await screener.get_latest_trading_date()
        logger.info(f"📅 最新取引日（キャッシュ済み）: {screener.latest_trading_date}")
        
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info(f"EMAフィルター: {PULLBACK_EMA_FILTER}")
        logger.info(f"ストキャスティクス: {'ON' if PULLBACK_STOCHASTIC_FILTER else 'OFF'}")
        logger.info("=" * 80)
        
        pb_start = datetime.now()
        week52_pullback = await screener.process_stocks_batch(
            stocks, screener.screen_stock_200day_pullback, "200日新高値押し目"
        )
        pb_time = int((datetime.now() - pb_start).total_seconds() * 1000)
        logger.info(f"✅ 200日新高値押し目検出: {len(week52_pullback)}銘柄 ({pb_time}ms)")
        
        # 最新取引日を使用（すでにキャッシュ済み）
        target_date = screener.latest_trading_date
        
        # 統計情報を表示
        if hasattr(screener, 'pullback_stats'):
            stats = screener.pullback_stats
            logger.info("\n" + "="*60)
            logger.info("📊 200日新高値押し目スクリーニング 詳細統計")
            logger.info("="*60)
            logger.info(f"📄 処理対象: {stats['total']:,}銘柄")
            
            if stats['total'] > 0:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄 ({stats['has_data']/stats['total']*100:.1f}%)")
            
            logger.info(f"\n🔹 条件別通過状況:")
            
            if stats['has_data'] > 0:
                logger.info(f"  1️⃣ 60日以内に52週高値更新: {stats['recent_high']:,}銘柄 ({stats['recent_high']/stats['has_data']*100:.2f}%)")
            
            if stats['recent_high'] > 0:
                logger.info(f"  2️⃣ 30%以内の押し目: {stats['within_30pct']:,}銘柄 ({stats['within_30pct']/stats['recent_high']*100:.2f}%)")
            
            logger.info(f"\n🔹 EMAタッチ別統計:")
            logger.info(f"  🔸 10EMAタッチ: {stats['ema10_touch']:,}銘柄")
            logger.info(f"  🔸 20EMAタッチ: {stats['ema20_touch']:,}銘柄")
            logger.info(f"  🔸 50EMAタッチ: {stats['ema50_touch']:,}銘柄")
            
            if stats['within_30pct'] > 0:
                logger.info(f"  ✅ いずれかのEMAタッチ: {stats['any_ema_touch']:,}銘柄 ({stats['any_ema_touch']/stats['within_30pct']*100:.2f}%)")
            
            logger.info(f"\n⭐ 全条件通過: {stats['passed_all']:,}銘柄")
            logger.info("="*60 + "\n")
        
        # 間引き処理
        week52_pullback_sampled = sample_stocks_balanced(week52_pullback, max_per_range=10)
        logger.info(f"📊 間引き後: {len(week52_pullback_sampled)}銘柄")
        
        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "200day_pullback", target_date,
            len(week52_pullback), pb_time
        )
        if screening_id:
            screener.sb_client.save_detected_stocks(screening_id, week52_pullback_sampled)
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
        
        logger.info("✅ 200日新高値押し目スクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
