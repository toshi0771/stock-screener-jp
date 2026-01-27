# Supabase表示とGitHub Actions結果の差異分析

**日時:** 2026年1月27日  
**調査対象:** 4つのスクリーニング実行スクリプト

---

## 📊 観察された差異

### 1. パーフェクトオーダー（1月26日）
- **GitHub Actions**: 検出0銘柄
- **Supabase**: 表示74銘柄
- **ステータス**: ❌ 不一致

### 2. 200日新高値押し目（1月26日）
- **GitHub Actions**: 検出0銘柄
- **Supabase**: 最新は1月21日（1月26日のデータなし）
- **ステータス**: ⚠️ データ欠落

### 3. ボリンジャーバンド（1月26日）
- **GitHub Actions**: 検出18銘柄
- **Supabase**: 表示18銘柄
- **ステータス**: ✅ 一致

### 4. スクイーズ（1月26日）
- **GitHub Actions**: 検出0銘柄
- **Supabase**: 表示0銘柄
- **ステータス**: ✅ 一致

---

## 🔍 根本原因の特定

### 問題1: 最新取引日の取得ロジックに欠陥

**すべてのスクリプトに共通する問題:**

```python
# 最新取引日を取得（検出された銘柄から）
if perfect_order:  # または bollinger_band, week52_pullback, squeeze
    # 検出された銘柄から最新取引日を取得
    first_stock = perfect_order[0]
    ...
    target_date = pd.to_datetime(latest_date).strftime('%Y-%m--%d')
```

**致命的な欠陥:**
- **検出銘柄が0の場合、`if`ブロックがスキップされる**
- `target_date`が初期値（`datetime.now().strftime('%Y-%m-%d')`）のまま
- **Supabase保存時に誤った日付が使用される**

### 問題2: Supabase保存ロジックの不完全性

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

---

## 🎯 パーフェクトオーダーの74銘柄表示の謎

### 仮説1: 古いデータが残っている（最有力）

**シナリオ:**
1. 1月20日（または過去の日付）: パーフェクトオーダーで74銘柄検出
2. `screening_results`テーブルに`screening_id=X`、`total_stocks_found=74`が保存
3. `detected_stocks`テーブルに74銘柄の詳細が保存（`screening_result_id=X`）
4. 1月26日: パーフェクトオーダーで0銘柄検出
5. `screening_results`テーブルに`screening_id=Y`、`total_stocks_found=0`が保存
6. `detected_stocks`テーブルには何も保存されない（`save_detected_stocks()`が`return False`）
7. **フロントエンドが`screening_id=X`の古いデータを表示**

### 仮説2: フロントエンドのクエリロジックに問題

**推定されるクエリ:**

```sql
-- 間違ったクエリ（古いデータを表示）
SELECT * FROM detected_stocks
WHERE screening_result_id IN (
  SELECT id FROM screening_results
  WHERE screening_type = 'perfect_order'
  AND total_stocks_found > 0  -- ← この条件が問題
  ORDER BY screening_date DESC
  LIMIT 1
)
```

**正しいクエリ:**

```sql
-- 正しいクエリ（最新の日付を表示、0銘柄でもOK）
SELECT * FROM detected_stocks
WHERE screening_result_id = (
  SELECT id FROM screening_results
  WHERE screening_type = 'perfect_order'
  ORDER BY screening_date DESC
  LIMIT 1
)
```

---

## 🔧 修正案

### 修正案A: 最新取引日の取得を改善（優先度: 高）

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

### 修正案B: 0銘柄時に古いデータを削除（優先度: 中）

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

### 修正案C: フロントエンドのクエリを修正（優先度: 中）

**Supabaseのフロントエンド（Next.jsなど）で、最新の`screening_results`を取得するクエリを修正:**

```typescript
// 変更前（推定）
const { data } = await supabase
  .from('detected_stocks')
  .select('*')
  .eq('screening_result_id', 
    supabase
      .from('screening_results')
      .select('id')
      .eq('screening_type', 'perfect_order')
      .gt('total_stocks_found', 0)  // ← この条件を削除
      .order('screening_date', { ascending: false })
      .limit(1)
  );

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

---

## 📝 200日新高値押し目の欠落について

### 観察
- Supabaseの最新データは1月21日
- 1月26日のデータが存在しない

### 原因
1. **1月26日の実行で0銘柄検出**
2. **`target_date`が更新されない**（`if week52_pullback:`がFalse）
3. **Supabase保存時に誤った日付（現在日時）が使用される可能性**
4. **または、保存自体が失敗している**

### 検証方法
- GitHub Actionsのログで以下を確認:
  - `save_screening_result()`の戻り値（screening_id）
  - `save_detected_stocks()`の戻り値（True/False）
  - Supabase保存成功/失敗のログ

---

## ✅ 次のアクション

### 優先度1: 修正案Aを実装（即座に実施）
1. `get_latest_trading_date()`メソッドを追加
2. 4つのスクリプトすべてで使用
3. 検出銘柄の有無に関わらず、正しい取引日を取得

### 優先度2: 修正案Bを実装（推奨）
1. `save_detected_stocks()`で0銘柄時に古いデータを削除
2. フロントエンドが常に最新のデータを表示

### 優先度3: フロントエンドのクエリを確認（必要に応じて）
1. Supabaseのフロントエンドコードを確認
2. クエリロジックが正しいか検証
3. 必要に応じて修正案Cを実装

---

## 🔄 ボリンジャーバンドとスクイーズが正しく動作する理由

### ボリンジャーバンド: 18銘柄検出
- `if bollinger_band:` → True
- `target_date`が正しく更新される
- Supabaseに正しいデータが保存される

### スクイーズ: 0銘柄検出
- `if squeeze:` → False
- `target_date`が更新されない
- **しかし、Supabaseにも0銘柄が表示される（一致）**

**なぜスクイーズは一致するのか？**
- 推測: 過去にスクイーズで検出されたデータが少ない、または定期的に削除されている
- または、フロントエンドのロジックがスクイーズのみ異なる

---

## 📊 まとめ

| スクリーニング | GitHub | Supabase | 原因 | 修正優先度 |
|---|---|---|---|---|
| パーフェクトオーダー | 0銘柄 | 74銘柄 | 古いデータが残存 | 高 |
| 200日新高値押し目 | 0銘柄 | 1/21まで | データ欠落 | 高 |
| ボリンジャーバンド | 18銘柄 | 18銘柄 | 正常 | - |
| スクイーズ | 0銘柄 | 0銘柄 | 正常 | - |

**結論:**
- **修正案Aを即座に実装** → 最新取引日の取得を改善
- **修正案Bを推奨** → 0銘柄時に古いデータを削除
- **修正案Cは必要に応じて** → フロントエンドのクエリを確認
