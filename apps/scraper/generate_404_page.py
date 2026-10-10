#!/usr/bin/env python3
"""404 ページに出す「有名なポケモンが1体だけ描かれたポケふた」の候補を焼き込む。

図鑑（data.pokefuta.com）の 404.html と、写真館（pokefuta.com）の not-found が同じ候補を使う。
- 図鑑: 404.html の `not-found:pick` ブロックに候補 JSON を書く
- 写真館: `--json` で書いた api/lost-manholes.json をブラウザから読む（CORS は `*`）

候補は「設置済み・描かれたポケモンが1体・そのポケモンが FAMOUS_POKEMON にある・蓋の画像
（manhole/image/{id}_lid.jpeg）がある」もの。どれを出すかはブラウザで毎回ランダムに選ぶ。

使い方:
  python3 apps/scraper/generate_404_page.py                      # apps/web/404.html を更新
  python3 apps/scraper/generate_404_page.py dist/404.html --json dist/api/lost-manholes.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "docs" / "pokefuta.ndjson"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"
DEFAULT_TARGET = ROOT / "apps" / "web" / "404.html"

# ポケモンをよく知らない人でも分かる顔ぶれ。ここに無いポケモンの蓋は 404 に出さない
FAMOUS_POKEMON = [
    "ヤドン", "ピカチュウ", "イーブイ", "ラプラス", "コイキング", "ギャラドス", "カイリュー",
    "フシギダネ", "ヒトカゲ", "ゼニガメ", "フシギバナ", "リザードン", "カメックス",
    "ミュウ", "ニャース", "ロコン", "ラッキー", "ガーディ", "ウインディ", "ニョロモ",
    "シャワーズ", "サンダース", "ブースター", "エーフィ", "ブラッキー", "リーフィア", "グレイシア", "ニンフィア",
    "ミジュマル", "ゲッコウガ", "ルカリオ", "ルギア", "ホウオウ", "レックウザ", "カイオーガ",
    "プテラ", "イワーク", "ミロカロス", "セレビィ", "ウッウ",
]

BLOCK_RE = re.compile(r"<!-- not-found:pick:start -->.*?<!-- not-found:pick:end -->", re.S)


def load_candidates(dataset: Path = DATASET, image_dir: Path = IMAGE_DIR) -> list[dict[str, str]]:
    famous = set(FAMOUS_POKEMON)
    items = []
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("installed") is False:
            continue
        pokemons = record.get("pokemons") or []
        if len(pokemons) != 1 or pokemons[0] not in famous:
            continue
        manhole_id = str(record["id"])
        if not (image_dir / f"{manhole_id}_lid.jpeg").exists():
            continue
        place = (record.get("title") or record.get("prefecture") or "").replace("/", "")
        items.append({"id": manhole_id, "pokemon": pokemons[0], "place": place})
    # 並びは表示に関係ないが、差分を読みやすくするため ID 順に固定する
    items.sort(key=lambda it: int(it["id"]) if it["id"].isdigit() else 10**9)
    return items


def render_block(items: list[dict[str, str]]) -> str:
    """候補 JSON だけを書く。リンクや画像の枠は 404.html 側にあり、JS が候補から1枚選んで差し替える。"""
    data = json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        "<!-- not-found:pick:start -->\n"
        f'      <script type="application/json" id="lost-data">{data}</script>\n'
        "      <!-- not-found:pick:end -->"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", type=Path, nargs="?", default=DEFAULT_TARGET)
    parser.add_argument("--json", type=Path, help="写真館が読む候補 JSON の出力先")
    args = parser.parse_args()

    items = load_candidates()
    if not items:
        raise SystemExit("[404] 候補が0件。FAMOUS_POKEMON か蓋の画像を確認すること")

    html = args.target.read_text(encoding="utf-8")
    if not BLOCK_RE.search(html):
        raise SystemExit(f"[404] {args.target} に not-found:pick のマーカーが無い")
    args.target.write_text(BLOCK_RE.sub(lambda _: render_block(items), html, count=1), encoding="utf-8")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": items}
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    pokemon = len({it["pokemon"] for it in items})
    print(f"[404] wrote {args.target}: {len(items)} manholes, {pokemon} Pokémon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
