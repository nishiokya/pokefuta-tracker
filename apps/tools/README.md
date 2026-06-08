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
| `import_michineki.py` | 道の駅JSONLDの生成・pokefutaへの roadside 自動登録（[詳細](#import_michinekipy)） |

## 依存パッケージ

`import_latest_manhole_photos.py` と `enrich_photo_comments.py` は追加パッケージが必要。

```bash
pip install -r requirements.txt
```

その他のスクリプトは標準ライブラリのみで動作する。

## 実行方法

プロジェクトルートから実行する（各スクリプトのデフォルトパスがルート相対のため）。

```bash
# 道の駅JSONLD再生成 + roadside自動登録
python3 apps/tools/import_michineki.py          # 本番適用
python3 apps/tools/import_michineki.py --dry-run # 確認のみ

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

## import_michineki.py

### データソース

| 項目 | 内容 |
|---|---|
| URL | `https://linkdata.org/download/rdf1s2861i/link/roadside_station.txt` |
| 元データ | 国土数値情報（道の駅データ）国土交通省 |
| ライセンス | [CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/deed.ja) |
| 形式 | TSV（先頭行 `#property\t...` がカラム定義） |
| 参照元 | https://linkdata.org/work/rdf1s2861i |

### 処理フロー

1. **ダウンロード** — `urllib.request` で TSV を取得
2. **パース** — `#property` ヘッダー行からカラム名を動的に取得し、廃止済み（`iclt:状態 == 廃止`）を除外
3. **名称クリーニング** — Wikipediaスタイルの曖昧さ回避 `_(XXX)` サフィックスを除去し `_` をスペースに変換
4. **JSONLD生成** — schema.org `TouristAttraction` 形式に変換し `dataset/michineki.json` へ保存（**gitignore対象・毎回再生成**）
5. **距離マッチング** — Haversine 50m 以内の pokefuta に `roadside` タグと `building` 名を付与
6. **パッチ適用** — `dataset/manhole_titles.json` を上書き更新

### 再実行のタイミング

- 道の駅データ（linkdata.org）が更新されたとき
- セマンティックエディターを起動する前（`dataset/michineki.json` は gitignore のため、初回 clone や CI 環境では存在しない）

```bash
# セマンティックエディター起動前に必要
python3 apps/tools/import_michineki.py
```

### 出力ファイル

| ファイル | 管理 | 内容 |
|---|---|---|
| `dataset/michineki.json` | gitignore（再生成） | 道の駅 ~1200件 JSON-LD |
| `dataset/manhole_titles.json` | git管理 | roadside タグ・building名 追記済み |
