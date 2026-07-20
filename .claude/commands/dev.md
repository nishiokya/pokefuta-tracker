Start the local dev server on port 8000, killing any existing process on that port first.

```bash
# Kill anything already on 8000
_pid=$(lsof -ti:8000 2>/dev/null)
[ -n "$_pid" ] && kill "$_pid" && echo "[dev] stopped previous server on :8000" || true

ROOT="$(git rev-parse --show-toplevel)" || { echo "[dev] ERROR: not in a git repo"; exit 1; }

if [ ! -d "$ROOT/dist" ]; then
  echo "[dev] ERROR: dist/ is missing. Run the static build/generation first."
  exit 1
fi
mkdir -p "$ROOT/dist/assets"

# Sync apps/web/ → dist/ (same mapping as pages-deploy.yml)
cp "$ROOT/apps/web/index.html"       "$ROOT/dist/index.html"        && echo "[dev] synced index.html"        || echo "[dev] WARN: index.html sync failed"
cp "$ROOT/apps/web/map.html"         "$ROOT/dist/map.html"          && echo "[dev] synced map.html"          || echo "[dev] WARN: map.html sync failed"
cp "$ROOT/apps/web/nearby_manholes.html" "$ROOT/dist/nearby.html"   && echo "[dev] synced nearby.html"       || echo "[dev] WARN: nearby.html sync failed"
cp "$ROOT/apps/web/gmanhole_map.html" "$ROOT/dist/gmanhole_map.html" && echo "[dev] synced gmanhole_map.html" || echo "[dev] WARN: gmanhole_map.html sync failed"
cp "$ROOT/apps/web/sitemap.xml"      "$ROOT/dist/sitemap.xml"        && echo "[dev] synced sitemap.xml"       || echo "[dev] WARN: sitemap.xml sync failed"
[ -d "$ROOT/apps/web/assets" ] && cp -r "$ROOT/apps/web/assets/." "$ROOT/dist/assets/" && echo "[dev] synced assets/" || echo "[dev] WARN: assets/ sync failed"
cp "$ROOT/docs/character_manholes.ndjson" "$ROOT/dist/character_manholes.ndjson" && echo "[dev] synced character_manholes.ndjson" || echo "[dev] WARN: character_manholes.ndjson sync failed"
python3 "$ROOT/apps/scraper/generate_character_manhole_page.py" --output "$ROOT/dist/character_manholes.html" && echo "[dev] regenerated character_manholes.html" || echo "[dev] WARN: character_manholes.html generation failed"

# Serve dist/ on port 8000
python3 -m http.server 8000 --directory "$ROOT/dist" &
_server_pid=$!
sleep 0.5
if kill -0 "$_server_pid" 2>/dev/null; then
  echo "[dev] http://localhost:8000"
else
  echo "[dev] ERROR: server failed to start (is dist/ built?)"
fi
```
