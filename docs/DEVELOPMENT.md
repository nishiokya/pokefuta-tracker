# 開発者向けドキュメント

## データ収集ワークフロー

初期化(大量取得)と日次/定期差分更新を分離しました。

### 1. 初期スクレイプ (手動専用)
初回のみ `apps/scraper/scrape_pokefuta.py` を使用して一括取得します。このスクリプトは「初期化」以外では使いません (GitHub Actions に組み込まないでください)。

例:
```bash
python apps/scraper/scrape_pokefuta.py --scan-max 500 --out apps/scraper/pokefuta.ndjson
git add apps/scraper/pokefuta.ndjson && git commit -m "feat: initial dataset"
```

公開用コピー（docs/ へ active レコードのみ）:
```bash
python -c "
import json
with open('apps/scraper/pokefuta.ndjson', 'r', encoding='utf-8') as f:
    active_records = [json.loads(line) for line in f if json.loads(line).get('status') == 'active']

with open('docs/pokefuta.ndjson', 'w', encoding='utf-8') as f:
    for record in active_records:
        json.dump(record, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
"
git add docs/pokefuta.ndjson && git commit -m "chore: publish initial dataset"
```

### 2. 差分アップデート (GitHub Actions / 手動検証)
日次 10:00 UTC は `.github/workflows/update-pokefuta.yml` が `apps/scraper/update_pokefuta.py` を実行します。主な処理:

1. 新規マンホール検出 (未登録 ID でページ取得成功)
2. 削除検出 (以前 active だった ID が 404 もしくは座標抽出失敗) → status=deleted
3. 変更検出 (タイトル / lat / lng / pokemons の差分)
4. スキーマ拡張フィールド更新:
	- `first_seen`: 初回検出日時 (UTC ISO8601)
	- `added_at`: Web UI 最近追加フィルタ用 (常に first_seen と同値)
	- `last_updated`: 内容差分または status 変化が発生した最新日時 (差分ない再取得では更新しない)
	- `status`: active | deleted
5. **内部用** `apps/scraper/pokefuta.ndjson` を全レコード (deleted 含む) で更新
6. **公開用** `docs/pokefuta.ndjson` は active レコードのみ出力
7. 差分を `CHANGELOG.md` に追記し、変更あれば自動 PR 作成

**重要：** 内部版（`apps/scraper/pokefuta.ndjson`）は削除済みレコードも保持し、完全な履歴を保証します。公開版（`docs/pokefuta.ndjson`）は軽量化のため active レコードのみ配信します。

ローカル検証例:
```bash
python apps/scraper/update_pokefuta.py --scan-max 200 --out apps/scraper/pokefuta.ndjson --log-level DEBUG
git diff apps/scraper/pokefuta.ndjson --name-only
```

### スキーマ拡張 (NDJSON)
各行の JSON オブジェクト例 (active レコード):
```json
{
	"id": "123",
	"title": "鹿児島県/指宿市 ポケふた",
	"title_en": "",
	"title_zh": "",
	"prefecture": "鹿児島県",
	"city": "指宿市",
	"address": "...",
	"city_url": "https://...",
	"lat": 31.12345,
	"lng": 130.54321,
	"pokemons": ["イーブイ"],
	"pokemons_en": [],
	"pokemons_zh": [],
	"detail_url": "https://local.pokemon.jp/manhole/desc/123/?is_modal=1",
	"prefecture_site_url": "",
	"first_seen": "2025-10-18T00:00:00Z",
	"added_at": "2025-10-18T00:00:00Z",
	"last_updated": "2025-10-18T00:05:12Z",
	"status": "active"
}
```

削除検出後は `status: deleted` となり、`docs/pokefuta.ndjson` には出力されません (履歴は内部ファイルに保持)。`last_seen` / `source_last_checked` は 2025-10-19 の変更で廃止され `last_updated` に統合、差分ない取得では更新されないため PR のノイズが減ります。

## GitHub Actions (Artifact デプロイ方式)
日次差分更新と公開デプロイを分離しました。

### 1. データ更新 (差分検出 + PR): `.github/workflows/update-pokefuta.yml`
**毎日 10:00 UTC** に実行し、以下のみを行います:
- スクレイピング差分更新 (`apps/scraper/update_pokefuta.py`)
- **内部用** `apps/scraper/pokefuta.ndjson` を全レコード（deleted 含む）で更新
- **公開用** `docs/pokefuta.ndjson` を active レコードのみで更新
- 差分あれば `CHANGELOG.md` 追記と PR 作成
- KML スナップショット生成 (`docs/pokefuta.kml`)

### 2. Pages Artifact ビルド & デプロイ: `.github/workflows/pages-deploy.yml`
**毎日 10:30 UTC** (update-pokefuta.yml 実行後) に実行し、以下を行います:
1. `dist/` ディレクトリを作成
2. 公開用データ (`docs/pokefuta.ndjson`) を `dist/` へコピー
3. ソース HTML (`apps/web/*.html`) を `dist/index.html`, `dist/nearby.html` としてコピー
4. 旧 URL 互換用リダイレクト `dist/nearby_manholes.html` を生成
5. アセット/アイコンを `dist/assets/` へ配置
6. `upload-pages-artifact` → `deploy-pages` で GitHub Pages に反映

**重要：** `dist/` は Git にコミットされず、毎回フレッシュに生成されます。これにより PR ノイズとリポジトリ肥大化を防ぎます。

### ディレクトリ構成

| ディレクトリ | 役割 | 管理方式 |
|-----------|------|----------|
| `apps/scraper/pokefuta.ndjson` | **内部用完全版** - 全レコード (active + deleted) の主要データソース | Git コミット・手動/自動更新 |
| `docs/pokefuta.ndjson` | **公開用アクティブ版** - active レコードのみ。GitHub Releases、API エンドポイント、README の参照先 | Git コミット・自動更新 (update-pokefuta.yml) |
| `docs/*.kml` | **KML スナップショット** - Google Earth 互換形式 | Git コミット・自動更新 |
| `dist/pokefuta.ndjson` | **Pages Artifact 用** - 公開用アクティブ版の複製 | Git 未追跡・生成物 |
| `apps/web/*.html` | **Web UI ソース** - 編集対象 | Git コミット・手動編集 |
| `dist/*` | **Pages 公開物** - HTML + assets + data の統合 | Git 未追跡・pages-deploy.yml が生成 |

### フロントエンド編集ポリシー
編集対象は **`apps/web/index.html`** / **`apps/web/nearby_manholes.html`** などソースのみ。公開ページは Artifact から生成されるため直接編集できません。

### 削除済みレコードの管理
- **内部版** (`apps/scraper/pokefuta.ndjson`): `status=deleted` レコードを永続保持し、削除履歴を保証
- **公開版** (`docs/pokefuta.ndjson`): active レコードのみを配信（軽量化・ユーザー体験向上）

## 今後の改善アイデア
- 多言語ポケモン名の正規化マッピング
- レート制限 / リトライ戦略の自動調整 (サーバ負荷軽減)
- 失敗 ID リトライキューの永続化
- 削除済み一覧の別エンドポイント化 (`deleted.ndjson`)

## ガンダムマンホール対応 (試験的機能)

`apps/scraper/scrape_gmanhole.py` によりガンダムマンホール公式サイトの連番詳細ページから以下を抽出しています:

- id / title / prefecture / city / address / image_urls / characters / series / slug / images_count
- ジオコーディング (国土地理院 API 既定 / `--geocode-provider` 切り替え)
- timestamps: first_seen / added_at / last_updated / status

公開マップ: **[ガンダム & ポケふた統合マップ](https://nishiokya.github.io/pokefuta-tracker/gmanhole_map.html)**

### スクレイプ例
```bash
python apps/scraper/scrape_gmanhole.py --scan-max 80 --geocode --geocode-provider gsi --out gmanhole.ndjson
cp gmanhole.ndjson apps/web/assets/gmanhole.ndjson
```

### 緯度経度補完機能
緯度経度が不明なガンダムマンホールを手動で補完するためのツールを提供しています：

```bash
# 緯度経度が不明なレコードをTSVファイルに抽出
python3 extract_missing_coordinates.py

# 生成されたTSVファイル (missing_gundam_coordinates.tsv) を編集して
# lat, lng 列に緯度経度を手動入力

# スクレイピング時にTSVファイルを参照して座標を補完
# (coordinate_supplementor.py を使用)
```

TSVファイルには以下の情報が含まれます：
- ID, タイトル, 都道府県, 市町村, 住所
- 詳細URL, キャラクター, シリーズ情報
- 緯度経度入力欄と備考欄

### 今後の拡張予定
- キャラクター/シリーズ語彙の自動強化
- 作品別フィルタ UI
- JIS コード付与 / GeoJSON エクスポート
- 重複地点での統合ポップアップ

フィードバック歓迎です。ガンダム側スキーマ安定後に CI 経由で自動更新へ移行予定です。

## プロジェクト構成 (移行後)

```
apps/
├── web/                      # Webインターフェース (ソース HTML と静的資産)
│   ├── index.html           # メインのマップページ (ソース)
│   ├── nearby_manholes.html # 近くのマンホールページ (ソース)
│   └── assets/              # CSS 等
├── scraper/                 # データ収集ロジック
│   ├── scrape_pokefuta.py   # 初期一括取得
│   └── update_pokefuta.py   # 日次差分更新
.github/workflows/           # CI/CD ワークフロー
│   ├── scrape-daily.yml     # データ差分 + PR (生成物コミットなし)
│   └── pages-deploy.yml     # Artifact 作成 + Pages デプロイ
dist/                        # (生成物) Git 未コミット / Actions 内で生成
└── (index.html / pokefuta.ndjson / assets ...)

※ 旧 `docs/` は移行後削除予定 (互換リダイレクトは dist に生成)。
```
