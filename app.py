"""
株式スクリーニングWebアプリケーション（シンプル実データ連携版）
Supabaseから最新のスクリーニング結果を取得して表示
"""

from flask import Flask, render_template, jsonify, request
import os
import sys
from datetime import datetime, timedelta
from supabase import create_client, Client
# 環境変数読み込み（.envファイルから手動読み込み）
import pathlib
env_file = pathlib.Path('/home/ubuntu/stock_screener_enhanced/.env')
if env_file.exists():
    for line in env_file.read_text().strip().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Supabase接続設定
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URLとSUPABASE_ANON_KEYを.envファイルに設定してください")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
print(f"✅ Supabase接続成功: {SUPABASE_URL}", file=sys.stderr)


def get_latest_screening_results(screening_type, market='all'):
    """
    Supabaseから最新のスクリーニング結果を取得（シンプル版）
    """
    try:
        print(f"\n🔍 スクリーニング検索開始", file=sys.stderr)
        print(f"   Type: {screening_type}, Market: {market}", file=sys.stderr)
        
        # 最新のスクリーニング結果を取得（過去30日以内、フィルター条件を緩和）
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # screening_resultsテーブルから最新の結果IDを取得（total_stocks_found > 0のみ）
        query = supabase.table('screening_results')\
            .select('id, screening_date, total_stocks_found, market_filter')\
            .eq('screening_type', screening_type)\
            .gt('total_stocks_found', 0)\
            .gte('screening_date', thirty_days_ago)\
            .order('screening_date', desc=True)\
            .limit(10)
        
        screening_results = query.execute()
        
        print(f"   検索結果: {len(screening_results.data)}件", file=sys.stderr)
        
        if not screening_results.data or len(screening_results.data) == 0:
            print(f"⚠️ {screening_type}の最新結果が見つかりません", file=sys.stderr)
            return []
        
        # 市場フィルターに合致する結果を探す
        screening_result_id = None
        for result in screening_results.data:
            result_market = result.get('market_filter')
            print(f"   候補: ID={result['id'][:8]}..., Date={result['screening_date']}, Market={result_market}, Count={result['total_stocks_found']}", file=sys.stderr)
            
            # 市場フィルターが一致するか、Noneの場合は使用
            if market == 'all':
                if result_market == 'all' or result_market is None:
                    screening_result_id = result['id']
                    print(f"   ✅ 選択: {screening_result_id[:8]}...", file=sys.stderr)
                    break
            elif result_market == market:
                screening_result_id = result['id']
                print(f"   ✅ 選択: {screening_result_id[:8]}...", file=sys.stderr)
                break
        
        if not screening_result_id:
            # 市場フィルターが一致しない場合は、最新のものを使用
            screening_result_id = screening_results.data[0]['id']
            print(f"   ⚠️ 市場フィルター不一致、最新を使用: {screening_result_id[:8]}...", file=sys.stderr)
        
        # detected_stocksテーブルから検出銘柄を取得
        detected_stocks = supabase.table('detected_stocks')\
            .select('*')\
            .eq('screening_result_id', screening_result_id)\
            .execute()
        
        print(f"   検出銘柄数: {len(detected_stocks.data)}件", file=sys.stderr)
        
        if not detected_stocks.data:
            print(f"⚠️ 検出銘柄が見つかりません", file=sys.stderr)
            return []
        
        # 市場フィルター適用（detected_stocksレベルで）
        if market != 'all':
            detected_stocks.data = [s for s in detected_stocks.data if s['market'] == market]
            print(f"   市場フィルター適用後: {len(detected_stocks.data)}件", file=sys.stderr)
        
        # 結果を整形
        results = []
        for stock in detected_stocks.data:
            # 銘柄コードを5桁から4桁に変換（先頭の0を削除）
            stock_code = str(stock['stock_code'])
            if len(stock_code) == 5 and stock_code.startswith('0'):
                stock_code = stock_code[1:]  # 先頭の0を削除
            
            result = {
                'code': stock_code,
                'name': stock['company_name'],
                'market': stock['market'],
                'price': float(stock['close_price']),
                'volume': int(stock['volume']),
            }
            
            # スクリーニング手法別の追加情報
            if screening_type == 'perfect_order':
                result.update({
                    'ema10': float(stock['ema_10']) if stock['ema_10'] else None,
                    'ema20': float(stock['ema_20']) if stock['ema_20'] else None,
                    'ema50': float(stock['ema_50']) if stock['ema_50'] else None,
                    'sma200': float(stock['sma_200']) if stock['sma_200'] else None,
                    'sma200_position': stock['sma200_position']
                })
            elif screening_type == 'bollinger_band':
                result.update({
                    'upper3': float(stock['bollinger_upper']) if stock['bollinger_upper'] else None,
                    'lower3': float(stock['bollinger_lower']) if stock['bollinger_lower'] else None,
                    'touch_direction': stock['touch_direction']
                })
            elif screening_type == '52week_pullback':
                result.update({
                    'ema10': float(stock['ema_10']) if stock['ema_10'] else None,
                    'ema20': float(stock['ema_20']) if stock['ema_20'] else None,
                    'ema50': float(stock['ema_50']) if stock['ema_50'] else None,
                    'week52_high': float(stock['week52_high']) if stock['week52_high'] else None,
                    'ema_touch': stock['touch_ema'],
                    'stochastic_k': float(stock['stochastic_k']) if stock['stochastic_k'] else None,
                    'stochastic_d': float(stock['stochastic_d']) if stock['stochastic_d'] else None
                })
            
            results.append(result)
        
        print(f"✅ {len(results)}件の銘柄を返却", file=sys.stderr)
        return results
    
    except Exception as e:
        print(f"❌ Supabaseデータ取得エラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []


@app.route('/')
def index():
    """トップページ"""
    return render_template('index_new.html')


@app.route('/api/screening', methods=['POST'])
def api_screening():
    """スクリーニング実行API（フィルター付き）"""
    try:
        data = request.get_json()
        method = data.get('method')
        options = data.get('options', {})
        
        # 市場選択を取得
        market = options.get('market', 'all')
        
        # オプションパラメータを取得
        sma200_filter = options.get('sma200', 'all')  # パーフェクトオーダー用
        ema50_divergence = options.get('ema50_divergence', 'all')  # パーフェクトオーダー用
        sigma_filter = options.get('sigma', 'all')  # ボリンジャーバンド用
        use_stochastic = options.get('use_stochastic', False)  # 52週新高値押し目用
        
        print(f"\n🔍 APIリクエスト受信: {method}, 市場: {market}, SMA200: {sma200_filter}, EMA50乖離: {ema50_divergence}, σ: {sigma_filter}, ストキャス: {use_stochastic}", file=sys.stderr)
        
        # Supabaseから実データを取得
        results = get_latest_screening_results(method, market)
        
        # パーフェクトオーダー: 200SMAフィルター適用
        if method == 'perfect_order' and sma200_filter != 'all':
            if sma200_filter == 'above':
                results = [r for r in results if r.get('sma200_position') == 'above']
            elif sma200_filter == 'below':
                results = [r for r in results if r.get('sma200_position') == 'below']
        
        # パーフェクトオーダー: 50EMA乖離率フィルター適用
        if method == 'perfect_order' and ema50_divergence != 'all':
            threshold = float(ema50_divergence) / 100.0  # 10% -> 0.1
            filtered_results = []
            for r in results:
                price = r.get('price')
                ema50 = r.get('ema50')
                if price and ema50 and ema50 > 0:
                    divergence = abs(price - ema50) / ema50
                    if divergence < threshold:
                        filtered_results.append(r)
            results = filtered_results
            print(f"   50EMA乖離率フィルター適用後: {len(results)}件", file=sys.stderr)
        
        # ボリンジャーバンド: σフィルター適用
        if method == 'bollinger_band' and sigma_filter != 'all':
            results = [r for r in results if r.get('touch_direction') == sigma_filter]
            print(f"   σフィルター適用後: {len(results)}件", file=sys.stderr)
        
        # 52週新高値押し目: タッチEMAフィルター適用
        if method == '52week_pullback' and 'ema_touch' in options and options['ema_touch'] != 'all':
            ema_touch_filter = options['ema_touch']
            results = [r for r in results if r.get('ema_touch') == ema_touch_filter]
            print(f"   タッチEMAフィルター適用後: {len(results)}件", file=sys.stderr)
        
        # 52週新高値押し目: ストキャスティクスフィルター適用
        if method == '52week_pullback' and use_stochastic:
            # ストキャスティクスKが20以下の銘柄のみ抜き出し
            results = [r for r in results if r.get('stochastic_k') is not None and r.get('stochastic_k') <= 20]
            print(f"   ストキャスティクスフィルター適用後: {len(results)}件", file=sys.stderr)
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
    
    except Exception as e:
        print(f"❌ APIエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/historical', methods=['POST'])
def api_historical():
    """過去データ取得API"""
    try:
        data = request.get_json()
        method = data.get('method')
        days_ago = data.get('days_ago', 10)
        
        print(f"\n📅 過去データリクエスト: {method}, {days_ago}日前", file=sys.stderr)
        
        # 指定日数前の日付を計算
        target_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        # screening_resultsテーブルから指定日付の結果を取得
        query = supabase.table('screening_results')\
            .select('id, screening_date, total_stocks_found')\
            .eq('screening_type', method)\
            .gt('total_stocks_found', 0)\
            .lte('screening_date', target_date)\
            .order('screening_date', desc=True)\
            .limit(1)
        
        screening_results = query.execute()
        
        if not screening_results.data or len(screening_results.data) == 0:
            print(f"⚠️ {method}の{days_ago}日前の結果が見つかりません", file=sys.stderr)
            return jsonify({
                'success': True,
                'results': [],
                'count': 0
            })
        
        screening_result_id = screening_results.data[0]['id']
        screening_date = screening_results.data[0]['screening_date']
        
        print(f"   検索結果: {screening_date}のデータを取得", file=sys.stderr)
        
        # detected_stocksテーブルから検出銘柄を取得
        detected_stocks = supabase.table('detected_stocks')\
            .select('*')\
            .eq('screening_result_id', screening_result_id)\
            .execute()
        
        # 結果を整形
        results = []
        for stock in detected_stocks.data:
            # 銘柄コードを5桁から4桁に変換
            stock_code = str(stock['stock_code'])
            if len(stock_code) == 5 and stock_code.startswith('0'):
                stock_code = stock_code[1:]
            
            result = {
                'code': stock_code,
                'name': stock['company_name'],
                'market': stock['market'],
                'price': float(stock['close_price']),
                'volume': int(stock['volume']),
            }
            
            # スクリーニング手法別の追加情報
            if method == 'perfect_order':
                result.update({
                    'ema10': float(stock['ema_10']) if stock['ema_10'] else None,
                    'ema20': float(stock['ema_20']) if stock['ema_20'] else None,
                    'ema50': float(stock['ema_50']) if stock['ema_50'] else None,
                })
            elif method == 'bollinger_band':
                result.update({
                    'touch_direction': stock['touch_direction']
                })
            elif method == '52week_pullback':
                result.update({
                    'ema_touch': stock['touch_ema'],
                    'stochastic_k': float(stock['stochastic_k']) if stock['stochastic_k'] else None,
                })
            
            results.append(result)
        
        print(f"✅ {len(results)}件の過去データを返却", file=sys.stderr)
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'date': screening_date
        })
    
    except Exception as e:
        print(f"❌ 過去データAPIエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """ヘルスチェックAPI"""
    try:
        # Supabase接続確認
        result = supabase.table('screening_results').select('id').limit(1).execute()
        return jsonify({
            'status': 'healthy',
            'supabase': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/api/history')
def get_history():
    """過去データ履歴を取得"""
    try:
        days = int(request.args.get('days', 30))
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        print(f"\n📅 過去データ履歴リクエスト: {days}日間", file=sys.stderr)
        
        # screening_resultsテーブルから期間内のデータを取得
        query = supabase.table('screening_results')\
            .select('id, screening_date, screening_type, total_stocks_found')\
            .gte('screening_date', start_date)\
            .order('screening_date', desc=True)
        
        results = query.execute()
        
        # 日付ごとにデータを集計
        history_dict = {}
        for row in results.data:
            date = row['screening_date']
            screening_type = row['screening_type']
            count = row['total_stocks_found']
            result_id = row.get('id')
            
            if date not in history_dict:
                history_dict[date] = {
                    'date': date,
                    'perfect_order': 0,
                    'bollinger_band': 0,
                    'pullback_200day': 0,
                    'perfect_order_id': None,
                    'bollinger_band_id': None,
                    'pullback_200day_id': None
                }
            
            if screening_type == 'perfect_order':
                history_dict[date]['perfect_order'] = count
                history_dict[date]['perfect_order_id'] = result_id
            elif screening_type == 'bollinger_band':
                history_dict[date]['bollinger_band'] = count
                history_dict[date]['bollinger_band_id'] = result_id
            elif screening_type == '200day_pullback':
                history_dict[date]['pullback_200day'] = count
                history_dict[date]['pullback_200day_id'] = result_id
        
        # 銘柄名を取得（分類別）
        for date_data in history_dict.values():
            # パーフェクトオーダーの銘柄取得（sma200_positionで分類）
            if date_data['perfect_order_id']:
                stocks = supabase.table('detected_stocks')\
                    .select('company_name, stock_code, market, sma200_position')\
                    .eq('screening_result_id', date_data['perfect_order_id'])\
                    .execute()
                
                # sma200_positionで分類
                above_200sma = []
                below_200sma = []
                for s in stocks.data:
                    stock_info = {
                        'code': str(s['stock_code'])[:-1] if str(s['stock_code']).endswith('0') and len(str(s['stock_code']))==5 else s['stock_code'],
                        'company_name': s['company_name']
                    }
                    if s.get('sma200_position') == 'above':
                        above_200sma.append(stock_info)
                    else:
                        below_200sma.append(stock_info)
                
                date_data['perfect_order_above_200sma'] = above_200sma
                date_data['perfect_order_below_200sma'] = below_200sma
            else:
                date_data['perfect_order_above_200sma'] = []
                date_data['perfect_order_below_200sma'] = []
            
                # ボリンジャーバンドの銘柄取得（touch_directionで分類）
            try:
                bollinger_stocks = supabase.table('detected_stocks')\
                    .select('company_name, stock_code, market, touch_direction')\
                    .eq('screening_result_id', result_id)\
                    .eq('method', 'bollinger_band')\
                    .execute()
                # touch_directionで分類
                plus_3sigma = []
                minus_3sigma = []
                for s in bollinger_stocks.data:
                    stock_info = {
                        'code': str(s['stock_code'])[:-1] if str(s['stock_code']).endswith('0') and len(str(s['stock_code']))==5 else s['stock_code'],
                        'company_name': s['company_name']
                    }
                    touch_dir = s.get('touch_direction')
                    if touch_dir == '+3σ' or touch_dir == 'upper':
                        plus_3sigma.append(stock_info)
                    elif touch_dir == '-3σ' or touch_dir == 'lower':
                        minus_3sigma.append(stock_info)
                
                date_data['bollinger_plus_3sigma'] = plus_3sigma
                date_data['bollinger_minus_3sigma'] = minus_3sigma
            except Exception as e:
                print(f"   ボリンジャーバンド銘柄取得エラー: {e}", file=sys.stderr)
                date_data['bollinger_plus_3sigma'] = []
                date_data['bollinger_minus_3sigma'] = []
            
            # 200日新高値押し目の銘柄取得（touch_emaで分類）
            if date_data['pullback_200day_id']:
                stocks = supabase.table('detected_stocks')\
                    .select('company_name, stock_code, market, touch_ema')\
                    .eq('screening_result_id', date_data['pullback_200day_id'])\
                    .execute()
                
                # touch_emaで分類
                ema10_stocks = []
                ema20_stocks = []
                ema50_stocks = []
                for s in stocks.data:
                    stock_info = {
                        'code': str(s['stock_code'])[:-1] if str(s['stock_code']).endswith('0') and len(str(s['stock_code']))==5 else s['stock_code'],
                        'company_name': s['company_name']
                    }
                    ema_touch = s.get('touch_ema', '')
                    if '10EMA' in ema_touch:
                        ema10_stocks.append(stock_info)
                    if '20EMA' in ema_touch:
                        ema20_stocks.append(stock_info)
                    if '50EMA' in ema_touch:
                        ema50_stocks.append(stock_info)
                
                date_data['pullback_10ema'] = ema10_stocks
                date_data['pullback_20ema'] = ema20_stocks
                date_data['pullback_50ema'] = ema50_stocks
            else:
                date_data['pullback_10ema'] = []
                date_data['pullback_20ema'] = []
                date_data['pullback_50ema'] = []
        
        # リストに変換してソート
        history_list = sorted(history_dict.values(), key=lambda x: x['date'], reverse=True)
        
        print(f"   取得件数: {len(history_list)}日分", file=sys.stderr)
        
        return jsonify({
            'success': True,
            'history': history_list
        })
        
    except Exception as e:
        print(f"❌ 過去データ取得エラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("=" * 60, file=sys.stderr)
    print("株式スクリーニングWebアプリケーション起動（シンプル実データ連携版）", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Supabase URL: {SUPABASE_URL}", file=sys.stderr)
    print("アクセスURL: http://localhost:5000", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    app.run(debug=True, host='0.0.0.0', port=5000)

