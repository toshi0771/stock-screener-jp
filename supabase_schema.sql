-- 株式スクリーニングアプリケーション用 Supabaseデータベーススキーマ
-- 作成日: 2025年10月9日

-- 1. ユーザーテーブル（将来のユーザー認証機能用）
CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    subscription_plan VARCHAR(50) DEFAULT 'free', -- free, premium, pro
    is_active BOOLEAN DEFAULT true
);

-- 2. スクリーニング結果テーブル（メインテーブル）
CREATE TABLE IF NOT EXISTS screening_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    screening_type VARCHAR(50) NOT NULL, -- 'perfect_order', 'bollinger_band', '52week_pullback'
    screening_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- フィルター条件
    market_filter VARCHAR(20), -- 'all', 'prime', 'standard', 'growth'
    stochastic_oversold BOOLEAN DEFAULT false,
    ema_touch_filter VARCHAR(20), -- 'all', '10ema', '20ema', '50ema'
    divergence_filter VARCHAR(20), -- パーフェクトオーダー用
    sma200_filter VARCHAR(20), -- パーフェクトオーダー用
    
    -- 結果統計
    total_stocks_found INTEGER DEFAULT 0,
    execution_time_ms INTEGER DEFAULT 0,
    
    UNIQUE(user_id, screening_type, screening_date, market_filter, stochastic_oversold, ema_touch_filter, divergence_filter, sma200_filter)
);

-- 3. 検出銘柄詳細テーブル
CREATE TABLE IF NOT EXISTS detected_stocks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    screening_result_id UUID REFERENCES screening_results(id) ON DELETE CASCADE,
    
    -- 銘柄基本情報
    stock_code VARCHAR(10) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    market VARCHAR(20) NOT NULL, -- 'プライム', 'スタンダード', 'グロース'
    
    -- 価格情報
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    
    -- テクニカル指標
    ema_10 DECIMAL(10,2),
    ema_20 DECIMAL(10,2),
    ema_50 DECIMAL(10,2),
    sma_200 DECIMAL(10,2),
    
    -- 52週新高値押し目検出用
    week52_high DECIMAL(10,2),
    week52_high_date DATE,
    touch_date DATE,
    touch_ema VARCHAR(50), -- '10EMA', '20EMA', '50EMA', '10EMA,20EMA' など
    pullback_percentage DECIMAL(5,2), -- 新高値からの下落率
    days_since_high INTEGER, -- 新高値からの経過日数
    
    -- ボリンジャーバンド用
    bollinger_upper DECIMAL(10,2),
    bollinger_lower DECIMAL(10,2),
    bollinger_middle DECIMAL(10,2),
    touch_direction VARCHAR(10), -- 'upper', 'lower'
    
    -- ストキャスティクス
    stochastic_k DECIMAL(5,2),
    stochastic_d DECIMAL(5,2),
    
    -- パーフェクトオーダー用
    divergence_percentage DECIMAL(5,2), -- 乖離率
    sma200_position VARCHAR(10), -- 'above', 'below'
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. 日次市場データテーブル（将来のAI推奨機能用）
CREATE TABLE IF NOT EXISTS daily_market_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date DATE NOT NULL,
    stock_code VARCHAR(10) NOT NULL,
    
    -- OHLCV
    open_price DECIMAL(10,2) NOT NULL,
    high_price DECIMAL(10,2) NOT NULL,
    low_price DECIMAL(10,2) NOT NULL,
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    
    -- テクニカル指標
    ema_10 DECIMAL(10,2),
    ema_20 DECIMAL(10,2),
    ema_50 DECIMAL(10,2),
    sma_200 DECIMAL(10,2),
    
    -- ボリンジャーバンド
    bollinger_upper DECIMAL(10,2),
    bollinger_middle DECIMAL(10,2),
    bollinger_lower DECIMAL(10,2),
    
    -- ストキャスティクス
    stochastic_k DECIMAL(5,2),
    stochastic_d DECIMAL(5,2),
    
    -- 52週高値・安値
    week52_high DECIMAL(10,2),
    week52_low DECIMAL(10,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(date, stock_code)
);

-- 5. AI推奨結果テーブル（将来機能用）
CREATE TABLE IF NOT EXISTS ai_recommendations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    stock_code VARCHAR(10) NOT NULL,
    recommendation_date DATE NOT NULL,
    
    -- 推奨内容
    action VARCHAR(20) NOT NULL, -- 'buy', 'sell', 'hold'
    confidence_score DECIMAL(3,2) NOT NULL, -- 0.00-1.00
    
    -- 価格推奨
    entry_price DECIMAL(10,2),
    target_price DECIMAL(10,2),
    stop_loss_price DECIMAL(10,2),
    
    -- 推奨理由
    reason TEXT,
    technical_signals JSONB, -- テクニカル指標の詳細
    
    -- 実績追跡用
    actual_entry_price DECIMAL(10,2),
    actual_exit_price DECIMAL(10,2),
    actual_exit_date DATE,
    profit_loss_percentage DECIMAL(5,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- インデックス作成（検索パフォーマンス向上）
CREATE INDEX IF NOT EXISTS idx_screening_results_date ON screening_results(screening_date);
CREATE INDEX IF NOT EXISTS idx_screening_results_type ON screening_results(screening_type);
CREATE INDEX IF NOT EXISTS idx_screening_results_user_date ON screening_results(user_id, screening_date);

CREATE INDEX IF NOT EXISTS idx_detected_stocks_code ON detected_stocks(stock_code);
CREATE INDEX IF NOT EXISTS idx_detected_stocks_screening_result ON detected_stocks(screening_result_id);

CREATE INDEX IF NOT EXISTS idx_daily_market_data_date ON daily_market_data(date);
CREATE INDEX IF NOT EXISTS idx_daily_market_data_code ON daily_market_data(stock_code);
CREATE INDEX IF NOT EXISTS idx_daily_market_data_code_date ON daily_market_data(stock_code, date);

CREATE INDEX IF NOT EXISTS idx_ai_recommendations_user_date ON ai_recommendations(user_id, recommendation_date);
CREATE INDEX IF NOT EXISTS idx_ai_recommendations_code ON ai_recommendations(stock_code);

-- Row Level Security (RLS) 設定（セキュリティ強化）
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE screening_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE detected_stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_recommendations ENABLE ROW LEVEL SECURITY;

-- RLSポリシー（ユーザーは自分のデータのみアクセス可能）
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can view own screening results" ON screening_results
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can view own detected stocks" ON detected_stocks
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM screening_results 
            WHERE screening_results.id = detected_stocks.screening_result_id 
            AND screening_results.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can view own AI recommendations" ON ai_recommendations
    FOR ALL USING (auth.uid() = user_id);

-- 日次市場データは全ユーザーが読み取り可能（公開データ）
CREATE POLICY "Anyone can read daily market data" ON daily_market_data
    FOR SELECT USING (true);

-- 管理者のみが日次市場データを挿入・更新可能
CREATE POLICY "Service role can manage daily market data" ON daily_market_data
    FOR ALL USING (auth.role() = 'service_role');

-- 初期データ挿入（テスト用ユーザー）
INSERT INTO users (id, email, subscription_plan) 
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'test@example.com',
    'free'
) ON CONFLICT (email) DO NOTHING;

-- コメント追加
COMMENT ON TABLE users IS '株式スクリーニングアプリケーションのユーザー情報';
COMMENT ON TABLE screening_results IS 'スクリーニング実行結果の概要情報';
COMMENT ON TABLE detected_stocks IS 'スクリーニングで検出された個別銘柄の詳細情報';
COMMENT ON TABLE daily_market_data IS '日次株価・テクニカル指標データ（AI推奨機能用）';
COMMENT ON TABLE ai_recommendations IS 'AI による銘柄推奨結果（将来機能）';
