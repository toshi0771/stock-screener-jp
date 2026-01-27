# 永続キャッシュ問題の詳細分析

**作成日:** 2026年1月27日  
**対象:** persistent_cache.py  
**問題:** 200日新高値押し目スクリーニングで検出0銘柄

---

## 📋 実行結果の確認

### 1_27_200n2.jpg（実行ログ）

**実行環境:**
- 実行日: 2026-01-26（日曜日）
- 契約日確定: 2026-01-26
- キャッシュヒット: 55MB（57,828,125 B）
- 永続キャッシュディレクトリ: /home/runner/.cache/stock_prices

**処理状況:**
- 100/3783銘柄処理完了
- 200/3783銘柄処理完了
- 300/3783銘柄処理完了
- ...（続く）

### 1_27_200n1.jpg（最終結果）

**スクリーニング結果:**
- ✅ 処理完了: 2時間6分23秒
- ❌ **検出: 0銘柄**
- メモリ: 103.03MB
- **データ取得成功: 0銘柄（0.0%）**

**条件別通過状況:**
- 条件別通過状況: すべて0銘柄
- EMAタッチ別統計: すべて0銘柄
- 10EMAタッチ: 0銘柄
- 20EMAタッチ: 0銘柄
- 50EMAタッチ: 0銘柄
- 全条件通過: 0銘柄

---

## 🔍 根本原因の特定

### 問題1: 週末実行時の日付ミスマッチ

**症状:**
- 実行日: 2026-01-26（日曜日）
- 契約日確定: 2026-01-26（日曜日のまま）
- **週末のデータは存在しない**

**原因:**
- `trading_day_helper.py`の`get_latest_trading_day()`が正しく動作していない可能性
- または、呼び出し側で週末調整が行われていない

**コード確認（daily_data_collection.py Line 852）:**
```python
# キャッシュされた最新の取引日を使用
end_date = self.latest_trading_date
```

**推定:**
- `self.latest_trading_date`が2026-01-26（日曜日）になっている
- 本来は2026-01-24（金曜日）になるべき

### 問題2: persistent_cache.get()のフィルタリングロジック

**コード確認（persistent_cache.py Line 160-185）:**
```python
# 必要な期間のデータを抽出
try:
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
        
        # end_dt が最新データより新しい場合、start_dt以降のすべてのデータを返す
        # （土日実行時のキャッシュミスマッチ対策）
        filtered_df = df[df['Date'] >= start_dt].copy()
        if len(filtered_df) > 0:
            self.hits += 1
            logger.debug(f"キャッシュヒット（部分）: {stock_code} ({len(filtered_df)}行, end_dt超過)")
            return filtered_df
        else:
            logger.debug(f"キャッシュに必要な期間のデータなし: {stock_code}")
            self.misses += 1
            return None
```

**分析:**

1. **第1フィルター（Line 167）:**
   - 条件: `df['Date'] >= start_dt & df['Date'] <= end_dt`
   - start_dt: 2025-03-31頃（300日前）
   - end_dt: 2026-01-26（日曜日）
   - **問題:** キャッシュの最新データは2026-01-24（金曜日）まで
   - **結果:** `df['Date'] <= 2026-01-26`は満たすが、2026-01-26のデータは存在しない

2. **第2フィルター（Line 177）:**
   - 条件: `df['Date'] >= start_dt`
   - **目的:** end_dtが最新データより新しい場合の対策
   - **問題:** このロジックは正しいはずだが、なぜ0行になるのか？

### 問題3: start_dtの計算ミス

**推定される問題:**
- `get_date_range_for_screening(end_date, 300)`の計算が間違っている可能性
- end_date = 2026-01-26（日曜日）
- start_date = 2026-01-26 - 300日 = 2025-03-31頃

**しかし、キャッシュに保存されているデータは:**
- 最新日: 2026-01-24（金曜日）
- 最古日: 不明（おそらく2025年の日付）

**可能性1: start_dtが未来の日付になっている**
- もし`get_date_range_for_screening()`が営業日ベースで計算している場合
- start_dtが実際のキャッシュデータより新しくなる可能性がある

**可能性2: キャッシュが空**
- キャッシュファイルは存在するが、中身が空の可能性
- または、Date列が存在しない

### 問題4: データ取得成功率0.0%

**症状:**
- データ取得成功: 0銘柄（0.0%）
- これは`df is None or len(df) < 200`で除外されている

**原因:**
- `persistent_cache.get()`が`None`を返している
- または、返されたDataFrameの行数が200未満

**推定フロー:**
1. `persistent_cache.get(code, start_str, end_str)` → `None`を返す
2. `cache.get_or_fetch()` → APIから取得を試みる
3. しかし、日曜日なので最新データは金曜日まで
4. 取得したデータを`persistent_cache.set()`で保存
5. しかし、次の銘柄でも同じ問題が発生

**なぜAPIから取得しないのか？**
- 可能性1: キャッシュヒットしているため、APIを呼ばない
- 可能性2: APIから取得しても、フィルタリングで0行になる

---

## 🐛 バグの特定

### バグ1: get_date_range_for_screening()の問題

**コード確認（trading_day_helper.py）:**
```python
def get_date_range_for_screening(end_date: datetime, days: int) -> Tuple[str, str]:
    """
    スクリーニング用の日付範囲を計算
    
    Args:
        end_date: 終了日（datetime）
        days: 遡る日数
    
    Returns:
        (start_str, end_str)のタプル（YYYYMMDD形式）
    """
    start_date = end_date - timedelta(days=days)
    return start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')
```

**問題:**
- `days=300`は暦日ベースの日数
- しかし、株価データは営業日ベースでしか存在しない
- 300暦日 ≈ 215営業日（土日祝日を除く）

**影響:**
- start_date = 2026-01-26 - 300日 = 2025-03-31
- しかし、キャッシュには2025-03-31のデータが存在しない可能性
- 実際の営業日は2025-04-01以降から始まる可能性

### バグ2: persistent_cache.get()のフィルタリング

**問題の再現:**
1. end_dt = 2026-01-26（日曜日）
2. キャッシュの最新データ = 2026-01-24（金曜日）
3. 第1フィルター: `df['Date'] <= 2026-01-26` → 2026-01-24までのデータを返す（正常）
4. しかし、なぜか0行になる

**推定原因:**
- start_dtの計算が間違っている
- または、キャッシュに保存されているDataFrameが空

### バグ3: latest_trading_dateが週末のまま

**問題:**
- `self.latest_trading_date`が2026-01-26（日曜日）になっている
- 本来は`get_latest_trading_day()`で2026-01-24（金曜日）に調整されるべき

**推定原因:**
- `get_latest_trading_day()`が正しく動作していない
- または、呼び出されていない

---

## 🔧 修正案

### 修正1: get_latest_trading_day()の確認

**確認事項:**
1. `get_latest_trading_day()`が正しく呼ばれているか
2. 戻り値が正しく`self.latest_trading_date`に設定されているか
3. 週末・祝日の調整が正しく動作しているか

### 修正2: persistent_cache.get()のデバッグログ追加

**追加するログ:**
```python
logger.info(f"🔍 キャッシュ取得: {stock_code}")
logger.info(f"  start_date: {start_date}, end_date: {end_date}")
logger.info(f"  キャッシュファイル: {cache_path.exists()}")
if result is not None:
    df, last_date = result
    logger.info(f"  キャッシュデータ: {len(df)}行, 最終日: {last_date}")
    logger.info(f"  Date範囲: {df['Date'].min()} ~ {df['Date'].max()}")
    logger.info(f"  フィルター後: {len(filtered_df)}行")
```

### 修正3: get_date_range_for_screening()の改善

**改善案:**
- 営業日ベースで日数を計算する
- または、余裕を持って350日分取得する

```python
def get_date_range_for_screening(end_date: datetime, days: int) -> Tuple[str, str]:
    """
    スクリーニング用の日付範囲を計算（余裕を持たせる）
    
    Args:
        end_date: 終了日（datetime）
        days: 必要な営業日数
    
    Returns:
        (start_str, end_str)のタプル（YYYYMMDD形式）
    """
    # 営業日ベースでdays日分を確保するため、暦日で1.5倍の余裕を持たせる
    calendar_days = int(days * 1.5)
    start_date = end_date - timedelta(days=calendar_days)
    return start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')
```

### 修正4: データ取得成功率の確認

**確認事項:**
1. `persistent_cache.get()`が`None`を返す理由
2. `cache.get_or_fetch()`が呼ばれているか
3. APIから取得したデータが正しく保存されているか

---

## 📊 統計情報

### キャッシュ統計（推定）

| 項目 | 値 |
|------|-----|
| キャッシュファイル数 | 2,269個 |
| 合計サイズ | 442.57MB |
| ヒット数 | 0個 |
| ミス数 | 0個 |
| ヒット率 | 0% |

**問題:**
- ヒット数が0 → すべてミスしている
- しかし、キャッシュファイルは存在する（2,269個）
- **推定:** フィルタリングで0行になっている

---

## 🎯 次のアクション

### 優先度1: デバッグログの追加

1. `persistent_cache.get()`に詳細ログを追加
2. `get_latest_trading_day()`の戻り値を確認
3. `get_date_range_for_screening()`の計算結果を確認

### 優先度2: 修正の実装

1. `get_date_range_for_screening()`を改善（余裕を持たせる）
2. `persistent_cache.get()`のフィルタリングロジックを見直し
3. `get_latest_trading_day()`の動作を確認

### 優先度3: テスト実行

1. デバッグログを追加した状態で再実行
2. ログから問題箇所を特定
3. 修正を実装して再テスト

---

## 📝 結論

**根本原因（推定）:**

1. **latest_trading_dateが週末のまま**
   - `self.latest_trading_date`が2026-01-26（日曜日）
   - 本来は2026-01-24（金曜日）になるべき

2. **persistent_cache.get()のフィルタリングで0行**
   - end_dt = 2026-01-26（日曜日）
   - キャッシュの最新データ = 2026-01-24（金曜日）
   - フィルタリング後に0行になる原因が不明

3. **start_dtの計算ミス**
   - 300暦日で計算しているため、営業日ベースで不足する可能性

**最優先対策:**
- デバッグログを追加して、実際の動作を確認する
- `get_latest_trading_day()`が正しく動作しているか確認
- `persistent_cache.get()`のフィルタリングロジックを見直す

**タイムアウト時間:**
- ワークフローファイルを確認する必要がある
- ユーザーによると6時間（12時間ではない）
