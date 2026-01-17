#!/usr/bin/env python3
"""ボリンジャーバンドスクリーニング専用スクリプト"""

import asyncio
import sys
import os
from datetime import datetime
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
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 80)
        
        bb_start = datetime.now()
        bollinger_band = await screener.process_stocks_batch(
            stocks, screener.screen_stock_bollinger_band, "ボリンジャーバンド"
        )
        bb_time = int((datetime.now() - bb_start).total_seconds() * 1000)
        logger.info(f"✅ ボリンジャーバンド検出: {len(bollinger_band)}銘柄 ({bb_time}ms)")
        
        # 間引き処理
        bollinger_band_sampled = sample_stocks_balanced(bollinger_band, max_per_range=10)
        logger.info(f"📊 間引き後: {len(bollinger_band_sampled)}銘柄")
        
        # Supabase保存
        screening_id = screener.sb_client.save_screening_result(
            "bollinger_band", target_date,
            len(bollinger_band), bb_time
        )
        if screening_id:
            screener.sb_client.save_detected_stocks(screening_id, bollinger_band_sampled)
            logger.info(f"💾 Supabase保存完了 (screening_id: {screening_id})")
        
        logger.info("=" * 80)
        logger.info("✅ ボリンジャーバンドスクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
