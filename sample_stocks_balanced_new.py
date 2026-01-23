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
        3. 銘柄数の比率に基づいて抽出数を決定（合計max_per_range銘柄）
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
        
        # 各市場から抽出する銘柄数を計算
        market_samples = {}
        remaining = target_count
        
        # 比率に基づいて抽出数を計算
        for market, count in sorted(market_counts.items()):
            if remaining <= 0:
                break
            
            # 比率を計算（小数点以下切り捨て）
            ratio = count / total_in_range
            sample_count = int(ratio * target_count)
            
            # 最低1銘柄は抽出（銘柄が存在する場合）
            if sample_count == 0 and count > 0 and remaining > 0:
                sample_count = 1
            
            # 実際の銘柄数を超えないように調整
            sample_count = min(sample_count, count, remaining)
            
            market_samples[market] = sample_count
            remaining -= sample_count
        
        # 残りがある場合は、最も銘柄数が多い市場に割り当て
        if remaining > 0:
            max_market = max(market_counts, key=market_counts.get)
            market_samples[max_market] = min(
                market_samples.get(max_market, 0) + remaining,
                market_counts[max_market]
            )
        
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
    for i in range(40):
        test_stocks.append({'code': f'1{i:03d}', 'name': f'プライム{i}', 'market': 'プライム', 'price': 1000})
    for i in range(30):
        test_stocks.append({'code': f'1{i+100:03d}', 'name': f'スタンダード{i}', 'market': 'スタンダード', 'price': 1000})
    for i in range(10):
        test_stocks.append({'code': f'1{i+200:03d}', 'name': f'グロース{i}', 'market': 'グロース', 'price': 1000})
    
    # 2000番台: プライム50, スタンダード40, グロース20（合計110銘柄）
    for i in range(50):
        test_stocks.append({'code': f'2{i:03d}', 'name': f'プライム{i}', 'market': 'プライム', 'price': 2000})
    for i in range(40):
        test_stocks.append({'code': f'2{i+100:03d}', 'name': f'スタンダード{i}', 'market': 'スタンダード', 'price': 2000})
    for i in range(20):
        test_stocks.append({'code': f'2{i+200:03d}', 'name': f'グロース{i}', 'market': 'グロース', 'price': 2000})
    
    print("=" * 60)
    print("テストデータ:")
    print(f"  1000番台: プライム40, スタンダード30, グロース10（合計80銘柄）")
    print(f"  2000番台: プライム50, スタンダード40, グロース20（合計110銘柄）")
    print(f"  総計: {len(test_stocks)}銘柄")
    print("=" * 60)
    
    # サンプリング実行
    sampled = sample_stocks_balanced(test_stocks, max_per_range=10)
    
    print("\n" + "=" * 60)
    print("サンプリング結果:")
    print("=" * 60)
    
    # 帯別・市場別に集計
    for range_key in ['1000', '2000']:
        print(f"\n{range_key}番台:")
        for market in ['プライム', 'スタンダード', 'グロース']:
            stocks_in_market = [s for s in sampled if s['code'].startswith(range_key[0]) and s['market'] == market]
            if stocks_in_market:
                print(f"  {market}: {len(stocks_in_market)}銘柄")
                for s in stocks_in_market:
                    print(f"    - {s['code']} {s['name']}")
