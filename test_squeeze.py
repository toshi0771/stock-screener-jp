#!/usr/bin/env python3
"""スクイーズ条件のデバッグテスト"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
import pandas as pd
import sys
import os

# パスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daily_data_collection import AsyncJQuantsClient

async def test_squeeze():
    client = AsyncJQuantsClient()
    
    async with aiohttp.ClientSession() as session:
        # テスト銘柄（トヨタ）
        code = '7203'
        end_date = datetime.now()
        start_date = end_date - timedelta(days=150)
        
        df = await client.get_prices_daily_quotes(
            session, code,
            start_date.strftime('%Y%m%d'),
            end_date.strftime('%Y%m%d')
        )
        
        if df is None:
            print('データ取得失敗')
            return
        
        print(f'取得データ: {len(df)}行')
        print(f'日付範囲: {df.iloc[0]["Date"]} - {df.iloc[-1]["Date"]}')
        
        # 最新100日分
        df = df.tail(100)
        
        prices = df['Close']
        high = df['High']
        low = df['Low']
        
        # BBW計算
        sma20 = prices.rolling(window=20).mean()
        std20 = prices.rolling(window=20).std()
        upper = sma20 + (std20 * 2)
        lower = sma20 - (std20 * 2)
        bbw = (upper - lower) / sma20 * 100
        
        # 50EMA
        ema50 = prices.ewm(span=50, adjust=False).mean()
        
        # 乖離率
        deviation = abs(prices - ema50) / ema50 * 100
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - prices.shift(1))
        tr3 = abs(low - prices.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=14, adjust=False).mean()
        
        # 最新値
        current_bbw = bbw.iloc[-1]
        current_deviation = deviation.iloc[-1]
        current_atr = atr.iloc[-1]
        
        # 過去60日の最小値
        bbw_min_60d = bbw.iloc[-60:].min()
        atr_min_60d = atr.iloc[-60:].min()
        
        print(f'\n=== スクイーズ条件チェック (7203 トヨタ) ===')
        print(f'現在BBW: {current_bbw:.4f}')
        print(f'過去60日BBW最小: {bbw_min_60d:.4f}')
        print(f'BBW比率: {current_bbw / bbw_min_60d:.4f} (閾値: 1.3)')
        print(f'BBW条件: {current_bbw <= bbw_min_60d * 1.3}')
        print()
        print(f'現在乖離率: {current_deviation:.4f}% (閾値: 5.0%)')
        print(f'乖離率条件: {current_deviation <= 5.0}')
        print()
        print(f'現在ATR: {current_atr:.4f}')
        print(f'過去60日ATR最小: {atr_min_60d:.4f}')
        print(f'ATR比率: {current_atr / atr_min_60d:.4f} (閾値: 1.3)')
        print(f'ATR条件: {current_atr <= atr_min_60d * 1.3}')
        
        # 全条件
        all_conditions = (
            current_bbw <= bbw_min_60d * 1.3 and
            current_deviation <= 5.0 and
            current_atr <= atr_min_60d * 1.3
        )
        print(f'\n全条件: {all_conditions}')

if __name__ == "__main__":
    asyncio.run(test_squeeze())
