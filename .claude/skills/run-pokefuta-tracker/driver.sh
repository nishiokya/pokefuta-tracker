#!/usr/bin/env bash
# pokefuta-tracker 静的サイトのローカル起動 + スモークテスト + スクリーンショット。
# Usage:
#   driver.sh          # sync → serve → curl smoke → screenshots → サーバーは起動したまま
#   driver.sh stop     # ポートのサーバーを停止
# 環境変数: PORT (default 8000), SS_DIR (スクリーンショット出力先, default $TMPDIR/pokefuta-run)
set -u
ROOT="$(git rev-parse --show-toplevel)" || { echo "[driver] ERROR: not in a git repo"; exit 1; }
PORT="${PORT:-8000}"
SS_DIR="${SS_DIR:-${TMPDIR:-/tmp}/pokefuta-run}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CHROME" ] || CHROME="$(command -v google-chrome || command -v chromium || true)"

kill_port() {
  local pid; pid=$(lsof -ti:"$PORT" 2>/dev/null)
  [ -n "$pid" ] && kill $pid 2>/dev/null && echo "[driver] stopped server on :$PORT"
}

if [ "${1:-}" = "stop" ]; then kill_port; exit 0; fi

[ -d "$ROOT/dist" ] || { echo "[driver] ERROR: dist/ missing — SKILL.md の Build セクションを先に実行"; exit 1; }
mkdir -p "$SS_DIR" "$ROOT/dist/assets"

# ── apps/web → dist 同期（pages-deploy.yml と同じマッピング）──
cd "$ROOT"
cp apps/web/index.html dist/index.html
cp apps/web/nearby_manholes.html dist/nearby.html
cp apps/web/map.html dist/map.html 2>/dev/null || true
cp apps/web/gmanhole_map.html dist/gmanhole_map.html
cp apps/web/design_manhole.html dist/design_manhole.html
python3 apps/scraper/generate_character_manhole_page.py --output dist/character_manholes.html 2>/dev/null || true
cp apps/web/login.html dist/login.html 2>/dev/null || true
cp apps/web/robots.txt dist/robots.txt
cp apps/web/sitemap.xml dist/sitemap.xml 2>/dev/null || true
cp -r apps/web/assets/. dist/assets/
# docs/ の公開データも同期（古いdistだと api/*.json が欠けていることがある）
mkdir -p dist/api
cp docs/api/*.json dist/api/ 2>/dev/null || true
cp docs/pokefuta.ndjson docs/gmanhole.ndjson docs/character_manholes.ndjson docs/latest-manhole-photos.json docs/pokemon_metadata.json dist/ 2>/dev/null || true
echo "[driver] synced apps/web + docs data -> dist"

# ── サーバー起動（nohup で完全にデタッチ: 呼び出し元シェルが死んでも生き残る）──
kill_port
nohup python3 -m http.server "$PORT" --directory "$ROOT/dist" >/dev/null 2>&1 &
disown 2>/dev/null || true
sleep 1
curl -sf -o /dev/null "http://localhost:$PORT/" || { echo "[driver] ERROR: server failed to start"; exit 1; }
echo "[driver] serving dist/ at http://localhost:$PORT"

# ── curl スモーク: ステータス + コンテンツマーカー ──
FAIL=0
check() { # path marker
  local body; body=$(curl -sf "http://localhost:$PORT$1")
  if [ $? -ne 0 ]; then echo "[smoke] FAIL $1 (not 200)"; FAIL=1; return; fi
  if echo "$body" | grep -q "$2"; then echo "[smoke] ok   $1"; else echo "[smoke] FAIL $1 (marker '$2' not found)"; FAIL=1; fi
}
check /                     "ポケふた"
check /design_manhole.html  "FAQPage"
check /character_manholes.html "収録している作品"
check /gmanhole_map.html    "キャラマンホール"
check /summary/             "ポケふた"
check /robots.txt           "Sitemap:"
check /api/site-stats.json  '"manholes"'
check /pokefuta.ndjson      '"id"'
first_manhole=$(ls dist/manholes 2>/dev/null | head -1)
[ -n "$first_manhole" ] && check "/manholes/$first_manhole/" "ポケふた" || echo "[smoke] skip /manholes/ (未生成)"
first_pref=$(ls dist/prefectures 2>/dev/null | head -1)
[ -n "$first_pref" ] && check "/prefectures/$first_pref/" "ポケふた" || echo "[smoke] skip /prefectures/ (未生成)"

# ── スクリーンショット（Chromeは撮影後も終了しないことがある → ファイル出現を待って kill）──
shot() { # path outfile
  [ -n "$CHROME" ] || { echo "[ss] skip $1 (chrome not found)"; return; }
  local out="$SS_DIR/$2" prof; prof=$(mktemp -d)
  rm -f "$out"
  "$CHROME" --headless=new --disable-gpu --user-data-dir="$prof" \
    --window-size=1280,900 --virtual-time-budget=8000 --hide-scrollbars \
    --screenshot="$out" "http://localhost:$PORT$1" >/dev/null 2>&1 &
  local cpid=$!
  for _ in $(seq 1 30); do [ -s "$out" ] && break; sleep 1; done
  sleep 1
  kill "$cpid" 2>/dev/null; wait "$cpid" 2>/dev/null
  rm -rf "$prof"
  if [ -s "$out" ]; then echo "[ss] $out"; else echo "[ss] FAIL $1"; FAIL=1; fi
}
shot /                    index.png
shot /design_manhole.html design_manhole.png
shot /character_manholes.html character_manholes.png
[ -n "$first_pref" ] && shot "/prefectures/$first_pref/" "prefecture.png"

echo
if [ "$FAIL" = 0 ]; then echo "[driver] ALL OK — server still running on :$PORT ('driver.sh stop' で停止)"; else echo "[driver] FAILURES above — server on :$PORT"; exit 1; fi
