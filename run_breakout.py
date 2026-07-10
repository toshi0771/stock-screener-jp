#!/usr/bin/env python3
"""ハンマー（下髭）スクリーニング専用スクリプト"""

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
    """ハンマーのみを実行"""
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
        
        # ハンマースクリーニングのみ実行
        logger.info("=" * 80)
        logger.info("🎯 ハンマー（下髭）スクリーニング開始")
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 80)
        
        bo_start = datetime.now()
        breakout = await screener.process_stocks_batch(
            stocks, screener.screen_stock_breakout, "ハンマー"
        )
        bo_time = int((datetime.now() - bo_start).total_seconds() * 1000)
        logger.info(f"✅ ハンマー検出: {len(breakout)}銘柄 ({bo_time}ms)")

        # 詳細統計を出力
        if hasattr(screener, 'perfect_order_stats'):
            s = screener.perfect_order_stats
            logger.info("=" * 60)
            logger.info("📊 ハンマースクリーニング 詳細統計")
            logger.info("=" * 60)
            logger.info(f"  処理対象:             {s['total']:,}銘柄")
            logger.info(f"  データ取得成功:       {s['has_data']:,}銘柄")
            logger.info(f"  52週高値-20%以下通過: {s['passed_bottom_zone']:,}銘柄")
            logger.info(f"  ストキャス%K≤20通過: {s['passed_stochastic']:,}銘柄")
            logger.info(f"  50EMA乖離5%以上通過: {s['passed_ema_deviation']:,}銘柄")
            logger.info(f"  下髭比率≥45%通過:    {s['passed_shadow_ratio']:,}銘柄")
            logger.info(f"  下髭÷実体≥1.0倍通過: {s['passed_shadow_body']:,}銘柄")
            logger.info(f"  終値位置上位30%通過:  {s['passed_close_position']:,}銘柄")
            logger.info(f"  陽線通過:             {s['passed_bullish']:,}銘柄")
            logger.info(f"  最終検出:             {s['final_detected']:,}銘柄")
            logger.info("=" * 60)
        
        # 🔧 FIX: 既に取得済みなので再取得不要（datetimeを文字列に変換）
        target_date = screener.latest_trading_date.strftime('%Y-%m-%d')
        logger.info(f"📅 最新取引日（保存用）: {target_date}")
        
        # 間引き処理
        breakout_sampled = sample_stocks_balanced(breakout, max_per_range=10)
        logger.info(f"📊 間引き後: {len(breakout_sampled)}銘柄")
        
        # 前日比較（ログ用のみ。表示対象は絞らず、当日の検出結果をそのまま使う）
        # 継続銘柄（前日も検出）は当日も条件を満たしているため自然に表示され続ける。
        # 90銘柄への水増し／切り捨ては行わない（最小限の実検出数のみ保存する）。
        # ※ボリンジャー・200日押し目はFixBLで既に修正済みだったが、ハンマーのみ
        #   この処理が残っており「毎日同じ銘柄が出る」原因の一つになっていた。
        try:
            yesterday = (screener.latest_trading_date - timedelta(days=3)).strftime('%Y-%m-%d')
            logger.info(f"📅 前日比較: {yesterday} ～ {target_date} の範囲で検索")
            prev_result = screener.sb_client.client.table('screening_results')\
                .select('id')\
                .eq('screening_type', 'breakout')\
                .gte('screening_date', yesterday)\
                .lt('screening_date', target_date)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            logger.info(f"📅 前日データ: {prev_result.data}")
            if prev_result.data:
                prev_id = prev_result.data[0]['id']
                prev_stocks = screener.sb_client.client.table('detected_stocks')\
                    .select('stock_code')\
                    .eq('screening_result_id', prev_id)\
                    .execute()
                prev_codes = {str(s['stock_code']) for s in prev_stocks.data}
                
                new_count = sum(1 for s in breakout_sampled if str(s['code']) not in prev_codes)
                cont_count = len(breakout_sampled) - new_count
                
                logger.info(f"📊 新規検出: {new_count}銘柄 / 継続: {cont_count}銘柄（表示件数への影響なし）")
        except Exception as e:
            logger.warning(f"前日比較スキップ: {e}")
        
        # 銘柄コード昇順でソート（表示順を一定にする）
        breakout_sampled = sorted(
            breakout_sampled,
            key=lambda x: str(x.get('code', ''))
        )
        logger.info(f"📊 コード昇順ソート完了: {len(breakout_sampled)}銘柄")

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
        
        logger.info("✅ ハンマースクリーニング完了")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
