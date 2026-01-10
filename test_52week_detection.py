#!/usr/bin/env python3
"""
200日新高値押し目検出のテストスクリプト
養命酒（2540）、旭硝子（5201）、東洋製罐（5901）で動作確認
"""

import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
import os
import sys

# 環境変数を設定（テスト用）
os.environ['JQUANTS_REFRESH_TOKEN'] = os.getenv('JQUANTS_REFRESH_TOKEN', '')
os.environ['SUPABASE_URL'] = os.getenv('SUPABASE_URL', '')
os.environ['SUPABASE_ANON_KEY'] = os.getenv('SUPABASE_ANON_KEY', '')

# daily_data_collection.pyから必要なクラスをインポート
sys.path.insert(0, '/home/ubuntu/stock-screener-jp')
from daily_data_collection import AsyncJQuantsClient, ParallelStockScreener


async def test_52week_detection():
    """200日新高値押し目検出のテスト"""
    
    # テスト対象銘柄
    test_stocks = [
        {"Code": "25400", "CompanyName": "養命酒製造", "MarketCode": "0111"},
        {"Code": "52010", "CompanyName": "旭硝子", "MarketCode": "0111"},
        {"Code": "59010", "CompanyName": "東洋製罐グループホールディングス", "MarketCode": "0111"}
    ]
    
    screener = ParallelStockScreener()
    
    async with aiohttp.ClientSession() as session:
        # 認証
        auth_result = await screener.jq_client.authenticate(session)
        if not auth_result:
            print("❌ 認証失敗")
            return
        
        print("✅ jQuants API認証成功")
        print("=" * 60)
        
        # 各銘柄をテスト
        for stock in test_stocks:
            print(f"\n🔍 テスト銘柄: {stock['CompanyName']} ({stock['Code']})")
            print("-" * 60)
            
            result = await screener.screen_stock_52week_pullback(stock, session)
            
            if result:
                print("✅ 検出成功！")
                print(f"  - 銘柄名: {result['name']}")
                print(f"  - 現在株価: {result['price']:,.0f}円")
                print(f"  - 52週高値: {result['high_52week']:,.0f}円")
                print(f"  - 押し目率: {result['pullback_pct']}%")
                print(f"  - タッチEMA: {result['touched_emas']}")
                print(f"  - EMA10: {result['ema_10']:,.0f}円")
                print(f"  - EMA20: {result['ema_20']:,.0f}円")
                print(f"  - EMA50: {result['ema_50']:,.0f}円")
                if result.get('stochastic_k'):
                    print(f"  - ストキャス%K: {result['stochastic_k']}")
            else:
                print("❌ 検出されませんでした")
                
                # デバッグ情報を取得
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                
                df = await screener.jq_client.get_prices_daily_quotes(
                    session, stock['Code'],
                    start_date.strftime("%Y%m%d"),
                    end_date.strftime("%Y%m%d")
                )
                
                if df is not None and len(df) >= 260:
                    # EMA計算
                    df['EMA10'] = screener.calculate_ema(df['Close'], 10)
                    df['EMA20'] = screener.calculate_ema(df['Close'], 20)
                    df['EMA50'] = screener.calculate_ema(df['Close'], 50)
                    
                    # 52週最高値
                    high_52w = df['High'].tail(260).max()
                    latest = df.iloc[-1]
                    
                    print(f"  📊 デバッグ情報:")
                    print(f"  - 始値: {latest['Open']:,.0f}円")
                    print(f"  - 高値: {latest['High']:,.0f}円")
                    print(f"  - 安値: {latest['Low']:,.0f}円")
                    print(f"  - 終値: {latest['Close']:,.0f}円")
                    print(f"  - 52週高値: {high_52w:,.0f}円")
                    print(f"  - EMA10: {latest['EMA10']:,.0f}円")
                    print(f"  - EMA20: {latest['EMA20']:,.0f}円")
                    print(f"  - EMA50: {latest['EMA50']:,.0f}円")
                    
                    # 押し目率
                    pullback_pct = ((high_52w - latest['Close']) / high_52w) * 100
                    print(f"  - 押し目率: {pullback_pct:.2f}%")
                    
                    # EMAタッチ判定
                    low = latest['Low']
                    high = latest['High']
                    touched = []
                    
                    if low <= latest['EMA10'] <= high:
                        touched.append("10EMA")
                    if low <= latest['EMA20'] <= high:
                        touched.append("20EMA")
                    if low <= latest['EMA50'] <= high:
                        touched.append("50EMA")
                    
                    print(f"  - タッチEMA: {','.join(touched) if touched else 'なし'}")
                    
                    if pullback_pct > 30:
                        print(f"  ⚠️ 押し目率が30%を超えています")
                    if not touched:
                        print(f"  ⚠️ EMAにタッチしていません")
        
        print("\n" + "=" * 60)
        print("テスト完了")


if __name__ == "__main__":
    asyncio.run(test_52week_detection())
