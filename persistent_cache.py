"""
永続キャッシュモジュール

GitHub Actionsのキャッシュ機能と連携して、株価データを永続化します。
"""

import os
import pickle
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


class PersistentPriceCache:
    """
    ファイルベースの永続株価データキャッシュ
    
    GitHub Actionsのキャッシュ機能と連携して、
    株価データをファイルシステムに保存・読み込みします。
    """
    
    def __init__(self, cache_dir: str = "~/.cache/stock_prices"):
        """
        Args:
            cache_dir: キャッシュディレクトリのパス
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.hits = 0
        self.misses = 0
        
        logger.info(f"永続キャッシュ初期化: {self.cache_dir}")
    
    def _get_cache_key(self, stock_code: str, start_date: str, end_date: str) -> str:
        """
        キャッシュキーを生成
        
        Args:
            stock_code: 銘柄コード
            start_date: 開始日（YYYYMMDD）
            end_date: 終了日（YYYYMMDD）
        
        Returns:
            キャッシュキー
        """
        return f"{stock_code}_{start_date}_{end_date}"
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """
        キャッシュファイルのパスを取得
        
        Args:
            cache_key: キャッシュキー
        
        Returns:
            キャッシュファイルのパス
        """
        return self.cache_dir / f"{cache_key}.pkl"
    
    def _is_cache_valid(self, cache_path: Path, max_age_days: int = 1) -> bool:
        """
        キャッシュが有効かチェック
        
        Args:
            cache_path: キャッシュファイルのパス
            max_age_days: 最大有効日数
        
        Returns:
            有効ならTrue
        """
        if not cache_path.exists():
            return False
        
        # ファイルの最終更新日時を取得
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age = datetime.now() - mtime
        
        return age.days < max_age_days
    
    async def get(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        max_age_days: int = 1
    ) -> Optional[pd.DataFrame]:
        """
        キャッシュからデータを取得
        
        Args:
            stock_code: 銘柄コード
            start_date: 開始日（YYYYMMDD）
            end_date: 終了日（YYYYMMDD）
            max_age_days: 最大有効日数
        
        Returns:
            キャッシュされたDataFrame、なければNone
        """
        cache_key = self._get_cache_key(stock_code, start_date, end_date)
        cache_path = self._get_cache_path(cache_key)
        
        if not self._is_cache_valid(cache_path, max_age_days):
            self.misses += 1
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                df = pickle.load(f)
            
            self.hits += 1
            logger.debug(f"キャッシュヒット: {cache_key}")
            return df
        
        except Exception as e:
            logger.warning(f"キャッシュ読み込みエラー [{cache_key}]: {e}")
            self.misses += 1
            return None
    
    async def set(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        df: pd.DataFrame
    ) -> bool:
        """
        データをキャッシュに保存
        
        Args:
            stock_code: 銘柄コード
            start_date: 開始日（YYYYMMDD）
            end_date: 終了日（YYYYMMDD）
            df: 保存するDataFrame
        
        Returns:
            成功したらTrue
        """
        cache_key = self._get_cache_key(stock_code, start_date, end_date)
        cache_path = self._get_cache_path(cache_key)
        
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(df, f)
            
            logger.debug(f"キャッシュ保存: {cache_key}")
            return True
        
        except Exception as e:
            logger.warning(f"キャッシュ保存エラー [{cache_key}]: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        キャッシュ統計を取得
        
        Returns:
            統計情報の辞書
        """
        total_files = len(list(self.cache_dir.glob("*.pkl")))
        total_size_mb = sum(
            f.stat().st_size for f in self.cache_dir.glob("*.pkl")
        ) / (1024 * 1024)
        
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "files": total_files,
            "size_mb": round(total_size_mb, 2),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(hit_rate, 2)
        }
    
    def clear_old_cache(self, max_age_days: int = 7):
        """
        古いキャッシュファイルを削除
        
        Args:
            max_age_days: 削除する最大日数
        """
        now = datetime.now()
        deleted_count = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age = now - mtime
            
            if age.days >= max_age_days:
                cache_file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"古いキャッシュを削除: {deleted_count}ファイル")
