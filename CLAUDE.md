manhole_titles.jsonは手動で更新している
dataset/prefecture_events.json は手動更新（都道府県ページに出す開催中スタンプラリー等のリンク。end_date 過ぎは日次再生成で自動非表示）
pokefuta.ndjsonはapps/scraperで更新している
latest-manhole-photos.json は import-manhole-photos.yml が Supabase から日次自動生成（画像DL込み。手動で回すときだけ `/import-photos` スキル）
docs/api/*.json は bake-app-data.yml が Supabase から日次生成（pokefuta.com アプリの /api/manholes・/api/site-stats がこれを読む）

## ディレクトリ構成

- `apps/scraper/` — GitHub Actions から自動実行されるスクリプト群（update-pokefuta.yml / pages-deploy.yml）
  - `address_parser.py` / `manhole_titles.py` は上記スクリプトの内部ライブラリ
- `apps/tools/` — 手動実行ツール・初期化アーカイブ（例外: import_latest_manhole_photos.py は import-manhole-photos.yml からも呼ばれる）
- `apps/web/` — フロントエンド
