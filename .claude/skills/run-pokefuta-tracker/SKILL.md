---
name: run-pokefuta-tracker
description: Build, run, smoke-test, and screenshot the pokefuta-tracker static site (data.pokefuta.com) locally. Use when asked to run/start the app or dev server, verify a change in the real browser, take a screenshot of a page, or smoke-test the site build.
---

# Run pokefuta-tracker

静的サイト（GitHub Pages / data.pokefuta.com）。ソースは `apps/web/` + Python生成スクリプト（`apps/scraper/`）→ `dist/`（gitignore済み）に焼き込み、`python3 -m http.server` で配信する。エージェントは **`driver.sh`** で起動・スモーク・スクリーンショットまで一発で行う。パスはすべてリポジトリルート基準。

## Run（エージェント用 — まずこれ）

```bash
.claude/skills/run-pokefuta-tracker/driver.sh
```

やること: `apps/web/` → `dist/` 同期 → :8000 で配信（nohupでデタッチ、シェルが死んでも生存）→ 主要10ページの curl スモーク（200+コンテンツマーカー）→ ヘッドレスChromeで4枚スクリーンショット。**最後に `ALL OK` が出て、サーバーは起動したまま残る。**

- スクリーンショット出力先: `$TMPDIR/pokefuta-run/{index,design_manhole,character_manholes,prefecture}.png` — **必ず Read で目視確認する**（真っ白/エラーページならFAIL扱い）
- ポート/出力先の変更: `PORT=8001 SS_DIR=/path driver.sh`
- 停止: `.claude/skills/run-pokefuta-tracker/driver.sh stop`
- 前提: `dist/` が存在すること。無ければ下の Build を先に実行。

個別ページを追加でスクリーンショットしたい場合（driver.shの `shot` と同じパターン）:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --user-data-dir="$(mktemp -d)" --window-size=1280,900 --virtual-time-budget=8000 \
  --screenshot=/tmp/page.png http://localhost:8000/summary/ >/dev/null 2>&1 &
CPID=$!; for _ in $(seq 1 30); do [ -s /tmp/page.png ] && break; sleep 1; done; kill $CPID 2>/dev/null
```

## Prerequisites

- Python 3（3.14で検証）。サイトビルドの外部依存は **Pillow のみ**（`generate_summary_ogp.py` 用）。確認: `python3 -c "import PIL"`
- 無い場合: `python3 -m venv .venv && .venv/bin/pip install Pillow` して `python3` を `.venv/bin/python3` に読み替え
- `pip3 install -r requirements.txt` は **Homebrew Python では失敗する**（PEP 668 externally-managed）。requirements.txt の bs4/cairosvg/requests はスクレイパー（CI）用で、ローカルのサイトビルドには不要
- スクリーンショット: Google Chrome（`/Applications/Google Chrome.app`）

## Build（クリーンチェックアウト → dist/ 生成、約1〜2分）

pages-deploy.yml と同じ手順のローカル版。全部リポジトリルートで実行（検証済み）:

```bash
python3 apps/scraper/generate_prefecture_trivia.py --check
python3 apps/scraper/generate_manhole_pages.py
python3 apps/scraper/generate_pokemon_pages.py
python3 apps/scraper/generate_pokemon_index_page.py
python3 apps/scraper/generate_character_manhole_page.py --output dist/character_manholes.html
python3 apps/scraper/generate_summary_ogp.py
python3 apps/scraper/generate_summary_pages.py
python3 apps/scraper/generate_prefecture_pages.py
python3 apps/scraper/generate_sitemap.py
cp apps/web/index.html dist/index.html
cp apps/web/nearby_manholes.html dist/nearby.html
cp apps/web/map.html dist/map.html
cp apps/web/gmanhole_map.html dist/gmanhole_map.html
cp apps/web/design_manhole.html dist/design_manhole.html
cp apps/web/login.html dist/login.html
cp apps/web/sitemap.xml dist/sitemap.xml
cp apps/web/robots.txt dist/robots.txt
python3 tools/build_i18n.py
echo '<!doctype html><meta http-equiv="refresh" content="0; url=./nearby.html">' > dist/nearby_manholes.html
python3 apps/scraper/inject_site_header.py dist
mkdir -p dist/assets dist/manhole/image dist/api
cp -r apps/web/assets/* dist/assets/
cp -r dataset/manhole/image/* dist/manhole/image/
cp docs/pokefuta.ndjson docs/gmanhole.ndjson docs/character_manholes.ndjson docs/latest-manhole-photos.json docs/pokemon_metadata.json dist/
cp docs/api/*.json dist/api/
python3 apps/scraper/generate_top_feed.py --output dist/api/top-feed.json
```

結果: dist/ ≈ 102MB、HTML 約3,300ページ。**スキップしてよいもの**: `generate_manhole_ogp.py`（マンホール別OGP画像。CI専用・遅い・ローカル表示に不要）。

## Run（人間用）

`/dev` コマンド（`.claude/commands/dev.md`）= 同期+配信のみの軽量版。または driver.sh を実行してブラウザで http://localhost:8000 を開く。

## Test

```bash
cd apps/scraper && python3 -m unittest discover -p 'test_*.py'
```

65テスト・約0.1秒。**mainでも 4 failures + 2 errors が出るのが既知の状態**（summary系の古いテスト）。自分の変更の影響を見るときは main での結果と比較すること。pytest は入っていない（`python3 -m pytest` は No module named pytest）。

## Gotchas（全部このマシンで実際に踏んだもの）

- **Chrome `--headless=new --screenshot` はPNGを書いた後も終了しないことがある**（ページのタイマー/フェッチが生きている）。フォアグラウンドで待つとハングに見える。→ バックグラウンド起動してファイル出現をポーリングし kill（driver.sh の `shot` 参照）
- **`--user-data-dir` を使い回すと2回目の起動がプロファイルロックで無限に待つ**。→ 毎回 `mktemp -d`
- **ツール呼び出しのシェル内で `(cmd &)` で起動したサーバーは、そのシェルがタイムアウト/SIGTERMされるとプロセスグループごと死ぬ**。スクリーンショットが突然 `ERR_CONNECTION_REFUSED` になったらこれ。→ driver.sh は `nohup + disown` で起動する
- **`apps/web/*.html` を dist へ同期すると `inject_site_header.py` の注入前ソースに戻る**。共通ヘッダーの見た目を確認したいときは同期後に `python3 apps/scraper/inject_site_header.py dist` を再実行
- **「みんなの投稿」ギャラリー等はローカルでは出ない**。pokefuta.com のAPI（CORS/Supabase）に依存し、失敗時はセクションごと非表示になる仕様。ローカルで空でもバグではない
- 地図タイル（OpenStreetMap）とLeafletはCDN読みなのでネット接続が必要。オフラインだと地図部分だけ空になる

## Troubleshooting

| 症状 | 原因と対処 |
|---|---|
| スクリーンショットが「このサイトにアクセスできません ERR_CONNECTION_REFUSED」 | サーバーが死んでいる（上記プロセスグループ問題）。driver.sh で立て直す |
| `pip3 install -r requirements.txt` が `externally-managed-environment` で失敗 | 正常。ビルドに必要なのはPillowだけ。無ければ venv（Prerequisites参照） |
| Chrome コマンドが返ってこない | 正常動作の範囲。PNGは大抵書き込み済み。ファイルを確認して kill |
| `driver.sh` が `dist/ missing` | クリーンチェックアウト。Build セクションを先に実行 |
