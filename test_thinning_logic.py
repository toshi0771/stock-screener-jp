#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
間引きロジックの単体テスト
"""

import sys
sys.path.insert(0, '/home/ubuntu/stock-screener-jp')

from daily_data_collection import sample_stocks_balanced

def test_thinning_logic():
    """間引きロジックのテスト"""
    
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
    
    # 検証
    print("\n" + "=" * 60)
    print("検証結果:")
    print("=" * 60)
    
    # 各帯が10銘柄以下か確認
    for range_key in ['1000', '2000', '3000']:
        stocks_in_range = [s for s in sampled if s['code'].startswith(range_key[0])]
        status = "✅" if len(stocks_in_range) <= 10 else "❌"
        print(f"{status} {range_key}番台: {len(stocks_in_range)}銘柄（最大10銘柄）")
    
    # ランダム性の確認（銘柄コード順ではないか）
    print("\n銘柄コード順ではないか確認:")
    for range_key in ['1000', '2000', '3000']:
        stocks_in_range = [s for s in sampled if s['code'].startswith(range_key[0])]
        codes = [s['code'] for s in stocks_in_range]
        is_sorted = codes == sorted(codes)
        status = "❌ ランダム" if not is_sorted else "⚠️ ソート済み"
        print(f"{status} {range_key}番台: {codes[:5]}...")
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    test_thinning_logic()
