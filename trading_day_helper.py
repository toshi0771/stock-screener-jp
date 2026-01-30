"""
取引日取得のヘルパーモジュール

安全な日付調整ロジックを提供します。
"""

import logging
from datetime import datetime, timedelta
import aiohttp
import pytz

logger = logging.getLogger(__name__)


async def get_latest_trading_day(jq_client, session: aiohttp.ClientSession, base_date: datetime = None) -> datetime:
    """
    最新の取引日を安全に取得
    
    Args:
        jq_client: J-Quants クライアント
        session: aiohttp セッション
        base_date: 基準日（Noneの場合は現在日時）
    
    Returns:
        最新の取引日（datetime）
    """
    # 🔧 FIX: 日本時間（JST）に変換
    jst = pytz.timezone('Asia/Tokyo')
    
    if base_date is None:
        # UTCで取得してJSTに変換
        base_date_jst = datetime.now(pytz.utc).astimezone(jst)
    elif base_date.tzinfo is None:
        # タイムゾーン情報がない場合、JSTとして扱う
        base_date_jst = jst.localize(base_date)
    else:
        # 他のタイムゾーンの場合、JSTに変換
        base_date_jst = base_date.astimezone(jst)
    
    # 16:00前チェック（日本時間で判定）
    current_hour = base_date_jst.hour  # ← JST時刻
    current_date_str = base_date_jst.strftime('%Y-%m-%d %H:%M:%S %Z')
    
    logger.info(f"⏰ 現在時刻（JST）: {current_date_str}")
    
    if current_hour < 16:  # ← JSTで判定（正しい）
        logger.info(f"⏰ JST {current_hour}:00 < 16:00 のため、前日を基準日とします")
        logger.info(f"   理由: jQuants APIのデータ提供は16:00以降です")
        base_date_jst = base_date_jst - timedelta(days=1)
    else:
        logger.info(f"⏰ JST {current_hour}:00 >= 16:00 のため、当日を基準日とします")
    
    # タイムゾーン情報を削除してnaive datetimeに戻す
    end_date = base_date_jst.replace(tzinfo=None)
    max_attempts = 10
    attempts = 0
    
    logger.debug(f"取引日取得開始: base_date_jst={base_date_jst.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    while attempts < max_attempts:
        # 週末をスキップ
        while end_date.weekday() >= 5:  # 5=土曜, 6=日曜
            end_date = end_date - timedelta(days=1)
            logger.debug(f"  週末スキップ: {end_date.strftime('%Y-%m-%d')} ({['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]})")
        
        # 祝日チェック
        try:
            date_str = end_date.strftime("%Y-%m-%d")
            is_trading = await jq_client.is_trading_day(session, date_str)
            
            if is_trading:
                logger.info(f"✅ 取引日確定: {date_str} ({['月', '火', '水', '木', '金', '土', '日'][end_date.weekday()]})")
                # タイムゾーン情報を削除して返す
                return end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
            else:
                logger.debug(f"  非取引日: {date_str}")
        
        except Exception as e:
            logger.warning(f"⚠️ is_trading_day() API エラー: {e}")
            # APIエラー時は前日に戻って続行
            end_date = end_date - timedelta(days=1)
            attempts += 1
            continue
        
        # 非取引日の場合、前日に戻る
        end_date = end_date - timedelta(days=1)
        attempts += 1
    
    # 最大試行回数を超えた場合、フォールバック
    fallback_date = end_date - timedelta(days=7)
    logger.error(f"❌ 取引日の取得に失敗しました（{max_attempts}回試行）。フォールバック: {fallback_date.strftime('%Y-%m-%d')}")
    # タイムゾーン情報を削除して返す
    return fallback_date.replace(tzinfo=None) if fallback_date.tzinfo else fallback_date


def get_date_range_for_screening(end_date: datetime, lookback_days: int) -> tuple:
    """
    スクリーニング用の日付範囲を取得
    
    Args:
        end_date: 終了日（取引日）
        lookback_days: 遡る日数
    
    Returns:
        (start_str, end_str) のタプル（YYYYMMDD形式）
    """
    start_date = end_date - timedelta(days=lookback_days)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    
    logger.debug(f"日付範囲: {start_str} ～ {end_str} ({lookback_days}日間)")
    
    return start_str, end_str
