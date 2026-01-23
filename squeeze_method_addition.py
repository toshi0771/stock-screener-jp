"""
daily_data_collection.pyに追加するスクイーズ検出メソッド
"""

# ============================================================
# StockScreenerクラスに追加するメソッド
# ============================================================

async def screen_stock_squeeze(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
    """単一銘柄のスクイーズ（価格収縮）スクリーニング"""
    code = stock["Code"]
    name = stock.get("CompanyName", f"銘柄{code}")
    market = stock.get("MarketCode", "")
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=150)  # 100日分 + 余裕
        
        df = await self.jq_client.get_prices_daily_quotes(
            session, code,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d")
        )
        
        if df is None or len(df) < 100:
            return None
        
        # 最新100日分を取得
        df = df.tail(100)
        
        # 各指標を計算
        prices = df['Close']
        high = df['High']
        low = df['Low']
        
        # ボリンジャーバンド幅（BBW）
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
        
        # 最新の値
        current_bbw = bbw.iloc[-1]
        current_deviation = deviation.iloc[-1]
        current_atr = atr.iloc[-1]
        current_price = prices.iloc[-1]
        current_ema50 = ema50.iloc[-1]
        
        # 過去60日間の最小値
        bbw_min_60d = bbw.iloc[-60:].min()
        atr_min_60d = atr.iloc[-60:].min()
        
        # 検出条件
        bbw_threshold = 1.3
        deviation_threshold = 5.0
        atr_threshold = 1.3
        min_duration = 5
        
        # 条件1: BBWが狭い
        bbw_condition = current_bbw <= bbw_min_60d * bbw_threshold
        
        # 条件2: 株価がEMAに近い
        deviation_condition = current_deviation <= deviation_threshold
        
        # 条件3: ATRが低い
        atr_condition = current_atr <= atr_min_60d * atr_threshold
        
        # すべての条件を満たすか確認
        if not (bbw_condition and deviation_condition and atr_condition):
            return None
        
        # 継続日数を計算
        duration = 0
        for i in range(1, min(len(prices), 30)):  # 最大30日まで遡る
            idx = -i
            if (bbw.iloc[idx] <= bbw_min_60d * bbw_threshold and
                deviation.iloc[idx] <= deviation_threshold * 1.4 and
                atr.iloc[idx] <= atr_min_60d * atr_threshold):
                duration += 1
            else:
                break
        
        # 最小継続期間を満たすか確認
        if duration < min_duration:
            return None
        
        # 検出結果を返す
        return {
            "code": code,
            "name": name,
            "price": float(current_price),
            "market": self._market_code_to_name(market),
            "current_bbw": float(current_bbw),
            "bbw_min_60d": float(bbw_min_60d),
            "bbw_ratio": float(current_bbw / bbw_min_60d) if bbw_min_60d > 0 else None,
            "deviation_from_ema": float(current_deviation),
            "current_atr": float(current_atr),
            "atr_min_60d": float(atr_min_60d),
            "atr_ratio": float(current_atr / atr_min_60d) if atr_min_60d > 0 else None,
            "duration_days": int(duration),
            "ema_50": float(current_ema50),
            "volume": int(df.iloc[-1].get('Volume', 0))
        }
        
    except Exception as e:
        logger.debug(f"スクリーニングエラー [{code}]: {e}")
        return None


# ============================================================
# run_screeningメソッドに追加するコード
# ============================================================

# 200日新高値押し目の後に追加:

# スクイーズ（価格収縮）
logger.info("=" * 60)
logger.info("スクイーズ（価格収縮）スクリーニング開始")
sq_start = datetime.now()
squeeze = await self.process_stocks_batch(
    stocks, self.screen_stock_squeeze, "スクイーズ"
)
sq_time = int((datetime.now() - sq_start).total_seconds() * 1000)
logger.info(f"スクイーズ検出: {len(squeeze)}銘柄 ({sq_time}ms)")

# 間引き処理
squeeze_sampled = sample_stocks_balanced(squeeze, max_per_range=10)

screening_id = self.sb_client.save_screening_result(
    "squeeze", datetime.now().strftime('%Y-%m-%d'),
    len(squeeze), sq_time  # 元の検出数
)
if screening_id:
    # additional_dataとしてJSONB形式で保存
    stocks_with_additional_data = []
    for s in squeeze_sampled:
        stock_data = {
            "code": s["code"],
            "name": s["name"],
            "price": s["price"],
            "market": s["market"],
            "volume": s.get("volume", 0),
            "additional_data": {
                "current_bbw": s["current_bbw"],
                "bbw_min_60d": s["bbw_min_60d"],
                "bbw_ratio": s["bbw_ratio"],
                "deviation_from_ema": s["deviation_from_ema"],
                "current_atr": s["current_atr"],
                "atr_min_60d": s["atr_min_60d"],
                "atr_ratio": s["atr_ratio"],
                "duration_days": s["duration_days"],
                "current_price": s["price"],
                "ema_50": s["ema_50"]
            }
        }
        stocks_with_additional_data.append(stock_data)
    
    self.sb_client.save_detected_stocks(screening_id, stocks_with_additional_data)

# returnに追加:
return {
    "date": datetime.now().strftime('%Y-%m-%d'),
    "timestamp": datetime.now().isoformat(),
    "total_stocks": len(stocks),
    "execution_time_seconds": round(total_time, 1),
    "options": {
        "perfect_order_sma200": PERFECT_ORDER_SMA200_FILTER,
        "pullback_ema": PULLBACK_EMA_FILTER,
        "pullback_stochastic": PULLBACK_STOCHASTIC_FILTER
    },
    "perfect_order": perfect_order,
    "bollinger_band": bollinger_band,
    "200day_pullback": week52_pullback,
    "squeeze": squeeze  # 追加
}
