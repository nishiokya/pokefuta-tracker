Start the local dev server on port 8000, killing any existing process on that port first.

```bash
# Kill anything already on 8000
_pid=$(lsof -ti:8000 2>/dev/null)
[ -n "$_pid" ] && kill "$_pid" && echo "[dev] stopped previous server on :8000" || true

# Serve dist/ on port 8000
cd "$(git rev-parse --show-toplevel)"
python3 -m http.server 8000 --directory dist &
sleep 0.5
echo "[dev] http://localhost:8000"
```
