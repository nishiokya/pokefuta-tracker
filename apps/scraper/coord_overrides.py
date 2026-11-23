"""公式の緯度経度が実際の設置場所とずれているポケふたを、dataset/pokefuta_coord_overrides.json で上書きする。

公式の生データ（apps/scraper/pokefuta.ndjson）は変えず、公開用の docs/pokefuta.ndjson を書き出すときに当てる
（update-pokefuta.yml）。上書きの行には公式の元の座標（official）も持たせ、公式側の座標が変わっていたら
公式が直したとみなして上書きをやめる（警告だけ出す）。

    python3 apps/scraper/coord_overrides.py docs/pokefuta.ndjson   # その場で書き換える
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OVERRIDES = ROOT / "dataset" / "pokefuta_coord_overrides.json"
# 公式の座標が「記録した元の座標と同じ」とみなす幅（度）。小数の丸めの違いだけを吸収する
SAME_EPS = 1e-6


def load(path: Path = DEFAULT_OVERRIDES) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = data.get("overrides", {})
    for mid, o in overrides.items():
        for key in ("lat", "lng"):
            if not isinstance(o.get(key), (int, float)):
                raise ValueError(f"pokefuta_coord_overrides.json の {mid} に数値の {key} がない")
            if not isinstance((o.get("official") or {}).get(key), (int, float)):
                raise ValueError(f"pokefuta_coord_overrides.json の {mid} に official.{key} がない")
    return overrides


def _same(lat, lng, point: dict) -> bool:
    return (
        isinstance(lat, (int, float))
        and isinstance(lng, (int, float))
        and abs(lat - point["lat"]) <= SAME_EPS
        and abs(lng - point["lng"]) <= SAME_EPS
    )


def apply(records: list[dict], overrides: dict[str, dict]) -> tuple[int, list[str]]:
    """records の lat/lng を上書きする。戻り値は（上書きした件数, 警告）。"""
    applied = 0
    warnings: list[str] = []
    seen: set[str] = set()
    for r in records:
        mid = str(r.get("id"))
        o = overrides.get(mid)
        if o is None:
            continue
        seen.add(mid)
        lat, lng = r.get("lat"), r.get("lng")
        official = o["official"]
        if _same(lat, lng, o):  # もう上書き済み（手で2回流したとき）
            applied += 1
            continue
        if not _same(lat, lng, official):
            warnings.append(
                f"{mid}: 公式の座標が {official['lat']},{official['lng']} から {lat},{lng} に変わったので上書きしない"
                "（公式が直したなら pokefuta_coord_overrides.json から外す）"
            )
            continue
        r["lat"], r["lng"] = o["lat"], o["lng"]
        applied += 1
    for mid in sorted(set(overrides) - seen):
        warnings.append(f"{mid}: 上書きの対象が ndjson に無い")
    return applied, warnings


_LOADED: dict[str, dict] | None = None


def is_applied(record: dict, overrides: dict[str, dict] | None = None) -> bool:
    """この蓋の座標が上書きされている（docs の座標が上書きの座標と同じ）か。詳細ページの注記に使う。"""
    global _LOADED
    if overrides is None:
        if _LOADED is None:
            _LOADED = load()
        overrides = _LOADED
    o = overrides.get(str(record.get("id")))
    return bool(o) and _same(record.get("lat"), record.get("lng"), o)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    applied, warnings = apply(records, load())
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            json.dump(r, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            f.write("\n")
    for w in warnings:
        print(f"::warning::{w}")
    print(f"[coord_overrides] {applied} 件の座標を上書き → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
