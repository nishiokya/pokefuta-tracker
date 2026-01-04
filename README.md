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
- 🔍 フィルタ (都道府県 / ポケモン / 最近追加)

## 📊 オープンデータ

収集したマンホールデータは `data/` ディレクトリで公開しています。

- **[data/pokefuta.ndjson](data/pokefuta.ndjson)**: ポケふたの全データ (NDJSON形式)
- **[data/gmanhole.ndjson](data/gmanhole.ndjson)**: ガンダムマンホールのデータ (NDJSON形式)

### Pokemon Park KML の生成

`dataset/pokemon_park.tsv` から KML スナップショットを作るには、以下のスクリプトを手動で実行します。

```bash
python3 apps/scraper/export_pokemon_park_kml.py \
	--input dataset/pokemon_park.tsv \
	--output docs/pokemon_park.kml
```

生成された `docs/pokemon_park.kml` は GitHub Pages などにそのまま配置できます。

## 🛠️ 開発者向け

データ収集スクリプトや開発環境のセットアップについては [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) を参照してください。