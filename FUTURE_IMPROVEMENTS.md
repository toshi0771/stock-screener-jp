# 今後の改善提案

## 優先度: 高

### 1. EMA計算方法の検証と調整
**問題**: jQuants APIとTradingViewのEMA計算値に差異がある

**影響**: ファナック（6954）のような銘柄が検出されない

**提案**:
- jQuants APIのEMA計算方法を詳細に調査
- TradingViewのEMA計算方法と比較
- 必要に応じて独自のEMA計算ロジックを実装

**実装例**:
```python
def calculate_ema_tradingview_compatible(series, period):
    """TradingView互換のEMA計算"""
    # TradingViewと同じ初期値とスムージング係数を使用
    alpha = 2 / (period + 1)
    ema = series.ewm(alpha=alpha, adjust=False).mean()
    return ema
```

### 2. タッチ判定の許容誤差設定
**問題**: 厳密な一致判定のため、わずかな差異で検出されない

**提案**: 1-2%の許容誤差を設定

**実装例**:
```python
TOUCH_TOLERANCE = 0.01  # 1%

def is_ema_touched(low, high, ema, tolerance=TOUCH_TOLERANCE):
    """許容誤差を考慮したEMAタッチ判定"""
    low_with_tolerance = low * (1 - tolerance)
    high_with_tolerance = high * (1 + tolerance)
    return low_with_tolerance <= ema <= high_with_tolerance
```

### 3. データ取得確認機能
**問題**: データが取得できているか確認できない

**提案**: データ取得状況をログに出力

**実装例**:
```python
logger.info(f"データ取得期間: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
logger.info(f"取得データ件数: {len(df)}件")
logger.info(f"最新データ日付: {df['Date'].max()}")

# 当日のデータが取得できているか確認
today_str = end_date.strftime('%Y-%m-%d')
if today_str not in df['Date'].values:
    logger.warning(f"⚠️ {today_str}のデータが取得できていません")
```

## 優先度: 中

### 4. リトライロジックの強化
**問題**: API制限やネットワークエラーで一部銘柄のデータ取得が失敗する

**提案**: 
- リトライ回数を増やす（現在3回 → 5回）
- エクスポネンシャルバックオフを実装
- 失敗した銘柄を記録して再試行

### 5. パフォーマンス最適化
**問題**: 3788銘柄の処理に時間がかかる

**提案**:
- 同時実行数を調整（現在20 → 30-50）
- データキャッシュの実装
- 前日から変化がない銘柄をスキップ

### 6. アラート機能
**問題**: 検出数が異常に少ない場合に気づけない

**提案**:
- 検出数が閾値以下の場合にアラートを送信
- メール通知またはSlack通知

**実装例**:
```python
ALERT_THRESHOLD = 3  # 3銘柄以下でアラート

if detected_count < ALERT_THRESHOLD:
    logger.error(f"🚨 検出数が異常に少ないです: {detected_count}銘柄")
    # メールまたはSlack通知を送信
```

## 優先度: 低

### 7. バックテスト機能
**提案**: 過去のデータで検出精度を検証

### 8. Web UIの改善
**提案**: 
- 検出履歴のグラフ表示
- 銘柄の詳細チャート表示
- フィルター機能の追加

### 9. 複数のデータソース対応
**提案**: jQuants API以外のデータソースも利用可能にする

### 10. ドキュメント整備
**提案**:
- API仕様書
- スクリーニングロジックの詳細説明
- トラブルシューティングガイド

## 実装スケジュール案

### 短期（1週間以内）
- [ ] データ取得確認機能の追加
- [ ] アラート機能の実装

### 中期（1ヶ月以内）
- [ ] EMA計算方法の検証と調整
- [ ] タッチ判定の許容誤差設定
- [ ] リトライロジックの強化

### 長期（3ヶ月以内）
- [ ] パフォーマンス最適化
- [ ] バックテスト機能
- [ ] Web UIの改善
