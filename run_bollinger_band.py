#!/usr/bin/env python3
"""ボリンジャーバンドスクリーニング専用スクリプト"""

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
    """ボリンジャーバンドのみを実行"""
    screener = StockScreener()
    
    try:
        # 仮の実行日（後で最新取引日に更新）
        target_date = datetime.now().strftime('%Y-%m-%d')
        logger.info("=" * 80)
        logger.info(f"ボリンジャーバンド±3σスクリーニング開始")
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
                    logger.warning(f"⚠️  {target_date}は休日ですが、手動実行のため処理を続行します")
                else:
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
        logger.info(f"📅 最新取引日（スクリーニング用）: {screener.latest_trading_date}")
        
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 80)
        
        bb_start = datetime.now()
        bollinger_band = await screener.process_stocks_batch(
            stocks, screener.screen_stock_bollinger_band, "ボリンジャーバンド"
        )
        bb_time = int((datetime.now() - bb_start).total_seconds() * 1000)
        logger.info(f"✅ ボリンジャーバンド検出: {len(bollinger_band)}銘柄 ({bb_time}ms)")
        
        # 🔧 FIX: 既に取得済みなので再取得不要（datetimeを文字列に変換）
        target_date = screener.latest_trading_date.strftime('%Y-%m-%d')
        logger.info(f"📅 最新取引日（保存用）: {target_date}")
        
        # 間引き処理
        bollinger_band_sampled = sample_stocks_balanced(bollinger_band, max_per_range=10)
        logger.info(f"📊 間引き後: {len(bollinger_band_sampled)}銘柄")
        
        # 前日との差分フィルター（新規検出銘柄を優先）
        try:
            yesterday = (screener.latest_trading_date - timedelta(days=3)).strftime('%Y-%m-%d')
            prev_result = screener.sb_client.client.table('screening_results')\
                .select('id')\
                .eq('screening_type', 'bollinger_band')\
                .gte('screening_date', yesterday)\
                .lt('screening_date', target_date)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if prev_result.data:
                prev_id = prev_result.data[0]['id']
                prev_stocks = screener.sb_client.client.table('detected_stocks')\
                    .select('stock_code')\
                    .eq('screening_result_id', prev_id)\
                    .execute()
                prev_codes = {str(s['stock_code']) for s in prev_stocks.data}
                
                new_stocks = [s for s in bollinger_band_sampled if str(s['code']) not in prev_codes]
                cont_stocks = [s for s in bollinger_band_sampled if str(s['code']) in prev_codes]
                
                logger.info(f"📊 新規検出: {len(new_stocks)}銘柄 / 継続: {len(cont_stocks)}銘柄")
                
                MAX_TOTAL = 90
                if len(new_stocks) >= MAX_TOTAL:
                    bollinger_band_sampled = new_stocks[:MAX_TOTAL]
                else:
                    remaining = MAX_TOTAL - len(new_stocks)
                    import random
                    random.shuffle(cont_stocks)
                    bollinger_band_sampled = new_stocks + cont_stocks[:remaining]
                
                logger.info(f"📊 最終保存: {len(bollinger_band_sampled)}銘柄（新規優先）")
        except Exception as e:
            logger.warning(f"前日比較スキップ: {e}")
        
        # 銘柄コード昇順でソート（表示順を一定にする）
        bollinger_band_sampled = sorted(
            bollinger_band_sampled,
            key=lambda x: str(x.get('code', ''))
        )
        logger.info(f"📊 コード昇順ソート完了: {len(bollinger_band_sampled)}銘柄")

        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "bollinger_band", target_date,
            len(bollinger_band), bb_time
        )
        if screening_id:
            screener.sb_client.save_detected_stocks(screening_id, bollinger_band_sampled)
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
        
        logger.info("✅ ボリンジャーバンドスクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
