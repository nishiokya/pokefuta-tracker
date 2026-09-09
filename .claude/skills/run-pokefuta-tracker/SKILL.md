---
name: run-pokefuta-tracker
description: Build, run, smoke-test, screenshot, and click through the pokefuta-tracker static site (data.pokefuta.com) locally. Use when asked to run/start the app or dev server, verify a change in the real browser, take a screenshot of a page, check click tracking or collapsed sections, or smoke-test the site build.
---

# Run pokefuta-tracker

静的サイト（GitHub Pages / data.pokefuta.com）。`apps/web/` + Python生成スクリプト（`apps/scraper/`）→ `dist/`（gitignore済み）に焼き込み、`python3 -m http.server` で配信する。**ドライバは2本**:

| 用途 | 使うもの |
|---|---|
| 起動・全体スモーク・スクリーンショット | `driver.sh` |
| **ページを触って確かめる**（クリック / DOM取得 / アンカー / 全画面ショット） | `probe.mjs` |

パスはすべてリポジトリルート基準。

## Run（エージェント用 — まずこれ）

```bash
.claude/skills/run-pokefuta-tracker/driver.sh
```

`apps/web/` + `docs/` → `dist/` 同期 → :8000 で配信（nohupでデタッチ、呼び出し元シェルが死んでも生存）→ **13ページの curl スモーク**（200＋コンテンツマーカー）→ **5枚のスクリーンショット** → 本番デプロイと同じ loopback URL ゲート。最後に `ALL OK` が出て、サーバーは起動したまま残る（実測25秒）。

- 出力先: `$TMPDIR/pokefuta-run/{index,design_manhole,character_manholes,pokemon,prefecture}.png` — **必ず Read で目視確認する**（真っ白/エラーページならFAIL扱い）
- ポート/出力先の変更: `PORT=8001 SS_DIR=/path driver.sh`
- 停止: `.claude/skills/run-pokefuta-tracker/driver.sh stop`
- 前提: `dist/` があること。無ければ下の Build を先に実行

## Run（ページを触る — 変更の確認はほぼこれ）

`driver.sh` のスクリーンショットは**表示領域を撮るだけ**。折りたたみ・アンカージャンプ・`data-track` のクリック計測など「触らないと分からない」変更は `probe.mjs` を使う。**依存ゼロ**（Node 22+ の組み込み WebSocket で CDP を直接叩く。npm install も playwright も不要）。

```bash
node .claude/skills/run-pokefuta-tracker/probe.mjs http://localhost:8000/pokemon/ --eval "document.title"
```

オプション: `--eval <js>`（結果をJSONで標準出力）/ `--pre <js>`（クリック前に評価。スパイ設置用）/ `--click <sel>`（実座標での本物のクリック・複数可）/ `--hash '#frag'` / `--shot out.png` / `--full`（ページ全体）/ `--settle <ms>`（load後の待ち。既定1200、地図やfetchのあるページは伸ばす）。

**DOMを取る**（実測: 549件のリンクが閉じた `<details>` の中にある、が分かる）:

```bash
node .claude/skills/run-pokefuta-tracker/probe.mjs http://localhost:8000/pokemon/ --hash '#pokemon-list' --eval "
  (() => {
    const d = document.querySelector('.content-collapse');
    return { detailsOpen: d.open, linksInside: d.querySelectorAll('a[data-track]').length,
             visibleHeight: Math.round(d.getBoundingClientRect().height) };
  })()"
```

**クリックして状態が変わることを見る**（52px → 1980px）:

```bash
node .claude/skills/run-pokefuta-tracker/probe.mjs http://localhost:8000/pokemon/ \
  --click '.content-collapse summary' \
  --eval "({ open: document.querySelector('.content-collapse').open,
             height: Math.round(document.querySelector('.content-collapse').getBoundingClientRect().height) })"
```

**GA4クリック計測が本当に飛ぶか見る**（ローカルでは gtag が無効なのでスパイを差す。`--pre` の capture-phase preventDefault が無いとリンク遷移でコンテキストが消える）:

```bash
node .claude/skills/run-pokefuta-tracker/probe.mjs http://localhost:8000/pokemon/ \
  --pre "window.__ga=[]; window.gtag=function(){window.__ga.push([...arguments])};
         document.addEventListener('click', e => e.preventDefault(), true); true" \
  --click '.featured-grid .featured-card a' \
  --eval "window.__ga"
```

**ページ全体のスクリーンショット**（`--full`。実測 1280x14491 まで撮れる）:

```bash
node .claude/skills/run-pokefuta-tracker/probe.mjs http://localhost:8000/prefectures/ --shot /tmp/full.png --full
```

## Prerequisites

- Python 3（3.14.5で検証）。サイトビルドの外部依存は **Pillow のみ**（`generate_summary_ogp.py` 用）。確認:

  ```bash
  python3 -c "import PIL; print(PIL.__version__)"
  ```

  無ければ venv を作って `python3` を `.venv/bin/python3` に読み替える。`pip3 install -r requirements.txt` は Homebrew Python では PEP 668（externally-managed）で失敗するが、requirements.txt の bs4/cairosvg/requests は**スクレイパー（CI）用でローカルのサイトビルドには不要**。
- Node.js 22以上（`probe.mjs` 用。24.7.0で検証）。組み込み `WebSocket` を使うので追加インストール不要
- Google Chrome（`/Applications/Google Chrome.app`）。`CHROME=/path` で上書き可

## Build（クリーンチェックアウト → dist/ 生成、実測10秒）

pages-deploy.yml と同じ手順のローカル版。全部リポジトリルートで実行:

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
cp docs/pokefuta.ndjson docs/gmanhole.ndjson docs/character_manholes.ndjson docs/design_manholes.ndjson docs/latest-manhole-photos.json docs/pokemon_metadata.json dist/
cp docs/api/*.json dist/api/
cp dataset/prefecture_events.json dist/api/prefecture_events.json
python3 apps/scraper/generate_top_feed.py --output dist/api/top-feed.json
```

結果: dist/ ≈ 241MB、HTML 3,301ページ。**スキップしてよいもの**: `generate_manhole_ogp.py`（マンホール別OGP画像。CI専用・遅い・ローカル表示に不要）。

デプロイ前ゲート（`dist` に localhost/127.0.0.1 が混ざるとCIが落ちる。driver.sh が最後に自動実行するのと同じもの、単体では約7秒）:

```bash
python3 .github/scripts/check_production_urls.py --exclude 'supabase-ssr.js' dist
```

## Run（人間用）

`/dev` コマンド（`.claude/commands/dev.md`）= 同期+配信のみの軽量版。または driver.sh 実行後にブラウザで http://localhost:8000 を開く。

## Test

**リポジトリルートから**モジュール名で回す（CI と同じ形）:

```bash
ls apps/scraper/test_*.py | sed 's|/|.|g; s|\.py$||' | xargs python3 -m unittest
```

428テスト・約0.3秒。**mainでも 4 failures + 2 errors が出るのが既知の状態**（failures = `test_generate_summary_pages.DiscoveryHubTests` の4件、errors = `test_address_parser` / `test_update_pokefuta` の bs4 未インストール）。自分の変更の影響を見るときはこの数と比べる。pytest は入っていない。

pages-deploy.yml が実際に走らせるのはこのうち一部だけ。ワークフローからスクリプトを呼ぶ変更をしたら、対応するテスト実行ステップも同じワークフローに足すこと（CLAUDE.md のバッチワークフロー規約）。

## Gotchas（全部このマシンで実際に踏んだもの）

- **ビルドが tracked ファイルを書き換える。** `generate_sitemap.py` は `apps/web/sitemap.xml`（`--output` の既定値）、`generate_summary_ogp.py` は `apps/web/assets/ogp/pokefuta_summary_ogp.png` を更新する。ビルド後の `git status` に無関係な差分が出たらこれ。意図した更新でなければ `git checkout -- apps/web/sitemap.xml apps/web/assets/ogp/pokefuta_summary_ogp.png` で戻す
- **ローカルでは GA4 が無効。** `analytics.js` の `PRODUCTION_HOSTS = ['data.pokefuta.com']` でホスト判定しており、localhost では `PokefutaAnalytics.enabled === false`、gtag ローダーも読み込まれない（実測）。クリック計測を確認したいときは `probe.mjs --pre` で `window.gtag` を差し替える
- **`probe.mjs --click` でリンクを踏むと本当に遷移する** ので、直後の `--eval` は新しいページで走り `window.__ga` などは消える。→ `--pre` に `document.addEventListener('click', e => e.preventDefault(), true)` を入れる。**ただしこの capture preventDefault は `<details>` のネイティブ開閉も止める**ので、折りたたみを確認するときは入れないこと（両方いっぺんには見られない）
- **Chrome `--headless=new --screenshot` はPNGを書いた後も終了しないことがある**（ページのタイマー/フェッチが生きている）。フォアグラウンドで待つとハングに見える。→ バックグラウンド起動してファイル出現をポーリングし kill（driver.sh の `shot`）。`probe.mjs` は CDP 経由なのでこの問題は無い
- **`--user-data-dir` を使い回すと2回目の起動がプロファイルロックで無限に待つ**。→ 毎回 `mktemp -d`（両ドライバともそうしている）
- **ツール呼び出しのシェル内で `(cmd &)` で起動したサーバーは、そのシェルがタイムアウト/SIGTERMされるとプロセスグループごと死ぬ**。スクリーンショットが突然 `ERR_CONNECTION_REFUSED` になったらこれ。→ driver.sh は `nohup + disown` で起動する
- **`apps/web/*.html` を dist へ同期すると `inject_site_header.py` の注入前ソースに戻る**。共通ヘッダーの見た目を確認したいときは同期後に `python3 apps/scraper/inject_site_header.py dist` を再実行（driver.sh の同期も注入を落とすので、ヘッダー確認時は注意）
- **`dist/api/prefecture_events.json` は `docs/api/*.json` には入っていない**（ソースは `dataset/prefecture_events.json`）。コピーし忘れるとトップの「開催中スタンプラリー」バナーが黙って消える。同じく `docs/design_manholes.ndjson` を忘れるとデザインマンホールのギャラリーが空になる。どちらも driver.sh が同期する
- **蓋の呼び方は2層ルール**（キャラふた / キャラクターマンホール、#399）。`キャラマンホール` という表記は消えたので、スモークのコンテンツマーカーに使わない（実際にこれで driver.sh のチェックが腐っていた）
- **「みんなの投稿」ギャラリー等はローカルでは出ない**。pokefuta.com のAPI（CORS/Supabase）に依存し、失敗時はセクションごと非表示になる仕様。ローカルで空でもバグではない。一方トップのヒーローと統計は `dist/api/top-feed.json` をローカル生成するので**出るのが正しい**
- 地図タイル（OpenStreetMap）とLeafletはCDN読みなのでネット接続が必要。オフラインだと地図部分だけ空になる

## Troubleshooting

| 症状 | 原因と対処 |
|---|---|
| スクリーンショットが「このサイトにアクセスできません ERR_CONNECTION_REFUSED」 | サーバーが死んでいる（上記プロセスグループ問題）。driver.sh で立て直す |
| `[smoke] FAIL ... (marker '...' not found)` | 多くは**文言変更でマーカーが腐った**だけ。ページを開いて実際の文言を確認し、driver.sh のマーカーを直す（ページ自体の障害と決めつけない） |
| `probe.mjs` が `click: セレクタが見つからない` | `--settle` を伸ばす（fetch後に描画される要素）。それでも出ないならセレクタ違い |
| `probe.mjs` が `Chrome の DevTools エンドポイントに繋がらない` | Chrome のパスが違う。`CHROME=/path/to/chrome` を渡す |
| `cd apps/scraper && python3 -m unittest discover` で errors が5件出る | **この回し方が間違い**。`apps.scraper.*` を import する3モジュールが読めず 424テストに減る。上の Test セクションのコマンド（ルートから）を使う |
| `pip3 install -r requirements.txt` が `externally-managed-environment` で失敗 | 正常。ビルドに必要なのは Pillow だけ |
| `driver.sh` が `dist/ missing` | クリーンチェックアウト。Build セクションを先に実行 |
