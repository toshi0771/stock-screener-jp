"""
EMAタッチ判定モジュール
10EMA、20EMA、50EMAへのタッチ（接触）を精密に検出
"""

import pandas as pd
import numpy as np


class EMATouchDetector:
    """EMAタッチ判定クラス"""
    
    def __init__(self):
        self.ema_periods = [10, 20, 50]
    
    def calculate_ema(self, series, period):
        """
        指数移動平均(EMA)を計算
        
        Parameters:
        -----------
        series : pandas.Series
            価格データ
        period : int
            EMA期間
        
        Returns:
        --------
        pandas.Series : EMA値
        """
        return series.ewm(span=period, adjust=False).mean()
    
    def detect_ema_touch(self, df, ema_filter='all'):
        """
        EMAタッチを検出
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ（Date, Code, Close, High, Low列を含む）
        ema_filter : str
            EMAフィルター ('all', '10ema', '20ema', '50ema')
        
        Returns:
        --------
        list : EMAタッチ銘柄のリスト
        """
        if df is None or len(df) == 0:
            return []
        
        results = []
        
        # 銘柄コードでグループ化
        for code, group in df.groupby('Code'):
            # 日付でソート
            group = group.sort_values('Date').copy()
            
            if len(group) < 50:  # 最低50日分のデータが必要
                continue
            
            # EMAを計算
            group['EMA_10'] = self.calculate_ema(group['Close'], 10)
            group['EMA_20'] = self.calculate_ema(group['Close'], 20)
            group['EMA_50'] = self.calculate_ema(group['Close'], 50)
            
            # 最新のデータ
            latest = group.iloc[-1]
            
            # タッチ判定（高値 >= EMA >= 安値）
            touched_emas = []
            
            if ema_filter in ['all', '10ema']:
                if latest['Low'] <= latest['EMA_10'] <= latest['High']:
                    touched_emas.append('10EMA')
            
            if ema_filter in ['all', '20ema']:
                if latest['Low'] <= latest['EMA_20'] <= latest['High']:
                    touched_emas.append('20EMA')
            
            if ema_filter in ['all', '50ema']:
                if latest['Low'] <= latest['EMA_50'] <= latest['High']:
                    touched_emas.append('50EMA')
            
            if touched_emas:
                results.append({
                    'code': code,
                    'close': latest['Close'],
                    'ema_10': round(latest['EMA_10'], 2),
                    'ema_20': round(latest['EMA_20'], 2),
                    'ema_50': round(latest['EMA_50'], 2),
                    'touched_emas': ','.join(touched_emas),
                    'touch_date': latest['Date']
                })
        
        return results
    
    def check_ema_touch(self, high, low, ema):
        """
        単一のローソク足がEMAにタッチしているかチェック
        
        Parameters:
        -----------
        high : float
            高値
        low : float
            安値
        ema : float
            EMA値
        
        Returns:
        --------
        bool : タッチの有無
        """
        return low <= ema <= high
    
    def get_latest_touch_date(self, df, code, ema_period):
        """
        指定銘柄の最新EMAタッチ日を取得
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ
        code : str
            銘柄コード
        ema_period : int
            EMA期間
        
        Returns:
        --------
        datetime or None : 最新タッチ日
        """
        stock_data = df[df['Code'] == code].sort_values('Date').copy()
        
        if len(stock_data) < ema_period:
            return None
        
        # EMAを計算
        stock_data[f'EMA_{ema_period}'] = self.calculate_ema(stock_data['Close'], ema_period)
        
        # タッチ判定
        stock_data['Touch'] = stock_data.apply(
            lambda row: self.check_ema_touch(row['High'], row['Low'], row[f'EMA_{ema_period}']),
            axis=1
        )
        
        # 最新のタッチ日を取得
        touched = stock_data[stock_data['Touch'] == True]
        
        if len(touched) > 0:
            return touched.iloc[-1]['Date']
        
        return None

