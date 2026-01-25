"""
永続キャッシュモジュール

GitHub Actionsのキャッシュ機能と連携して、株価データを永続化します。
差分更新に対応し、銘柄コードのみをキーとして効率的にキャッシュします。
"""

import os
import pickle
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


class PersistentPriceCache:
    """
    ファイルベースの永続株価データキャッシュ（差分更新対応）
    
    GitHub Actionsのキャッシュ機能と連携して、
    株価データをファイルシステムに保存・読み込みします。
    
    キャッシュキーは銘柄コードのみとし、差分更新に対応します。
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
    
    def _get_cache_path(self, stock_code: str) -> Path:
        """
        キャッシュファイルのパスを取得
        
        Args:
            stock_code: 銘柄コード
        
        Returns:
            キャッシュファイルのパス
        """
        return self.cache_dir / f"{stock_code}.pkl"
    
    def _load_cache_data(self, cache_path: Path) -> Optional[Tuple[pd.DataFrame, str]]:
        """
        キャッシュファイルからデータと最終更新日を読み込む
        
        Args:
            cache_path: キャッシュファイルのパス
        
        Returns:
            (DataFrame, 最終更新日YYYYMMDD)のタプル、失敗時はNone
        """
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            
            # 新形式: {'df': DataFrame, 'last_date': 'YYYYMMDD'}
            if isinstance(data, dict) and 'df' in data and 'last_date' in data:
                return data['df'], data['last_date']
            
            # 旧形式（互換性のため）: DataFrameのみ
            if isinstance(data, pd.DataFrame):
                # DataFrameから最終日付を取得
                if 'Date' in data.columns and len(data) > 0:
                    last_date = pd.to_datetime(data['Date'].iloc[-1]).strftime('%Y%m%d')
                    return data, last_date
                else:
                    return None
            
            return None
        
        except Exception as e:
            logger.warning(f"キャッシュ読み込みエラー [{cache_path.name}]: {e}")
            return None
    
    def _save_cache_data(self, cache_path: Path, df: pd.DataFrame, last_date: str) -> bool:
        """
        データと最終更新日をキャッシュファイルに保存
        
        Args:
            cache_path: キャッシュファイルのパス
            df: 保存するDataFrame
            last_date: 最終更新日（YYYYMMDD）
        
        Returns:
            成功したらTrue
        """
        try:
            data = {
                'df': df,
                'last_date': last_date
            }
            
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            
            logger.debug(f"キャッシュ保存: {cache_path.name} (最終日: {last_date})")
            return True
        
        except Exception as e:
            logger.warning(f"キャッシュ保存エラー [{cache_path.name}]: {e}")
            return False
    
    async def get(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        max_age_days: int = 30
    ) -> Optional[pd.DataFrame]:
        """
        キャッシュからデータを取得（必要な期間のみ返す）
        
        Args:
            stock_code: 銘柄コード
            start_date: 開始日（YYYYMMDD）
            end_date: 終了日（YYYYMMDD）
            max_age_days: 最大有効日数（デフォルト30日）
        
        Returns:
            キャッシュされたDataFrame（指定期間のみ）、なければNone
        """
        cache_path = self._get_cache_path(stock_code)
        result = self._load_cache_data(cache_path)
        
        if result is None:
            self.misses += 1
            return None
        
        df, last_date = result
        
        # 最終更新日が古すぎる場合は無効
        try:
            last_update = datetime.strptime(last_date, '%Y%m%d')
            age = datetime.now() - last_update
            
            if age.days > max_age_days:
                logger.debug(f"キャッシュ期限切れ: {stock_code} (最終更新: {last_date}, {age.days}日前)")
                self.misses += 1
                return None
        except Exception as e:
            logger.warning(f"日付解析エラー [{stock_code}]: {e}")
            self.misses += 1
            return None
        
        # 必要な期間のデータを抽出
        try:
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                start_dt = pd.to_datetime(start_date, format='%Y%m%d')
                end_dt = pd.to_datetime(end_date, format='%Y%m%d')
                
                filtered_df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)].copy()
                
                # 必要な期間のデータが十分にあるか確認
                if len(filtered_df) > 0:
                    self.hits += 1
                    logger.debug(f"キャッシュヒット: {stock_code} ({len(filtered_df)}行)")
                    return filtered_df
                
                # end_dt が最新データより新しい場合、start_dt以降のすべてのデータを返す
                # （土日実行時のキャッシュミスマッチ対策）
                filtered_df = df[df['Date'] >= start_dt].copy()
                if len(filtered_df) > 0:
                    self.hits += 1
                    logger.debug(f"キャッシュヒット（部分）: {stock_code} ({len(filtered_df)}行, end_dt超過)")
                    return filtered_df
                else:
                    logger.debug(f"キャッシュに必要な期間のデータなし: {stock_code}")
                    self.misses += 1
                    return None
            else:
                self.misses += 1
                return None
        
        except Exception as e:
            logger.warning(f"データフィルタリングエラー [{stock_code}]: {e}")
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
        データをキャッシュに保存（差分更新対応）
        
        既存のキャッシュがある場合は、新しいデータとマージします。
        
        Args:
            stock_code: 銘柄コード
            start_date: 開始日（YYYYMMDD）
            end_date: 終了日（YYYYMMDD）
            df: 保存するDataFrame
        
        Returns:
            成功したらTrue
        """
        if df is None or len(df) == 0:
            return False
        
        cache_path = self._get_cache_path(stock_code)
        
        # 既存のキャッシュを読み込む
        result = self._load_cache_data(cache_path)
        
        if result is not None:
            existing_df, _ = result
            
            # 既存データと新しいデータをマージ
            try:
                # Date列を datetime 型に変換
                existing_df['Date'] = pd.to_datetime(existing_df['Date'])
                df['Date'] = pd.to_datetime(df['Date'])
                
                # 重複を削除してマージ
                merged_df = pd.concat([existing_df, df]).drop_duplicates(subset=['Date'], keep='last')
                merged_df = merged_df.sort_values('Date').reset_index(drop=True)
                
                # 最終日付を取得
                last_date = merged_df['Date'].iloc[-1].strftime('%Y%m%d')
                
                logger.debug(f"キャッシュマージ: {stock_code} (既存: {len(existing_df)}行, 新規: {len(df)}行, 合計: {len(merged_df)}行)")
                
                return self._save_cache_data(cache_path, merged_df, last_date)
            
            except Exception as e:
                logger.warning(f"キャッシュマージエラー [{stock_code}]: {e}")
                # マージ失敗時は新しいデータで上書き
        
        # 新規保存
        try:
            df['Date'] = pd.to_datetime(df['Date'])
            last_date = df['Date'].iloc[-1].strftime('%Y%m%d')
            return self._save_cache_data(cache_path, df, last_date)
        
        except Exception as e:
            logger.warning(f"キャッシュ保存エラー [{stock_code}]: {e}")
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
    
    def clear_old_cache(self, max_age_days: int = 30):
        """
        古いキャッシュファイルを削除
        
        Args:
            max_age_days: 削除する最大日数
        """
        now = datetime.now()
        deleted_count = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
            # ファイルの最終更新日時をチェック
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age = now - mtime
            
            if age.days >= max_age_days:
                cache_file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"古いキャッシュを削除: {deleted_count}ファイル")
