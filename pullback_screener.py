"""
52週新高値押し目統合スクリーニングエンジン
52週新高値検出、EMAタッチ判定、ストキャスティクスを統合
"""

import pandas as pd
from week52_high_detector import Week52HighDetector
from ema_touch_detector import EMATouchDetector
from stochastic_detector import StochasticDetector


class PullbackScreener:
    """52週新高値押し目統合スクリーナー"""
    
    def __init__(self):
        self.high_detector = Week52HighDetector()
        self.ema_detector = EMATouchDetector()
        self.stoch_detector = StochasticDetector()
    
    def screen(self, df, market_filter='all', ema_filter='all', stochastic_oversold=False):
        """
        52週新高値押し目スクリーニングを実行
        
        Parameters:
        -----------
        df : pandas.DataFrame
            株価データ（Date, Code, Close, High, Low, Market列を含む）
        market_filter : str
            市場フィルター ('all', 'prime', 'standard', 'growth')
        ema_filter : str
            EMAフィルター ('all', '10ema', '20ema', '50ema')
        stochastic_oversold : bool
            ストキャスティクス売られすぎフィルター
        
        Returns:
        --------
        list : 検出された銘柄のリスト
        """
        if df is None or len(df) == 0:
            return []
        
        # 市場フィルター適用
        if market_filter != 'all':
            market_map = {
                'prime': 'プライム',
                'standard': 'スタンダード',
                'growth': 'グロース'
            }
            df = df[df['Market'] == market_map.get(market_filter, market_filter)]
        
        # 52週新高値を検出
        high_stocks = self.high_detector.detect_52week_high(df)
        
        if not high_stocks:
            return []
        
        # EMAタッチを検出
        ema_stocks = self.ema_detector.detect_ema_touch(df, ema_filter)
        
        # ストキャスティクスを計算
        if stochastic_oversold:
            stoch_stocks = self.stoch_detector.detect_oversold(df)
            stoch_codes = {s['code'] for s in stoch_stocks}
        
        # 52週新高値とEMAタッチの両方を満たす銘柄を抽出
        high_codes = {s['code'] for s in high_stocks}
        ema_codes = {s['code'] for s in ema_stocks}
        
        matched_codes = high_codes & ema_codes
        
        # ストキャスティクスフィルター適用
        if stochastic_oversold:
            matched_codes = matched_codes & stoch_codes
        
        # 結果を統合
        results = []
        
        for code in matched_codes:
            # 52週新高値情報
            high_info = next((s for s in high_stocks if s['code'] == code), None)
            
            # EMA情報
            ema_info = next((s for s in ema_stocks if s['code'] == code), None)
            
            # ストキャスティクス情報
            stoch_info = None
            if stochastic_oversold:
                stoch_info = next((s for s in stoch_stocks if s['code'] == code), None)
            
            # 銘柄情報を取得
            stock_data = df[df['Code'] == code].sort_values('Date').iloc[-1]
            
            result = {
                'code': code,
                'name': stock_data.get('Name', f'銘柄{code}'),
                'market': stock_data.get('Market', 'Unknown'),
                'close': stock_data['Close'],
                'volume': stock_data.get('Volume', 0),
                'high_52week': high_info['high_52week'] if high_info else None,
                'high_date': high_info['high_date'] if high_info else None,
                'pullback_pct': high_info['pullback_pct'] if high_info else None,
                'days_since_high': high_info['days_since_high'] if high_info else None,
                'ema_10': ema_info['ema_10'] if ema_info else None,
                'ema_20': ema_info['ema_20'] if ema_info else None,
                'ema_50': ema_info['ema_50'] if ema_info else None,
                'touched_emas': ema_info['touched_emas'] if ema_info else None,
                'touch_date': ema_info['touch_date'] if ema_info else None,
                'stochastic_k': stoch_info['stochastic_k'] if stoch_info else None,
                'stochastic_d': stoch_info['stochastic_d'] if stoch_info else None
            }
            
            results.append(result)
        
        # 押し目率でソート（小さい順 = 新高値に近い）
        results.sort(key=lambda x: x['pullback_pct'] if x['pullback_pct'] else 100)
        
        return results
    
    def get_statistics(self, results):
        """
        スクリーニング結果の統計情報を取得
        
        Parameters:
        -----------
        results : list
            スクリーニング結果
        
        Returns:
        --------
        dict : 統計情報
        """
        if not results:
            return {
                'total': 0,
                'avg_pullback': 0,
                'avg_days_since_high': 0,
                'market_breakdown': {}
            }
        
        total = len(results)
        avg_pullback = sum(r['pullback_pct'] for r in results if r['pullback_pct']) / total
        avg_days = sum(r['days_since_high'] for r in results if r['days_since_high']) / total
        
        # 市場別内訳
        market_breakdown = {}
        for r in results:
            market = r['market']
            market_breakdown[market] = market_breakdown.get(market, 0) + 1
        
        return {
            'total': total,
            'avg_pullback': round(avg_pullback, 2),
            'avg_days_since_high': round(avg_days, 1),
            'market_breakdown': market_breakdown
        }

