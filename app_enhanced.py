"""
株式スクリーニングWebアプリケーション（拡張版）
3つのスクリーニング機能を統合したFlaskアプリ
"""

from flask import Flask, render_template, jsonify, request
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

# 絶対パスで設定
import sys
sys.path.insert(0, '/home/ubuntu/stock_screener_enhanced')

from pullback_screener import PullbackScreener

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False


class DummyDataGenerator:
    """ダミーデータ生成クラス"""
    
    @staticmethod
    def generate_stock_data(num_stocks=100, num_days=300):
        """
        ダミー株価データを生成
        
        Parameters:
        -----------
        num_stocks : int
            銘柄数
        num_days : int
            日数
        
        Returns:
        --------
        pandas.DataFrame : 株価データ
        """
        data = []
        
        markets = ['プライム', 'スタンダード', 'グロース']
        base_codes = [7203, 6758, 9984, 8306, 6861, 3382, 4661, 6432, 7846, 9787,
                      4385, 4477, 3694, 4488, 4490]
        
        # 日付範囲を生成
        end_date = datetime.now()
        dates = [end_date - timedelta(days=i) for i in range(num_days)]
        dates.reverse()
        
        for i in range(min(num_stocks, len(base_codes))):
            code = str(base_codes[i])
            market = random.choice(markets)
            name = f"銘柄{code}"
            
            # 初期価格
            base_price = random.uniform(1000, 5000)
            
            for date in dates:
                # ランダムウォーク
                change = random.uniform(-0.03, 0.03)
                base_price *= (1 + change)
                
                high = base_price * random.uniform(1.0, 1.02)
                low = base_price * random.uniform(0.98, 1.0)
                close = random.uniform(low, high)
                volume = random.randint(100000, 10000000)
                
                data.append({
                    'Date': date,
                    'Code': code,
                    'Name': name,
                    'Market': market,
                    'Open': base_price,
                    'High': high,
                    'Low': low,
                    'Close': close,
                    'Volume': volume
                })
        
        return pd.DataFrame(data)


# ダミーデータを生成
print("ダミーデータ生成中...")
dummy_df = DummyDataGenerator.generate_stock_data(num_stocks=15, num_days=300)
print(f"生成完了: {len(dummy_df)}レコード")


@app.route('/')
def index():
    """メインページ"""
    return render_template('index_enhanced.html')


@app.route('/api/status')
def api_status():
    """APIステータス"""
    return jsonify({
        'status': 'ok',
        'data_source': 'dummy',
        'total_stocks': len(dummy_df['Code'].unique()),
        'date_range': {
            'from': dummy_df['Date'].min().strftime('%Y-%m-%d'),
            'to': dummy_df['Date'].max().strftime('%Y-%m-%d')
        }
    })


@app.route('/api/screen/perfect_order', methods=['POST'])
def screen_perfect_order():
    """パーフェクトオーダースクリーニング"""
    try:
        params = request.json or {}
        market_filter = params.get('market', 'all')
        
        # 最新日のデータを取得
        latest_date = dummy_df['Date'].max()
        latest_df = dummy_df[dummy_df['Date'] == latest_date].copy()
        
        # 市場フィルター
        if market_filter != 'all':
            market_map = {'prime': 'プライム', 'standard': 'スタンダード', 'growth': 'グロース'}
            latest_df = latest_df[latest_df['Market'] == market_map.get(market_filter, market_filter)]
        
        # EMAを計算
        results = []
        for code, group in dummy_df.groupby('Code'):
            if market_filter != 'all':
                stock_market = group['Market'].iloc[0]
                market_map = {'prime': 'プライム', 'standard': 'スタンダード', 'growth': 'グロース'}
                if stock_market != market_map.get(market_filter, market_filter):
                    continue
            
            group = group.sort_values('Date')
            if len(group) < 50:
                continue
            
            # EMA計算
            ema_10 = group['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
            ema_20 = group['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
            ema_50 = group['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
            latest = group.iloc[-1]
            
            # パーフェクトオーダー判定
            if latest['Close'] >= ema_10 >= ema_20 >= ema_50:
                results.append({
                    'code': code,
                    'name': latest['Name'],
                    'market': latest['Market'],
                    'close': round(latest['Close'], 2),
                    'volume': int(latest['Volume']),
                    'ema_10': round(ema_10, 2),
                    'ema_20': round(ema_20, 2),
                    'ema_50': round(ema_50, 2)
                })
        
        return jsonify({
            'success': True,
            'total': len(results),
            'results': results
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/screen/bollinger_band', methods=['POST'])
def screen_bollinger_band():
    """ボリンジャーバンド±3σスクリーニング"""
    try:
        params = request.json or {}
        market_filter = params.get('market', 'all')
        
        results = []
        for code, group in dummy_df.groupby('Code'):
            if market_filter != 'all':
                stock_market = group['Market'].iloc[0]
                market_map = {'prime': 'プライム', 'standard': 'スタンダード', 'growth': 'グロース'}
                if stock_market != market_map.get(market_filter, market_filter):
                    continue
            
            group = group.sort_values('Date')
            if len(group) < 20:
                continue
            
            # ボリンジャーバンド計算
            sma_20 = group['Close'].rolling(window=20).mean().iloc[-1]
            std_20 = group['Close'].rolling(window=20).std().iloc[-1]
            upper_3sigma = sma_20 + 3 * std_20
            lower_3sigma = sma_20 - 3 * std_20
            latest = group.iloc[-1]
            
            # ±3σタッチ判定
            if latest['Close'] >= upper_3sigma or latest['Close'] <= lower_3sigma:
                signal = '買われすぎ' if latest['Close'] >= upper_3sigma else '売られすぎ'
                
                results.append({
                    'code': code,
                    'name': latest['Name'],
                    'market': latest['Market'],
                    'close': round(latest['Close'], 2),
                    'volume': int(latest['Volume']),
                    'sma_20': round(sma_20, 2),
                    'upper_3sigma': round(upper_3sigma, 2),
                    'lower_3sigma': round(lower_3sigma, 2),
                    'signal': signal
                })
        
        return jsonify({
            'success': True,
            'total': len(results),
            'results': results
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/screen/52week_pullback', methods=['POST'])
def screen_52week_pullback():
    """52週新高値押し目スクリーニング"""
    try:
        params = request.json or {}
        market_filter = params.get('market', 'all')
        ema_filter = params.get('ema_touch', 'all')
        stochastic_oversold = params.get('stochastic_oversold', False)
        
        # PullbackScreenerを使用
        screener = PullbackScreener()
        results = screener.screen(
            dummy_df,
            market_filter=market_filter,
            ema_filter=ema_filter,
            stochastic_oversold=stochastic_oversold
        )
        
        # 結果を整形
        formatted_results = []
        for r in results:
            formatted_results.append({
                'code': r['code'],
                'name': r['name'],
                'market': r['market'],
                'close': round(r['close'], 2),
                'volume': int(r['volume']),
                'high_52week': round(r['high_52week'], 2) if r['high_52week'] else None,
                'high_date': r['high_date'].strftime('%Y-%m-%d') if r['high_date'] else None,
                'pullback_pct': r['pullback_pct'],
                'days_since_high': r['days_since_high'],
                'touched_emas': r['touched_emas'],
                'touch_date': r['touch_date'].strftime('%Y-%m-%d') if r['touch_date'] else None,
                'stochastic_k': r['stochastic_k']
            })
        
        return jsonify({
            'success': True,
            'total': len(formatted_results),
            'results': formatted_results
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("株式スクリーニングWebアプリケーション起動")
    print("=" * 60)
    print(f"アクセスURL: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)

