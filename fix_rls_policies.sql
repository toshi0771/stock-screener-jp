-- Row Level Security ポリシーの調整
-- テスト用ユーザーでのデータ操作を可能にする

-- 既存のポリシーを削除
DROP POLICY IF EXISTS "Users can view own screening results" ON screening_results;
DROP POLICY IF EXISTS "Users can view own detected stocks" ON detected_stocks;
DROP POLICY IF EXISTS "Users can view own AI recommendations" ON ai_recommendations;

-- 新しいポリシーを作成（テスト用ユーザーを含む）
CREATE POLICY "Users can manage own screening results" ON screening_results
    FOR ALL USING (
        auth.uid() = user_id OR 
        user_id = '00000000-0000-0000-0000-000000000001'::uuid
    );

CREATE POLICY "Users can manage own detected stocks" ON detected_stocks
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM screening_results 
            WHERE screening_results.id = detected_stocks.screening_result_id 
            AND (screening_results.user_id = auth.uid() OR screening_results.user_id = '00000000-0000-0000-0000-000000000001'::uuid)
        )
    );

CREATE POLICY "Users can manage own AI recommendations" ON ai_recommendations
    FOR ALL USING (
        auth.uid() = user_id OR 
        user_id = '00000000-0000-0000-0000-000000000001'::uuid
    );

-- テスト用ユーザーが存在しない場合は作成
INSERT INTO users (id, email, subscription_plan) 
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'test@example.com',
    'free'
) ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    subscription_plan = EXCLUDED.subscription_plan,
    updated_at = NOW();
