# Refresh Token警告機能デプロイ手順書

## 📋 概要

Refresh Token有効期限警告機能と詳細エラーログを追加しました。

---

## 🎯 追加された機能

### 1. Refresh Token有効期限の自動チェック
- 起動時に自動的に有効期限をチェック
- 5日前から段階的な警告を表示
- 期限切れ時には明確なエラーメッセージを表示

### 2. 詳細なエラーログ
- HTTPステータスコード別のエラーハンドリング
- 具体的な対処方法の表示
- ネットワークエラーの明確な検知

---

## 🚀 デプロイ手順

### ステップ1: GitHubにプッシュ

```bash
# ローカル環境で実行
cd /path/to/stock-screener-jp
git pull origin main
git push origin main
```

### ステップ2: Renderで環境変数を追加

Renderダッシュボードで以下の環境変数を追加：

#### **stock-screener-daily-update（Cron Job）**

新しい環境変数を追加：

```
JQUANTS_TOKEN_CREATED_DATE=2025-11-25
```

**重要：** 
- 値は Refresh Token を取得した日付（YYYY-MM-DD形式）
- 今日が2025年11月25日で、今日Refresh Tokenを取得した場合は `2025-11-25`
- 既存の `JQUANTS_REFRESH_TOKEN` はそのまま

---

## 📊 警告レベル

| 経過日数 | ログレベル | メッセージ |
|---------|-----------|-----------|
| 0-4日 | ✅ INFO | 「Refresh Token有効期限: あとN日」 |
| 5日 | ⚠️ WARNING | 「有効期限が近づいています（残り2日）」 |
| 6日 | ⚠️ WARNING | 「有効期限が明日切れます！」 |
| 7日以上 | 🚨 ERROR | 「有効期限が切れています！」 |

---

## 🔧 運用方法

### Refresh Token更新時の手順

1. **jQuants APIで新しいRefresh Tokenを取得**
   - https://application.jpx-jquants.com/ にログイン
   - 「リフレッシュトークンを取得する」をクリック
   - 新しいトークンをコピー

2. **Renderで環境変数を更新**
   - `JQUANTS_REFRESH_TOKEN`: 新しいトークンを貼り付け
   - `JQUANTS_TOKEN_CREATED_DATE`: 今日の日付（YYYY-MM-DD）に更新
   - 「Save Changes」をクリック

3. **動作確認**
   - Cron Jobを手動実行（Trigger Run）
   - ログで「✅ Refresh Token有効期限: あと7日」を確認

---

## 📝 ログの確認方法

### Renderダッシュボード

1. **stock-screener-daily-update** をクリック
2. 左側メニューの **Logs** をクリック
3. 以下のログを確認：

**正常時：**
```
🔐 jQuants API認証開始...
✅ Refresh Token有効期限: あと7日（0日経過）
✅ jQuants API認証成功（ID Token取得完了）
```

**警告時（5日経過）：**
```
⚠️ Refresh Tokenの有効期限が近づいています（5日経過、残り2日）
```

**エラー時（期限切れ）：**
```
🚨 Refresh Tokenの有効期限が切れています！（7日経過）
🔧 対処方法: jQuants APIで新しいRefresh Tokenを取得し、環境変数を更新してください。
```

---

## ⚠️ 注意事項

### 環境変数の設定場所

| サービス | JQUANTS_REFRESH_TOKEN | JQUANTS_TOKEN_CREATED_DATE |
|---------|:---------------------:|:-------------------------:|
| **stock-screener-daily-update**<br>（Cron Job） | ✅ 必須 | ✅ 必須 |
| **stock-screener-jp**<br>（Web Service） | ❌ 不要 | ❌ 不要 |

**理由：**
- Cron JobはjQuants APIを直接呼び出すため必要
- Web ServiceはSupabaseからデータを読み取るだけなので不要

---

## 🎉 完了

以上でデプロイ完了です！

7日ごとにRefresh Tokenを更新する必要がありますが、5日前から警告が表示されるため、余裕を持って対応できます。
