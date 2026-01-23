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
import pytz
import math

# ============================================================
# スクリーニングオプション設定
# ============================================================

# パーフェクトオーダーオプション
PERFECT_ORDER_SMA200_FILTER = "all"  # "above" (200SMAより上), "below" (200SMAより下), "all" (全て)

# 200日新高値押し目オプション
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


def safe_float(value, default=None):
    """安全にfloatに変換（NaN, Infを回避）"""
    if value is None or value == "" or value == "NaN":
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default

def safe_int(value, default=None):
    """安全にintに変換"""
    if value is None or value == "":
        return default
    try:
        return int(float(value))  # float経由でintに変換
    except (ValueError, TypeError):
        return default


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
        """検出された銘柄の詳細を保存（バッチINSERT）"""
        if not self.enabled or not screening_result_id:
            return False
        
        if not stocks or len(stocks) == 0:
            logger.warning("保存する銘柄がありません")
            return False
        
        try:
            # バッチ用データリストを作成
            data_list = []
            for stock in stocks:
                data = {
                    "screening_result_id": screening_result_id,
                    "stock_code": str(stock.get("code", "")),
                    "company_name": str(stock.get("name", "")),
                    "market": str(stock.get("market", "")),
                    "close_price": safe_float(stock.get("price") or stock.get("close"), 0),
                    "volume": safe_int(stock.get("volume"), 0),
                    "ema_10": safe_float(stock.get("ema10") or stock.get("ema_10")),
                    "ema_20": safe_float(stock.get("ema20") or stock.get("ema_20")),
                    "ema_50": safe_float(stock.get("ema50") or stock.get("ema_50")),
                    "week52_high": safe_float(stock.get("high_52week")),
                    "touch_ema": str(stock.get("touched_emas") or stock.get("ema_touch") or "") if (stock.get("touched_emas") or stock.get("ema_touch")) else None,
                    "pullback_percentage": safe_float(stock.get("pullback_pct")),
                    "bollinger_upper": safe_float(stock.get("upper_3sigma")),
                    "bollinger_lower": safe_float(stock.get("lower_3sigma")),
                    "bollinger_middle": safe_float(stock.get("sma20")),
                    "touch_direction": str(stock.get("touch_direction", "upper")),
                    "sma_200": safe_float(stock.get("sma200")),
                    "sma200_position": str(stock.get("sma200_position", "")) if stock.get("sma200_position") else None,
                    "stochastic_k": safe_float(stock.get("stochastic_k")),
                    "stochastic_d": safe_float(stock.get("stochastic_d"))
                }
                data_list.append(data)
            
            # バッチINSERT（一括保存）
            self.client.table("detected_stocks").insert(data_list).execute()
            
            logger.info(f"Supabase詳細保存成功: {len(stocks)}銘柄")
            return True
            
        except Exception as e:
            logger.error(f"Supabase詳細保存エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


class AsyncJQuantsClient:
    """非同期jQuants APIクライアント"""
    
    def __init__(self):
        self.refresh_token = os.getenv('JQUANTS_REFRESH_TOKEN')
        self.id_token = None
        self.base_url = "https://api.jquants.com/v1"
        
        if not self.refresh_token:
            raise ValueError("JQUANTS_REFRESH_TOKEN が設定されていません")
        
        # Refresh Token有効期限チェック
        self._check_refresh_token_expiry()
    
    def _check_refresh_token_expiry(self):
        """Refresh Token有効期限をチェック"""
        token_created_date = os.getenv('JQUANTS_TOKEN_CREATED_DATE')
        
        if not token_created_date:
            logger.warning("⚠️ JQUANTS_TOKEN_CREATED_DATE が設定されていません。Refresh Token取得日を環境変数に設定することを推奨します。")
            return
        
        try:
            created = datetime.strptime(token_created_date, "%Y-%m-%d")
            days_since_created = (datetime.now() - created).days
            
            if days_since_created >= 7:
                logger.error(f"🚨 Refresh Tokenの有効期限が切れています！（{days_since_created}日経過）")
                logger.error("🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得し、環境変数を更新してください。")
            elif days_since_created >= 6:
                logger.warning(f"⚠️ Refresh Tokenの有効期限が明日切れます！（{days_since_created}日経過）")
                logger.warning("🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得してください。")
            elif days_since_created >= 5:
                logger.warning(f"⚠️ Refresh Tokenの有効期限が近づいています（{days_since_created}日経過、残り{7-days_since_created}日）")
            else:
                logger.info(f"✅ Refresh Token有効期限: あと{7-days_since_created}日（{days_since_created}日経過）")
        except ValueError as e:
            logger.error(f"❌ JQUANTS_TOKEN_CREATED_DATE の形式が不正です（正しい形式: YYYY-MM-DD）: {e}")
    
    async def authenticate(self, session: aiohttp.ClientSession):
        """認証してIDトークンを取得（詳細ログ付き）"""
        try:
            url = f"{self.base_url}/token/auth_refresh"
            params = {"refreshtoken": self.refresh_token}
            
            logger.info("🔐 jQuants API認証開始...")
            logger.info(f"🔑 Refresh Token長: {len(self.refresh_token) if self.refresh_token else 0}文字")
            logger.info(f"🔑 Refresh Token先頭: {self.refresh_token[:50] if self.refresh_token else 'None'}...")
            
            async with session.post(url, params=params) as response:
                status_code = response.status
                
                if status_code == 200:
                    data = await response.json()
                    self.id_token = data["idToken"]
                    logger.info("✅ jQuants API認証成功（ID Token取得完了）")
                    return True
                elif status_code == 400:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API認証失敗 [400 Bad Request]: Refresh Tokenの形式が不正です")
                    logger.error(f"詳細: {error_text}")
                    return False
                elif status_code == 401:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API認証失敗 [401 Unauthorized]: Refresh Tokenが無効または期限切れです")
                    logger.error(f"詳細: {error_text}")
                    logger.error("🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得し、環境変数 JQUANTS_REFRESH_TOKEN を更新してください")
                    return False
                else:
                    error_text = await response.text()
                    logger.error(f"❌ jQuants API認証失敗 [{status_code}]: {error_text}")
                    return False
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ jQuants API認証失敗（ネットワークエラー）: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ jQuants API認証失敗（予期しないエラー）: {e}")
            logger.error(f"エラータイプ: {type(e).__name__}")
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


def sample_stocks_balanced(stocks, max_per_range=10):
    """
    銘柄コード帯別・市場別の銘柄数に応じた割合でランダムサンプリング
    
    Args:
        stocks: 検出銘柄のリスト
        max_per_range: 各銘柄コード帯から抽出する最大銘柄数
    
    Returns:
        サンプリングされた銘柄のリスト
    
    ロジック:
        1. 各銘柄コード帯（1000-1999, 2000-2999など）内で市場別に分類
        2. 各市場の銘柄数を集計
        3. 最大剰余法（Largest Remainder Method）で抽出数を決定
        4. 各市場からランダムに抽出
    """
    import random
    
    if not stocks or len(stocks) <= 100:
        return stocks  # 100銘柄以下ならそのまま返す
    
    # 銘柄コード帯別・市場別に分類
    ranges = {}
    
    for stock in stocks:
        code = str(stock.get('code', '0000'))
        # 銘柄コードの先頭1桁を取得（1000番台、2000番台...）
        if len(code) >= 4:
            range_key = f"{code[0]}000"
        else:
            range_key = "other"
        
        market = stock.get('market', 'プライム')
        
        if range_key not in ranges:
            ranges[range_key] = {}
        if market not in ranges[range_key]:
            ranges[range_key][market] = []
        
        ranges[range_key][market].append(stock)
    
    # 各帯から市場別の銘柄数に応じてランダム抽出
    sampled = []
    
    for range_key, markets in sorted(ranges.items()):
        # 各市場の銘柄数を集計
        market_counts = {market: len(stocks_list) for market, stocks_list in markets.items()}
        total_in_range = sum(market_counts.values())
        
        # この帯から抽出する銘柄数（最大max_per_range）
        target_count = min(max_per_range, total_in_range)
        
        # 最大剰余法で各市場の抽出数を計算
        market_samples = {}
        quotas = {}  # 比例配分の商
        remainders = {}  # 比例配分の余り
        
        # ステップ1: 比例配分の商と余りを計算
        for market, count in market_counts.items():
            quota = (count / total_in_range) * target_count
            quotas[market] = int(quota)  # 整数部分
            remainders[market] = quota - int(quota)  # 小数部分（余り）
        
        # ステップ2: 商の合計を計算
        allocated = sum(quotas.values())
        
        # ステップ3: 残りの議席を余りが大きい順に配分
        remaining_seats = target_count - allocated
        if remaining_seats > 0:
            # 余りが大きい順にソート
            sorted_markets = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
            for i in range(remaining_seats):
                market = sorted_markets[i][0]
                quotas[market] += 1
        
        # 実際の銘柄数を超えないように調整
        for market, sample_count in quotas.items():
            market_samples[market] = min(sample_count, market_counts[market])
        
        # 各市場からランダムに抽出
        for market, sample_count in market_samples.items():
            if sample_count > 0:
                stocks_in_market = markets[market]
                # ランダムにサンプリング
                sampled_stocks = random.sample(stocks_in_market, min(sample_count, len(stocks_in_market)))
                sampled.extend(sampled_stocks)
    
    logger.info(f"📊 間引きロジック: {len(stocks)}銘柄 → {len(sampled)}銘柄")
    
    # 各帯の内訳をログ出力
    for range_key, markets in sorted(ranges.items()):
        market_summary = ", ".join([f"{m}:{len(s)}" for m, s in markets.items()])
        logger.info(f"   {range_key}番台: {market_summary}")
    
    return sampled


class StockScreener:
    """株式スクリーニングクラス"""
    
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
            
            # 乖離率フィルター: (株価 - 50EMA) / 株価 <= 20%
            divergence_pct = ((latest['Close'] - latest['EMA50']) / latest['Close']) * 100
            if divergence_pct > 20:
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
    
    async def screen_stock_200day_pullback(self, stock: Dict, session: aiohttp.ClientSession) -> Optional[Dict]:
        """単一銘柄の200日新高値押し目スクリーニング（EMAタッチ・ストキャスオプション付き）"""
        # 統計情報用のカウンターを初期化（初回のみ）
        if not hasattr(self, 'pullback_stats'):
            self.pullback_stats = {
                'total': 0,
                'has_data': 0,
                'recent_high': 0,
                'within_30pct': 0,
                'ema10_touch': 0,
                'ema20_touch': 0,
                'ema50_touch': 0,
                'any_ema_touch': 0,
                'passed_all': 0
            }
        
        self.pullback_stats['total'] += 1
        
        code = stock["Code"]
        name = stock.get("CompanyName", f"銘柄{code}")
        market = stock.get("MarketCode", "")
        
        # デバッグモード
        debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        debug_stock_code = os.getenv('DEBUG_STOCK_CODE', '')
        # 文字列比較を確実にするため、両方を文字列に変換
        is_debug_target = debug_mode and str(code) == str(debug_stock_code)
        
        # 6954の場合は必ずログ出力（デバッグモード関係なく）
        if code == "6954":
            logger.info(f"⚡⚡⚡ 6954検出！ screen_stock_200day_pullback() 開始 - {name}({code})")
            logger.info(f"⚡ debug_mode={debug_mode}, debug_stock_code='{debug_stock_code}', code='{code}'")
            logger.info(f"⚡ is_debug_target={is_debug_target}")
        
        # デバッグ：関数に入ったことを確認
        if is_debug_target:
            logger.info(f"⚡ DEBUG: screen_stock_200day_pullback() 開始 - {name}({code})")
            logger.info(f"⚡ DEBUG: debug_mode={debug_mode}, debug_stock_code={debug_stock_code}")
        
        try:
            # 日本時間で現在日時を取得
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            # 前日までのデータを取得（当日のデータはまだ確定していない可能性があるため）
            end_date = (now_jst - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
            start_date = end_date - timedelta(days=365)
            
            df = await self.jq_client.get_prices_daily_quotes(
                session, code,
                start_date.strftime("%Y%m%d"),
                end_date.strftime("%Y%m%d")
            )
            
            if df is None or len(df) < 200:  # 約8ヶ月分のデータがあればOK
                return None
            
            self.pullback_stats['has_data'] += 1
            
            # EMA計算
            df['EMA10'] = self.calculate_ema(df['Close'], 10)
            df['EMA20'] = self.calculate_ema(df['Close'], 20)
            df['EMA50'] = self.calculate_ema(df['Close'], 50)
            
            # 52週最高値（利用可能なデータの範囲内で計算、最大260日）
            lookback_days = min(260, len(df))
            high_52w = df['High'].tail(lookback_days).max()
            latest = df.iloc[-1]
            current_price = latest['Close']
            
            # 52週新高値を記録した日を特定
            high_52w_date_idx = df['High'].tail(lookback_days).idxmax()
            days_since_high = len(df) - 1 - high_52w_date_idx
            
            # 条件1: 過去60日以内に52週新高値を更新していること
            if days_since_high <= 60:
                self.pullback_stats['recent_high'] += 1
            else:
                return None
            
            # 新高値からの下落率
            pullback_pct = ((high_52w - current_price) / high_52w) * 100
            
            # 条件2: 52週新高値から30%以内の押し目
            if pullback_pct <= 30:
                self.pullback_stats['within_30pct'] += 1
            else:
                return None
            
            # EMAタッチ判定（4本値のいずれかがEMAにタッチ）
            touched_emas = []
            
            # 当日の4本値を取得
            open_price = latest['Open']
            high_price = latest['High']
            low_price = latest['Low']
            close_price = latest['Close']
            
            # デバッグログ
            if is_debug_target:
                logger.info(f"\n{'='*60}")
                logger.info(f"🔍 デバッグ詳細: {name}({code})")
                logger.info(f"日付: {latest['Date']}")
                logger.info(f"4本値:")
                logger.info(f"  始値: {open_price:,.0f}円")
                logger.info(f"  高値: {high_price:,.0f}円")
                logger.info(f"  安値: {low_price:,.0f}円")
                logger.info(f"  終値: {close_price:,.0f}円")
                logger.info(f"EMA:")
                logger.info(f"  EMA10: {latest['EMA10']:,.2f}円")
                logger.info(f"  EMA20: {latest['EMA20']:,.2f}円")
                logger.info(f"  EMA50: {latest['EMA50']:,.2f}円")
                logger.info(f"52週高値: {high_52w:,.0f}円")
                logger.info(f"52週高値更新日: {df.iloc[high_52w_date_idx]['Date']} ({days_since_high}日前)")
                logger.info(f"下落率: {pullback_pct:.2f}%")
            
            # EMA10タッチ判定：ローソク足の範囲内にEMAがあるか
            if low_price <= latest['EMA10'] <= high_price:
                touched_emas.append("10EMA")
                self.pullback_stats['ema10_touch'] += 1
            
            # EMA20タッチ判定
            if low_price <= latest['EMA20'] <= high_price:
                touched_emas.append("20EMA")
                self.pullback_stats['ema20_touch'] += 1
            
            # EMA50タッチ判定
            if low_price <= latest['EMA50'] <= high_price:
                touched_emas.append("50EMA")
                self.pullback_stats['ema50_touch'] += 1
            
            if is_debug_target:
                logger.info(f"\nタッチ判定:")
                logger.info(f"  EMA10タッチ: {low_price} <= {latest['EMA10']:.2f} <= {high_price} → {'✅' if '10EMA' in touched_emas else '❌'}")
                logger.info(f"  EMA20タッチ: {low_price} <= {latest['EMA20']:.2f} <= {high_price} → {'✅' if '20EMA' in touched_emas else '❌'}")
                logger.info(f"  EMA50タッチ: {low_price} <= {latest['EMA50']:.2f} <= {high_price} → {'✅' if '50EMA' in touched_emas else '❌'}")
                logger.info(f"タッチしたEMA: {touched_emas if touched_emas else 'なし'}")
                logger.info(f"{'='*60}\n")
            
            if touched_emas:
                self.pullback_stats['any_ema_touch'] += 1
            else:
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
            
            # 全条件通過！
            self.pullback_stats['passed_all'] += 1
            
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
        logger.info(f"  - 200日新高値押し目 EMAフィルター: {PULLBACK_EMA_FILTER}")
        logger.info(f"  - 200日新高値押し目 ストキャスティクス: {'ON' if PULLBACK_STOCHASTIC_FILTER else 'OFF'}")
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
        
        # 間引き処理
        perfect_order_sampled = sample_stocks_balanced(perfect_order, max_per_range=10)
        
        # Supabase保存（元の検出数を保持）
        screening_id = self.sb_client.save_screening_result(
            "perfect_order", datetime.now().strftime('%Y-%m-%d'),
            len(perfect_order), po_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, perfect_order_sampled)
        
        # ボリンジャーバンド
        logger.info("=" * 60)
        logger.info("ボリンジャーバンド±3σスクリーニング開始")
        bb_start = datetime.now()
        bollinger_band = await self.process_stocks_batch(
            stocks, self.screen_stock_bollinger_band, "ボリンジャーバンド"
        )
        bb_time = int((datetime.now() - bb_start).total_seconds() * 1000)
        logger.info(f"ボリンジャーバンド検出: {len(bollinger_band)}銘柄 ({bb_time}ms)")
        
        # 間引き処理
        bollinger_band_sampled = sample_stocks_balanced(bollinger_band, max_per_range=10)
        
        screening_id = self.sb_client.save_screening_result(
            "bollinger_band", datetime.now().strftime('%Y-%m-%d'),
            len(bollinger_band), bb_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, bollinger_band_sampled)
        
        # 200日新高値押し目
        logger.info("=" * 60)
        logger.info("200日新高値押し目スクリーニング開始")
        pb_start = datetime.now()
        week52_pullback = await self.process_stocks_batch(
            stocks, self.screen_stock_200day_pullback, "200日新高値押し目"
        )
        pb_time = int((datetime.now() - pb_start).total_seconds() * 1000)
        logger.info(f"200日新高値押し目検出: {len(week52_pullback)}銘柄 ({pb_time}ms)")
        
        # 間引き処理
        week52_pullback_sampled = sample_stocks_balanced(week52_pullback, max_per_range=10)
        
        # 統計情報を表示
        if hasattr(self, 'pullback_stats'):
            stats = self.pullback_stats
            logger.info("\n" + "="*60)
            logger.info("📊 200日新高値押し目スクリーニング 詳細統計")
            logger.info("="*60)
            logger.info(f"📄 処理対象: {stats['total']:,}銘柄")
            
            if stats['total'] > 0:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄 ({stats['has_data']/stats['total']*100:.1f}%)")
            else:
                logger.info(f"✅ データ取得成功: {stats['has_data']:,}銘柄")
            
            logger.info(f"\n🔹 条件別通過状況:")
            
            if stats['has_data'] > 0:
                logger.info(f"  1️⃣ 60日以内に52週高値更新: {stats['recent_high']:,}銘柄 ({stats['recent_high']/stats['has_data']*100:.2f}%)")
            else:
                logger.info(f"  1️⃣ 60日以内に52週高値更新: {stats['recent_high']:,}銘柄")
            
            if stats['recent_high'] > 0:
                logger.info(f"  2️⃣ 30%以内の押し目: {stats['within_30pct']:,}銘柄 ({stats['within_30pct']/stats['recent_high']*100:.2f}% of 条件1通過)")
            else:
                logger.info(f"  2️⃣ 30%以内の押し目: {stats['within_30pct']:,}銘柄 (条件1通過が0のため計算不可)")
            
            logger.info(f"\n🔹 EMAタッチ別統計:")
            logger.info(f"  🔸 10EMAタッチ: {stats['ema10_touch']:,}銘柄")
            logger.info(f"  🔸 20EMAタッチ: {stats['ema20_touch']:,}銘柄")
            logger.info(f"  🔸 50EMAタッチ: {stats['ema50_touch']:,}銘柄")
            
            if stats['within_30pct'] > 0:
                logger.info(f"  ✅ いずれかのEMAタッチ: {stats['any_ema_touch']:,}銘柄 ({stats['any_ema_touch']/stats['within_30pct']*100:.2f}% of 条件2通過)")
            else:
                logger.info(f"  ✅ いずれかのEMAタッチ: {stats['any_ema_touch']:,}銘柄 (条件2通過が0のため計算不可)")
            
            logger.info(f"\n⭐ 全条件通過: {stats['passed_all']:,}銘柄")
            logger.info("="*60 + "\n")
        
        screening_id = self.sb_client.save_screening_result(
            "200day_pullback", datetime.now().strftime('%Y-%m-%d'),
            len(week52_pullback), pb_time  # 元の検出数
        )
        if screening_id:
            self.sb_client.save_detected_stocks(screening_id, week52_pullback_sampled)
        
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
            "200day_pullback": week52_pullback,
            "squeeze": squeeze
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
                "200day_pullback": 0
            }
        }
        
        for data in history.values():
            stats["avg_detections"]["perfect_order"] += len(data.get("perfect_order", []))
            stats["avg_detections"]["bollinger_band"] += len(data.get("bollinger_band", []))
            stats["avg_detections"]["200day_pullback"] += len(data.get("200day_pullback", []))
        
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
        screener = StockScreener()
        
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
        
        # 6954が銘柄リストに含まれているか確認
        stock_6954 = next((s for s in all_stocks if s.get("Code") == "6954"), None)
        if stock_6954:
            logger.info(f"⚡⚡⚡ 6954が銘柄リストに存在: {stock_6954}")
        else:
            logger.error(f"❌ 6954が銘柄リストに存在しません！")
            # 全銘柄リストから検索
            stock_6954_all = next((s for s in all_stocks_data if s.get("Code") == "6954"), None)
            if stock_6954_all:
                logger.info(f"⚡ 6954は全銘柄リストに存在: {stock_6954_all}")
                logger.info(f"⚡ MarketCode: {stock_6954_all.get('MarketCode')}")
            else:
                logger.error(f"❌ 6954は全銘柄リストにも存在しません！")
        
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
            logger.info(f"  - 200日新高値押し目: {stats['avg_detections']['200day_pullback']}銘柄/日")
        
        logger.info("=" * 60)
        logger.info("日次データ収集完了")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))

