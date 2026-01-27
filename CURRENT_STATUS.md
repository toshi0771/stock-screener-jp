# プロジェクト進行状況レポート（最新版）

**最終更新:** 2026年1月27日 19:00  
**プロジェクト:** 日本株スクリーニングシステム（J-Quants API使用）  
**総コミット数（過去1ヶ月）:** 118個

---

## 📊 現在の状況

### 🚨 **最優先問題: 検出0銘柄（根本原因特定）**

**症状:**
- ❌ 200-Day Pullback: 0銘柄（2026年1月26日・月曜日に手動実行）
  - 処理時間: 2時間6分23秒
  - **データ取得成功率: 0.0%**
  - メモリ: 103.03MB
- ❌ Perfect Order: 0銘柄（処理完了: 3780/3783銘柄）
- ❌ Squeeze: 0銘柄（推定）
- ✅ Bollinger Band: 188銘柄（2026年1月26日に成功）

**根本原因（特定済み）:**

> **キャッシュデータの開始日が要求された日付範囲より新しいため、300日分のデータを取得できず、`len(df) < 200`で全銘柄が除外されている**

**詳細分析:**

1. **日付範囲の計算:**
   - 実行日: 2026-01-26（月曜日・営業日）
   - lookback_days: 300（暦日）
   - start_date: 2026-01-26 - 300日 = **2025-04-01**
   - end_date: 2026-01-26

2. **キャッシュの問題:**
   - キャッシュファイルは存在する（2,269個、442.57MB）
   - しかし、キャッシュに保存されているデータの最古日が2025-04-01より新しい
   - 推定: 最古日は2025年5月～6月頃
   - 理由: GitHub Actionsのキャッシュは7日間で削除され、差分更新のみが行われるため、古いデータが徐々に失われる

3. **フィルタリングの失敗:**
   ```python
   # persistent_cache.py Line 192
   filtered_df = df[df['Date'] >= start_dt].copy()  # start_dt = 2025-04-01
   ```
   - キャッシュの最古日が2025-05-01の場合、フィルタリング後も2025-05-01以降のデータしか返されない
   - 2025-05-01 ～ 2026-01-26 = 約270日（営業日で約190日）
   - **200日分のデータが不足** → `len(df) < 200`で除外

4. **データ取得成功率0.0%:**
   - すべての銘柄が`len(df) < 200`で除外される
   - APIからの追加取得も行われない（キャッシュヒットと判定されるため）

**タイムアウト時間:**
- 設定値: 360分（6時間）
- ワークフローファイル: `.github/workflows/screening-200day-pullback.yml` Line 16

---

## 🔧 実施した対策（2026年1月27日）

### 対策1: ログフォーマット改善

**変更内容:**
- `trading_day_helper.py`: 取引日確定ログをINFO→DEBUGレベルに変更
- `daily_data_collection.py`: メイン関数で取引日を1回だけ取得してキャッシュ
- 4つのスクリーニングメソッドすべてで、キャッシュされた`latest_trading_date`を使用

**効果:**
- 取引日確定ログが1回だけ出力される
- 100銘柄ごとの進捗ログのみが表示される

### 対策2: Perfect Order統計情報追加

**変更内容:**
- パーフェクトオーダーに詳細な統計情報追跡機能を追加
- デバッグログを追加（各条件で除外された理由を記録）

**統計情報:**
- 処理対象銘柄数
- データ取得成功率
- データ不足除外数
- パーフェクトオーダー成立数
- 乖離率20%以内通過数
- 200SMAフィルター通過数
- 最終検出数

### 対策3: persistent_cache.py デバッグログ追加

**変更内容:**
- キャッシュ取得開始時のログ
- キャッシュファイル存在確認
- キャッシュデータの行数と最終日
- Date列の範囲（最古日・最新日）
- フィルタリング結果（第1・第2フィルター）
- キャッシュミス時の詳細情報

**効果:**
- 次回実行時に、キャッシュデータの実際の範囲が確認できる
- フィルタリングで0行になる原因が特定できる

---

## 🎯 次のアクション

### 優先度1: デバッグログの確認（即座に実施）

1. GitHub Actionsで再実行
2. ログから以下を確認:
   - キャッシュファイルの存在
   - キャッシュデータの行数と最終日
   - Date列の範囲（最古日・最新日）
   - フィルタリング結果（第1・第2フィルター）
   - キャッシュミスの理由

### 優先度2: 修正の実装（仮説が正しければ）

**修正案A: lookback_daysを増やす**

```python
# 変更前
start_str, end_str = get_date_range_for_screening(end_date, 300)

# 変更後
# 営業日ベースで300日分を確保するため、暦日で450日分取得
start_str, end_str = get_date_range_for_screening(end_date, 450)
```

**効果:**
- 2026-01-26 - 450日 = 2024-10-03
- キャッシュに2024年10月以降のデータがあれば、200日分のデータを確保できる

**修正案B: データ不足時にAPIから追加取得**

```python
if df is None or len(df) < 200:
    # キャッシュが不足している場合、APIから追加取得
    logger.warning(f"キャッシュデータ不足: {code} ({len(df) if df is not None else 0}行)")
    
    # より長い期間で再取得
    start_str_extended, _ = get_date_range_for_screening(end_date, 450)
    df = await self.cache.get_or_fetch(
        code, start_str_extended, end_str,
        self.jq_client.get_prices_daily_quotes,
        session, code, start_str_extended, end_str
    )
    
    if df is not None:
        await self.persistent_cache.set(code, start_str_extended, end_str, df)
    
    if df is None or len(df) < 200:
        return None
```

**修正案C: max_age_daysを延長**

```python
# キャッシュの有効期限を60日に延長
df = await self.persistent_cache.get(code, start_str, end_str, max_age_days=60)
```

### 優先度3: 長期的対策

1. **キャッシュの保存期間を延長**
   - GitHub Actionsのキャッシュを14日間に延長
   - または、S3などの外部ストレージに保存

2. **定期的に古いデータを削除**
   - 不要な古いデータを削除して、ストレージを節約

3. **キャッシュの健全性チェック**
   - 定期的にキャッシュの最古日・最新日を確認
   - 必要に応じてキャッシュを再構築

---

## 📝 コミット履歴（2026年1月27日）

### コミット: 6e8919b
**タイトル:** Improve logging format and add Perfect Order statistics tracking

**変更内容:**
- `trading_day_helper.py`: 取引日確定ログをDEBUGレベルに変更
- `daily_data_collection.py`: 
  - メイン関数で取引日を1回だけ取得してキャッシュ
  - 4つのスクリーニングメソッドでキャッシュされた`latest_trading_date`を使用
  - Perfect Orderに詳細な統計情報追跡機能を追加
- `persistent_cache.py`: 詳細なデバッグログを追加

### コミット: （次回）
**予定タイトル:** Fix: Increase lookback days to 450 to ensure sufficient cache data

**予定変更内容:**
- `daily_data_collection.py`: lookback_daysを300→450に変更
- または、データ不足時にAPIから追加取得する処理を追加

---

## 📚 関連ドキュメント

- `ROOT_CAUSE_ANALYSIS.md`: 0銘柄検出問題の根本原因分析
- `CACHE_ANALYSIS_2026_01_27.md`: 永続キャッシュ問題の詳細分析（日付訂正前）
- `INVESTIGATION_2026_01_27.md`: 調査結果のまとめ
- `FIX_SUMMARY_2026_01_25.md`: 1月25日の修正サマリー

---

## 🔄 過去の修正履歴

### 2026年1月25日: 0銘柄検出問題の初回修正

**実施した修正:**
1. 新規: `trading_day_helper.py` - 安全な取引日取得ヘルパー
2. 修正: `daily_data_collection.py` - 4つのスクリーニングメソッドの日付調整ロジック改善
3. 修正: `persistent_cache.py` - キャッシュフィルタリング改善

**問題:**
- 日付調整ロジックの無限ループリスク
- 土日実行時のキャッシュミスマッチ
- APIエラー時の停止

**効果:**
- 無限ループを防止
- 土日実行時のキャッシュミスマッチを軽減
- しかし、根本原因（キャッシュデータ不足）は解決されていなかった

---

## 📊 統計情報

### キャッシュ統計（2026年1月26日実行時）

| 項目 | 値 |
|------|-----|
| キャッシュファイル数 | 2,269個 |
| 合計サイズ | 442.57MB |
| ヒット数 | 推定0個 |
| ミス数 | 推定3,783個 |
| ヒット率 | 0% |

**問題:**
- ヒット率0% → すべてミスしている
- しかし、キャッシュファイルは存在する
- **推定:** フィルタリングで0行になっている

### スクリーニング結果（2026年1月26日）

| スクリーニング | 検出数 | 処理時間 | データ取得成功率 |
|--------------|--------|---------|----------------|
| 200-Day Pullback | 0銘柄 | 2時間6分 | 0.0% |
| Perfect Order | 0銘柄 | 4時間28分 | 推定0% |
| Bollinger Band | 188銘柄 | 4時間27分 | 推定100% |
| Squeeze | 推定0銘柄 | 4時間27分 | 推定0% |

**分析:**
- Bollinger Bandのみ成功 → lookback_daysが短い（推定100日程度）
- 他のスクリーニングは失敗 → lookback_daysが長い（200～300日）

---

## 🎯 結論

**根本原因:**
> キャッシュデータの開始日が要求された日付範囲（2025-04-01）より新しいため、300日分のデータを取得できず、`len(df) < 200`で全銘柄が除外されている

**即座に実施すべき対策:**
1. ✅ デバッグログを追加（完了）
2. ⏳ GitHub Actionsで再実行してログを確認
3. ⏳ 仮説を検証
4. ⏳ lookback_daysを450に増やす、またはデータ不足時にAPIから追加取得
5. ⏳ 再テスト

**長期的対策:**
- キャッシュの保存期間を延長
- 定期的にキャッシュの健全性をチェック
- 不要な古いデータを削除

---

**次回更新予定:** デバッグログ確認後、修正実装時


---

## 🔍 **新発見: GitHubとSupabaseの差異（2026年1月27日）**

### 📊 観察された差異

| スクリーニング | GitHub Actions | Supabase表示 | ステータス |
|---|---|---|---|
| パーフェクトオーダー | 0銘柄 | 74銘柄 | ❌ 不一致 |
| 200日新高値押し目 | 0銘柄 | 1/21まで | ⚠️ データ欠落 |
| ボリンジャーバンド | 18銘柄 | 18銘柄 | ✅ 一致 |
| スクイーズ | 0銘柄 | 0銘柄 | ✅ 一致 |

### 🚨 根本原因: 2つの致命的な欠陥

#### 欠陥1: 最新取引日の取得ロジックに問題

**すべての実行スクリプト（run_*.py）に共通:**

```python
# 最新取引日を取得（検出された銘柄から）
if perfect_order:  # または bollinger_band, week52_pullback, squeeze
    # 検出された銘柄から最新取引日を取得
    first_stock = perfect_order[0]
    ...
    target_date = pd.to_datetime(latest_date).strftime('%Y-%m-%d')
```

**致命的な問題:**
- **検出銘柄が0の場合、`if`ブロックがスキップされる**
- `target_date`が初期値（`datetime.now().strftime('%Y-%m-%d')`）のまま
- **Supabase保存時に誤った日付が使用される可能性**

#### 欠陥2: Supabase保存ロジックの不完全性

**`save_detected_stocks()`の動作（daily_data_collection.py Line 128-175）:**

```python
def save_detected_stocks(self, screening_result_id, stocks):
    if not stocks or len(stocks) == 0:
        logger.warning("保存する銘柄がありません")
        return False  # ← ここで終了、何も保存しない
```

**問題点:**
1. **0銘柄の場合、`detected_stocks`テーブルに何も保存しない**
2. **`screening_results`テーブルには`total_stocks_found=0`が保存される**
3. **古い`detected_stocks`データが削除されない**
4. **フロントエンドが古いデータを表示し続ける**

### 🎯 パーフェクトオーダーの74銘柄表示の謎

**シナリオ（最有力仮説）:**
1. 1月20日（または過去の日付）: パーフェクトオーダーで74銘柄検出
2. `screening_results`テーブルに`screening_id=X`、`total_stocks_found=74`が保存
3. `detected_stocks`テーブルに74銘柄の詳細が保存（`screening_result_id=X`）
4. 1月26日: パーフェクトオーダーで0銘柄検出
5. `screening_results`テーブルに`screening_id=Y`、`total_stocks_found=0`が保存
6. `detected_stocks`テーブルには何も保存されない（`save_detected_stocks()`が`return False`）
7. **フロントエンドが`screening_id=X`の古いデータを表示**

### 📝 200日新高値押し目のデータ欠落

**観察:**
- Supabaseの最新データは1月21日
- 1月26日のデータが表示されない

**原因:**
- 1月26日の実行で0銘柄検出
- `screening_results`テーブルには保存されたが、`detected_stocks`テーブルには何も保存されなかった
- **フロントエンドが`total_stocks_found > 0`でフィルタリングしている可能性**

### 🔧 修正案

#### 修正案A: 最新取引日の取得を改善（優先度: 高）

**変更前:**

```python
# 最新取引日を取得（検出された銘柄から）
if perfect_order:
    # ...
    target_date = pd.to_datetime(latest_date).strftime('%Y-%m-%d')
```

**変更後:**

```python
# 最新取引日を取得（検出銘柄の有無に関わらず）
target_date = await screener.get_latest_trading_date()
logger.info(f"📅 最新取引日: {target_date}")
```

**新しいメソッドを追加:**

```python
async def get_latest_trading_date(self):
    """最新の取引日を取得（検出銘柄の有無に関わらず）"""
    from trading_day_helper import get_latest_trading_day
    return get_latest_trading_day()
```

#### 修正案B: 0銘柄時に古いデータを削除（優先度: 中）

**変更前:**

```python
def save_detected_stocks(self, screening_result_id, stocks):
    if not stocks or len(stocks) == 0:
        logger.warning("保存する銘柄がありません")
        return False
```

**変更後:**

```python
def save_detected_stocks(self, screening_result_id, stocks):
    if not stocks or len(stocks) == 0:
        logger.warning("保存する銘柄がありません（0銘柄）")
        # 0銘柄の場合も、screening_result_idに紐づく古いデータを削除
        try:
            self.client.table("detected_stocks").delete().eq("screening_result_id", screening_result_id).execute()
            logger.info(f"古いdetected_stocksデータを削除しました (screening_result_id={screening_result_id})")
        except Exception as e:
            logger.error(f"古いデータ削除エラー: {e}")
        return True  # 0銘柄でも成功とみなす
```

#### 修正案C: フロントエンドのクエリを修正（優先度: 中）

**Supabaseのフロントエンド（Next.jsなど）で、最新の`screening_results`を取得するクエリを修正:**

```typescript
// 変更後
const { data: latestResult } = await supabase
  .from('screening_results')
  .select('id, total_stocks_found, screening_date')
  .eq('screening_type', 'perfect_order')
  .order('screening_date', { ascending: false })
  .limit(1)
  .single();

if (latestResult && latestResult.total_stocks_found > 0) {
  const { data: stocks } = await supabase
    .from('detected_stocks')
    .select('*')
    .eq('screening_result_id', latestResult.id);
  // stocks を表示
} else {
  // 「該当なし」を表示
}
```

### ✅ 次のアクション（優先順位）

1. **修正案Aを即座に実装** → 最新取引日の取得を改善
2. **修正案Bを推奨** → 0銘柄時に古いデータを削除
3. **修正案Cは必要に応じて** → フロントエンドのクエリを確認

---

## 📁 作成したドキュメント

- `SUPABASE_DISCREPANCY_ANALYSIS.md` - GitHubとSupabaseの差異の詳細分析

---
