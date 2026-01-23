-- pullback_52week を pullback_200day に更新するSQLスクリプト

-- detected_stocks テーブルの method カラムを更新
UPDATE detected_stocks
SET method = '200day_pullback'
WHERE method = 'pullback_52week' OR method = '52week_pullback';

-- screening_results テーブルの screening_type カラムを更新
UPDATE screening_results
SET screening_type = '200day_pullback'
WHERE screening_type = 'pullback_52week' OR screening_type = '52week_pullback';

-- screening_results テーブルのカラム名は変更不要
-- （pullback_52week_id は既存データとの互換性のため維持）

-- 更新結果を確認
SELECT 
    method,
    COUNT(*) as count
FROM detected_stocks
WHERE method LIKE '%pullback%'
GROUP BY method;
