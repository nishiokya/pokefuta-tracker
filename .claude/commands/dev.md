Start the local dev server on port 8000, killing any existing process on that port first.

```bash
# Kill anything already on 8000
_pid=$(lsof -ti:8000 2>/dev/null)
[ -n "$_pid" ] && kill "$_pid" && echo "[dev] stopped previous server on :8000" || true

ROOT="$(git rev-parse --show-toplevel)"

# Sync apps/web/ → dist/ (map page + assets only; dist/index.html is the text-first page, not overwritten)
cp "$ROOT/apps/web/index.html" "$ROOT/dist/map.html" 2>/dev/null && echo "[dev] synced map.html"
cp -r "$ROOT/apps/web/assets/"* "$ROOT/dist/assets/" 2>/dev/null && echo "[dev] synced assets/"

# Serve dist/ on port 8000
python3 -m http.server 8000 --directory "$ROOT/dist" &
sleep 0.5
echo "[dev] http://localhost:8000"
```
