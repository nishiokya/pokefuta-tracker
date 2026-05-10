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

### 都道府県別リンク
以下のリンクから各都道府県のポケふたをすぐに表示できます：

**北海道地方**
- [北海道](https://data.pokefuta.com/?pref=北海道)
- [青森県](https://data.pokefuta.com/?pref=青森県)
- [岩手県](https://data.pokefuta.com/?pref=岩手県)
- [宮城県](https://data.pokefuta.com/?pref=宮城県)
- [秋田県](https://data.pokefuta.com/?pref=秋田県)
- [山形県](https://data.pokefuta.com/?pref=山形県)
- [福島県](https://data.pokefuta.com/?pref=福島県)

**関東地方**
- [茨城県](https://data.pokefuta.com/?pref=茨城県)
- [栃木県](https://data.pokefuta.com/?pref=栃木県)
- [埼玉県](https://data.pokefuta.com/?pref=埼玉県)
- [千葉県](https://data.pokefuta.com/?pref=千葉県)
- [東京都](https://data.pokefuta.com/?pref=東京都)
- [神奈川県](https://data.pokefuta.com/?pref=神奈川県)

**中部地方**
- [新潟県](https://data.pokefuta.com/?pref=新潟県)
- [富山県](https://data.pokefuta.com/?pref=富山県)
- [石川県](https://data.pokefuta.com/?pref=石川県)
- [福井県](https://data.pokefuta.com/?pref=福井県)
- [岐阜県](https://data.pokefuta.com/?pref=岐阜県)
- [静岡県](https://data.pokefuta.com/?pref=静岡県)
- [愛知県](https://data.pokefuta.com/?pref=愛知県)

**近畿地方**
- [三重県](https://data.pokefuta.com/?pref=三重県)
- [滋賀県](https://data.pokefuta.com/?pref=滋賀県)
- [京都府](https://data.pokefuta.com/?pref=京都府)
- [大阪府](https://data.pokefuta.com/?pref=大阪府)
- [兵庫県](https://data.pokefuta.com/?pref=兵庫県)
- [奈良県](https://data.pokefuta.com/?pref=奈良県)
- [和歌山県](https://data.pokefuta.com/?pref=和歌山県)

**中国・四国地方**
- [鳥取県](https://data.pokefuta.com/?pref=鳥取県)
- [島根県](https://data.pokefuta.com/?pref=島根県)
- [岡山県](https://data.pokefuta.com/?pref=岡山県)
- [山口県](https://data.pokefuta.com/?pref=山口県)
- [徳島県](https://data.pokefuta.com/?pref=徳島県)
- [香川県](https://data.pokefuta.com/?pref=香川県)
- [愛媛県](https://data.pokefuta.com/?pref=愛媛県)
- [高知県](https://data.pokefuta.com/?pref=高知県)

**九州・沖縄地方**
- [福岡県](https://data.pokefuta.com/?pref=福岡県)
- [佐賀県](https://data.pokefuta.com/?pref=佐賀県)
- [長崎県](https://data.pokefuta.com/?pref=長崎県)
- [宮崎県](https://data.pokefuta.com/?pref=宮崎県)
- [鹿児島県](https://data.pokefuta.com/?pref=鹿児島県)
- [沖縄県](https://data.pokefuta.com/?pref=沖縄県)

## 📊 オープンデータ

収集したマンホールデータは公開リポジトリ (`docs/` ディレクトリ) で公開しています。

- **[docs/pokefuta.ndjson](docs/pokefuta.ndjson)**: ポケふたの公開データ（active レコードのみ、NDJSON形式）
- **[apps/web/assets/gmanhole.ndjson](apps/web/assets/gmanhole.ndjson)**: ガンダムマンホールのデータ (NDJSON形式)

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