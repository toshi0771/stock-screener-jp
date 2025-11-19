# Flaskアプリケーション トラブルシューティングガイド

**作成日**: 2025年10月23日  
**バージョン**: 1.0  
**対象**: 株式スクリーニングWebアプリケーション

---

## 目次

1. [よくある問題と解決方法](#よくある問題と解決方法)
2. [504 Gateway Timeout エラー](#504-gateway-timeout-エラー)
3. [ポート競合エラー](#ポート競合エラー)
4. [プロセス停止状態の対処](#プロセス停止状態の対処)
5. [モジュール不足エラー](#モジュール不足エラー)
6. [Supabase接続エラー](#supabase接続エラー)
7. [デバッグ方法](#デバッグ方法)
8. [ロリポップサーバーへのデプロイ](#ロリポップサーバーへのデプロイ)

---

## よくある問題と解決方法

### 問題1: アプリが起動しない

**症状**:
```bash
$ python3 app.py
ModuleNotFoundError: No module named 'flask'
```

**解決方法**:
```bash
# 必要なパッケージをインストール
pip3 install flask supabase pandas numpy aiohttp

# または requirements.txt から一括インストール
pip3 install -r requirements.txt
```

---

### 問題2: 環境変数が読み込めない

**症状**:
```
ValueError: SUPABASE_URLとSUPABASE_ANON_KEYを.envファイルに設定してください
```

**解決方法**:

1. `.env`ファイルが存在するか確認:
```bash
ls -la /home/ubuntu/stock_screener_enhanced/.env
```

2. `.env`ファイルの内容を確認:
```bash
cat /home/ubuntu/stock_screener_enhanced/.env
```

3. 必要な環境変数が設定されているか確認:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
JQUANTS_REFRESH_TOKEN=your-refresh-token
```

4. 環境変数を手動で設定:
```bash
export SUPABASE_URL="https://asdvlrcwkbmwbosecoti.supabase.co"
export SUPABASE_ANON_KEY="your-key"
export JQUANTS_REFRESH_TOKEN="your-token"
```

---

## 504 Gateway Timeout エラー

### 原因

Flaskプロセスが停止状態（Stopped）になっている、またはアプリが応答していない。

### 確認方法

```bash
# プロセス状態を確認
ps aux | grep "python3 app.py" | grep -v grep
```

出力例:
```
ubuntu  8689  0.1  1.5  75188 61996 pts/11   T    15:49   0:00 python3 app.py
                                            ↑
                                            T = Stopped（停止状態）
```

### 解決方法

#### 方法1: プロセスを再起動

```bash
# 1. 停止中のプロセスを強制終了
kill -9 $(ps aux | grep "python3 app.py" | grep -v grep | awk '{print $2}')

# 2. 少し待機
sleep 2

# 3. アプリを再起動
cd /home/ubuntu/stock_screener_enhanced
nohup python3 -u app.py > /tmp/flask_app.log 2>&1 </dev/null &

# 4. 起動確認
sleep 3
curl -s http://localhost:5000 | head -10
```

#### 方法2: デーモンモードで起動

```bash
# バックグラウンドで安定動作させる
cd /home/ubuntu/stock_screener_enhanced
nohup python3 -u app.py > /tmp/flask_daemon.log 2>&1 </dev/null &
```

---

## ポート競合エラー

### 症状

```
Address already in use
Port 5000 is in use by another program.
```

### 確認方法

```bash
# ポート5000を使用しているプロセスを確認
lsof -i :5000 | grep LISTEN
```

### 解決方法

#### 方法1: 既存プロセスを終了

```bash
# ポート5000を使用しているプロセスIDを取得
lsof -i :5000 | grep LISTEN | awk '{print $2}' | sort -u

# プロセスを終了（例: PID 1234の場合）
kill -9 1234

# または一括終了
kill -9 $(lsof -i :5000 | grep LISTEN | awk '{print $2}' | sort -u)
```

#### 方法2: 別のポートを使用

`app.py`の最後の部分を編集:
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)  # ポート5001に変更
```

---

## プロセス停止状態の対処

### プロセスが停止状態（T）になる原因

- バックグラウンドジョブが一時停止された
- Ctrl+Z が押された
- システムリソース不足

### 確認方法

```bash
ps aux | grep "python3 app.py" | grep -v grep
```

出力の`STAT`列が`T`の場合、停止状態。

### 解決方法

```bash
# 1. すべてのFlaskプロセスを強制終了
kill -9 $(ps aux | grep "python3 app.py" | grep -v grep | awk '{print $2}')

# 2. プロセスが終了したか確認
ps aux | grep "python3 app.py" | grep -v grep || echo "プロセス終了完了"

# 3. 再起動
cd /home/ubuntu/stock_screener_enhanced
nohup python3 -u app.py > /tmp/flask_app.log 2>&1 </dev/null &

# 4. プロセス状態を確認（STATがSまたはSlならOK）
ps aux | grep "python3 app.py" | grep -v grep
```

---

## モジュール不足エラー

### よくあるエラー

```python
ModuleNotFoundError: No module named 'dotenv'
ModuleNotFoundError: No module named 'aiohttp'
ModuleNotFoundError: No module named 'supabase'
```

### 解決方法

```bash
# 個別インストール
pip3 install python-dotenv
pip3 install aiohttp
pip3 install supabase

# または一括インストール
pip3 install flask supabase python-dotenv pandas numpy aiohttp
```

### requirements.txt を使用する場合

```bash
cd /home/ubuntu/stock_screener_enhanced
pip3 install -r requirements.txt
```

---

## Supabase接続エラー

### 症状

```
Supabase接続失敗: [エラーメッセージ]
```

### 確認項目

1. **環境変数の確認**:
```bash
echo $SUPABASE_URL
echo $SUPABASE_ANON_KEY
```

2. **ネットワーク接続の確認**:
```bash
curl -I https://asdvlrcwkbmwbosecoti.supabase.co
```

3. **Supabaseダッシュボードで確認**:
- https://app.supabase.com にアクセス
- プロジェクトが正常に動作しているか確認
- APIキーが正しいか確認

### 解決方法

1. `.env`ファイルを確認:
```bash
cat /home/ubuntu/stock_screener_enhanced/.env
```

2. 環境変数を再設定:
```bash
export SUPABASE_URL="https://asdvlrcwkbmwbosecoti.supabase.co"
export SUPABASE_ANON_KEY="your-anon-key"
```

3. アプリを再起動

---

## デバッグ方法

### ログファイルの確認

```bash
# 最新のログを確認
tail -f /tmp/flask_app.log

# 過去のログを確認
cat /tmp/flask_app.log

# エラーのみを抽出
grep -i error /tmp/flask_app.log
```

### リアルタイムデバッグ

```bash
# フォアグラウンドで起動（ログが直接表示される）
cd /home/ubuntu/stock_screener_enhanced
python3 app.py
```

### curlでAPIテスト

```bash
# トップページにアクセス
curl http://localhost:5000

# APIエンドポイントをテスト
curl -X POST http://localhost:5000/api/screening \
  -H "Content-Type: application/json" \
  -d '{"method":"perfect_order","options":{"market":"all"}}'

# 過去データAPIをテスト
curl http://localhost:5000/api/history?days=30
```

### プロセス監視

```bash
# プロセスの状態を継続的に監視
watch -n 2 'ps aux | grep "python3 app.py" | grep -v grep'
```

---

## ロリポップサーバーへのデプロイ

### 事前準備

1. **ロリポップサーバーにSSH接続**
2. **Pythonバージョン確認**:
```bash
python3 --version
```

### デプロイ手順

#### 1. ファイルのアップロード

FTPまたはSCPでファイルをアップロード:
```bash
# ローカルからロリポップへ
scp stock_screener_final_20251023_155934.tar.gz user@lolipop-server:/path/to/deploy/
```

#### 2. サーバーで展開

```bash
# ロリポップサーバーにSSH接続
ssh user@lolipop-server

# アーカイブを展開
cd /path/to/deploy/
tar -xzf stock_screener_final_20251023_155934.tar.gz
cd stock_screener_enhanced/
```

#### 3. 環境変数の設定

```bash
# .envファイルを編集
nano .env

# 以下の内容を設定
SUPABASE_URL=https://asdvlrcwkbmwbosecoti.supabase.co
SUPABASE_ANON_KEY=your-anon-key
JQUANTS_REFRESH_TOKEN=your-refresh-token
```

#### 4. 依存パッケージのインストール

```bash
# 仮想環境を作成（推奨）
python3 -m venv venv
source venv/bin/activate

# パッケージをインストール
pip3 install flask supabase pandas numpy aiohttp
```

#### 5. アプリケーションの起動

**開発サーバー（テスト用）**:
```bash
python3 app.py
```

**本番環境（Gunicorn使用）**:
```bash
# Gunicornをインストール
pip3 install gunicorn

# Gunicornで起動
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**デーモン化（systemd）**:

`/etc/systemd/system/stock-screener.service`を作成:
```ini
[Unit]
Description=Stock Screener Web Application
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/stock_screener_enhanced
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

起動:
```bash
sudo systemctl daemon-reload
sudo systemctl start stock-screener
sudo systemctl enable stock-screener
sudo systemctl status stock-screener
```

#### 6. Nginx設定（リバースプロキシ）

`/etc/nginx/sites-available/stock-screener`を作成:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

有効化:
```bash
sudo ln -s /etc/nginx/sites-available/stock-screener /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## トラブルシューティングチェックリスト

### アプリが起動しない場合

- [ ] 必要なパッケージがインストールされているか
- [ ] `.env`ファイルが存在し、正しい内容か
- [ ] ポート5000が空いているか
- [ ] Pythonバージョンが3.11以上か

### 504エラーが発生する場合

- [ ] Flaskプロセスが動作しているか
- [ ] プロセスが停止状態（T）になっていないか
- [ ] ログファイルにエラーがないか
- [ ] curlでローカルアクセスできるか

### データが表示されない場合

- [ ] Supabaseに接続できているか
- [ ] データベースにデータが存在するか
- [ ] APIエンドポイントが正常に動作しているか
- [ ] ブラウザのコンソールにエラーがないか

---

## 緊急時の対処

### 完全リセット手順

```bash
# 1. すべてのFlaskプロセスを終了
kill -9 $(ps aux | grep "python3 app.py" | grep -v grep | awk '{print $2}')

# 2. ポート5000を解放
kill -9 $(lsof -i :5000 | grep LISTEN | awk '{print $2}' | sort -u)

# 3. ログファイルをクリア
rm -f /tmp/flask_*.log

# 4. 環境変数を再設定
export SUPABASE_URL="https://asdvlrcwkbmwbosecoti.supabase.co"
export SUPABASE_ANON_KEY="your-key"
export JQUANTS_REFRESH_TOKEN="your-token"

# 5. アプリを再起動
cd /home/ubuntu/stock_screener_enhanced
nohup python3 -u app.py > /tmp/flask_app.log 2>&1 </dev/null &

# 6. 起動確認
sleep 3
curl -s http://localhost:5000 | head -10
ps aux | grep "python3 app.py" | grep -v grep
```

---

## サポート情報

### ログファイルの場所

- Flask起動ログ: `/tmp/flask_app.log`
- スクリーニングログ: `/home/ubuntu/stock_screener_enhanced/logs/daily_collection_YYYYMMDD.log`

### 設定ファイルの場所

- 環境変数: `/home/ubuntu/stock_screener_enhanced/.env`
- アプリケーション: `/home/ubuntu/stock_screener_enhanced/app.py`
- HTMLテンプレート: `/home/ubuntu/stock_screener_enhanced/templates/index_new.html`

### 重要なコマンド

```bash
# プロセス確認
ps aux | grep "python3 app.py" | grep -v grep

# ポート確認
lsof -i :5000

# ログ確認
tail -f /tmp/flask_app.log

# 環境変数確認
env | grep -E "SUPABASE|JQUANTS"

# アプリ再起動
cd /home/ubuntu/stock_screener_enhanced && nohup python3 -u app.py > /tmp/flask_app.log 2>&1 </dev/null &
```

---

**最終更新**: 2025年10月23日  
**作成者**: Manus AI Agent

