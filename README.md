## データ収集ワークフロー

初期化(大量取得)と日次/定期差分更新を分離しました。

### 1. 初期スクレイプ (手動専用)
初回のみ `apps/scraper/scrape_pokefuta.py` を使用して一括取得します。このスクリプトは「初期化」以外では使いません (GitHub Actions に組み込まないでください)。

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
	- `last_seen`: 内容が変化した時 or 再取得成功時の最新観測日時
	- `added_at`: Web UI 用エイリアス (初期 = first_seen)
	- `source_last_checked`: 直近でページを再取得した日時 (変更なくても更新)
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
	"last_seen": "2025-10-18T00:05:12Z",
	"added_at": "2025-10-18T00:00:00Z",
	"source_last_checked": "2025-10-18T00:05:12Z",
	"status": "active"
}
```

削除検出後は `status: deleted` となり、`docs/pokefuta.ndjson` には出力されません (履歴は `apps/scraper/pokefuta.ndjson` に残る)。

## GitHub Actions
`.github/workflows/scrape-daily.yml` が毎日実行され、差分があれば PR を生成します (手動トリガ可)。

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
- **[マップビュー](https://nishiokya.github.io/pokefuta-tracker/)** - インタラクティブマップでポケふたを地図上で表示
- **[近くのマンホール](https://nishiokya.github.io/pokefuta-tracker/nearby_manholes.html)** - 現在地から近いポケふたをリスト表示

### 機能
- 📍 日本全国のポケふたを地図上で表示
- 🗾 Leafletベースのインタラクティブマップ
- 📝 各ポケふたの詳細情報（場所、ポケモン、公式詳細ページへのリンク）
- 📱 レスポンシブデザイン（PC・スマートフォン対応）
- 📏 位置情報による距離計算と近いマンホールの表示

### データソース
- スクレイピングによって取得した最新のポケふた情報
- NDJSON形式でデータを管理
- 自動デプロイによる定期更新

## 📁 プロジェクト構成

```
apps/
├── web/                      # Webインターフェース
│   ├── pokefuta_map.html    # メインのマップページ
│   ├── nearby_manholes.html # 近くのマンホールリストページ
│   └── pokefuta.ndjson      # ポケふたデータ（NDJSON形式）
├── scraper/                 # データ収集
│   └── scrape_pokefuta.py   # スクレイピングスクリプト
docs/                        # GitHub Pages用
├── index.html              # 公開用マップページ
├── nearby_manholes.html    # 公開用リストページ
└── pokefuta.ndjson         # 公開用データファイル
.github/workflows/           # CI/CD
└── deploy.yml              # GitHub Pages自動デプロイ
```