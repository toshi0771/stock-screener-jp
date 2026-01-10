# J-Quants API V2 移行手順書

## 目次

1. [概要](#概要)
2. [APIキーの取得](#apiキーの取得)
3. [環境変数の設定](#環境変数の設定)
4. [コードの修正](#コードの修正)
5. [動作確認](#動作確認)
6. [デプロイ](#デプロイ)

---

## 概要

J-Quants API V2では、リフレッシュトークン方式からAPIキー方式に変更されました。これにより、認証処理が大幅に簡素化され、トークンの手動更新が不要になります。

### V2への移行のメリット

**認証の簡素化**: リフレッシュトークンの手動更新が不要になり、APIキーは期限なしで永続的に利用できます。トークン取得でつまづく問題が解消され、初学者の方でも容易に利用開始できます。

**自動化の容易化**: APIキーをヘッダーに追加するだけで認証が完了するため、自動化・スクリプト化が非常に簡単になります。環境変数に一度設定すれば、以降は手動操作が不要です。

**レスポンスの最適化**: カラム名が短縮され、レスポンスサイズが圧縮されました。これにより、大容量データで発生していたページネーションの頻度が低減し、転送量が削減されて処理が軽くなります。

**明確なレートリミット**: プランごとにAPIリクエスト数の上限が明確に設定されました（Free: 5回/分、Light: 60回/分、Standard: 120回/分、Premium: 500回/分）。

### 主な変更点

| 項目 | V1 API | V2 API |
|------|--------|--------|
| **認証方式** | リフレッシュトークン + IDトークン | APIキー（`x-api-key` ヘッダー） |
| **認証の期限** | 有効期限あり（定期更新必要） | 期限なし（再発行・削除は可能） |
| **エンドポイント** | `/v1/prices/daily_quotes` など | `/v2/equities/bars/daily` など |
| **レスポンス構造** | APIによって異なる | `{"data": [...], "pagination_key": "..."}` |
| **カラム名** | `Open`, `High`, `Low`, `Close` など | `O`, `H`, `L`, `C` など（短縮形） |

---

## APIキーの取得

### ステップ1: ユーザー登録（初回のみ）

J-Quants APIを初めて利用する場合は、まずユーザー登録を行います。

1. [J-Quants ユーザー登録ページ](https://jpx-jquants.com/ja/register)にアクセス
2. メールアドレスを入力して仮登録
3. 送られてきたメールのURLをクリックして登録を完了

### ステップ2: サブスクリプション登録（初回のみ）

ユーザー登録後、サブスクリプションプランに登録します。APIを利用するには、Freeプランも含めたいずれかのプランへの登録が必要です。

1. [サインインページ](https://jpx-jquants.com/ja/signin)からログイン
2. サブスクリプションプランを選択
   - **Free**: 5リクエスト/分、基本的なデータ
   - **Light**: 60リクエスト/分、過去3年分のデータ
   - **Standard**: 120リクエスト/分、過去10年分のデータ
   - **Premium**: 500リクエスト/分、過去20年分のデータ
3. プランの登録を完了

### ステップ3: APIキーの発行

サブスクリプション登録後、APIキーを発行します。

1. [ダッシュボード](https://jpx-jquants.com/ja/dashboard)にログイン
2. メニューから **[設定 » API キー]** を選択
3. **APIキーを発行** ボタンをクリック
4. 発行されたAPIキーをコピーして安全に保管

**重要**: APIキーは期限なしで永続的に利用できますが、外部に漏洩しないよう厳重に管理してください。GitHubなどの公開リポジトリにコミットしないよう注意が必要です。

---

## 環境変数の設定

### Renderでの設定（本番環境）

Renderにデプロイしているアプリケーションの環境変数を設定します。

1. [Render Dashboard](https://dashboard.render.com/)にログイン
2. 該当のWeb Service（`stock-screener-jp`）を選択
3. 左メニューから **Environment** タブをクリック
4. **Add Environment Variable** ボタンをクリック
5. 以下の環境変数を追加：
   - **Key**: `JQUANTS_API_KEY`
   - **Value**: `取得したAPIキー`（先ほどコピーしたもの）
6. **Save Changes** ボタンをクリック

環境変数を保存すると、Renderが自動的にアプリケーションを再デプロイします。数分待つと、新しい環境変数が反映されます。

### ローカル開発環境での設定

ローカルでテストする場合は、`.env` ファイルに環境変数を設定します。

1. プロジェクトのルートディレクトリに `.env` ファイルを作成（存在しない場合）
2. 以下の内容を追加：

```bash
JQUANTS_API_KEY=your_api_key_here
```

3. `.gitignore` ファイルに `.env` を追加（既に追加されている場合は不要）

```
.env
```

**注意**: `.env` ファイルは絶対にGitにコミットしないでください。APIキーが外部に漏洩すると、不正利用される可能性があります。

---

## コードの修正

### 現在のコード構造の確認

現在の `daily_data_collection.py` では、リフレッシュトークンを使用してIDトークンを取得し、それを使ってAPIリクエストを行っています。

```python
# 現在のV1 API認証方式
def get_id_token(self):
    response = requests.post(
        "https://api.jquants.com/v1/token/auth_refresh",
        params={"refreshtoken": self.refresh_token}
    )
    return response.json()["idToken"]
```

### V2 APIへの修正方針

V2 APIでは、APIキーをリクエストヘッダーに追加するだけで認証が完了します。トークン取得処理は不要になります。

#### 修正が必要なファイル

1. **`daily_data_collection.py`**: データ収集スクリプト
   - 認証処理の変更
   - エンドポイントURLの変更
   - レスポンスのカラム名の変更に対応

2. **`app.py`**: Webアプリケーション
   - データベースから取得したデータの表示は変更不要（カラム名はデータベース内で統一）

#### 修正例: 認証処理

**V1 API（旧）**:
```python
class JQuantsDataCollector:
    def __init__(self):
        self.refresh_token = os.getenv("JQUANTS_REFRESH_TOKEN")
        self.id_token = None
    
    def get_id_token(self):
        response = requests.post(
            "https://api.jquants.com/v1/token/auth_refresh",
            params={"refreshtoken": self.refresh_token}
        )
        return response.json()["idToken"]
    
    def get_headers(self):
        if not self.id_token:
            self.id_token = self.get_id_token()
        return {"Authorization": f"Bearer {self.id_token}"}
```

**V2 API（新）**:
```python
class JQuantsDataCollector:
    def __init__(self):
        self.api_key = os.getenv("JQUANTS_API_KEY")
    
    def get_headers(self):
        return {"x-api-key": self.api_key}
```

#### 修正例: エンドポイントとカラム名

**V1 API（旧）**:
```python
# 株価データ取得
response = requests.get(
    "https://api.jquants.com/v1/prices/daily_quotes",
    headers=self.get_headers(),
    params={"code": code, "date": date}
)
data = response.json()

# カラム名: Open, High, Low, Close, Volume
price_data = {
    "open": item["Open"],
    "high": item["High"],
    "low": item["Low"],
    "close": item["Close"],
    "volume": item["Volume"]
}
```

**V2 API（新）**:
```python
# 株価データ取得
response = requests.get(
    "https://api.jquants.com/v2/equities/bars/daily",
    headers=self.get_headers(),
    params={"code": code, "date": date}
)
data = response.json()

# レスポンス構造: {"data": [...], "pagination_key": "..."}
# カラム名: O, H, L, C, Vo（短縮形）
for item in data["data"]:
    price_data = {
        "open": item["O"],
        "high": item["H"],
        "low": item["L"],
        "close": item["C"],
        "volume": item["Vo"]
    }
```

#### 主要なエンドポイントの対応表

| データ種別 | V1 エンドポイント | V2 エンドポイント |
|-----------|------------------|------------------|
| 株価四本値 | `/v1/prices/daily_quotes` | `/v2/equities/bars/daily` |
| 上場銘柄一覧 | `/v1/listed/info` | `/v2/equities/master` |
| 財務情報 | `/v1/fins/statements` | `/v2/fins/summary` |
| 取引カレンダー | `/v1/markets/trading_calendar` | `/v2/markets/calendar` |

#### カラム名の対応表（株価四本値）

| 項目 | V1 カラム名 | V2 カラム名 |
|------|-----------|-----------|
| 日付 | `Date` | `Date` |
| 銘柄コード | `Code` | `Code` |
| 始値 | `Open` | `O` |
| 高値 | `High` | `H` |
| 安値 | `Low` | `L` |
| 終値 | `Close` | `C` |
| 出来高 | `Volume` | `Vo` |
| 売買代金 | `TurnoverValue` | `Va` |
| 調整後終値 | `AdjustmentClose` | `AdjC` |

---

## 動作確認

### ローカルでのテスト

コードを修正したら、まずローカル環境でテストします。

1. `.env` ファイルにAPIキーが設定されていることを確認
2. テストスクリプトを実行：

```bash
cd /home/ubuntu/stock-screener-jp
python3 daily_data_collection.py
```

3. エラーが出ないことを確認
4. データが正しく取得できているか確認

### APIキーの動作確認

簡単なテストスクリプトでAPIキーが正しく動作するか確認できます。

```python
import os
import requests

# 環境変数からAPIキーを取得
api_key = os.getenv("JQUANTS_API_KEY")

# ヘッダーにAPIキーを設定
headers = {"x-api-key": api_key}

# テストリクエスト（株価四本値）
response = requests.get(
    "https://api.jquants.com/v2/equities/bars/daily",
    headers=headers,
    params={"code": "86970", "date": "20240104"}
)

# レスポンスを確認
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
```

**期待される結果**:
- Status Code: `200`
- Response: `{"data": [...], "pagination_key": null}`

---

## デプロイ

### Gitへのコミット

ローカルでの動作確認が完了したら、変更をGitにコミットしてプッシュします。

```bash
cd /home/ubuntu/stock-screener-jp

# 変更状況を確認
git status

# 変更をステージング
git add daily_data_collection.py

# コミット
git commit -m "Migrate to J-Quants API V2 with API key authentication"

# プッシュ
git push origin main
```

### Renderでの自動デプロイ

GitHubにプッシュすると、Renderが自動的にデプロイを開始します。

1. [Render Dashboard](https://dashboard.render.com/)で該当のWeb Serviceを開く
2. **Events** タブで自動デプロイの進行状況を確認
3. デプロイが完了したら、**Logs** タブでエラーがないか確認

### Cron Jobの確認

データ収集のCron Jobも同様に更新されます。

1. Render Dashboardで該当のCron Jobを開く
2. **Environment** タブで `JQUANTS_API_KEY` が設定されていることを確認
3. 次回の実行時刻を確認（日次16:00 JST）

### 本番環境での動作確認

デプロイ完了後、本番環境で動作確認を行います。

1. https://stock-screener-jp.onrender.com にアクセス
2. 各スクリーニング手法のボタンをクリック
3. データが正しく表示されることを確認
4. 過去データの表示も確認

---

## トラブルシューティング

### エラー: 401 Unauthorized

**原因**: APIキーが正しく設定されていない、または無効です。

**解決方法**:
1. 環境変数 `JQUANTS_API_KEY` が正しく設定されているか確認
2. APIキーが正しくコピーされているか確認（余分なスペースがないか）
3. J-Quants ダッシュボードでAPIキーが有効か確認

### エラー: 429 Too Many Requests

**原因**: レートリミットを超えています。

**解決方法**:
1. プランのレートリミットを確認（Free: 5回/分、Light: 60回/分など）
2. リクエスト頻度を調整
3. 必要に応じてプランをアップグレード

### エラー: KeyError (カラム名)

**原因**: V1のカラム名を使用しています。

**解決方法**:
1. カラム名をV2の短縮形に変更（`Open` → `O` など）
2. レスポンス構造を確認（`data` キーの配列として返却される）

---

## 参考リンク

- [J-Quants API V2 公式ドキュメント](https://jpx-jquants.com/ja/spec/migration-v1-v2)
- [クイックスタート](https://jpx-jquants.com/ja/spec/quickstart)
- [MCPサーバー設定](https://jpx-jquants.com/ja/spec/mcp-server)
- [Qiita記事: V2リリース](https://qiita.com/j_quants/items/c8669bfec76355c32400)

---

## まとめ

J-Quants API V2への移行により、認証処理が大幅に簡素化され、リフレッシュトークンの手動更新が不要になります。APIキーを一度設定すれば、永続的に利用できるため、運用の手間が大幅に削減されます。

**移行の主なステップ**:
1. ✅ J-Quants ダッシュボードでAPIキーを発行
2. ✅ Renderの環境変数に `JQUANTS_API_KEY` を設定
3. ✅ コードを修正（認証処理、エンドポイント、カラム名）
4. ✅ ローカルでテスト
5. ✅ GitHubにプッシュして自動デプロイ
6. ✅ 本番環境で動作確認

V1 APIは数か月間の並走期間がありますが、早めにV2 APIへ移行することを推奨します。
