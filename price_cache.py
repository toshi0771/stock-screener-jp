"""
株価データキャッシュモジュール
複数のスクリーニング手法で同じ銘柄の株価データを共有し、API呼び出しを削減
"""
import asyncio
from datetime import datetime
from typing import Dict, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class PriceDataCache:
    """株価データのキャッシュクラス（メモリベース）"""
    
    def __init__(self):
        self._cache: Dict[str, pd.DataFrame] = {}
        self._lock = asyncio.Lock()
        self._hit_count = 0
        self._miss_count = 0
    
    def _generate_key(self, code: str, start_date: str, end_date: str) -> str:
        """キャッシュキーを生成"""
        return f"{code}_{start_date}_{end_date}"
    
    async def get(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        キャッシュから株価データを取得
        
        Args:
            code: 銘柄コード
            start_date: 開始日（YYYYMMDD形式）
            end_date: 終了日（YYYYMMDD形式）
        
        Returns:
            キャッシュされたDataFrame、存在しない場合はNone
        """
        key = self._generate_key(code, start_date, end_date)
        
        async with self._lock:
            if key in self._cache:
                self._hit_count += 1
                logger.debug(f"キャッシュヒット [{code}] {start_date}~{end_date}")
                return self._cache[key].copy()
            else:
                self._miss_count += 1
                return None
    
    async def set(self, code: str, start_date: str, end_date: str, data: pd.DataFrame):
        """
        株価データをキャッシュに保存
        
        Args:
            code: 銘柄コード
            start_date: 開始日（YYYYMMDD形式）
            end_date: 終了日（YYYYMMDD形式）
            data: 株価データのDataFrame
        """
        key = self._generate_key(code, start_date, end_date)
        
        async with self._lock:
            self._cache[key] = data.copy()
            logger.debug(f"キャッシュ保存 [{code}] {start_date}~{end_date}, {len(data)}行")
    
    async def get_or_fetch(self, code: str, start_date: str, end_date: str, 
                          fetch_func, *args, **kwargs) -> Optional[pd.DataFrame]:
        """
        キャッシュから取得、存在しない場合はAPIから取得してキャッシュ
        
        Args:
            code: 銘柄コード
            start_date: 開始日（YYYYMMDD形式）
            end_date: 終了日（YYYYMMDD形式）
            fetch_func: データ取得関数（async）
            *args, **kwargs: fetch_funcに渡す引数
        
        Returns:
            株価データのDataFrame
        """
        # キャッシュから取得を試みる
        cached_data = await self.get(code, start_date, end_date)
        if cached_data is not None:
            return cached_data
        
        # キャッシュになければAPIから取得
        data = await fetch_func(*args, **kwargs)
        
        # 取得したデータをキャッシュに保存
        if data is not None and not data.empty:
            await self.set(code, start_date, end_date, data)
        
        return data
    
    def get_stats(self) -> Dict[str, int]:
        """キャッシュ統計を取得"""
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0
        
        return {
            "cache_size": len(self._cache),
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": round(hit_rate, 2)
        }
    
    def clear(self):
        """キャッシュをクリア"""
        self._cache.clear()
        logger.info("キャッシュをクリアしました")
    
    def log_stats(self):
        """キャッシュ統計をログ出力"""
        stats = self.get_stats()
        logger.info(
            f"キャッシュ統計: "
            f"サイズ={stats['cache_size']}, "
            f"ヒット={stats['hit_count']}, "
            f"ミス={stats['miss_count']}, "
            f"ヒット率={stats['hit_rate']}%"
        )


# グローバルキャッシュインスタンス
_global_cache: Optional[PriceDataCache] = None


def get_cache() -> PriceDataCache:
    """グローバルキャッシュインスタンスを取得"""
    global _global_cache
    if _global_cache is None:
        _global_cache = PriceDataCache()
    return _global_cache
