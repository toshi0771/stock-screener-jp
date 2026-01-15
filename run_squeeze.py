#!/usr/bin/env python3
"""スクイーズ（価格収縮）スクリーニング専用スクリプト"""

import asyncio
import sys
from datetime import datetime
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
        target_date = datetime.now().strftime('%Y-%m-%d')
        logger.info("=" * 80)
        logger.info(f"スクイーズ（価格収縮）スクリーニング開始")
        logger.info("=" * 80)
        
        # 営業日チェック
        import aiohttp
        async with aiohttp.ClientSession() as session:
            if not await screener.is_trading_day(session, target_date):
                logger.info(f"⚠️  {target_date}は取引日ではありません。処理を終了します。")
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
        
        sq_start = datetime.now()
        squeeze = await screener.process_stocks_batch(
            stocks, screener.screen_stock_squeeze, "スクイーズ"
        )
        sq_time = int((datetime.now() - sq_start).total_seconds() * 1000)
        logger.info(f"✅ スクイーズ検出: {len(squeeze)}銘柄 ({sq_time}ms)")
        
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
        
        logger.info("=" * 80)
        logger.info("✅ スクイーズスクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
