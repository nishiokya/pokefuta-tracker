# apps/tools

GitHub Actions からは呼ばれない手動実行ツール群。

## スクリプト一覧

| スクリプト | 用途 |
|---|---|
| `scrape_pokefuta.py` | ポケふた公式サイトから初期データ取得（初期化完了済みアーカイブ） |
| `scrape_gmanhole.py` | ガンダムマンホール初期データ取得（初期化完了済みアーカイブ） |
| `enrich_photo_comments.py` | Claude API でユーザー投稿コメントから施設名・アクセス情報を抽出し `latest-manhole-photos.json` を拡張 |
| `import_latest_manhole_photos.py` | 兄弟サイトの写真を JPEG ローカル化・サムネイル化 |
| `export_pokemon_park_kml.py` | `dataset/pokemon_park.tsv` → KML 変換 |
| `check_quality.py` | `pokefuta.ndjson` の address フィールド完全性チェック |

## 依存パッケージ

`enrich_photo_comments.py` のみ追加パッケージが必要。

```bash
pip install anthropic
```

その他のスクリプトは標準ライブラリのみで動作する。

## 実行方法

プロジェクトルートから実行する（各スクリプトのデフォルトパスがルート相対のため）。

```bash
# データ品質チェック（pokefuta.ndjson は自動解決）
python apps/tools/check_quality.py

# 写真コメント解析（要 pip install anthropic・ANTHROPIC_API_KEY）
python apps/tools/enrich_photo_comments.py

# 写真インポート（週次手動更新）
# 1. apps/web/latest-manhole-photos.json を更新してから実行
cp apps/web/latest-manhole-photos.json docs/latest-manhole-photos.json
# 2. R2 presign でダウンロード（.env.local に R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT が必要）
python3 apps/tools/import_latest_manhole_photos.py --presign-r2
# → dataset/manhole/image/{id}_latest.jpeg が更新される

# ポケモンパーク KML 生成
python apps/tools/export_pokemon_park_kml.py
```
