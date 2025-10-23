## データ収集ワークフロー

初期化(大量取得)と日次/定期差分更新を分離しました。

### 1. 初期スクレイプ (手動専用)
初回のみ `apps/scraper/scrape_pokefuta.py` を使用して一括取- 📍 ### 機能
- 📍 日本全国のポケふたを地図上で表示
- 🗾 Leafletベースのインタラクティブマップ
- 📝 各ポケふたの詳細情報（場所、ポケモン、公式詳細ページへのリンク）
- 📱 レスポンシブデザイン（PC・スマートフォン対応）
- 🔍 フィルタ (都道府県 / ポケモン / 最近追加)
- 📍 近くのマンホール表示機能 (`nearby_manholes.html`)ふたを地図上で表示
- 🗾 Leafletベースのインタラクティブマップ
- 📝 各ポケふたの詳細情報（場所、ポケモン、公式詳細ページへのリンク）
- 📱 レスポンシブデザイン（PC・スマートフォン対応）
- 🔍 フィルタ (都道府県 / ポケモン / 最近追加)
- 📍 近くのマンホール表示機能 (`nearby_manholes.html`)のスクリプトは「初期化」以外では使いません (GitHub Actions に組み込まないでください)。

例:
```bash
python apps/scraper/scrape_pokefuta.py --scan-max 500 --out apps/scraper/pokefuta.ndjson
git add apps/scraper/pokefuta.ndjson && git commit -m "feat: initial dataset"
```

公開用コピー:
```bash
cp apps/scraper/pokefuta.ndjson docs/pokefuta.ndjson
git add docs/pokefuta.ndjson && git commit -m "chore: publish initial dataset"
```

### 2. 差分アップデート (GitHub Actions / 手動検証)
日次は `.github/workflows/scrape-daily.yml` が `apps/scraper/update_pokefuta.py` を実行します。主な処理:
1. 新規マンホール検出 (未登録 ID でページ取得成功)
2. 削除検出 (以前 active だった ID が 404 もしくは座標抽出失敗) → status=deleted
3. 変更検出 (タイトル / lat / lng / pokemons の差分)
4. スキーマ拡張フィールド更新:
	- `first_seen`: 初回検出日時 (UTC ISO8601)
	- `added_at`: Web UI 最近追加フィルタ用 (常に first_seen と同値)
	- `last_updated`: 内容差分または status 変化が発生した最新日時 (差分ない再取得では更新しない)
	- `status`: active | deleted
5. `apps/scraper/pokefuta.ndjson` を全レコード (deleted 含む) で更新
6. 公開用 `docs/pokefuta.ndjson` は active のみ出力
7. 差分を `CHANGELOG.md` に追記し、変更あれば自動 PR 作成

ローカル検証例:
```bash
python apps/scraper/update_pokefuta.py --scan-max 200 --out apps/scraper/pokefuta.ndjson --copy-to docs/pokefuta.ndjson --log-level DEBUG
git diff --name-only
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

### 1. データ更新 (差分検出 + PR): `.github/workflows/scrape-daily.yml`
毎日 10:00 UTC に実行し、以下のみを行います:
- スクレイピング差分更新 (`apps/scraper/update_pokefuta.py`)
- 内部データファイル更新 (`apps/scraper/pokefuta.ndjson` 全レコード)
- 差分あれば `CHANGELOG.md` 追記と PR 作成 (生成物は含めない)

公開用 active レコードはワークフロー内で一時的に `/tmp/pokefuta_public.ndjson` に書き出し、コミットしません。

### 2. Pages Artifact ビルド & デプロイ: `.github/workflows/pages-deploy.yml`
毎日 10:30 UTC (更新後) に実行し、以下を行います:
1. `dist/` を作成し active レコードのみの `pokefuta.ndjson` を生成。
2. ソース HTML (`apps/web/*.html`) を `dist/index.html`, `dist/nearby.html` としてコピー。
3. 旧 URL 互換用リダイレクト `dist/nearby_manholes.html` を生成。
4. アセット/アイコンを `dist/` へ配置。
5. `upload-pages-artifact` → `deploy-pages` で GitHub Pages に反映。

`dist/` は Git にコミットせず、生成物を履歴から排除することで PR ノイズとリポジトリ肥大化を防ぎます。

### フロントエンド編集ポリシー
編集対象は **`apps/web/index.html`** / **`apps/web/nearby_manholes.html`** などソースのみ。公開ページは Artifact から生成されるため直接編集できません。

### 移行履歴
以前は `docs/` フォルダをコミットして公開していましたが Artifact 方式へ移行し、今後削除予定です (互換リダイレクトは Artifact 内で再生成)。

## 今後の改善アイデア
- 多言語ポケモン名の正規化マッピング
- レート制限 / リトライ戦略の自動調整 (サーバ負荷軽減)
- 失敗 ID リトライキューの永続化
- 削除済み一覧の別エンドポイント化 (`deleted.ndjson`)

# Pokefuta Tracker

訪れたポケモンマンホール（ポケふた）を管理・可視化するためのアプリケーションです。
地図上にポケふたを表示し、訪問済みのチェック、進捗管理、CSV/GeoJSONエクスポートなどが可能です。

## 🌐 ポケふたマップ（GitHub Pages）

インタラクティブなポケふたマップをGitHub Pagesで公開しています：

### ページ一覧
- **[マップビュー](https://data.pokefuta.com/)** - インタラクティブマップでポケふたを地図上で表示
- **[近くのマンホール](https://data.pokefuta.com/nearby_manholes.html)** - 現在地から近いポケふたを検索
- **[ガンダム & ポケふた統合マップ (試験)](https://nishiokya.github.io/pokefuta-tracker/gmanhole_map.html)** - ガンダムマンホール + ポケふたを同時可視化 (重複座標ハイライト)

### 機能
- 📍 日本全国のポケふたを地図上で表示
- 🗾 Leafletベースのインタラクティブマップ
- 📝 各ポケふたの詳細情報（場所、ポケモン、公式詳細ページへのリンク）
- 📱 レスポンシブデザイン（PC・スマートフォン対応）
- � フィルタ (都道府県 / ポケモン / 最近追加)
- ※ 近くのマンホール表示機能 (旧 `nearby.html`) は廃止しました。要望があれば低精度版 / PWA 版として再検討します。

### データソース
- スクレイピングによって取得した最新のポケふた情報
- NDJSON形式でデータを管理
- 自動デプロイによる定期更新

## 🤖 ガンダムマンホール対応 (試験的機能)

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

### 今後の拡張予定
- キャラクター/シリーズ語彙の自動強化
- 作品別フィルタ UI
- JIS コード付与 / GeoJSON エクスポート
- 重複地点での統合ポップアップ

フィードバック歓迎です。ガンダム側スキーマ安定後に CI 経由で自動更新へ移行予定です。

## 📁 プロジェクト構成 (移行後)

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