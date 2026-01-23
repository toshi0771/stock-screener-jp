import random
from typing import List, Dict

def sample_stocks_balanced(stocks: List[Dict], max_per_range: int = 10) -> List[Dict]:
    """
    銘柄コード帯別・市場別の銘柄数に応じた割合でランダムサンプリング
    
    Args:
        stocks: 検出銘柄のリスト
        max_per_range: 各銘柄コード帯から抽出する最大銘柄数（デフォルト: 10）
    
    Returns:
        サンプリングされた銘柄のリスト
    
    ロジック:
        1. 各銘柄コード帯（1000-1999, 2000-2999など）内で市場別に分類
        2. 各市場の銘柄数を集計
        3. 最大剰余法（Largest Remainder Method）で抽出数を決定
        4. 各市場からランダムに抽出
    """
    if not stocks or len(stocks) <= 100:
        return stocks  # 100銘柄以下ならそのまま返す
    
    # 銘柄コード帯別・市場別に分類
    ranges = {}
    
    for stock in stocks:
        code = str(stock.get('code', '0000'))
        # 銘柄コードの先頭1桁を取得（1000番台、2000番台...）
        if len(code) >= 4:
            range_key = f"{code[0]}000"
        else:
            range_key = "other"
        
        market = stock.get('market', 'プライム')
        
        if range_key not in ranges:
            ranges[range_key] = {}
        if market not in ranges[range_key]:
            ranges[range_key][market] = []
        
        ranges[range_key][market].append(stock)
    
    # 各帯から市場別の銘柄数に応じてランダム抽出
    sampled = []
    
    for range_key, markets in sorted(ranges.items()):
        # 各市場の銘柄数を集計
        market_counts = {market: len(stocks_list) for market, stocks_list in markets.items()}
        total_in_range = sum(market_counts.values())
        
        # この帯から抽出する銘柄数（最大max_per_range）
        target_count = min(max_per_range, total_in_range)
        
        # 最大剰余法で各市場の抽出数を計算
        market_samples = {}
        quotas = {}  # 比例配分の商
        remainders = {}  # 比例配分の余り
        
        # ステップ1: 比例配分の商と余りを計算
        for market, count in market_counts.items():
            quota = (count / total_in_range) * target_count
            quotas[market] = int(quota)  # 整数部分
            remainders[market] = quota - int(quota)  # 小数部分（余り）
        
        # ステップ2: 商の合計を計算
        allocated = sum(quotas.values())
        
        # ステップ3: 残りの議席を余りが大きい順に配分
        remaining_seats = target_count - allocated
        if remaining_seats > 0:
            # 余りが大きい順にソート
            sorted_markets = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
            for i in range(remaining_seats):
                market = sorted_markets[i][0]
                quotas[market] += 1
        
        # 実際の銘柄数を超えないように調整
        for market, sample_count in quotas.items():
            market_samples[market] = min(sample_count, market_counts[market])
        
        # 各市場からランダムに抽出
        for market, sample_count in market_samples.items():
            if sample_count > 0:
                stocks_in_market = markets[market]
                # ランダムにサンプリング
                sampled_stocks = random.sample(stocks_in_market, min(sample_count, len(stocks_in_market)))
                sampled.extend(sampled_stocks)
    
    print(f"📊 間引きロジック: {len(stocks)}銘柄 → {len(sampled)}銘柄")
    
    # 各帯の内訳をログ出力
    for range_key, markets in sorted(ranges.items()):
        market_summary = ", ".join([f"{m}:{len(s)}" for m, s in markets.items()])
        print(f"   {range_key}番台: {market_summary}")
    
    return sampled


# テスト用データ
if __name__ == "__main__":
    # テストデータ作成（100銘柄以上）
    test_stocks = []
    
    # 1000番台: プライム40, スタンダード30, グロース10（合計80銘柄）
    # 比率 4:3:1 → 10銘柄抽出時の期待値: 5:4:1
    for i in range(40):
        test_stocks.append({'code': f'1{i:03d}', 'name': f'プライム{i}', 'market': 'プライム', 'price': 1000})
    for i in range(30):
        test_stocks.append({'code': f'1{i+100:03d}', 'name': f'スタンダード{i}', 'market': 'スタンダード', 'price': 1000})
    for i in range(10):
        test_stocks.append({'code': f'1{i+200:03d}', 'name': f'グロース{i}', 'market': 'グロース', 'price': 1000})
    
    # 2000番台: プライム50, スタンダード40, グロース20（合計110銘柄）
    # 比率 5:4:2 → 10銘柄抽出時の期待値: 5:4:1 または 5:3:2
    for i in range(50):
        test_stocks.append({'code': f'2{i:03d}', 'name': f'プライム{i}', 'market': 'プライム', 'price': 2000})
    for i in range(40):
        test_stocks.append({'code': f'2{i+100:03d}', 'name': f'スタンダード{i}', 'market': 'スタンダード', 'price': 2000})
    for i in range(20):
        test_stocks.append({'code': f'2{i+200:03d}', 'name': f'グロース{i}', 'market': 'グロース', 'price': 2000})
    
    # 3000番台: プライム20, スタンダード20, グロース20（合計60銘柄）
    # 比率 1:1:1 → 10銘柄抽出時の期待値: 3:3:3 または 4:3:3
    for i in range(20):
        test_stocks.append({'code': f'3{i:03d}', 'name': f'プライム{i}', 'market': 'プライム', 'price': 3000})
    for i in range(20):
        test_stocks.append({'code': f'3{i+100:03d}', 'name': f'スタンダード{i}', 'market': 'スタンダード', 'price': 3000})
    for i in range(20):
        test_stocks.append({'code': f'3{i+200:03d}', 'name': f'グロース{i}', 'market': 'グロース', 'price': 3000})
    
    print("=" * 60)
    print("テストデータ:")
    print(f"  1000番台: プライム40, スタンダード30, グロース10（合計80銘柄）")
    print(f"            比率 4:3:1 → 期待値 5:4:1")
    print(f"  2000番台: プライム50, スタンダード40, グロース20（合計110銘柄）")
    print(f"            比率 5:4:2 → 期待値 5:4:1 または 5:3:2")
    print(f"  3000番台: プライム20, スタンダード20, グロース20（合計60銘柄）")
    print(f"            比率 1:1:1 → 期待値 3:3:3 または 4:3:3")
    print(f"  総計: {len(test_stocks)}銘柄")
    print("=" * 60)
    
    # サンプリング実行
    sampled = sample_stocks_balanced(test_stocks, max_per_range=10)
    
    print("\n" + "=" * 60)
    print("サンプリング結果:")
    print("=" * 60)
    
    # 帯別・市場別に集計
    for range_key in ['1000', '2000', '3000']:
        print(f"\n{range_key}番台:")
        total_in_range = 0
        for market in ['プライム', 'スタンダード', 'グロース']:
            stocks_in_market = [s for s in sampled if s['code'].startswith(range_key[0]) and s['market'] == market]
            if stocks_in_market:
                print(f"  {market}: {len(stocks_in_market)}銘柄")
                total_in_range += len(stocks_in_market)
                # 最初の3銘柄のみ表示
                for s in stocks_in_market[:3]:
                    print(f"    - {s['code']} {s['name']}")
                if len(stocks_in_market) > 3:
                    print(f"    ... 他{len(stocks_in_market)-3}銘柄")
        print(f"  合計: {total_in_range}銘柄")
