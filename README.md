# 株式スクリーニング 日次データ収集システム

## 概要

東証終了後に自動実行される日次株式スクリーニングデータ収集システムです。3つのスクリーニング手法で銘柄を検出し、過去90日分の履歴を管理します。

## 機能

### スクリーニング手法

1. **パーフェクトオーダー**
   - 条件: 株価 ≥ 10EMA ≥ 20EMA ≥ 50EMA
   - 上昇トレンドの強い銘柄を検出

2. **ボリンジャーバンド±3σ**
   - 条件: 株価がボリンジャーバンドの±3σに到達
   - 買われすぎ/売られすぎの銘柄を検出

3. **52週新高値押し目**
   - 条件: 52週新高値達成後、10EMA/20EMA/50EMAにタッチ
   - 押し目買いのチャンスを検出

### データ管理

- **履歴保存**: JSON形式で過去90日分のデータを保持
- **ログ記録**: 日次実行ログを自動生成
- **統計情報**: 平均検出数などの統計を自動計算

## ディレクトリ構成

```
stock_screener_enhanced/
├── daily_data_collection.py    # メインスクリプト
├── data/
│   └── screening_history.json  # 履歴データ(過去90日分)
├── logs/
│   └── daily_collection_YYYYMMDD.log  # 実行ログ
└── README.md                    # このファイル
```

## 使用方法

### 手動実行

```bash
cd /home/ubuntu/stock_screener_enhanced
python3 daily_data_collection.py
```

### 自動実行(cron設定例)

東証終了後の15:30に自動実行:

```bash
30 15 * * 1-5 cd /home/ubuntu/stock_screener_enhanced && python3 daily_data_collection.py
```

## jQuants API設定

実際の株価データを取得するには、jQuants APIキーが必要です。

### 環境変数設定

```bash
export JQUANTS_REFRESH_TOKEN="your_refresh_token_here"
```

または、`.env`ファイルに記載:

```
JQUANTS_REFRESH_TOKEN=your_refresh_token_here
```

### APIキー未設定時の動作

APIキーが設定されていない場合、ダミーデータを生成してスクリプトは正常に動作します。

## 出力データ形式

### screening_history.json

```json
{
  "2025-10-18": {
    "date": "2025-10-18",
    "timestamp": "2025-10-18T07:52:21.389469",
    "total_stocks": 15,
    "perfect_order": [
      {
        "code": "7203",
        "name": "銘柄7203",
        "price": 2242.74,
        "ema10": 1444.8,
        "ema20": 2045.47,
        "ema50": 2102.52,
        "market": "Prime"
      }
    ],
    "bollinger_band": [...],
    "52week_pullback": [...]
  }
}
```

## 技術仕様

- **言語**: Python 3.11
- **データソース**: jQuants API
- **データ処理**: pandas, numpy
- **ファイル形式**: JSON (UTF-8)
- **ログ形式**: テキスト (UTF-8)

## パフォーマンス

- **処理速度**: 約4,000銘柄を数秒で処理
- **メモリ使用**: 最適化されたデータ構造
- **ファイルサイズ**: 90日分で約5-10MB

## トラブルシューティング

### ファイルパスエラー

すべてのファイルパスは絶対パスで指定されています:
- BASE_DIR: `/home/ubuntu/stock_screener_enhanced`
- DATA_DIR: `/home/ubuntu/stock_screener_enhanced/data`
- LOG_DIR: `/home/ubuntu/stock_screener_enhanced/logs`

### API認証エラー

jQuants APIキーが正しく設定されているか確認してください:

```bash
echo $JQUANTS_REFRESH_TOKEN
```

### 履歴データの確認

```bash
cat /home/ubuntu/stock_screener_enhanced/data/screening_history.json | python3 -m json.tool
```

## 今後の拡張予定

1. **Supabase連携**: データベースへの自動保存
2. **バックテスト機能**: 過去データでの戦略検証
3. **アラート機能**: 条件達成時の通知
4. **Webダッシュボード**: 可視化インターフェース

## バージョン

- **Version**: 1.0.0
- **作成日**: 2025年10月18日
- **最終更新**: 2025年10月18日

## ライセンス

Private Use Only

## 開発者

Manus AI Agent

