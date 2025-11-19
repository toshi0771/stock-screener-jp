"""
ストキャスティクス計算モジュール
%K値が20%以下の売られすぎ条件を検出
"""

import pandas as pd


class StochasticDetector:
    """ストキャスティクス検出クラス"""
    
    def __init__(self, k_period=14, d_period=3):
        """
        Parameters:
        -----------
        k_period : int
            %K期間（デフォルト14日）
        d_period : int
            %D期間（デフォルト3日）
        """
        self.k_period = k_period
        self.d_period = d_period
        self.oversold_threshold = 20  # 売られすぎ閾値
        self.overbought_threshold = 80  # 買われすぎ閾値
    
    def calculate_stochastic(self, df):
        """
        ストキャスティクス（%K, %D）を計算
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ（Date, Code, Close, High, Low列を含む）
        
        Returns:
        --------
        pandas.DataFrame : ストキャスティクス値を追加したDataFrame
        """
        if df is None or len(df) == 0:
            return df
        
        result_df = df.copy()
        
        # 銘柄コードでグループ化
        for code, group in df.groupby('Code'):
            # 日付でソート
            group = group.sort_values('Date').copy()
            
            if len(group) < self.k_period:
                continue
            
            # 過去N日間の最高値・最安値
            group['Highest_High'] = group['High'].rolling(window=self.k_period).max()
            group['Lowest_Low'] = group['Low'].rolling(window=self.k_period).min()
            
            # %K計算
            group['Stochastic_K'] = ((group['Close'] - group['Lowest_Low']) / 
                                      (group['Highest_High'] - group['Lowest_Low'])) * 100
            
            # %D計算（%Kの移動平均）
            group['Stochastic_D'] = group['Stochastic_K'].rolling(window=self.d_period).mean()
            
            # 結果を更新
            result_df.loc[group.index, 'Stochastic_K'] = group['Stochastic_K']
            result_df.loc[group.index, 'Stochastic_D'] = group['Stochastic_D']
        
        return result_df
    
    def detect_oversold(self, df):
        """
        売られすぎ銘柄を検出（%K <= 20）
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ（ストキャスティクス計算済み）
        
        Returns:
        --------
        list : 売られすぎ銘柄のリスト
        """
        if df is None or len(df) == 0:
            return []
        
        # ストキャスティクスを計算
        df_with_stoch = self.calculate_stochastic(df)
        
        results = []
        
        # 銘柄コードでグループ化
        for code, group in df_with_stoch.groupby('Code'):
            # 最新のデータ
            latest = group.sort_values('Date').iloc[-1]
            
            # 売られすぎ判定
            if pd.notna(latest.get('Stochastic_K')) and latest['Stochastic_K'] <= self.oversold_threshold:
                results.append({
                    'code': code,
                    'close': latest['Close'],
                    'stochastic_k': round(latest['Stochastic_K'], 2),
                    'stochastic_d': round(latest['Stochastic_D'], 2) if pd.notna(latest.get('Stochastic_D')) else None,
                    'date': latest['Date']
                })
        
        return results
    
    def is_oversold(self, k_value):
        """
        %K値が売られすぎかチェック
        
        Parameters:
        -----------
        k_value : float
            %K値
        
        Returns:
        --------
        bool : 売られすぎの有無
        """
        return k_value <= self.oversold_threshold
    
    def is_overbought(self, k_value):
        """
        %K値が買われすぎかチェック
        
        Parameters:
        -----------
        k_value : float
            %K値
        
        Returns:
        --------
        bool : 買われすぎの有無
        """
        return k_value >= self.overbought_threshold
    
    def get_signal(self, k_value):
        """
        ストキャスティクスシグナルを取得
        
        Parameters:
        -----------
        k_value : float
            %K値
        
        Returns:
        --------
        str : シグナル（'oversold', 'overbought', 'neutral'）
        """
        if self.is_oversold(k_value):
            return 'oversold'
        elif self.is_overbought(k_value):
            return 'overbought'
        else:
            return 'neutral'

