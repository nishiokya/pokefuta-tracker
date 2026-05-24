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

## 実行方法

```bash
cd apps/tools
python check_quality.py
python enrich_photo_comments.py  # 要 ANTHROPIC_API_KEY
```
