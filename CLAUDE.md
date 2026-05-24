manhole_titles.jsonは手動で更新している
pokefuta.ndjsonはapp/scraperで更新している
latest-manhole-photos.json　はpokefuta.comからもらっている

## ディレクトリ構成

- `apps/scraper/` — GitHub Actions から自動実行されるスクリプト群（update-pokefuta.yml / pages-deploy.yml）
  - `address_parser.py` / `manhole_titles.py` は上記スクリプトの内部ライブラリ
- `apps/tools/` — 手動実行ツール・初期化アーカイブ（CI からは呼ばれない）
- `apps/web/` — フロントエンド
