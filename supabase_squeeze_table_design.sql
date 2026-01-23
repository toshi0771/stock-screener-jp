-- ============================================================
-- 価格収縮（スクイーズ）検出結果テーブル
-- ============================================================

-- screening_resultsテーブルに新しいメソッドを追加
-- method = 'squeeze' として保存

-- detected_stocksテーブルの構造は既存のものを使用
-- 追加カラムは不要（既存のカラムで対応可能）

-- ============================================================
-- 使用するカラム
-- ============================================================

-- screening_results テーブル:
--   - id: UUID (主キー)
--   - date: DATE (スクリーニング実行日)
--   - method: TEXT ('squeeze')
--   - total_stocks: INTEGER (検出銘柄数)
--   - created_at: TIMESTAMP

-- detected_stocks テーブル:
--   - id: UUID (主キー)
--   - screening_result_id: UUID (外部キー)
--   - stock_code: TEXT (銘柄コード)
--   - company_name: TEXT (会社名)
--   - market: TEXT (市場)
--   - additional_data: JSONB (追加データ)
--   - created_at: TIMESTAMP

-- ============================================================
-- additional_data の構造（JSONB）
-- ============================================================

-- {
--   "current_bbw": 1.66,              // 現在のBBW (%)
--   "bbw_min_60d": 1.66,              // 過去60日のBBW最小値 (%)
--   "bbw_ratio": 1.00,                // BBW比率（現在値/最小値）
--   "deviation_from_ema": 0.43,       // 株価と50EMAの乖離率 (%)
--   "current_atr": 12.02,             // 現在のATR
--   "atr_min_60d": 11.72,             // 過去60日のATR最小値
--   "atr_ratio": 1.03,                // ATR比率（現在値/最小値）
--   "duration_days": 6,               // 収縮継続日数
--   "current_price": 830.0,           // 現在の株価
--   "ema_50": 828.5                   // 50EMA
-- }

-- ============================================================
-- インデックス（既存）
-- ============================================================

-- screening_results:
--   - idx_screening_results_date_method: (date, method)

-- detected_stocks:
--   - idx_detected_stocks_screening_result_id: (screening_result_id)
--   - idx_detected_stocks_stock_code: (stock_code)

-- ============================================================
-- クエリ例
-- ============================================================

-- 1. 最新のスクイーズ検出結果を取得
-- SELECT * FROM screening_results 
-- WHERE method = 'squeeze' 
-- ORDER BY date DESC 
-- LIMIT 1;

-- 2. 特定日のスクイーズ銘柄を取得（継続日数でソート）
-- SELECT 
--   ds.stock_code,
--   ds.company_name,
--   ds.market,
--   ds.additional_data->>'duration_days' as duration_days,
--   ds.additional_data->>'current_bbw' as current_bbw,
--   ds.additional_data->>'deviation_from_ema' as deviation_from_ema
-- FROM detected_stocks ds
-- JOIN screening_results sr ON ds.screening_result_id = sr.id
-- WHERE sr.method = 'squeeze' AND sr.date = '2025-12-25'
-- ORDER BY (ds.additional_data->>'duration_days')::integer DESC;

-- 3. 収縮期間でフィルター（1週間～2週間）
-- SELECT * FROM detected_stocks ds
-- JOIN screening_results sr ON ds.screening_result_id = sr.id
-- WHERE sr.method = 'squeeze' 
--   AND sr.date = '2025-12-25'
--   AND (ds.additional_data->>'duration_days')::integer BETWEEN 8 AND 14
-- ORDER BY (ds.additional_data->>'duration_days')::integer DESC;

-- 4. 過去のスクイーズ検出履歴（日別集計）
-- SELECT 
--   date,
--   total_stocks,
--   created_at
-- FROM screening_results
-- WHERE method = 'squeeze'
-- ORDER BY date DESC
-- LIMIT 30;

-- ============================================================
-- 注意事項
-- ============================================================

-- 1. 既存のテーブル構造を使用するため、新しいテーブル作成は不要
-- 2. method = 'squeeze' として保存
-- 3. additional_data (JSONB) に詳細データを保存
-- 4. 既存のインデックスで十分なパフォーマンスが得られる
