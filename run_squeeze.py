#!/usr/bin/env python3
"""スクイーズ（価格収縮）スクリーニング専用スクリプト"""

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
    """スクイーズのみを実行"""
    screener = StockScreener()
    
    try:
        # 仮の実行日（後で最新取引日に更新）
        target_date = datetime.now().strftime('%Y-%m-%d')
        logger.info("=" * 80)
        logger.info(f"スクイーズ（価格収縮）スクリーニング開始")
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
        
        sq_start = datetime.now()
        squeeze = await screener.process_stocks_batch(
            stocks, screener.screen_stock_squeeze, "スクイーズ"
        )
        sq_time = int((datetime.now() - sq_start).total_seconds() * 1000)
        logger.info(f"✅ スクイーズ検出: {len(squeeze)}銘柄 ({sq_time}ms)")
        
        # スクイーズ条件の統計情報を出力
        if hasattr(screener, 'squeeze_stats'):
            stats = screener.squeeze_stats
            logger.info("\n" + "="*80)
            logger.info("📊 スクイーズ条件チェック結果:")
            logger.info(f"  全銘柄数: {stats['total']}")
            logger.info(f"  データ取得成功: {stats['has_data']}銘柄")
            logger.info(f"  BBW条件で除外: {stats['bbw_failed']}銘柄")
            logger.info(f"  乖離率条件で除外: {stats['deviation_failed']}銘柄")
            logger.info(f"  ATR条件で除外: {stats['atr_failed']}銘柄")
            logger.info(f"  継続日数不足で除外: {stats['duration_failed']}銘柄")
            logger.info(f"  EMA50平坦でない: {stats['ema50_flat_failed']}銘柄 （上昇・下落トレンド中を除外）")
            logger.info(f"  最終検出数: {stats['passed_all']}銘柄")
            logger.info("="*80)
        
        # 🔧 FIX: 既に取得済みなので再取得不要（datetimeを文字列に変換）
        target_date = screener.latest_trading_date.strftime('%Y-%m-%d')
        logger.info(f"📅 最新取引日（保存用）: {target_date}")
        
        # 間引き処理
        squeeze_sampled = sample_stocks_balanced(squeeze, max_per_range=10)
        logger.info(f"📊 間引き後: {len(squeeze_sampled)}銘柄")
        
        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "squeeze", target_date,
            len(squeeze), sq_time
        )
        if screening_id:
            # additional_dataとしてJSONB形式で保存
            stocks_with_additional_data = []
            for s in squeeze_sampled:
                stock_data = {
                    "code": s["code"],
                    "name": s["name"],
                    "price": s["price"],
                    "market": s["market"],
                    "volume": s.get("volume", 0),
                    "additional_data": {
                        "bbw": s.get("bbw"),
                        "deviation": s.get("deviation"),
                        "atr": s.get("atr"),
                        "days": s.get("days")
                    }
                }
                stocks_with_additional_data.append(stock_data)
            
            screener.sb_client.save_detected_stocks(screening_id, stocks_with_additional_data)
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
        
        logger.info("✅ スクイーズスクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
