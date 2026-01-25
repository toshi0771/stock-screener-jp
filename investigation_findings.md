# 0銘柄検出問題の調査結果

**調査日時:** 2026年1月25日  
**調査対象:** 200-Day Pullback, Perfect Order, Squeeze スクリーニング

---

## 🔍 発見した問題点

### 1. **キャッシュが空の状態**
- ローカルサンドボックスの `~/.cache/stock_prices` にキャッシュファイルが0個
- GitHub Actionsではキャッシュが存在する可能性があるが、ローカルでは確認不可

### 2. **日付調整ロジックの潜在的な問題**

#### 問題箇所（daily_data_collection.py）

**200-Day Pullback (Line 843-854):**
```python
end_date = datetime.now()
# 休場日の場合、前営業日に調整（土日・祝日対応）
while end_date.weekday() >= 5:  # 5=土曜, 6=日曜
    end_date = end_date - timedelta(days=1)
# 祝日チェック（J-Quants API使用）
is_trading = await self.jq_client.is_trading_day(session, end_date.strftime("%Y-%m-%d"))
while not is_trading:
    end_date = end_date - timedelta(days=1)
    # 週末をスキップ
    while end_date.weekday() >= 5:
        end_date = end_date - timedelta(days=1)
    is_trading = await self.jq_client.is_trading_day(session, end_date.strftime("%Y-%m-%d"))
```

**問題点:**
- ネストされた `while` ループが無限ループになる可能性
- `is_trading_day()` APIが連続で呼ばれると、レート制限に引っかかる可能性
- エラーハンドリングがないため、API障害時に停止する

**Perfect Order (Line 644-655):** 同様の問題
**Squeeze (Line 1031-1044):** 同様の問題（CURRENT_STATUS.mdに記載）

### 3. **データ不足判定が厳しすぎる可能性**

```python
if df is None or len(df) < 200:  # 約8ヶ月分のデータがあればOK
    return None
```

- 営業日ベースで200日 = 約10ヶ月分
- 新規上場銘柄や、データ欠損がある銘柄は除外される
- キャッシュから取得したデータが期間フィルタリングされた後、200行未満になる可能性

### 4. **キャッシュの日付フィルタリング問題**

**persistent_cache.py (Line 160-177):**
```python
# 必要な期間のデータを抽出
if 'Date' in df.columns:
    df['Date'] = pd.to_datetime(df['Date'])
    start_dt = pd.to_datetime(start_date, format='%Y%m%d')
    end_dt = pd.to_datetime(end_date, format='%Y%m%d')
    
    filtered_df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)].copy()
    
    # 必要な期間のデータが十分にあるか確認
    if len(filtered_df) > 0:
        self.hits += 1
        logger.debug(f"キャッシュヒット: {stock_code} ({len(filtered_df)}行)")
        return filtered_df
    else:
        logger.debug(f"キャッシュに必要な期間のデータなし: {stock_code}")
        self.misses += 1
        return None
```

**問題点:**
- キャッシュに古いデータがある場合、`end_dt` が最新取引日より新しいと、フィルタ後に0行になる
- 例: キャッシュの最終日が2026-01-24、リクエストが2026-01-25の場合、フィルタ結果が0行

---

## 💡 推定される根本原因

### シナリオ1: 土日実行時のキャッシュミスマッチ
1. **金曜日（1/24）**: Bollinger Bandが実行され、キャッシュ作成（最終日=2026-01-24）
2. **土曜日（1/25）**: 他のスクリーニングが実行
3. 日付調整ロジックで `end_date` が 2026-01-24（金曜日）に調整される
4. キャッシュから取得を試みるが、`end_str = "20260124"` でフィルタリング
5. **しかし、`datetime.now()` が土曜日の場合、調整前の日付でキャッシュキーが生成される可能性**

### シナリオ2: 日付調整ロジックの無限ループ
1. `is_trading_day()` APIが何らかの理由で常に `False` を返す
2. 無限ループに入り、タイムアウトまで実行
3. 結果として0銘柄検出

### シナリオ3: データ不足による除外
1. キャッシュから取得したデータが期間フィルタリングされる
2. フィルタ後のデータが200行未満
3. すべての銘柄が `len(df) < 200` で除外される

---

## 🔧 推奨される修正案

### 修正1: 日付調整ロジックの改善

```python
async def get_latest_trading_day(self, session: aiohttp.ClientSession) -> datetime:
    """最新の取引日を取得（安全な実装）"""
    end_date = datetime.now()
    max_attempts = 10
    attempts = 0
    
    while attempts < max_attempts:
        # 週末をスキップ
        while end_date.weekday() >= 5:
            end_date = end_date - timedelta(days=1)
        
        # 祝日チェック
        try:
            is_trading = await self.jq_client.is_trading_day(session, end_date.strftime("%Y-%m-%d"))
            if is_trading:
                return end_date
        except Exception as e:
            logger.warning(f"is_trading_day() API エラー: {e}")
            # APIエラー時は前日に戻る
            end_date = end_date - timedelta(days=1)
            attempts += 1
            continue
        
        # 非取引日の場合、前日に戻る
        end_date = end_date - timedelta(days=1)
        attempts += 1
    
    # 最大試行回数を超えた場合、現在日時から5営業日前を返す
    logger.error(f"取引日の取得に失敗しました。デフォルトで5日前を使用します。")
    return datetime.now() - timedelta(days=7)
```

### 修正2: データ不足判定の緩和

```python
# 200日ではなく、150日（約7ヶ月）に緩和
if df is None or len(df) < 150:
    return None
```

### 修正3: キャッシュフィルタリングの改善

```python
# persistent_cache.py の get() メソッド
# end_date が最新データより新しい場合、最新データまでを返す
if len(filtered_df) == 0:
    # end_dt が最新データより新しい場合、start_dt以降のすべてのデータを返す
    filtered_df = df[df['Date'] >= start_dt].copy()
    if len(filtered_df) > 0:
        self.hits += 1
        logger.debug(f"キャッシュヒット（部分）: {stock_code} ({len(filtered_df)}行)")
        return filtered_df
```

### 修正4: デバッグログの追加

```python
# スクリーニング開始時にログ出力
logger.info(f"スクリーニング開始: end_date={end_date.strftime('%Y-%m-%d')}, start_date={start_date.strftime('%Y-%m-%d')}")
logger.info(f"リクエスト期間: {start_str} ～ {end_str}")

# データ取得後にログ出力
if df is not None:
    logger.info(f"データ取得成功: {code} - {len(df)}行")
else:
    logger.info(f"データ取得失敗: {code}")
```

---

## 📋 次のアクション

1. **修正1を実装**: 日付調整ロジックを安全な実装に変更
2. **修正2を実装**: データ不足判定を150行に緩和
3. **修正3を実装**: キャッシュフィルタリングを改善
4. **修正4を実装**: デバッグログを追加
5. **テスト実行**: ローカルまたはGitHub Actionsで手動実行
6. **結果確認**: 検出銘柄数を確認

---

## 🎯 優先度

**最優先（High）:**
- 修正1: 日付調整ロジックの改善（無限ループリスク）
- 修正4: デバッグログの追加（問題の可視化）

**高優先度（Medium）:**
- 修正3: キャッシュフィルタリングの改善（キャッシュミスマッチ）

**中優先度（Low）:**
- 修正2: データ不足判定の緩和（影響範囲が限定的）
