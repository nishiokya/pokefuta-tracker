manhole_titles.jsonは手動で更新している
pokefuta.ndjsonはapps/scraperで更新している
latest-manhole-photos.json　はpokefuta.comからもらっている（週次手動更新）
docs/api/*.json は bake-app-data.yml が Supabase から日次生成（pokefuta.com アプリの /api/manholes・/api/site-stats がこれを読む）
- apps/web/ を更新したら `/import-photos` スキルを実行 → docs/ 同期 + dataset/manhole/image/ ダウンロード

## ディレクトリ構成

- `apps/scraper/` — GitHub Actions から自動実行されるスクリプト群（update-pokefuta.yml / pages-deploy.yml）
  - `address_parser.py` / `manhole_titles.py` は上記スクリプトの内部ライブラリ
- `apps/tools/` — 手動実行ツール・初期化アーカイブ（CI からは呼ばれない）
- `apps/web/` — フロントエンド
