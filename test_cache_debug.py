#!/usr/bin/env python3
"""
キャッシュの内容を確認するデバッグスクリプト
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# プロジェクトのモジュールをインポート
sys.path.insert(0, os.path.dirname(__file__))
from persistent_cache import PersistentPriceCache

async def main():
    """キャッシュの内容を確認"""
    
    # 永続キャッシュを初期化
    cache = PersistentPriceCache()
    
    # キャッシュディレクトリの確認
    logger.info(f"キャッシュディレクトリ: {cache.cache_dir}")
    logger.info(f"キャッシュディレクトリ存在: {cache.cache_dir.exists()}")
    
    if not cache.cache_dir.exists():
        logger.error("❌ キャッシュディレクトリが存在しません！")
        return
    
    # キャッシュファイル一覧
    cache_files = list(cache.cache_dir.glob("*.pkl"))
    logger.info(f"キャッシュファイル数: {len(cache_files)}")
    
    if len(cache_files) == 0:
        logger.error("❌ キャッシュファイルが1つもありません！")
        logger.info("\n【原因】")
        logger.info("1. GitHub Actionsのキャッシュが復元されていない")
        logger.info("2. キャッシュディレクトリのパスが間違っている")
        logger.info("3. まだ一度もデータが保存されていない")
        return
    
    # 最初の3つのキャッシュファイルをテスト
    logger.info("\n" + "="*80)
    logger.info("サンプルキャッシュファイルの内容確認:")
    logger.info("="*80)
    
    for cache_file in cache_files[:3]:
        stock_code = cache_file.stem  # ファイル名から拡張子を除いた部分
        logger.info(f"\n【銘柄コード: {stock_code}】")
        
        # キャッシュデータを読み込み
        result = cache._load_cache_data(cache_file)
        
        if result is None:
            logger.error(f"  ❌ キャッシュ読み込み失敗")
            continue
        
        df, last_date = result
        logger.info(f"  ✅ 読み込み成功")
        logger.info(f"  最終更新日: {last_date}")
        logger.info(f"  データ行数: {len(df)}行")
        
        if len(df) > 0:
            # 日付範囲を確認
            if 'Date' in df.columns:
                import pandas as pd
                df['Date'] = pd.to_datetime(df['Date'])
                first_date = df['Date'].min()
                last_date_dt = df['Date'].max()
                logger.info(f"  日付範囲: {first_date.strftime('%Y-%m-%d')} 〜 {last_date_dt.strftime('%Y-%m-%d')}")
                logger.info(f"  日数: {(last_date_dt - first_date).days + 1}日")
            
            # 最初の5行を表示
            logger.info(f"\n  最初の5行:")
            logger.info(f"{df.head().to_string()}")
    
    # スクリーニングで要求される期間をテスト
    logger.info("\n" + "="*80)
    logger.info("スクリーニング要求期間でのキャッシュ取得テスト:")
    logger.info("="*80)
    
    # 過去200日分のデータを要求（スクリーニングの典型的な要求）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=200)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    
    logger.info(f"\n要求期間: {start_str} 〜 {end_str} (200日分)")
    
    # 最初の銘柄でテスト
    if len(cache_files) > 0:
        test_code = cache_files[0].stem
        logger.info(f"テスト銘柄: {test_code}")
        
        df = await cache.get(test_code, start_str, end_str)
        
        if df is None:
            logger.error(f"  ❌ キャッシュから取得できませんでした")
        elif len(df) < 100:
            logger.warning(f"  ⚠️  取得したデータが100行未満: {len(df)}行")
            logger.warning(f"  → スクリーニングで除外されます！")
        else:
            logger.info(f"  ✅ 取得成功: {len(df)}行")
    
    # 統計情報
    logger.info("\n" + "="*80)
    stats = cache.get_stats()
    logger.info("キャッシュ統計:")
    logger.info(f"  ファイル数: {stats['files']}件")
    logger.info(f"  合計サイズ: {stats['size_mb']}MB")
    logger.info(f"  ヒット数: {stats['hits']}回")
    logger.info(f"  ミス数: {stats['misses']}回")
    logger.info(f"  ヒット率: {stats['hit_rate']}%")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
