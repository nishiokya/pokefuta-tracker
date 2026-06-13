#!/usr/bin/env python3
"""Generate prefecture trivia from the public Pokefuta dataset.

Dataset-derived facts are recalculated on every run. Editorial facts and
Pokemon groups live in dataset/prefecture_trivia_sources.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_SOURCES = ROOT / "dataset" / "prefecture_trivia_sources.json"
DEFAULT_OUTPUT = ROOT / "dataset" / "prefecture_trivia.json"

PREFECTURE_ORDER = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県",
    "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県",
    "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県",
    "鹿児島県", "沖縄県",
]

TRIVIA_PRIORITY = {
    "local_connection": 100,
    "wordplay": 95,
    "support_pokemon": 90,
    "single_municipality": 80,
    "municipality_concentration": 75,
    "pokemon_group_100": 70,
    "pokemon_100": 65,
    "top_pokemon": 20,
    "remote_island": 15,
    "world_heritage": 15,
    "roadside_station": 15,
    "station": 15,
    "airport": 15,
    "extreme_point": 15,
}


class ValidationError(ValueError):
    pass


def load_records(path: Path) -> list[dict]:
    records: dict[str, dict] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            record_id = str(record.get("id", "")).strip()
            if not record_id:
                raise ValidationError(f"{path}:{line_number}: record has no id")
            records[record_id] = {**records.get(record_id, {}), **record}
    return [record for record in records.values() if record.get("status", "active") == "active"]


def load_sources(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("source master must be a JSON object")
    return data


def _valid_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate_sources(sources: dict, records: list[dict]) -> None:
    known_prefectures = {record.get("prefecture") for record in records}
    known_pokemon = {
        pokemon
        for record in records
        for pokemon in record.get("pokemons", [])
        if isinstance(pokemon, str)
    }
    group_ids: set[str] = set()
    trivia_ids: set[str] = set()

    for group in sources.get("pokemon_groups", []):
        group_id = group.get("id")
        if not group_id or group_id in group_ids:
            raise ValidationError(f"missing or duplicate Pokemon group id: {group_id!r}")
        group_ids.add(group_id)
        if group.get("prefecture") not in known_prefectures:
            raise ValidationError(f"{group_id}: unknown prefecture")
        pokemon = group.get("pokemon")
        if not isinstance(pokemon, list) or not pokemon:
            raise ValidationError(f"{group_id}: pokemon must be a non-empty list")
        unknown = sorted(set(pokemon) - known_pokemon)
        if unknown:
            raise ValidationError(f"{group_id}: unknown Pokemon: {', '.join(unknown)}")

    for entry in sources.get("editorial_trivia", []):
        entry_id = entry.get("id")
        if not entry_id or entry_id in trivia_ids:
            raise ValidationError(f"missing or duplicate editorial trivia id: {entry_id!r}")
        trivia_ids.add(entry_id)
        if entry.get("prefecture") not in known_prefectures:
            raise ValidationError(f"{entry_id}: unknown prefecture")
        if entry.get("type") not in TRIVIA_PRIORITY:
            raise ValidationError(f"{entry_id}: unknown trivia type")
        if not entry.get("text"):
            raise ValidationError(f"{entry_id}: text is required")
        if not _valid_https_url(entry.get("source_url")):
            raise ValidationError(f"{entry_id}: an HTTPS source_url is required")
        if not entry.get("verified_at"):
            raise ValidationError(f"{entry_id}: verified_at is required")
        forbidden = {"count", "manhole_count", "municipality_count", "coverage_percent"}
        present = forbidden.intersection(entry)
        if present:
            raise ValidationError(
                f"{entry_id}: calculated values must not be stored in the source master: "
                f"{', '.join(sorted(present))}"
            )


def _coverage(records: list[dict], pokemon: list[str]) -> int:
    target = set(pokemon)
    return sum(bool(target.intersection(record.get("pokemons", []))) for record in records)


def _dataset_trivia(
    prefecture: str,
    records: list[dict],
    municipality_counts: Counter,
    pokemon_counts: Counter,
    coverage: list[dict],
) -> list[dict]:
    trivia: list[dict] = []
    municipalities = sorted({
        record.get("city", "").strip()
        for record in records
        if record.get("city", "").strip()
    })
    total = len(records)

    if len(municipalities) == 1 and total > 1:
        city = municipalities[0]
        trivia.append({
            "id": f"{prefecture}-single-municipality",
            "type": "single_municipality",
            "text": f"県内{total}枚のポケふたはすべて{city}にあります",
            "source_type": "dataset",
        })
    elif municipality_counts and total:
        ranked = sorted(
            municipality_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        top_city, top_count = ranked[0]
        next_count = ranked[1][1] if len(ranked) > 1 else 0
        top_share = top_count * 100 / total
        if top_count >= 3 and top_share >= 30 and top_count > next_count:
            remaining = ranked[1:]
            if remaining and all(count == 1 for _, count in remaining):
                text = (
                    f"{top_city}に{top_count}枚が集まり、"
                    f"ほかの{len(remaining)}自治体は各1枚です"
                )
            elif remaining:
                runner_up_city, runner_up_count = remaining[0]
                text = (
                    f"最多は{top_city}の{top_count}枚で、"
                    f"次いで{runner_up_city}の{runner_up_count}枚です"
                )
            else:
                text = f"最多は{top_city}の{top_count}枚です"
            trivia.append({
                "id": f"{prefecture}-municipality-concentration",
                "type": "municipality_concentration",
                "text": text,
                "source_type": "dataset",
            })

    for item in coverage:
        if item["coverage_percent"] != 100:
            continue
        fact_type = "pokemon_group_100" if len(item["pokemon"]) > 1 else "pokemon_100"
        trivia.append({
            "id": f"{prefecture}-{item['id']}-100",
            "type": fact_type,
            "text": f"県内{total}枚すべてに{item['label']}が登場します",
            "source_type": "dataset",
        })

    full_coverage_pokemon = {
        pokemon
        for item in coverage
        if item["coverage_percent"] == 100
        for pokemon in item["pokemon"]
    }
    if pokemon_counts and total and max(pokemon_counts.values()) >= 2:
        count = max(pokemon_counts.values())
        leaders = sorted(
            name for name, appearances in pokemon_counts.items()
            if appearances == count and name not in full_coverage_pokemon
        )
        if leaders:
            pokemon = leaders[0]
            if len(leaders) > 1:
                examples = "・".join(leaders[:3])
                text = f"最多は{examples}など{len(leaders)}種で、それぞれ{count}枚に登場します"
            else:
                text = f"最も多く登場するのは{pokemon}で、{count}枚に描かれています"
            trivia.append({
                "id": f"{prefecture}-top-pokemon",
                "type": "top_pokemon",
                "text": text,
                "source_type": "dataset",
            })
    return trivia


def generate(records: list[dict], sources: dict) -> list[dict]:
    validate_sources(sources, records)
    records_by_prefecture = {prefecture: [] for prefecture in PREFECTURE_ORDER}
    for record in records:
        prefecture = record.get("prefecture")
        if prefecture in records_by_prefecture:
            records_by_prefecture[prefecture].append(record)

    groups_by_prefecture: dict[str, list[dict]] = {}
    for group in sources.get("pokemon_groups", []):
        groups_by_prefecture.setdefault(group["prefecture"], []).append(group)
    editorial_by_prefecture: dict[str, list[dict]] = {}
    for entry in sources.get("editorial_trivia", []):
        editorial_by_prefecture.setdefault(entry["prefecture"], []).append(entry)

    result = []
    for prefecture in PREFECTURE_ORDER:
        pref_records = records_by_prefecture[prefecture]
        municipalities = sorted({
            record.get("city", "").strip()
            for record in pref_records
            if record.get("city", "").strip()
        })
        municipality_counts = Counter(
            record.get("city", "").strip()
            for record in pref_records
            if record.get("city", "").strip()
        )
        pokemon_counts = Counter(
            pokemon
            for record in pref_records
            for pokemon in sorted(set(record.get("pokemons", [])))
            if isinstance(pokemon, str) and pokemon.strip()
        )
        total = len(pref_records)

        coverage: list[dict] = []
        for pokemon, count in sorted(pokemon_counts.items(), key=lambda item: (-item[1], item[0])):
            coverage.append({
                "id": pokemon,
                "label": pokemon,
                "pokemon": [pokemon],
                "cover_count": count,
                "coverage_percent": round(count * 100 / total, 1) if total else 0,
            })
        for group in groups_by_prefecture.get(prefecture, []):
            count = _coverage(pref_records, group["pokemon"])
            coverage.append({
                "id": group["id"],
                "label": group["label"],
                "pokemon": group["pokemon"],
                "cover_count": count,
                "coverage_percent": round(count * 100 / total, 1) if total else 0,
            })

        trivia = _dataset_trivia(
            prefecture,
            pref_records,
            municipality_counts,
            pokemon_counts,
            coverage,
        )
        for entry in editorial_by_prefecture.get(prefecture, []):
            trivia.append({
                "id": entry["id"],
                "type": entry["type"],
                "text": entry["text"],
                "source_type": "official",
                "source_url": entry["source_url"],
                "source_label": entry.get("source_label", "公式サイト"),
                "verified_at": entry["verified_at"],
            })
        trivia.sort(key=lambda item: (-TRIVIA_PRIORITY[item["type"]], item["id"]))

        result.append({
            "prefecture": prefecture,
            "manhole_count": total,
            "municipality_count": len(municipalities),
            "municipalities": municipalities,
            "municipality_distribution": [
                {"municipality": city, "manhole_count": count}
                for city, count in sorted(
                    municipality_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "pokemon_coverage": coverage,
            "trivia": trivia,
        })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Fail if output is stale")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        records = load_records(args.input)
        generated = generate(records, load_sources(args.sources))
    except (OSError, ValidationError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(generated, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"[ERROR] stale generated file: {args.output}", file=sys.stderr)
            return 1
        print(f"[OK] {args.output} is current")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    trivia_count = sum(len(item["trivia"]) for item in generated)
    print(f"[OK] wrote {len(generated)} prefectures / {trivia_count} trivia to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
