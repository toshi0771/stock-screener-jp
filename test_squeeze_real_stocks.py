#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実際の銘柄データでスクイーズ検出をテスト
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# プロジェクトのパスを追加
sys.path.insert(0, '/home/ubuntu/stock-screener-jp')

from squeeze_detection import detect_squeeze, calculate_bbw, calculate_deviation_from_ema, calculate_atr

# 環境変数から認証情報を取得
JQUANTS_REFRESH_TOKEN = os.getenv('JQUANTS_REFRESH_TOKEN')

if not JQUANTS_REFRESH_TOKEN:
    print("❌ JQUANTS_REFRESH_TOKEN が設定されていません")
    sys.exit(1)

# jquantsライブラリをインポート
try:
    import jquantsapi
except ImportError:
    print("❌ jquantsapi がインストールされていません")
    print("   pip3 install jquantsapi")
    sys.exit(1)


def get_stock_data(code: str, days: int = 100) -> dict:
    """
    jQuants APIから株価データを取得
    
    Args:
        code: 銘柄コード（4桁）
        days: 取得する日数
    
    Returns:
        株価データの辞書
    """
    try:
        # jQuants APIクライアントを初期化
        cli = jquantsapi.Client(refresh_token=JQUANTS_REFRESH_TOKEN)
        
        # 日付範囲を計算
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 50)  # 余裕を持って取得
        
        # 株価データを取得
        df = cli.get_price_range(
            start_dt=start_date.strftime('%Y%m%d'),
            end_dt=end_date.strftime('%Y%m%d'),
            code=code
        )
        
        if df is None or df.empty:
            print(f"❌ {code}: データが取得できませんでした")
            return None
        
        # 日付でソート
        df = df.sort_values('Date')
        
        # 最新のdays日分を取得
        df = df.tail(days)
        
        if len(df) < days:
            print(f"⚠️ {code}: データが不足しています（{len(df)}日分）")
        
        return {
            'code': code,
            'name': df['CompanyName'].iloc[-1] if 'CompanyName' in df.columns else code,
            'market': df['MarketCode'].iloc[-1] if 'MarketCode' in df.columns else 'Unknown',
            'prices': df['Close'].values,
            'high': df['High'].values,
            'low': df['Low'].values,
            'dates': df['Date'].values
        }
    
    except Exception as e:
        print(f"❌ {code}: エラーが発生しました: {e}")
        return None


def test_squeeze_detection():
    """実際の銘柄データでスクイーズ検出をテスト"""
    
    # テスト対象の銘柄
    test_stocks = [
        '3512',  # 日本フエルト
        '3513',  # イチカワ
        '4784',  # GMOインターネット
        # トリニティ工業の銘柄コードを追加（不明な場合はスキップ）
    ]
    
    print("=" * 80)
    print("実際の銘柄データでスクイーズ検出をテスト")
    print("=" * 80)
    
    for code in test_stocks:
        print(f"\n{'=' * 80}")
        print(f"銘柄: {code}")
        print("=" * 80)
        
        # 株価データを取得
        stock_data = get_stock_data(code, days=100)
        
        if not stock_data:
            continue
        
        # Seriesに変換
        prices = pd.Series(stock_data['prices'])
        high = pd.Series(stock_data['high'])
        low = pd.Series(stock_data['low'])
        
        print(f"銘柄名: {stock_data['name']}")
        print(f"市場: {stock_data['market']}")
        print(f"データ期間: {len(prices)}日")
        print(f"最新終値: {prices.iloc[-1]:.2f}円")
        
        # スクイーズ検出（複数のパラメータでテスト）
        print("\n" + "-" * 80)
        print("スクイーズ検出結果:")
        print("-" * 80)
        
        # パターン1: 標準（5日間以上）
        result1 = detect_squeeze(
            prices, high, low,
            min_duration=5,
            bbw_threshold=1.3,
            deviation_threshold=5.0
        )
        
        # パターン2: 厳しい（7日間以上）
        result2 = detect_squeeze(
            prices, high, low,
            min_duration=7,
            bbw_threshold=1.2,
            deviation_threshold=3.0
        )
        
        # パターン3: 緩い（3日間以上）
        result3 = detect_squeeze(
            prices, high, low,
            min_duration=3,
            bbw_threshold=1.5,
            deviation_threshold=7.0
        )
        
        # 結果を表示
        print("\n【パターン1: 標準（5日間以上、BBW×1.3、乖離率5%）】")
        if result1:
            print("  ✅ 検出されました")
            print(f"    BBW: {result1['current_bbw']:.2f}% (最小値: {result1['bbw_min_60d']:.2f}%, 比率: {result1['bbw_ratio']:.2f}倍)")
            print(f"    乖離率: {result1['deviation_from_ema']:.2f}%")
            print(f"    ATR: {result1['current_atr']:.2f} (最小値: {result1['atr_min_60d']:.2f}, 比率: {result1['atr_ratio']:.2f}倍)")
            print(f"    継続日数: {result1['duration_days']}日")
        else:
            print("  ❌ 検出されませんでした")
        
        print("\n【パターン2: 厳しい（7日間以上、BBW×1.2、乖離率3%）】")
        if result2:
            print("  ✅ 検出されました")
            print(f"    継続日数: {result2['duration_days']}日")
        else:
            print("  ❌ 検出されませんでした")
        
        print("\n【パターン3: 緩い（3日間以上、BBW×1.5、乖離率7%）】")
        if result3:
            print("  ✅ 検出されました")
            print(f"    継続日数: {result3['duration_days']}日")
        else:
            print("  ❌ 検出されませんでした")
        
        # 各指標の推移を表示
        print("\n" + "-" * 80)
        print("指標の推移:")
        print("-" * 80)
        
        bbw = calculate_bbw(prices)
        deviation = calculate_deviation_from_ema(prices)
        atr = calculate_atr(high, low, prices)
        
        print(f"BBW:")
        print(f"  最新: {bbw.iloc[-1]:.2f}%")
        print(f"  5日前: {bbw.iloc[-6]:.2f}%")
        print(f"  10日前: {bbw.iloc[-11]:.2f}%")
        print(f"  過去60日最小値: {bbw.iloc[-60:].min():.2f}%")
        print(f"  過去60日最大値: {bbw.iloc[-60:].max():.2f}%")
        
        print(f"\n乖離率:")
        print(f"  最新: {deviation.iloc[-1]:.2f}%")
        print(f"  5日前: {deviation.iloc[-6]:.2f}%")
        print(f"  10日前: {deviation.iloc[-11]:.2f}%")
        
        print(f"\nATR:")
        print(f"  最新: {atr.iloc[-1]:.2f}")
        print(f"  5日前: {atr.iloc[-6]:.2f}")
        print(f"  10日前: {atr.iloc[-11]:.2f}")
        print(f"  過去60日最小値: {atr.iloc[-60:].min():.2f}")
        print(f"  過去60日最大値: {atr.iloc[-60:].max():.2f}")
    
    print("\n" + "=" * 80)
    print("テスト完了")
    print("=" * 80)


if __name__ == "__main__":
    test_squeeze_detection()
