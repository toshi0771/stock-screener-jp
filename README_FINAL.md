# 株式スクリーニングWebアプリケーション - 最終版

## 概要

日本株の3つのスクリーニング手法を実装したWebアプリケーションです。Supabaseから実際のスクリーニング結果を取得して表示します。

## 主な機能

### 1. パーフェクトオーダー検出
- 条件: 株価 >= 10EMA >= 20EMA >= 50EMA
- オプション:
  - 市場選択（全て/プライム/スタンダード/グロース）
  - 200SMAフィルター（全て/200SMAより上/200SMAより下）

### 2. ボリンジャーバンド±3σタッチ検出
- 条件: 株価が±3σにタッチ
- オプション:
  - 市場選択（全て/プライム/スタンダード/グロース）

### 3. 52週新高値押し目検出
- 条件: 52週新高値達成後、10EMA/20EMA/50EMAにタッチ
- オプション:
  - 市場選択（全て/プライム/スタンダード/グロース）
  - ストキャス売られすぎフィルター（ON/OFF）

## ファイル構成

```
stock_screener_enhanced/
├── app.py                          # メインアプリケーション（実データ連携版）
├── daily_data_collection.py       # 日次データ収集スクリプト
├── templates/
│   └── index_market_filter.html   # HTMLテンプレート（市場選択機能付き）
├── .env                            # 環境変数（Supabase認証情報）
├── requirements.txt                # Pythonパッケージリスト
└── README_FINAL.md                 # このファイル
```

## セットアップ手順

### 1. 必要なパッケージのインストール

```bash
pip3 install flask supabase python-dotenv pandas numpy jquants-api-client
```

### 2. 環境変数の設定

`.env`ファイルに以下の情報を設定してください：

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
JQUANTS_REFRESH_TOKEN=your-refresh-token
```

### 3. アプリケーションの起動

```bash
python3 app.py
```

アクセスURL: http://localhost:5000

## 日次データ収集

毎営業日15:30に自動実行されるCron設定済み：

```bash
# Cronジョブ確認
crontab -l

# 手動実行
python3 daily_data_collection.py
```

実行結果はSupabaseに自動保存されます。

## データベース構造

### screening_results テーブル
- スクリーニング実行結果の概要情報
- フィールド: screening_type, screening_date, market_filter, total_stocks_found など

### detected_stocks テーブル
- 検出された個別銘柄の詳細情報
- フィールド: stock_code, company_name, market, close_price, volume, EMA/SMA値 など

## API エンドポイント

### POST /api/screening
スクリーニング実行

**リクエスト例:**
```json
{
  "method": "perfect_order",
  "options": {
    "market": "all",
    "sma200_filter": "all"
  }
}
```

**レスポンス例:**
```json
{
  "success": true,
  "count": 3,
  "results": [
    {
      "code": "96720",
      "name": "東京都競馬",
      "market": "プライム",
      "price": 5620.0,
      "volume": 56800,
      "ema10": 5534.47,
      "ema20": 5457.08,
      "ema50": 5296.42
    }
  ]
}
```

### GET /api/health
ヘルスチェック

## ロリポップサーバーへのデプロイ

### 1. ファイルのアップロード
- FTPまたはSSHでファイルをアップロード
- `.env`ファイルも忘れずにアップロード

### 2. Pythonバージョン確認
```bash
python3 --version
```

### 3. パッケージインストール
```bash
pip3 install --user flask supabase python-dotenv pandas numpy
```

### 4. アプリケーション起動
```bash
# 開発サーバー（テスト用）
python3 app.py

# 本番環境（Gunicorn推奨）
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## トラブルシューティング

### データが取得できない場合
1. Supabase接続を確認: `/api/health` にアクセス
2. `.env`ファイルの認証情報を確認
3. Supabaseのテーブルにデータが存在するか確認

### Cronが実行されない場合
```bash
# Cronログ確認
tail -f /var/log/cron

# 手動実行でテスト
python3 daily_data_collection.py
```

## 技術スタック

- **バックエンド**: Flask (Python)
- **データベース**: Supabase (PostgreSQL)
- **データソース**: jQuants API
- **フロントエンド**: HTML/CSS/JavaScript
- **デプロイ**: ロリポップサーバー（予定）

## 作成日

2025年10月21日

## バージョン

v2.0 - 市場選択機能付き実データ連携版

