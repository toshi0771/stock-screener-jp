#!/usr/bin/env python3
"""
ファナック（6954）の12月1日データを取得して、EMAタッチ判定を検証
"""

import os
import sys
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta

# 環境変数（テスト用）
JQUANTS_REFRESH_TOKEN = os.getenv('JQUANTS_REFRESH_TOKEN')

class AsyncJQuantsClient:
    def __init__(self):
        self.base_url = "https://api.jquants.com/v1"
        self.refresh_token = JQUANTS_REFRESH_TOKEN
        self.id_token = None
    
    async def authenticate(self, session):
        """Refresh TokenからID Tokenを取得"""
        url = f"{self.base_url}/token/auth_refresh"
        params = {"refreshtoken": self.refresh_token}
        
        async with session.post(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                self.id_token = data["idToken"]
                print(f"✅ jQuants API認証成功")
                return True
            else:
                print(f"❌ jQuants API認証失敗: {response.status}")
                return False
    
    async def get_stock_prices(self, session, code, from_date, to_date):
        """株価データを取得"""
        if not self.id_token:
            await self.authenticate(session)
        
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
                return data.get("daily_quotes", [])
            else:
                print(f"❌ 株価データ取得失敗: {response.status}")
                return []

def calculate_ema(series, period):
    """EMAを計算"""
    return series.ewm(span=period, adjust=False).mean()

async def test_fanuc_detection():
    """ファナック（6954）の検出ロジックをテスト"""
    
    print("=" * 80)
    print("ファナック（6954）12月1日データ検証")
    print("=" * 80)
    
    # 日付設定
    target_date = "2025-12-01"
    from_date = "2024-12-01"  # 過去1年分のデータ
    to_date = "2025-12-01"
    
    client = AsyncJQuantsClient()
    
    async with aiohttp.ClientSession() as session:
        # データ取得
        print(f"\n📊 データ取得中: {from_date} ~ {to_date}")
        quotes = await client.get_stock_prices(session, "69540", from_date, to_date)
        
        if not quotes:
            print("❌ データ取得失敗")
            return
        
        print(f"✅ {len(quotes)}日分のデータを取得")
        
        # DataFrameに変換
        df = pd.DataFrame(quotes)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        # 数値型に変換
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # EMA計算
        df['EMA10'] = calculate_ema(df['Close'], 10)
        df['EMA20'] = calculate_ema(df['Close'], 20)
        df['EMA50'] = calculate_ema(df['Close'], 50)
        
        # 12月1日のデータを取得
        target_data = df[df['Date'] == target_date]
        
        if target_data.empty:
            print(f"\n❌ {target_date}のデータが見つかりません")
            return
        
        latest = target_data.iloc[-1]
        
        print(f"\n{'='*80}")
        print(f"📅 日付: {latest['Date'].strftime('%Y-%m-%d')}")
        print(f"{'='*80}")
        
        print(f"\n【4本値】")
        print(f"  始値: {latest['Open']:.2f}円")
        print(f"  高値: {latest['High']:.2f}円")
        print(f"  安値: {latest['Low']:.2f}円")
        print(f"  終値: {latest['Close']:.2f}円")
        
        print(f"\n【EMA】")
        print(f"  EMA10: {latest['EMA10']:.2f}円")
        print(f"  EMA20: {latest['EMA20']:.2f}円")
        print(f"  EMA50: {latest['EMA50']:.2f}円")
        
        # タッチ判定
        print(f"\n【タッチ判定】")
        touched_emas = []
        
        low_price = latest['Low']
        high_price = latest['High']
        
        print(f"  ローソク足の範囲: {low_price:.2f}円 ~ {high_price:.2f}円")
        print()
        
        # EMA10判定
        if low_price <= latest['EMA10'] <= high_price:
            touched_emas.append("10EMA")
            print(f"  ✅ EMA10タッチ: {low_price:.2f} <= {latest['EMA10']:.2f} <= {high_price:.2f}")
        else:
            print(f"  ❌ EMA10タッチなし: {low_price:.2f} <= {latest['EMA10']:.2f} <= {high_price:.2f}")
            if latest['EMA10'] < low_price:
                print(f"     → EMA10が安値より下（差: {low_price - latest['EMA10']:.2f}円）")
            else:
                print(f"     → EMA10が高値より上（差: {latest['EMA10'] - high_price:.2f}円）")
        
        # EMA20判定
        if low_price <= latest['EMA20'] <= high_price:
            touched_emas.append("20EMA")
            print(f"  ✅ EMA20タッチ: {low_price:.2f} <= {latest['EMA20']:.2f} <= {high_price:.2f}")
        else:
            print(f"  ❌ EMA20タッチなし: {low_price:.2f} <= {latest['EMA20']:.2f} <= {high_price:.2f}")
            if latest['EMA20'] < low_price:
                print(f"     → EMA20が安値より下（差: {low_price - latest['EMA20']:.2f}円）")
            else:
                print(f"     → EMA20が高値より上（差: {latest['EMA20'] - high_price:.2f}円）")
        
        # EMA50判定
        if low_price <= latest['EMA50'] <= high_price:
            touched_emas.append("50EMA")
            print(f"  ✅ EMA50タッチ: {low_price:.2f} <= {latest['EMA50']:.2f} <= {high_price:.2f}")
        else:
            print(f"  ❌ EMA50タッチなし: {low_price:.2f} <= {latest['EMA50']:.2f} <= {high_price:.2f}")
            if latest['EMA50'] < low_price:
                print(f"     → EMA50が安値より下（差: {low_price - latest['EMA50']:.2f}円）")
            else:
                print(f"     → EMA50が高値より上（差: {latest['EMA50'] - high_price:.2f}円）")
        
        # 52週高値チェック
        print(f"\n【52週高値チェック】")
        high_52w = df['High'].tail(260).max()
        current_price = latest['Close']
        pullback_pct = ((high_52w - current_price) / high_52w) * 100
        
        print(f"  52週最高値: {high_52w:.2f}円")
        print(f"  現在株価: {current_price:.2f}円")
        print(f"  下落率: {pullback_pct:.2f}%")
        
        if pullback_pct > 30:
            print(f"  ❌ 52週高値から30%以上下落（検出対象外）")
        else:
            print(f"  ✅ 52週高値から30%以内（検出対象）")
        
        # 最終判定
        print(f"\n{'='*80}")
        print(f"【最終判定】")
        print(f"{'='*80}")
        
        if touched_emas:
            print(f"✅ タッチしたEMA: {', '.join(touched_emas)}")
            if pullback_pct <= 30:
                print(f"✅ 52週新高値押し目として検出されるべき")
            else:
                print(f"❌ 52週高値から30%以上下落のため検出されない")
        else:
            print(f"❌ どのEMAにもタッチしていない")
            print(f"❌ 52週新高値押し目として検出されない")
        
        print(f"{'='*80}\n")

if __name__ == "__main__":
    if not JQUANTS_REFRESH_TOKEN:
        print("❌ 環境変数 JQUANTS_REFRESH_TOKEN が設定されていません")
        sys.exit(1)
    
    asyncio.run(test_fanuc_detection())
