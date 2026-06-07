タグ追加ツール（manhole-semantic-editor）を起動する。

```bash
# Kill anything already on 5177
_pid=$(lsof -ti:5177 2>/dev/null)
[ -n "$_pid" ] && kill "$_pid" && echo "[tag-editor] stopped previous server on :5177" || true

# Launch the editor
cd "$(git rev-parse --show-toplevel)/tools/manhole-semantic-editor"
npm run dev &
sleep 1
echo "[tag-editor] http://localhost:5177"
```
