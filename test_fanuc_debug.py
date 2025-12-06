#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ファナック（6954）の52週高値押し目検出デバッグスクリプト
"""

import os
import asyncio
from datetime import datetime, timedelta
import aiohttp
import pandas as pd

# 環境変数から取得
JQUANTS_REFRESH_TOKEN = os.getenv('JQUANTS_REFRESH_TOKEN')

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
            
            print("🔐 jQuants API認証中...")
            
            async with session.post(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    self.id_token = data["idToken"]
                    print("✅ 認証成功")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ 認証失敗 [{response.status}]: {error_text}")
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
            
            print(f"📊 株価データ取得中: {code} ({from_date} - {to_date})")
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "daily_quotes" in data and data["daily_quotes"]:
                        df = pd.DataFrame(data["daily_quotes"])
                        print(f"✅ データ取得成功: {len(df)}件")
                        return df
                    else:
                        print(f"⚠️ データが空です")
                        return None
                else:
                    error_text = await response.text()
                    print(f"❌ データ取得失敗 [{response.status}]: {error_text}")
                    return None
                    
        except Exception as e:
            print(f"❌ データ取得エラー: {e}")
            return None


def calculate_ema(series, period):
    """EMAを計算"""
    return series.ewm(span=period, adjust=False).mean()


async def test_fanuc_detection():
    """ファナック（6954）の検出テスト"""
    
    print("="*60)
    print("ファナック（6954）52週高値押し目検出テスト")
    print("="*60)
    
    client = JQuantsClient()
    
    async with aiohttp.ClientSession() as session:
        # 認証
        if not await client.authenticate(session):
            print("❌ 認証に失敗しました")
            return
        
        # データ取得期間
        end_date = datetime(2025, 12, 1)  # 12月1日
        start_date = end_date - timedelta(days=365)  # 1年前
        
        # 株価データ取得
        df = await client.get_prices_daily_quotes(
            session,
            "69540",  # ファナック
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d")
        )
        
        if df is None or len(df) == 0:
            print("❌ データが取得できませんでした")
            return
        
        print(f"\n📈 取得データ: {len(df)}日分")
        print(f"期間: {df['Date'].min()} - {df['Date'].max()}")
        
        # EMA計算
        print("\n🔢 EMA計算中...")
        df['EMA10'] = calculate_ema(df['Close'], 10)
        df['EMA20'] = calculate_ema(df['Close'], 20)
        df['EMA50'] = calculate_ema(df['Close'], 50)
        
        # 52週最高値
        high_52w = df['High'].tail(260).max()
        
        # 12月1日のデータを取得
        target_date = "2025-12-01"
        target_data = df[df['Date'] == target_date]
        
        if len(target_data) == 0:
            print(f"\n❌ {target_date}のデータが見つかりません")
            print(f"最新のデータ: {df['Date'].max()}")
            print("\n利用可能な最新5日間のデータ:")
            print(df[['Date', 'Open', 'High', 'Low', 'Close']].tail(5))
            return
        
        latest = target_data.iloc[0]
        
        print(f"\n{'='*60}")
        print(f"🔍 ファナック（6954）- {target_date}")
        print(f"{'='*60}")
        print(f"\n4本値:")
        print(f"  始値: {latest['Open']:,.0f}円")
        print(f"  高値: {latest['High']:,.0f}円")
        print(f"  安値: {latest['Low']:,.0f}円")
        print(f"  終値: {latest['Close']:,.0f}円")
        
        print(f"\nEMA:")
        print(f"  EMA10: {latest['EMA10']:,.2f}円")
        print(f"  EMA20: {latest['EMA20']:,.2f}円")
        print(f"  EMA50: {latest['EMA50']:,.2f}円")
        
        print(f"\n52週高値: {high_52w:,.0f}円")
        
        # 下落率計算
        current_price = latest['Close']
        pullback_pct = ((high_52w - current_price) / high_52w) * 100
        print(f"下落率: {pullback_pct:.2f}%")
        
        # 条件チェック
        print(f"\n条件チェック:")
        print(f"  下落率30%以内: {pullback_pct <= 30} ({'✅' if pullback_pct <= 30 else '❌'})")
        
        # タッチ判定
        open_price = latest['Open']
        high_price = latest['High']
        low_price = latest['Low']
        close_price = latest['Close']
        
        print(f"\nタッチ判定:")
        
        ema10_touch = low_price <= latest['EMA10'] <= high_price
        print(f"  EMA10タッチ: {low_price:,.0f} <= {latest['EMA10']:,.2f} <= {high_price:,.0f}")
        print(f"    → {ema10_touch} ({'✅' if ema10_touch else '❌'})")
        
        ema20_touch = low_price <= latest['EMA20'] <= high_price
        print(f"  EMA20タッチ: {low_price:,.0f} <= {latest['EMA20']:,.2f} <= {high_price:,.0f}")
        print(f"    → {ema20_touch} ({'✅' if ema20_touch else '❌'})")
        
        ema50_touch = low_price <= latest['EMA50'] <= high_price
        print(f"  EMA50タッチ: {low_price:,.0f} <= {latest['EMA50']:,.2f} <= {high_price:,.0f}")
        print(f"    → {ema50_touch} ({'✅' if ema50_touch else '❌'})")
        
        touched_emas = []
        if ema10_touch:
            touched_emas.append("10EMA")
        if ema20_touch:
            touched_emas.append("20EMA")
        if ema50_touch:
            touched_emas.append("50EMA")
        
        print(f"\nタッチしたEMA: {', '.join(touched_emas) if touched_emas else 'なし'}")
        
        # 最終判定
        print(f"\n{'='*60}")
        if pullback_pct <= 30 and touched_emas:
            print("✅ 検出条件を満たしています！")
        else:
            print("❌ 検出条件を満たしていません")
            if pullback_pct > 30:
                print(f"  理由: 下落率が30%を超えています ({pullback_pct:.2f}%)")
            if not touched_emas:
                print(f"  理由: EMAにタッチしていません")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(test_fanuc_detection())
