#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日次株式スクリーニングデータ収集スクリプト（並列処理・全銘柄対応・オプション機能付き）
asyncio + aiohttpによる高速並列処理で全銘柄をスクリーニング
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
import pandas as pd
from typing import List, Dict, Any, Optional

# ============================================================
# スクリーニングオプション設定
# ============================================================

# パーフェクトオーダーオプション
PERFECT_ORDER_SMA200_FILTER = "all"  # "above" (200SMAより上), "below" (200SMAより下), "all" (全て)

# 52週新高値押し目オプション
PULLBACK_EMA_FILTER = "all"  # "10ema", "20ema", "50ema", "all" (いずれか)
PULLBACK_STOCHASTIC_FILTER = False  # True: ストキャス売られすぎのみ, False: 全て

# ============================================================

# 絶対パスで設定
BASE_DIR = Path("/home/ubuntu/stock_screener_enhanced")
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ログ設定
log_file = LOG_DIR / f"daily_collection_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 設定
CONCURRENT_REQUESTS = 20  # 同時実行数
HISTORY_DAYS = 90
RETRY_COUNT = 3
RETRY_DELAY = 1


class SupabaseClient:
    """Supabase クライアント"""
    
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_ANON_KEY')
        self.enabled = bool(self.url and self.key)
        self.client = None
        
        if self.enabled:
            try:
                from supabase import create_client
                self.client = create_client(self.url, self.key)
                logger.info("Supabase接続成功")
            except Exception as e:
                logger.error(f"Supabase接続失敗: {e}")
                self.enabled = False
    
    def save_screening_result(self, screening_type, date, total_stocks, execution_time_ms=0):
        """スクリーニング結果の概要を保存"""
        if not self.enabled:
            return None
        
        try:
            data = {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "screening_type": screening_type,
                "screening_date": date,
                "market_filter": "all",
                "total_stocks_found": total_stocks,
                "execution_time_ms": execution_time_ms
            }
            
            result = self.client.table("screening_results").insert(data).execute()
            logger.info(f"Supabase保存成功: {screening_type} - {total_stocks}銘柄")
            return result.data[0]["id"] if result.data else None
            
        except Exception as e:
            logger.error(f"Supabase保存エラー ({screening_type}): {e}")
            return None
    
    def save_detected_stocks(self, screening_result_id, stocks):
        """検出された銘柄の詳細を保存"""
        if not self.enabled or not screening_result_id:
            return False
        
        try:
            for stock in stocks:
                data = {
                    "screening_result_id": screening_result_id,
                    "stock_code": stock.get("code"),
                    "company_name": stock.get("name"),
                    "market": stock.get("market"),
                    "close_price": stock.get("price") or stock.get("close"),
                    "volume": stock.get("volume", 0),
                    "ema_10": stock.get("ema10") or stock.get("ema_10"),
                    "ema_20": stock.get("ema20") or stock.get("ema_20"),
                    "ema_50": stock.get("ema50") or stock.get("ema_50"),
                    "week52_high": stock.get("high_52week"),
                    "touch_ema": stock.get("touched_emas") or stock.get("ema_touch"),
                    "pullback_percentage": stock.get("pullback_pct"),
                    "bollinger_upper": stock.get("upper_3sigma"),
                    "bollinger_lower": stock.get("lower_3sigma"),
                    "bollinger_middle": stock.get("sma20"),
                    "touch_direction": stock.get("touch_direction", "upper"),
                    "sma_200": stock.get("sma200"),
                    "stochastic_k": stock.get("stochastic_k"),
                    "stochastic_d": stock.get("stochastic_d")
                }
                
                self.client.table("detected_stocks").insert(data).execute()
            
            logger.info(f"Supabase詳細保存成功: {len(stocks)}銘柄")
            return True
            
        except Exception as e:
            logger.error(f"Supabase詳細保存エラー: {e}")
            return False


class AsyncJQuantsClient:
    """非同期jQuants APIクライアント"""
    
    def __init__(self):
        self.refresh_token = os.getenv('JQUANTS_REFRESH_TOKEN')
        self.id_token = None
        self.base_url = "https://api.jquants.com/v1"
        
        if not self.refresh_token:
            raise ValueError("JQUANTS_REFRESH_TOKEN が設定されていません")
    
    async def authenticate(self, session: aiohttp.ClientSession):
        """認証してIDトークンを取得"""
        try:
            url = f"{self.base_url}/token/auth_refresh"
            params = {"refreshtoken": self.refresh_token}
            
            async with session.post(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                self.id_token = data["idToken"]
                logger.info("jQuants API認証成功")
                return True
        except Exception as e:
            logger.error(f"jQuants API認証失敗: {e}")
            return False
    
    async def get_listed_info(self, session: aiohttp.ClientSession):
        """上場銘柄一覧を取得"""
        if not self.id_token:
            await self.authenticate(session)
        
        try:
            url = f"{self.base_url}/listed/info"
            headers = {"Authorization": f"Bearer {self.id_token}"}
            
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                return data["info"]
        except Exception as e:
            logger.error(f"銘柄一覧取得失敗: {e}")
            return None
    
    async def get_prices_daily_quotes(self, session: aiohttp.ClientSession, code: str, 
                                     from_date: str, to_date: str, retry: int = 0):
        """日次株価データを取得（リトライ機能付き）"""
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
                response.raise_for_status()
                data = await response.json()
                
                if "daily_quotes" in data and data["daily_quotes"]:
                    df = pd.DataFrame(data["daily_quotes"])
                    return df
                return None
                
        except Exception as e:
            if retry < RETRY_COUNT:
                await asyncio.sleep(RETRY_DELAY)
                return await self.get_prices_daily_quotes(session, code, from_date, to_date, retry + 1)
            logger.warning(f"株価データ取得失敗 [{code}]: {e}")
            return None


class ParallelStockScreener:
    """並列株式スクリーニング実行クラス"""
    
    def __init__(self):
        self.jq_client = AsyncJQuantsClient()
        self.sb_client = SupabaseClient()
        self.session = None
        self.progress = {"total": 0, "processed": 0, "detected": 0}
    
    def calculate_ema(self, series, period):
        """EMAを計算"""
        return series.ewm(span=period, adjust=False).mean()
    
    def calculate_sma(self, series, period):
        """SMAを計算"""
        return series.rolling(window=period).mean()
    
    def calculate_stochastic(self, df, k_period=14, d_period=3):
        """ストキャスティクスを計算"""
        if df is None or len(df) < k_period:
            return None, None
        
        # 過去N日間の最高値・最安値
        highest_high = df['High'].rolling(window=k_period).max()
        lowest_low = df['Low'].rolling(window=k_period).min()
        
        # %K計算
        stoch_k = ((df['Close'] - lowest_low) / (highest_high - lowest_low)) * 100
        
        # %D計算（%Kの移動平均）
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        return stoch_k.iloc[-1], stoch_d.iloc[-1]
    
    def _market_code_to_name(self, code):
        """市場コードを市場名に変換"""
        market_map = {
            "0111": "プライム",
            "0112": "スタンダード",
            "0113": "グロース"
        }
        return market_map.get(code, code)
    
    async def screen_stock_perfect_order(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄のパーフェクトオーダースクリーニング（200SMAオプション付き）"""
        code = stock["Code"]
        name = stock.get("CompanyName", f"銘柄{code}")
        market = stock.get("MarketCode", "")
        
        try:
            # 株価データ取得（200SMA用に追加データ取得）
            end_date = datetime.now()
            start_date = end_date - timedelta(days=300)  # 200SMA計算のため余裕を持たせる
            
            df = await self.jq_client.get_prices_daily_quotes(
                session, code,
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d")
            )
            
            if df is None or len(df) < 200:
                return None
            
            # EMA計算
            df['EMA10'] = self.calculate_ema(df['Close'], 10)
            df['EMA20'] = self.calculate_ema(df['Close'], 20)
            df['EMA50'] = self.calculate_ema(df['Close'], 50)
            
            # 200SMA計算
            df['SMA200'] = self.calculate_sma(df['Close'], 200)
            
            latest = df.iloc[-1]
            
            # パーフェクトオーダー判定
            if not (latest['Close'] >= latest['EMA10'] >= 
                    latest['EMA20'] >= latest['EMA50']):
                return None
            
            # 乖離率フィルター: (株価 - 50EMA) / 株価 <= 30%
            divergence_pct = ((latest['Close'] - latest['EMA50']) / latest['Close']) * 100
            if divergence_pct > 30:
                return None
            
            # 200SMAフィルター適用
            if PERFECT_ORDER_SMA200_FILTER == "above":
                if latest['Close'] < latest['SMA200']:
                    return None
            elif PERFECT_ORDER_SMA200_FILTER == "below":
                if latest['Close'] > latest['SMA200']:
                    return None
            # "all"の場合はフィルターなし
            
            return {
                "code": code,
                "name": name,
                "price": float(latest['Close']),
                "ema10": float(latest['EMA10']),
                "ema20": float(latest['EMA20']),
                "ema50": float(latest['EMA50']),
                "sma200": float(latest['SMA200']),
                "sma200_position": "above" if latest['Close'] >= latest['SMA200'] else "below",
                "market": self._market_code_to_name(market),
                "volume": int(latest.get('Volume', 0))
            }
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def screen_stock_bollinger_band(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄のボリンジャーバンドスクリーニング"""
        code = stock["Code"]
        name = stock.get("CompanyName", f"銘柄{code}")
        market = stock.get("MarketCode", "")
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=260)
            
            df = await self.jq_client.get_prices_daily_quotes(
                session, code,
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d")
            )
            
            if df is None or len(df) < 20:
                return None
            
            # ボリンジャーバンド計算
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['STD20'] = df['Close'].rolling(window=20).std()
            df['Upper3'] = df['SMA20'] + (df['STD20'] * 3)
            df['Lower3'] = df['SMA20'] - (df['STD20'] * 3)
            
            latest = df.iloc[-1]
            
            # ±3σタッチ判定
            if latest['Close'] >= latest['Upper3'] or latest['Close'] <= latest['Lower3']:
                touch_direction = "upper" if latest['Close'] >= latest['Upper3'] else "lower"
                
                return {
                    "code": code,
                    "name": name,
                    "price": float(latest['Close']),
                    "sma20": float(latest['SMA20']),
                    "upper_3sigma": float(latest['Upper3']),
                    "lower_3sigma": float(latest['Lower3']),
                    "touch_direction": touch_direction,
                    "market": self._market_code_to_name(market),
                    "volume": int(latest.get('Volume', 0))
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def screen_stock_52week_pullback(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄の52週新高値押し目スクリーニング（EMAフィルター・ストキャスティクスオプション付き）"""
        code = stock["Code"]
        name = stock.get("CompanyName", f"銘柄{code}")
        market = stock.get("MarketCode", "")
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
            df = await self.jq_client.get_prices_daily_quotes(
                session, code,
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d")
            )
            
            if df is None or len(df) < 260:
                return None
            
            # EMA計算
            df['EMA10'] = self.calculate_ema(df['Close'], 10)
            df['EMA20'] = self.calculate_ema(df['Close'], 20)
            df['EMA50'] = self.calculate_ema(df['Close'], 50)
            
            # 52週最高値
            high_52w = df['High'].tail(260).max()
            latest = df.iloc[-1]
            current_price = latest['Close']
            
            # 新高値からの下落率
            pullback_pct = ((high_52w - current_price) / high_52w) * 100
            
            # 条件: 52週新高値から30%以内の押し目
            if pullback_pct > 30:
                return None
            
            # EMAタッチ判定
            touched_emas = []
            tolerance = 0.02
            
            if abs(current_price - latest['EMA10']) / latest['EMA10'] <= tolerance:
                touched_emas.append("10EMA")
            if abs(current_price - latest['EMA20']) / latest['EMA20'] <= tolerance:
                touched_emas.append("20EMA")
            if abs(current_price - latest['EMA50']) / latest['EMA50'] <= tolerance:
                touched_emas.append("50EMA")
            
            if not touched_emas:
                return None
            
            # EMAフィルター適用
            if PULLBACK_EMA_FILTER != "all":
                if PULLBACK_EMA_FILTER == "10ema" and "10EMA" not in touched_emas:
                    return None
                elif PULLBACK_EMA_FILTER == "20ema" and "20EMA" not in touched_emas:
                    return None
                elif PULLBACK_EMA_FILTER == "50ema" and "50EMA" not in touched_emas:
                    return None
            
            # ストキャスティクス計算
            stoch_k, stoch_d = self.calculate_stochastic(df)
            
            # ストキャスティクスフィルター適用
            if PULLBACK_STOCHASTIC_FILTER:
                if stoch_k is None or stoch_k > 20:  # 売られすぎ閾値
                    return None
            
            return {
                "code": code,
                "name": name,
                "price": float(current_price),
                "high_52week": float(high_52w),
                "pullback_pct": round(pullback_pct, 2),
                "touched_emas": ",".join(touched_emas),
                "ema_10": float(latest['EMA10']),
                "ema_20": float(latest['EMA20']),
                "ema_50": float(latest['EMA50']),
                "stochastic_k": round(stoch_k, 2) if stoch_k is not None else None,
                "stochastic_d": round(stoch_d, 2) if stoch_d is not None else None,
                "market": self._market_code_to_name(market),
                "volume": int(latest.get('Volume', 0))
            }
            
        except Exception as e:
            logger.debug(f"スクリーニングエラー [{code}]: {e}")
            return None
    
    async def process_stocks_batch(self, stocks: List[Dict], screening_func, method_name: str):
        """銘柄のバッチ処理"""
        self.progress["total"] = len(stocks)
        self.progress["processed"] = 0
        self.progress["detected"] = 0
        
        connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS)
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 認証
            await self.jq_client.authenticate(session)
            
            # セマフォで同時実行数を制限
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            
            async def process_with_semaphore(stock):
                async with semaphore:
                    result = await screening_func(stock, session)
                    self.progress["processed"] += 1
                    
                    if self.progress["processed"] % 100 == 0:
                        logger.info(f"{method_name}: {self.progress['processed']}/{self.progress['total']} 処理完了 "
                                  f"({self.progress['detected']}銘柄検出)")
                    
                    if result:
                        self.progress["detected"] += 1
                    
                    return result
            
            # 並列実行
            tasks = [process_with_semaphore(stock) for stock in stocks]
            results = await asyncio.gather(*tasks)
            
            # Noneを除外
            return [r for r in results if r is not None]
    
    async def run_screening(self, stocks: List[Dict]):
        """全スクリーニング手法を並列実行"""
        logger.info(f"並列スクリーニング開始: {len(stocks)}銘柄")
        logger.info(f"同時実行数: {CONCURRENT_REQUESTS}")
        logger.info("=" * 60)
        logger.info("スクリーニングオプション設定:")
        logger.info(f"  - パーフェクトオーダー 200SMAフィルター: {PERFECT_ORDER_SMA200_FILTER}")
        logger.info(f"  - 52週新高値押し目 EMAフィルター: {PULLBACK_EMA_FILTER}")
        logger.info(f"  - 52週新高値押し目 ストキャスティクス: {'ON' if PULLBACK_STOCHASTIC_FILTER else 'OFF'}")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        # パーフェクトオーダー
        logger.info("パーフェクトオーダースクリーニング開始")
        po_start = datetime.now()
        perfect_order = await self.process_stocks_batch(
            stocks, self.screen_stock_perfect_order, "パーフェクトオーダー"
        )
        po_time = int((datetime.now() - po_start).total_seconds() * 1000)
        logger.info(f"パーフェクトオーダー検出: {len(perfect_order)}銘柄 ({po_time}ms)")
        
        # Supabase保存
        screening_id = self.sb_client.save_screening_result(
            "perfect_order", datetime.now().strftime('%Y-%m-%d'),
            len(perfect_order), po_time
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, perfect_order)
        
        # ボリンジャーバンド
        logger.info("=" * 60)
        logger.info("ボリンジャーバンド±3σスクリーニング開始")
        bb_start = datetime.now()
        bollinger_band = await self.process_stocks_batch(
            stocks, self.screen_stock_bollinger_band, "ボリンジャーバンド"
        )
        bb_time = int((datetime.now() - bb_start).total_seconds() * 1000)
        logger.info(f"ボリンジャーバンド検出: {len(bollinger_band)}銘柄 ({bb_time}ms)")
        
        screening_id = self.sb_client.save_screening_result(
            "bollinger_band", datetime.now().strftime('%Y-%m-%d'),
            len(bollinger_band), bb_time
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, bollinger_band)
        
        # 52週新高値押し目
        logger.info("=" * 60)
        logger.info("52週新高値押し目スクリーニング開始")
        pb_start = datetime.now()
        week52_pullback = await self.process_stocks_batch(
            stocks, self.screen_stock_52week_pullback, "52週新高値押し目"
        )
        pb_time = int((datetime.now() - pb_start).total_seconds() * 1000)
        logger.info(f"52週新高値押し目検出: {len(week52_pullback)}銘柄 ({pb_time}ms)")
        
        screening_id = self.sb_client.save_screening_result(
            "52week_pullback", datetime.now().strftime('%Y-%m-%d'),
            len(week52_pullback), pb_time
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, week52_pullback)
        
        total_time = (datetime.now() - start_time).total_seconds()
        logger.info("=" * 60)
        logger.info(f"全スクリーニング完了: {total_time:.1f}秒")
        
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
            "52week_pullback": week52_pullback
        }


class HistoryManager:
    """履歴管理クラス"""
    
    def __init__(self):
        self.history_file = DATA_DIR / "screening_history.json"
        self.max_days = HISTORY_DAYS
    
    def load_history(self):
        if not self.history_file.exists():
            return {}
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"履歴読み込みエラー: {e}")
            return {}
    
    def save_history(self, data):
        history = self.load_history()
        today = datetime.now().strftime('%Y-%m-%d')
        
        history[today] = data
        
        # 90日以前のデータを削除
        cutoff_date = (datetime.now() - timedelta(days=self.max_days)).strftime('%Y-%m-%d')
        history = {k: v for k, v in history.items() if k >= cutoff_date}
        
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.info(f"履歴保存完了: {self.history_file}")
        except Exception as e:
            logger.error(f"履歴保存エラー: {e}")
    
    def get_statistics(self):
        history = self.load_history()
        
        if not history:
            return None
        
        stats = {
            "total_days": len(history),
            "date_range": {
                "from": min(history.keys()),
                "to": max(history.keys())
            },
            "avg_detections": {
                "perfect_order": 0,
                "bollinger_band": 0,
                "52week_pullback": 0
            }
        }
        
        for data in history.values():
            stats["avg_detections"]["perfect_order"] += len(data.get("perfect_order", []))
            stats["avg_detections"]["bollinger_band"] += len(data.get("bollinger_band", []))
            stats["avg_detections"]["52week_pullback"] += len(data.get("52week_pullback", []))
        
        days = len(history)
        for key in stats["avg_detections"]:
            stats["avg_detections"][key] = round(stats["avg_detections"][key] / days, 2)
        
        return stats


async def main():
    """メイン処理"""
    logger.info("=" * 60)
    logger.info("日次株式スクリーニングデータ収集開始（並列処理・全銘柄対応・オプション機能付き）")
    logger.info("=" * 60)
    
    try:
        screener = ParallelStockScreener()
        
        # 銘柄リスト取得
        logger.info("銘柄リスト取得中...")
        
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(connector=connector) as session:
            await screener.jq_client.authenticate(session)
            all_stocks_data = await screener.jq_client.get_listed_info(session)
        
        if not all_stocks_data:
            logger.error("銘柄リスト取得失敗")
            return 1
        
        # 市場コードでフィルタ
        market_codes = {"0111": "プライム", "0112": "スタンダード", "0113": "グロース"}
        all_stocks = [s for s in all_stocks_data if s.get("MarketCode") in market_codes]
        
        # 市場別統計
        for code, name in market_codes.items():
            count = len([s for s in all_stocks if s.get("MarketCode") == code])
            logger.info(f"{name}市場: {count}銘柄")
        
        logger.info(f"合計: {len(all_stocks)}銘柄")
        
        # スクリーニング実行
        results = await screener.run_screening(all_stocks)
        
        # ローカル履歴に保存
        history_manager = HistoryManager()
        history_manager.save_history(results)
        
        # 統計情報を表示
        stats = history_manager.get_statistics()
        if stats:
            logger.info("=" * 60)
            logger.info("統計情報")
            logger.info(f"履歴日数: {stats['total_days']}日")
            logger.info(f"期間: {stats['date_range']['from']} ~ {stats['date_range']['to']}")
            logger.info(f"平均検出数:")
            logger.info(f"  - パーフェクトオーダー: {stats['avg_detections']['perfect_order']}銘柄/日")
            logger.info(f"  - ボリンジャーバンド: {stats['avg_detections']['bollinger_band']}銘柄/日")
            logger.info(f"  - 52週新高値押し目: {stats['avg_detections']['52week_pullback']}銘柄/日")
        
        logger.info("=" * 60)
        logger.info("日次データ収集完了")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))

