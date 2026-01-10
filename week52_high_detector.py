"""
52週新高値検出モジュール
過去252営業日（約1年）の最高値を計算し、直近20営業日以内の新高値達成銘柄を検出
"""

import pandas as pd
from datetime import datetime, timedelta


class Week52HighDetector:
    """52週新高値検出クラス"""
    
    def __init__(self):
        self.lookback_days = 252  # 約1年（営業日）
        self.recent_days = 20  # 直近20営業日以内
    
    def detect_52week_high(self, df):
        """
        52週新高値を検出
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ（Date, Code, Close, High列を含む）
        
        Returns:
        --------
        list : 52週新高値達成銘柄のリスト
        """
        if df is None or len(df) == 0:
            return []
        
        results = []
        
        # 銘柄コードでグループ化
        for code, group in df.groupby('Code'):
            # 日付でソート
            group = group.sort_values('Date')
            
            if len(group) < self.lookback_days:
                continue
            
            # 過去252営業日の最高値を計算
            group['High_52W'] = group['High'].rolling(window=self.lookback_days, min_periods=1).max()
            
            # 直近20営業日のデータ
            recent_data = group.tail(self.recent_days)
            
            # 新高値達成を検出（当日高値 >= 52週最高値）
            for idx, row in recent_data.iterrows():
                if row['High'] >= row['High_52W']:
                    # 新高値達成日からの経過日数を計算
                    high_date = row['Date']
                    latest_date = group['Date'].max()
                    days_since_high = (latest_date - high_date).days
                    
                    # 押し目の深さを計算
                    latest_close = group[group['Date'] == latest_date]['Close'].values[0]
                    pullback_pct = ((row['High'] - latest_close) / row['High']) * 100
                    
                    results.append({
                        'code': code,
                        'high_52week': row['High_52W'],
                        'high_date': high_date,
                        'latest_close': latest_close,
                        'pullback_pct': round(pullback_pct, 2),
                        'days_since_high': days_since_high
                    })
                    break  # 最初の新高値のみ
        
        return results
    
    def is_within_recent_high(self, df, code, days=20):
        """
        指定銘柄が直近N営業日以内に52週新高値を達成したかチェック
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ
        code : str
            銘柄コード
        days : int
            チェックする日数
        
        Returns:
        --------
        bool : 新高値達成の有無
        """
        stock_data = df[df['Code'] == code].sort_values('Date')
        
        if len(stock_data) < self.lookback_days:
            return False
        
        # 過去252営業日の最高値
        stock_data['High_52W'] = stock_data['High'].rolling(window=self.lookback_days, min_periods=1).max()
        
        # 直近N営業日
        recent = stock_data.tail(days)
        
        # 新高値達成チェック
        for idx, row in recent.iterrows():
            if row['High'] >= row['High_52W']:
                return True
        
        return False

