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