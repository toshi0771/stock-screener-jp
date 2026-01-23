#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レート制限対応のテストスクリプト
少数の銘柄で動作確認
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# 環境変数を読み込み
from dotenv import load_dotenv
load_dotenv()

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# daily_data_collection.pyから必要なクラスをインポート
sys.path.insert(0, str(Path(__file__).parent))
from daily_data_collection import AsyncJQuantsClient, StockScreener

async def test_rate_limit():
    """レート制限のテスト"""
    logger.info("=" * 60)
    logger.info("レート制限対応テスト開始")
    logger.info("=" * 60)
    
    # JQuantsクライアントの初期化
    jq_client = AsyncJQuantsClient()
    
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        # 認証
        await jq_client.authenticate(session)
        
        # 銘柄一覧を取得（最新の営業日のデータ）
        logger.info("銘柄一覧を取得中...")
        stocks = await jq_client.get_listed_info(session)
        
        if not stocks:
            logger.error("銘柄一覧の取得に失敗しました")
            return 1
        
        logger.info(f"取得した銘柄数: {len(stocks)}銘柄")
        
        # テスト用に最初の10銘柄のみを使用
        test_stocks = stocks[:10]
        logger.info(f"テスト対象: {len(test_stocks)}銘柄")
        
        # スクリーナーの初期化
        screener = StockScreener()
        
        # パーフェクトオーダーのスクリーニングをテスト
        logger.info("=" * 60)
        logger.info("パーフェクトオーダースクリーニング（テスト）")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        results = await screener.process_stocks_batch(
            test_stocks, 
            screener.screen_stock_perfect_order, 
            "パーフェクトオーダー（テスト）"
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        
        logger.info("=" * 60)
        logger.info(f"テスト完了: {len(results)}銘柄検出")
        logger.info(f"処理時間: {elapsed:.1f}秒")
        logger.info(f"平均処理時間: {elapsed/len(test_stocks):.2f}秒/銘柄")
        logger.info("=" * 60)
        
        if len(results) > 0:
            logger.info(f"検出銘柄例: {results[0]}")
        
        return 0

if __name__ == "__main__":
    exit(asyncio.run(test_rate_limit()))
