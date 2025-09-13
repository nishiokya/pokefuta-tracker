# 🔄 Automatic PR Creation System

このプロジェクトでは、ポケふたデータの変更（新規追加・削除）があった場合に自動でプルリクエストを作成し、変更履歴を追跡する機能があります。

## ⚙️ システム概要

### 🤖 自動化ワークフロー
1. **データスクレイピング** - 公式サイトから最新データを取得
2. **データクリーニング** - ポケモン名正規化、重複削除
3. **変更検出** - 新規追加・削除されたIDを特定
4. **変更履歴更新** - CHANGELOG.mdを自動更新
5. **PR作成** - 変更があった場合にプルリクエストを自動作成

### 📋 必要な権限
デフォルトの`GITHUB_TOKEN`を使用するため、追加のSecrets設定は不要です。

## ⚙️ 動作仕様

### 📊 自動実行タイミング
- **毎日10:00 UTC** (19:00 JST) に自動実行
- **手動実行**も可能 (Actions タブから)

### 🔄 PR作成条件
- ✅ **新規ID追加**があった場合
- ❌ **既存ID削除**があった場合
- ℹ️ **変更なし**の場合は通常のコミットのみ

### 📋 PR内容
- **変更サマリー**（追加・削除数、ネット変更数）
- **詳細ID一覧**（追加・削除されたIDの明細）
- **CHANGELOG.md更新**
- **自動ラベル付け**（automated, data-update）
- **ライブマップリンク**

## 🧹 データクリーニング機能

### 自動実行される処理
1. **ポケモン名正規化**
   - 「ずかんへ」「図鑑」などの削除
   - 重複データの除去

2. **都道府県・市町村抽出**
   - タイトルからの自動抽出
   - データ構造の統一

3. **都道府県サイトリンク分離**
   - ポケモン名から分離
   - 専用フィールドへの格納

4. **データ品質向上**
   - 一意性確保
   - 形式統一

## 🚀 使用例

### ローカルでのテスト実行
```bash
cd apps/scraper

# データクリーニングのみ（変更履歴更新なし）
python clean_and_notify.py --input pokefuta.ndjson --output pokefuta.clean.ndjson --no-changelog

# 変更履歴更新付き
python clean_and_notify.py --input pokefuta.ndjson --output pokefuta.ndjson

# カスタムパス指定
python clean_and_notify.py --input raw_data.ndjson --changelog custom_changelog.md
```

### ログレベル調整
```bash
python clean_and_notify.py --log-level DEBUG
```

## 🔍 トラブルシューティング

### PR作成エラー
- GitHub Actionsの権限設定を確認
- `GITHUB_TOKEN`が正しく設定されているか確認
- ブランチ作成権限があるか確認

### データエラー
- JSON形式が正しいか確認
- 必須フィールド（id, lat, lng, detail_url）が存在するか確認
- ファイルエンコーディングがUTF-8であることを確認

## 📈 機能拡張

将来的に以下の機能追加も可能：
- **Slack/Discord通知**
- **カスタムPRテンプレート**
- **詳細変更差分**
- **自動マージ機能**
- **データ品質レポート**

---

🤖 **Generated with [Claude Code](https://claude.ai/code)**