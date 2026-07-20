#!/usr/bin/env python3
"""Generate the public sitemap for the Pokefuta map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS

BASE_URL = "https://data.pokefuta.com/"
I18N_LANGS = ["en", "zh-TW", "zh-CN", "ko"]

PREFECTURES = PREFECTURE_ORDER


def read_all_manhole_ids(path: Path) -> list[str]:
    """Read all manhole IDs from the dataset."""
    ids = []
    if not path.exists():
        return ids

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        manhole_id = str(record.get("id") or "").strip()
        if manhole_id:
            ids.append(manhole_id)

    return sorted(set(ids), key=lambda value: (len(value), value))


_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def _filter_pokemons(pokemons: list) -> list[str]:
    if not isinstance(pokemons, list):
        return []
    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def _normalize_katakana(text: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
        for c in text
    )


def read_pokemon_slugs(ndjson_path: Path, metadata_path: Path) -> list[str]:
    """Return sorted slug list for Pokemon that appear on at least one pokefuta."""
    if not metadata_path.exists():
        logger.warning(f"Pokemon metadata not found: {metadata_path} — skipping Pokemon URLs")
        return []

    try:
        meta_list = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read Pokemon metadata ({exc}) — skipping Pokemon URLs")
        return []

    # Build ja_name → slug (base form preferred over regional variants)
    ja_to_slug: dict[str, str] = {}
    for pokemon in meta_list:
        if not isinstance(pokemon, dict):
            continue
        ja_name = pokemon.get("names", {}).get("ja", "")
        slug = pokemon.get("slug", "")
        form = pokemon.get("form") or ""
        if not ja_name or not slug:
            continue
        # Prefer base form (form == None) for direct ja_name key
        if ja_name not in ja_to_slug or not form:
            ja_to_slug[ja_name] = slug
        # Regional prefix variant (e.g. "アローラロコン" → slug)
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in ja_to_slug:
                ja_to_slug[combined] = slug

    # Katakana normalization for hiragana-mixed names
    for key in list(ja_to_slug.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in ja_to_slug:
            ja_to_slug[normalized] = ja_to_slug[key]

    # Collect slugs from active manholes
    found_slugs: set[str] = set()
    if ndjson_path.exists():
        for line in ndjson_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") != "active":
                continue
            for ja_name in _filter_pokemons(record.get("pokemons", [])):
                slug = ja_to_slug.get(ja_name) or ja_to_slug.get(
                    _normalize_katakana(ja_name)
                )
                if slug:
                    found_slugs.add(slug)

    return sorted(found_slugs)


def url_entry(loc: str, changefreq: str, priority: str) -> str:
    return "\n".join(
        [
            "  <url>",
            f"    <loc>{escape(loc)}</loc>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    )


def build_sitemap(manhole_ids: list[str], pokemon_slugs: list[str] | None = None) -> str:
    entries = [
        url_entry(BASE_URL, "daily", "1.0"),
        url_entry(f"{BASE_URL}summary/", "weekly", "0.9"),
        url_entry(f"{BASE_URL}pokemon/", "weekly", "0.9"),
        url_entry(f"{BASE_URL}nearby.html", "weekly", "0.6"),
        url_entry(f"{BASE_URL}character_manholes.html", "weekly", "0.8"),
        url_entry(f"{BASE_URL}gmanhole_map.html", "weekly", "0.7"),
        url_entry(f"{BASE_URL}design_manhole.html", "weekly", "0.6"),
    ]

    for lang in I18N_LANGS:
        entries.append(url_entry(f"{BASE_URL}{lang}/", "weekly", "0.9"))

    for prefecture in PREFECTURES:
        entries.append(
            url_entry(
                f"{BASE_URL}prefectures/{PREFECTURE_SLUGS[prefecture]}/",
                "weekly",
                "0.8",
            )
        )

    # Static manhole detail pages (primary SEO target)
    for manhole_id in manhole_ids:
        entries.append(
            url_entry(f"{BASE_URL}manholes/{quote(manhole_id)}/", "weekly", "0.8")
        )

    # Pokemon LP pages (Japanese root)
    for slug in pokemon_slugs or []:
        entries.append(
            url_entry(f"{BASE_URL}pokemon/{quote(slug)}/", "weekly", "0.1")
        )

    # Pokemon LP pages (multilingual)
    for lang in I18N_LANGS:
        entries.append(url_entry(f"{BASE_URL}{lang}/pokemon/", "weekly", "0.9"))
        for slug in pokemon_slugs or []:
            entries.append(
                url_entry(f"{BASE_URL}{lang}/pokemon/{quote(slug)}/", "weekly", "0.1")
            )

    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *entries,
            "</urlset>",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="docs/pokefuta.ndjson")
    parser.add_argument("--pokemon", default="docs/pokemon_metadata.json")
    parser.add_argument("--output", default="apps/web/sitemap.xml")
    args = parser.parse_args()

    manhole_ids = read_all_manhole_ids(Path(args.data))
    if not manhole_ids:
        print("No manhole IDs found in dataset")
        return 1

    pokemon_slugs = read_pokemon_slugs(Path(args.data), Path(args.pokemon))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_sitemap(manhole_ids, pokemon_slugs), encoding="utf-8"
    )
    print(
        f"[generate_sitemap] wrote {output_path} with "
        f"{len(manhole_ids)} manhole URLs + {len(pokemon_slugs)} pokemon URLs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
