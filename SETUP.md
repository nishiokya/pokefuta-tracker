# 🔄 セットアップガイドと開発ワークフロー

このドキュメントは、pokefuta-tracker プロジェクトの初期セットアップ、ディレクトリ構造、およびデータフローについて説明します。

## 📁 ディレクトリ構造

```
pokefuta-tracker/
├── apps/
│   ├── scraper/                    # データ収集・処理エンジン
│   │   ├── pokefuta.ndjson         # 【内部用・完全版】全レコード (active + deleted)
│   │   ├── scrape_pokefuta.py      # 初期化スクリプト（手動専用）
│   │   ├── update_pokefuta.py      # 日次差分更新（GitHub Actions自動）
│   │   ├── export_kml.py           # KML生成
│   │   ├── export_pokemon_park_kml.py # Pokemon Park KML生成
│   │   ├── clean_and_notify.py     # データクリーニング（参考）
│   │   ├── fill_address.py         # 住所フィールド自動補完
│   │   └── test_pokefuta.json      # テストデータ
│   └── web/                        # Web UI ソースコード
│       ├── index.html              # メインマップ
│       ├── nearby_manholes.html    # 近くのマンホール検索
│       ├── gmanhole_map.html       # ガンダムマンホール統合マップ
│       └── assets/                 # CSS・アイコン・リソース
├── dataset/                        # 手動管理メタデータ
│   ├── title.tsv                   # ポケふた詳細情報（住所、建物名、リンク等）
│   ├── pokemon_park.tsv            # ポケモンパーク情報
│   ├── mie_stamp_2025_v2.tsv       # 三重県スタンプ情報
│   ├── city_link.tsv               # 市区町村リンク
│   └── manhole_icon.png            # マンホールアイコン
├── docs/                           # 【公開用・アクティブ版】GitHub Pages用
│   ├── pokefuta.ndjson             # 公開データ（active レコードのみ）
│   ├── pokefuta.kml                # KML スナップショット
│   ├── index.html                  # ドキュメント
│   └── DEVELOPMENT.md              # 開発者向けドキュメント
├── dist/                           # GitHub Pages Artifact生成物（Git未追跡）
│   ├── index.html                  # pages-deploy.yml により生成
│   ├── pokefuta.ndjson             # 公開版データ複製
│   ├── assets/                     # CSS・アイコン
│   └── ...
├── schema/
│   └── database.sql                # DB スキーマ（予約）
├── .github/workflows/              # GitHub Actions ワークフロー
│   ├── update-pokefuta.yml         # 日次 10:00 UTC: データ更新 + 差分検出 + PR作成
│   └── pages-deploy.yml            # 日次 10:30 UTC: Pages Artifact ビルド＆デプロイ
├── SCHEMA.md                       # データスキーマ仕様書
├── DEVELOPMENT.md                  # 開発ガイド（詳細）
├── requirements.txt                # Python依存パッケージ
└── README.md                       # プロジェクト概要
```

## 🚀 初期セットアップ

### 1. 環境構築
```bash
# リポジトリクローン
git clone https://github.com/nishiokya/pokefuta-tracker.git
cd pokefuta-tracker

# Python仮想環境作成
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# または
.venv\Scripts\activate  # Windows

# 依存パッケージインストール
pip install -r requirements.txt
pip install beautifulsoup4 requests lxml
```

### 2. 初期データセット作成（初回のみ）
```bash
# Pokemon公式サイトから全ポケふたデータを一括取得
python apps/scraper/scrape_pokefuta.py --scan-max 500 --out apps/scraper/pokefuta.ndjson

# 内部版が完成したら、公開版（active のみ）を作成
python -c "
import json
with open('apps/scraper/pokefuta.ndjson', 'r', encoding='utf-8') as f:
    active_records = [json.loads(line) for line in f if json.loads(line).get('status') == 'active']

with open('docs/pokefuta.ndjson', 'w', encoding='utf-8') as f:
    for record in active_records:
        json.dump(record, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
"

# コミット
git add apps/scraper/pokefuta.ndjson docs/pokefuta.ndjson
git commit -m "feat: initialize pokefuta dataset"
```

### 3. メタデータ設定
`dataset/title.tsv` に手動で詳細情報（住所、施設名など）を入力してください。

```bash
# 初期テンプレート（オプション）
# dataset/title.tsv の構造：
# id    title    address    building    ...
# 1     ...      ...        ...         ...
```

## 📊 データフロー

### 日次更新ワークフロー（自動）

```
10:00 UTC: update-pokefuta.yml
├─ update_pokefuta.py --scan-max 500
│  ├─ 新規ID検出
│  ├─ 削除検出（404ページ）
│  ├─ 変更検出（lat/lng/pokemons）
│  └─ CHANGELOG.md 更新
├─ apps/scraper/pokefuta.ndjson 更新（全レコード + deleted保持）
├─ docs/pokefuta.ndjson 更新（active のみ）
├─ export_kml.py で docs/pokefuta.kml 生成
├─ 差分があれば PR 作成
└─ PR をマージ

10:30 UTC: pages-deploy.yml
├─ dist/ ディレクトリ作成
├─ docs/pokefuta.ndjson → dist/ コピー
├─ apps/web/*.html → dist/ コピー
├─ assets/ → dist/assets/ コピー
├─ upload-pages-artifact で Artifact生成
└─ GitHub Pages へ自動デプロイ
```

## 🔧 手動コマンド

### ローカルでのテスト

```bash
# 差分更新のテスト（スキャン数制限）
python apps/scraper/update_pokefuta.py \
  --scan-max 100 \
  --out apps/scraper/pokefuta.ndjson \
  --log-level DEBUG

# KML スナップショット生成
python apps/scraper/export_kml.py \
  --input apps/scraper/pokefuta.ndjson \
  --output docs/pokefuta.kml

# Pokemon Park KML生成
python apps/scraper/export_pokemon_park_kml.py \
  --input dataset/pokemon_park.tsv \
  --output docs/pokemon_park.kml
```

### 住所フィールド自動補完

```bash
# 公式ページから住所情報を抽出して fill_address.py で自動補完
python apps/scraper/fill_address.py \
  --in docs/pokefuta.ndjson \
  --out docs/pokefuta_filled.ndjson \
  --sleep 1.0 \
  --limit 50
```

## 📋 重要なポイント

### ✅ 内部版（apps/scraper/pokefuta.ndjson）
- **削除済みレコード（status=deleted）も保持** → 完全な履歴管理
- **全スキーマフィールドを保持** → メタデータ拡張対応
- **Git コミット対象** → 履歴追跡

### ✅ 公開版（docs/pokefuta.ndjson）
- **Active レコードのみ** → 軽量配信
- **GitHub Pages・API エンドポイント** → 外部参照先
- **GitHub Raw URL** → 他プロジェクトから利用可能
- **Git コミット対象** → 変更追跡

### ✅ Pages Artifact (dist/pokefuta.ndjson)
- **公開版のコピー** → pages-deploy.yml で生成
- **Git 未追跡** → リポジトリ肥大化防止
- **毎回フレッシュ生成** → 常に最新データを配信

## 🔄 自動 PR 作成システム

毎日 10:00 UTC に実行される `update-pokefuta.yml` ワークフロー：
- ポケふたデータを差分更新
- 新規追加・削除を検出
- CHANGELOG.md を自動更新
- **変更があれば自動で PR を作成**
- PR をマージすると、10:30 UTC に自動で Pages デプロイ

## 🆘 トラブルシューティング

### PR が作成されない
- `.github/workflows/update-pokefuta.yml` が正しいか確認
- `GITHUB_TOKEN` 権限を確認
- スクレイピング対象が更新されているか確認

### データファイルが古い
- `docs/pokefuta.ndjson` の最終更新日時を確認
- `apps/scraper/pokefuta.ndjson` のレコード数と比較
- Pages Artifact ビルドログを確認

### ローカルで動作確認したい
```bash
# 現在のワークフローを再現
python apps/scraper/update_pokefuta.py --scan-max 50 --out test_output.ndjson

# 公開版を作成
python -c "
import json
with open('test_output.ndjson', 'r') as f:
    records = [json.loads(line) for line in f if json.loads(line).get('status') == 'active']
with open('test_public.ndjson', 'w') as f:
    for r in records:
        json.dump(r, f, ensure_ascii=False)
        f.write('\n')
"
```

## 📖 関連ドキュメント
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - 開発ガイド（詳細）
- [SCHEMA.md](SCHEMA.md) - データスキーマ仕様書
- [README.md](README.md) - プロジェクト概要