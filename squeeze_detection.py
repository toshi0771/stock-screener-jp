#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
価格収縮（スクイーズ）検出ロジック
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
    """
    ボリンジャーバンドを計算
    
    Args:
        prices: 終値のSeries
        period: 期間（デフォルト: 20日）
        std_dev: 標準偏差の倍数（デフォルト: 2.0）
    
    Returns:
        upper: 上部バンド
        middle: 中央線（SMA）
        lower: 下部バンド
    """
    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower
    }


def calculate_bbw(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """
    ボリンジャーバンド幅（BBW: Bollinger Band Width）を計算
    
    Args:
        prices: 終値のSeries
        period: 期間（デフォルト: 20日）
        std_dev: 標準偏差の倍数（デフォルト: 2.0）
    
    Returns:
        BBW: ボリンジャーバンド幅（%）
    """
    bb = calculate_bollinger_bands(prices, period, std_dev)
    bbw = (bb['upper'] - bb['lower']) / bb['middle'] * 100
    return bbw


def calculate_ema(prices: pd.Series, period: int = 50) -> pd.Series:
    """
    指数移動平均（EMA）を計算
    
    Args:
        prices: 終値のSeries
        period: 期間（デフォルト: 50日）
    
    Returns:
        EMA: 指数移動平均
    """
    return prices.ewm(span=period, adjust=False).mean()


def calculate_deviation_from_ema(prices: pd.Series, ema_period: int = 50) -> pd.Series:
    """
    株価とEMAの乖離率を計算
    
    Args:
        prices: 終値のSeries
        ema_period: EMA期間（デフォルト: 50日）
    
    Returns:
        乖離率（%）
    """
    ema = calculate_ema(prices, ema_period)
    deviation = abs(prices - ema) / ema * 100
    return deviation


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    ATR（Average True Range）を計算
    
    Args:
        high: 高値のSeries
        low: 安値のSeries
        close: 終値のSeries
        period: 期間（デフォルト: 14日）
    
    Returns:
        ATR: 平均真の値幅
    """
    # 真の値幅を計算
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATRを計算（EMA）
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def detect_squeeze(
    prices: pd.Series,
    high: pd.Series,
    low: pd.Series,
    bb_period: int = 20,
    bb_std_dev: float = 2.0,
    ema_period: int = 50,
    atr_period: int = 14,
    lookback_period: int = 60,
    bbw_threshold: float = 1.3,
    deviation_threshold: float = 5.0,
    atr_threshold: float = 1.3,
    min_duration: int = 5
) -> Optional[Dict]:
    """
    価格収縮（スクイーズ）を検出
    
    Args:
        prices: 終値のSeries（過去100日分以上）
        high: 高値のSeries
        low: 安値のSeries
        bb_period: ボリンジャーバンド期間（デフォルト: 20日）
        bb_std_dev: ボリンジャーバンド標準偏差（デフォルト: 2.0）
        ema_period: EMA期間（デフォルト: 50日）
        atr_period: ATR期間（デフォルト: 14日）
        lookback_period: 比較期間（デフォルト: 60日）
        bbw_threshold: BBW閾値（最小値の倍数、デフォルト: 1.3）
        deviation_threshold: 乖離率閾値（%、デフォルト: 5.0）
        atr_threshold: ATR閾値（最小値の倍数、デフォルト: 1.3）
        min_duration: 最小継続期間（日数、デフォルト: 5）
    
    Returns:
        検出結果の辞書、または None
    """
    # データ長チェック
    if len(prices) < max(bb_period, ema_period, atr_period, lookback_period) + min_duration:
        return None
    
    # 各指標を計算
    bbw = calculate_bbw(prices, bb_period, bb_std_dev)
    deviation = calculate_deviation_from_ema(prices, ema_period)
    atr = calculate_atr(high, low, prices, atr_period)
    
    # 最新の値を取得
    current_bbw = bbw.iloc[-1]
    current_deviation = deviation.iloc[-1]
    current_atr = atr.iloc[-1]
    
    # 過去lookback_period日間の最小値を計算
    bbw_min = bbw.iloc[-lookback_period:].min()
    atr_min = atr.iloc[-lookback_period:].min()
    
    # 条件1: BBWが狭い
    bbw_condition = current_bbw <= bbw_min * bbw_threshold
    
    # 条件2: 株価がEMAに近い
    deviation_condition = current_deviation <= deviation_threshold
    
    # 条件3: ATRが低い
    atr_condition = current_atr <= atr_min * atr_threshold
    
    # すべての条件を満たすか確認
    if not (bbw_condition and deviation_condition and atr_condition):
        return None
    
    # 継続日数を計算
    duration = 0
    for i in range(1, min(len(prices), 30)):  # 最大30日まで遡る
        idx = -i
        if (bbw.iloc[idx] <= bbw_min * bbw_threshold and
            deviation.iloc[idx] <= deviation_threshold * 1.4 and  # 少し緩めに
            atr.iloc[idx] <= atr_min * atr_threshold):
            duration += 1
        else:
            break
    
    # 最小継続期間を満たすか確認
    if duration < min_duration:
        return None
    
    # 検出結果を返す
    return {
        'current_bbw': float(current_bbw),
        'bbw_min_60d': float(bbw_min),
        'bbw_ratio': float(current_bbw / bbw_min) if bbw_min > 0 else None,
        'deviation_from_ema': float(current_deviation),
        'current_atr': float(current_atr),
        'atr_min_60d': float(atr_min),
        'atr_ratio': float(current_atr / atr_min) if atr_min > 0 else None,
        'duration_days': int(duration),
        'detected': True
    }


def screen_squeeze_stocks(
    stock_data: List[Dict],
    bb_period: int = 20,
    bb_std_dev: float = 2.0,
    ema_period: int = 50,
    atr_period: int = 14,
    lookback_period: int = 60,
    bbw_threshold: float = 1.3,
    deviation_threshold: float = 5.0,
    atr_threshold: float = 1.3,
    min_duration: int = 5
) -> List[Dict]:
    """
    複数の銘柄に対してスクイーズ検出を実行
    
    Args:
        stock_data: 銘柄データのリスト
            各要素は以下のキーを持つ辞書:
            - code: 銘柄コード
            - name: 銘柄名
            - market: 市場
            - prices: 終値のリスト（過去100日分以上）
            - high: 高値のリスト
            - low: 安値のリスト
        その他のパラメータ: detect_squeeze()と同じ
    
    Returns:
        検出された銘柄のリスト
    """
    detected_stocks = []
    
    for stock in stock_data:
        try:
            # DataFrameに変換
            prices = pd.Series(stock['prices'])
            high = pd.Series(stock['high'])
            low = pd.Series(stock['low'])
            
            # スクイーズ検出
            result = detect_squeeze(
                prices, high, low,
                bb_period, bb_std_dev, ema_period, atr_period,
                lookback_period, bbw_threshold, deviation_threshold,
                atr_threshold, min_duration
            )
            
            if result:
                detected_stocks.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'market': stock['market'],
                    **result
                })
        except Exception as e:
            print(f"Error processing {stock.get('code', 'unknown')}: {e}")
            continue
    
    # 継続日数でソート（降順）
    detected_stocks.sort(key=lambda x: x['duration_days'], reverse=True)
    
    return detected_stocks


# テスト用コード
if __name__ == "__main__":
    # テストデータ作成（日本フエルトのような収縮パターン）
    np.random.seed(42)
    
    # 100日分のデータ
    days = 100
    
    # 最初の50日: 通常のボラティリティ
    prices1 = 800 + np.random.randn(50) * 20
    
    # 次の50日: 収縮（ボラティリティ低下）
    prices2 = 830 + np.random.randn(50) * 5  # 標準偏差を小さく
    
    prices = np.concatenate([prices1, prices2])
    high = prices + np.random.rand(days) * 10
    low = prices - np.random.rand(days) * 10
    
    # Seriesに変換
    prices_series = pd.Series(prices)
    high_series = pd.Series(high)
    low_series = pd.Series(low)
    
    # スクイーズ検出
    result = detect_squeeze(
        prices_series,
        high_series,
        low_series,
        min_duration=5
    )
    
    print("=" * 60)
    print("テスト結果:")
    print("=" * 60)
    
    if result:
        print("✅ スクイーズを検出しました！")
        print(f"  現在のBBW: {result['current_bbw']:.2f}%")
        print(f"  BBW最小値（60日）: {result['bbw_min_60d']:.2f}%")
        print(f"  BBW比率: {result['bbw_ratio']:.2f}倍")
        print(f"  乖離率: {result['deviation_from_ema']:.2f}%")
        print(f"  現在のATR: {result['current_atr']:.2f}")
        print(f"  ATR最小値（60日）: {result['atr_min_60d']:.2f}")
        print(f"  ATR比率: {result['atr_ratio']:.2f}倍")
        print(f"  継続日数: {result['duration_days']}日")
    else:
        print("❌ スクイーズは検出されませんでした")
    
    print("\n" + "=" * 60)
    print("BBWの推移:")
    print("=" * 60)
    bbw = calculate_bbw(prices_series)
    print(f"  最初の10日平均: {bbw.iloc[10:20].mean():.2f}%")
    print(f"  最後の10日平均: {bbw.iloc[-10:].mean():.2f}%")
    print(f"  全期間最小値: {bbw.min():.2f}%")
    print(f"  全期間最大値: {bbw.max():.2f}%")
