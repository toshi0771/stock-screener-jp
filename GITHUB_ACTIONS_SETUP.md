# GitHub Actions 自動データ収集設定手順

このドキュメントでは、GitHub Actionsを使用して毎日自動的に株式データを収集する設定方法を説明します。

---

## 📋 概要

GitHub Actionsワークフローが以下のスケジュールで自動実行されます：

- **実行時刻**: 日本時間 18:00（UTC 09:00）
- **実行曜日**: 月曜日〜金曜日（営業日のみ）
- **手動実行**: 必要に応じてGitHub UIから手動実行も可能

---

## 🔧 設定手順

### 1. GitHub Secretsに環境変数を設定

GitHubリポジトリで以下の環境変数を設定します。

#### 手順

1. GitHubリポジトリページにアクセス
   - https://github.com/toshi0771/stock-screener-jp

2. **Settings** タブをクリック

3. 左サイドバーの **Secrets and variables** → **Actions** をクリック

4. **New repository secret** ボタンをクリック

5. 以下の3つのSecretを追加：

#### Secret 1: JQUANTS_API_KEY

```
Name: JQUANTS_API_KEY
Secret: vNCOOZoAiT8cdlWrSeVGx7dBHjJhjMXctICqd01xBRk
```

#### Secret 2: SUPABASE_URL

```
Name: SUPABASE_URL
Secret: https://asdvlrcwkbmwbosecoti.supabase.co
```

#### Secret 3: SUPABASE_ANON_KEY

```
Name: SUPABASE_ANON_KEY
Secret: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFzZHZscmN3a2Jtd2Jvc2Vjb3RpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMjA5MzQsImV4cCI6MjA3NTU5NjkzNH0.fCULzu8evcw1MoxQybUOkdwimrmkIZ6pzVzqHuipHnY
```

---

### 2. ワークフローの有効化確認

1. GitHubリポジトリの **Actions** タブをクリック

2. **Daily Stock Data Collection** ワークフローが表示されることを確認

3. 初回は自動的に有効化されますが、無効になっている場合は **Enable workflow** をクリック

---

### 3. 手動実行でテスト

初回設定後、手動実行でテストすることを推奨します。

#### 手順

1. **Actions** タブをクリック

2. 左サイドバーの **Daily Stock Data Collection** をクリック

3. 右上の **Run workflow** ボタンをクリック

4. **Run workflow** を再度クリックして実行

5. 実行状況を確認
   - ✅ 成功: 緑色のチェックマーク
   - ❌ 失敗: 赤色のXマーク（ログを確認）

---

## 📊 実行結果の確認

### GitHub Actions

- **Actions** タブで実行履歴を確認
- 各実行のログを確認可能
- 失敗時はログファイルがアーティファクトとしてダウンロード可能

### Supabase

- Supabaseダッシュボードで `screening_results` テーブルを確認
- 新しいデータが追加されていることを確認

### アプリケーション

- https://stock-screener-jp.onrender.com
- **過去データ** モードで最新のデータが表示されることを確認

---

## ⚙️ ワークフローの詳細

### スケジュール

```yaml
schedule:
  - cron: '0 9 * * 1-5'  # UTC 09:00 = JST 18:00, Mon-Fri
```

### 実行内容

1. リポジトリをチェックアウト
2. Python 3.11をセットアップ
3. 依存関係をインストール
4. `daily_data_collection.py` を実行
5. 失敗時はログをアップロード

---

## 🔍 トラブルシューティング

### ワークフローが実行されない

- **原因**: リポジトリが60日間更新されていない
- **対処**: 手動実行またはコミットを行う

### 実行が失敗する

- **確認事項**:
  1. GitHub Secretsが正しく設定されているか
  2. J-Quants APIキーが有効か
  3. Supabase接続情報が正しいか
- **対処**: Actions タブでログを確認

### 営業日以外に実行される

- **原因**: GitHub Actionsは日本の祝日を認識しない
- **対処**: `daily_data_collection.py` の `is_trading_day()` が自動的にスキップ

---

## 📝 注意事項

1. **GitHub Actionsの実行時間制限**
   - 無料プランでは月2,000分まで
   - 1回の実行は通常5-10分程度

2. **J-Quants API制限**
   - V2 APIは1日あたりのリクエスト数に制限あり
   - 過度な実行は避ける

3. **Supabase制限**
   - 無料プランでは月間500MBまで
   - データ量を定期的に確認

---

## 🎯 次のステップ

1. ✅ GitHub Secretsを設定
2. ✅ 手動実行でテスト
3. ✅ 翌営業日に自動実行を確認
4. ✅ アプリケーションで新しいデータを確認

---

## 📚 参考リンク

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [J-Quants API V2 Documentation](https://jpx-jquants.com/en/)
- [Supabase Documentation](https://supabase.com/docs)
