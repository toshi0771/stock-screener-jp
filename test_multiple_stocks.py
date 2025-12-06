#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
複数銘柄の52週高値押し目検出デバッグスクリプト
"""

import os
import asyncio
from datetime import datetime, timedelta
import aiohttp
import pandas as pd

# 環境変数から取得
JQUANTS_REFRESH_TOKEN = os.getenv('JQUANTS_REFRESH_TOKEN')

# テスト対象銘柄
TEST_STOCKS = [
    {"code": "69540", "name": "ファナック", "expected_ema": "20EMA"},
    {"code": "19420", "name": "神田通信機", "expected_ema": "20EMA"},
    {"code": "63010", "name": "コマツ", "expected_ema": "50EMA"},
    {"code": "19640", "name": "中外炉工業", "expected_ema": "10EMA/20EMA"},
    {"code": "63310", "name": "三菱化工機", "expected_ema": "10EMA"},
    {"code": "41860", "name": "東京応化工業", "expected_ema": "10EMA"},
]

class JQuantsClient:
    def __init__(self):
        self.refresh_token = JQUANTS_REFRESH_TOKEN
        self.id_token = None
        self.base_url = "https://api.jquants.com/v1"
    
    async def authenticate(self, session):
        """認証"""
        try:
            url = f"{self.base_url}/token/auth_refresh"
            params = {"refreshtoken": self.refresh_token}
            
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.id_token = data["idToken"]
                    return True
                else:
                    return False
        except Exception as e:
            print(f"❌ 認証エラー: {e}")
            return False
    
    async def get_prices_daily_quotes(self, session, code, from_date, to_date):
        """日次株価データを取得"""
        if not self.id_token:
            await self.authenticate(session)
        
        try:
            url = f"{self.base_url}/prices/daily_quotes"
            headers = {"Authorization": f"Bearer {self.id_token}"}
            params = {
                "code": code,
                "from": from_date,
                "to": to_date
            }
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "daily_quotes" in data and data["daily_quotes"]:
                        df = pd.DataFrame(data["daily_quotes"])
                        return df
                    else:
                        return None
                else:
                    return None
                    
        except Exception as e:
            return None


def calculate_ema(series, period):
    """EMAを計算"""
    return series.ewm(span=period, adjust=False).mean()


async def test_stock(client, session, stock_info):
    """単一銘柄のテスト"""
    
    code = stock_info["code"]
    name = stock_info["name"]
    expected_ema = stock_info["expected_ema"]
    
    print(f"\n{'='*60}")
    print(f"🔍 {name}（{code[:4]}）- 期待: {expected_ema}タッチ")
    print(f"{'='*60}")
    
    # データ取得期間
    end_date = datetime(2025, 12, 1)  # 12月1日
    start_date = end_date - timedelta(days=365)  # 1年前
    
    # 株価データ取得
    df = await client.get_prices_daily_quotes(
        session,
        code,
        start_date.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d")
    )
    
    if df is None or len(df) == 0:
        print("❌ データが取得できませんでした")
        return None
    
    # EMA計算
    df['EMA10'] = calculate_ema(df['Close'], 10)
    df['EMA20'] = calculate_ema(df['Close'], 20)
    df['EMA50'] = calculate_ema(df['Close'], 50)
    
    # 52週最高値
    high_52w = df['High'].tail(260).max()
    
    # 12月1日のデータを取得
    target_date = "2025-12-01"
    target_data = df[df['Date'] == target_date]
    
    if len(target_data) == 0:
        print(f"❌ {target_date}のデータが見つかりません")
        print(f"最新のデータ: {df['Date'].max()}")
        return None
    
    latest = target_data.iloc[0]
    
    print(f"\n4本値:")
    print(f"  始値: {latest['Open']:,.0f}円")
    print(f"  高値: {latest['High']:,.0f}円")
    print(f"  安値: {latest['Low']:,.0f}円")
    print(f"  終値: {latest['Close']:,.0f}円")
    
    print(f"\nEMA:")
    print(f"  EMA10: {latest['EMA10']:,.2f}円")
    print(f"  EMA20: {latest['EMA20']:,.2f}円")
    print(f"  EMA50: {latest['EMA50']:,.2f}円")
    
    # 下落率計算
    current_price = latest['Close']
    pullback_pct = ((high_52w - current_price) / high_52w) * 100
    print(f"\n52週高値: {high_52w:,.0f}円")
    print(f"下落率: {pullback_pct:.2f}%")
    
    # タッチ判定
    low_price = latest['Low']
    high_price = latest['High']
    
    print(f"\nタッチ判定:")
    
    ema10_touch = low_price <= latest['EMA10'] <= high_price
    print(f"  EMA10: {low_price:,.0f} <= {latest['EMA10']:,.2f} <= {high_price:,.0f} → {'✅' if ema10_touch else '❌'}")
    
    ema20_touch = low_price <= latest['EMA20'] <= high_price
    print(f"  EMA20: {low_price:,.0f} <= {latest['EMA20']:,.2f} <= {high_price:,.0f} → {'✅' if ema20_touch else '❌'}")
    
    ema50_touch = low_price <= latest['EMA50'] <= high_price
    print(f"  EMA50: {low_price:,.0f} <= {latest['EMA50']:,.2f} <= {high_price:,.0f} → {'✅' if ema50_touch else '❌'}")
    
    touched_emas = []
    if ema10_touch:
        touched_emas.append("10EMA")
    if ema20_touch:
        touched_emas.append("20EMA")
    if ema50_touch:
        touched_emas.append("50EMA")
    
    print(f"\nタッチしたEMA: {', '.join(touched_emas) if touched_emas else 'なし'}")
    
    # 最終判定
    if pullback_pct <= 30 and touched_emas:
        print(f"✅ 検出条件を満たしています！")
        return True
    else:
        print(f"❌ 検出条件を満たしていません")
        if pullback_pct > 30:
            print(f"  理由: 下落率が30%を超えています ({pullback_pct:.2f}%)")
        if not touched_emas:
            print(f"  理由: EMAにタッチしていません")
        return False


async def test_all_stocks():
    """全銘柄のテスト"""
    
    print("="*60)
    print("複数銘柄の52週高値押し目検出テスト")
    print("="*60)
    
    client = JQuantsClient()
    
    async with aiohttp.ClientSession() as session:
        # 認証
        print("🔐 jQuants API認証中...")
        if not await client.authenticate(session):
            print("❌ 認証に失敗しました")
            return
        print("✅ 認証成功\n")
        
        # 各銘柄をテスト
        results = []
        for stock_info in TEST_STOCKS:
            result = await test_stock(client, session, stock_info)
            results.append({
                "name": stock_info["name"],
                "code": stock_info["code"][:4],
                "expected": stock_info["expected_ema"],
                "detected": result
            })
            await asyncio.sleep(0.5)  # API制限対策
        
        # サマリー
        print(f"\n{'='*60}")
        print("テスト結果サマリー")
        print(f"{'='*60}")
        
        detected_count = sum(1 for r in results if r["detected"])
        
        for r in results:
            status = "✅ 検出" if r["detected"] else "❌ 未検出"
            print(f"{r['name']}（{r['code']}）: {status} (期待: {r['expected']})")
        
        print(f"\n検出数: {detected_count}/{len(results)}銘柄")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(test_all_stocks())
