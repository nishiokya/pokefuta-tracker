#!/usr/bin/env python3
"""Generate static SEO-optimized LP pages for individual Pokemon.

Creates /pokemon/{slug}/index.html for each Pokemon that appears on at least
one active pokefuta manhole.  Each page includes title, meta description,
canonical URL, OGP tags, JSON-LD (CollectionPage), a manhole list, and CTAs.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://data.pokefuta.com/"
GA_MEASUREMENT_ID = "G-K18NR4GZG2"
DEFAULT_OGP_IMAGE = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"

# Regional form prefix mapping (pokefuta data uses these prefixes)
_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def _normalize_katakana(text: str) -> str:
    """Convert hiragana to katakana for loose matching."""
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
        for c in text
    )


def load_pokemon_metadata(path: Path) -> dict[str, dict]:
    """Load Pokemon metadata; index by Japanese name (including regional forms)."""
    if not path.exists():
        logger.warning(f"Pokemon metadata not found: {path}")
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, dict] = {}

    for pokemon in data:
        if not isinstance(pokemon, dict):
            continue
        names = pokemon.get("names", {})
        ja_name = names.get("ja", "")
        form = pokemon.get("form") or ""
        if not ja_name:
            continue

        # Direct name: prefer base form (form == None) over regional variants.
        # Alolan/Galarian/Hisuian entries share the same names.ja as the base
        # Pokemon, so we must not let them overwrite the base slug.
        if ja_name not in metadata or not form:
            metadata[ja_name] = pokemon

        # Regional prefix variants: metadata stores "ロコン" for alolan vulpix,
        # but pokefuta data uses "アローラロコン"
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in metadata:
                metadata[combined] = pokemon

    # Normalize katakana: handle ゴンべ (hiragana べ) → ゴンベ mismatch
    for key in list(metadata.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in metadata:
            metadata[normalized] = metadata[key]

    logger.info(f"Loaded {len(metadata)} Pokemon name variants from metadata")
    return metadata


def filter_pokemons(pokemons: list) -> list[str]:
    """Remove prefecture site link entries from the pokemons field."""
    if not isinstance(pokemons, list):
        return []
    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def read_manholes(path: Path) -> list[dict]:
    """Read active manhole records from NDJSON."""
    if not path.exists():
        logger.warning(f"Manhole data not found: {path}")
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("status") == "active":
            records.append(r)
    return records


def build_pokemon_index(
    manholes: list[dict],
    metadata: dict[str, dict],
) -> dict[str, tuple[dict, list[dict]]]:
    """Return {slug: (pokemon_meta, [manhole, ...])} for Pokemon with >=1 pokefuta."""
    index: dict[str, tuple[dict, list[dict]]] = {}
    slug_to_meta: dict[str, dict] = {}
    ja_to_slug: dict[str, str] = {}

    for ja_name, meta in metadata.items():
        slug = meta.get("slug", "")
        if slug:
            ja_to_slug[ja_name] = slug
            slug_to_meta[slug] = meta

    for manhole in manholes:
        for ja_name in filter_pokemons(manhole.get("pokemons", [])):
            # Try direct match, then katakana-normalized match
            slug = ja_to_slug.get(ja_name) or ja_to_slug.get(
                _normalize_katakana(ja_name)
            )
            if not slug:
                continue
            meta = slug_to_meta[slug]
            if slug not in index:
                index[slug] = (meta, [])
            index[slug][1].append(manhole)

    return index


def build_related_map(
    index: dict[str, tuple[dict, list[dict]]],
    metadata: dict[str, dict],
) -> dict[str, list[tuple[str, str]]]:
    """Return {slug: [(related_slug, ja_name), ...]} sharing a base evolution family."""
    slug_to_family: dict[str, str] = {}
    slug_to_ja: dict[str, str] = {}
    for _ja_name, meta in metadata.items():
        slug = meta.get("slug", "")
        fam = (meta.get("evolution") or {}).get("family_id", "")
        if slug and fam:
            slug_to_family[slug] = fam
            slug_to_ja.setdefault(slug, meta.get("names", {}).get("ja", slug))

    base_to_slugs: dict[str, list[str]] = defaultdict(list)
    for slug in index:
        fam = slug_to_family.get(slug, "")
        base = fam.split("-")[0] if fam else ""
        if base:
            base_to_slugs[base].append(slug)

    result: dict[str, list[tuple[str, str]]] = {}
    for slug in index:
        fam = slug_to_family.get(slug, "")
        base = fam.split("-")[0] if fam else ""
        related = [
            (s, slug_to_ja.get(s, s))
            for s in sorted(base_to_slugs.get(base, []))
            if s != slug
        ]
        result[slug] = related
    return result


def generate_html(
    slug: str,
    pokemon: dict,
    manholes: list[dict],
    related: list[tuple[str, str]],
    image_dir: Path,
) -> str:
    """Return complete HTML for a Pokemon LP page."""
    names = pokemon.get("names", {})
    name_ja = names.get("ja", slug)
    name_en = names.get("en", "")
    name_ko = names.get("ko", "")
    name_zh = names.get("zh-Hans", "")
    types_data = pokemon.get("types", [])
    types_ja = [t.get("ja", "") for t in types_data if isinstance(t, dict)]
    generation = pokemon.get("generation")

    canonical_url = f"{BASE_URL}pokemon/{quote(slug)}/"
    map_url = BASE_URL
    count = len(manholes)

    title = f"{name_ja}のポケふた一覧 | 全国のポケモンマンホールマップ"
    description = (
        f"{name_ja}が描かれた全国のポケふた（ポケモンマンホール）を地図で探せます。"
        f"旅行先や現在地から近くのポケふたを見つけよう。"
    )

    # OGP title keeps it short
    og_title = f"{name_ja}のポケふた一覧"
    og_desc = description

    # Multilingual names line
    multilang_parts = [p for p in [name_en, name_ko, name_zh] if p]
    multilang_html = ""
    if multilang_parts:
        multilang_html = (
            f"<p class='poke-multilang'>{escape(' / '.join(multilang_parts))}</p>"
        )

    # Type badges
    type_badges = "".join(
        f"<span class='type-badge'>{escape(t)}</span>" for t in types_ja
    )
    type_html = (
        f"<div class='type-badges'>{type_badges}</div>" if type_badges else ""
    )

    gen_html = f"<p class='poke-gen'>第{generation}世代</p>" if generation else ""

    # JSON-LD
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": og_title,
        "description": description,
        "url": canonical_url,
        "inLanguage": "ja",
    }
    jsonld_str = json.dumps(jsonld, ensure_ascii=False, indent=2)

    # Manhole sections grouped by prefecture
    sorted_manholes = sorted(
        manholes,
        key=lambda m: (m.get("prefecture", ""), m.get("city", "")),
    )
    sections_html = ""
    for prefecture, group in groupby(sorted_manholes, key=lambda m: m.get("prefecture", "")):
        pref_h2 = f"{prefecture}の{name_ja}のポケふた"
        cards_html = ""
        for m in group:
            mid = str(m.get("id", "")).strip()
            pref = m.get("prefecture", "")
            city = m.get("city", "")
            label = f"{pref}{city}のポケふた"
            pokes = filter_pokemons(m.get("pokemons", []))
            sub = "・".join(pokes) if pokes else ""

            img_html = ""
            img_path = image_dir / f"{mid}_latest.jpeg"
            if img_path.exists():
                img_url = f"https://data.pokefuta.com/manhole/image/{mid}_latest.jpeg"
                alt = f"{pref}{city}の{name_ja}のポケふた"
                img_html = (
                    f"<img src='{img_url}' alt='{escape(alt)}'"
                    f" loading='lazy' decoding='async' width='320' height='180'>"
                )

            cards_html += (
                f"<li class='manhole-item'>"
                f"<a href='/manholes/{quote(mid)}/'>"
                + img_html
                + f"<span class='manhole-location'>{escape(label)}</span>"
                + (f"<span class='manhole-poke'>{escape(sub)}</span>" if sub else "")
                + f"</a></li>"
            )
        sections_html += (
            f"<section class='pref-section'>"
            f"<h2>{escape(pref_h2)}</h2>"
            f"<ul class='manhole-list'>{cards_html}</ul>"
            f"</section>"
        )

    # Related Pokemon section
    related_html = ""
    if related:
        links = "".join(
            f"<li><a href='/pokemon/{quote(s)}/'>{escape(ja)}</a></li>"
            for s, ja in related
        )
        related_html = (
            f"<div class='section-card related-section'>"
            f"<h2>関連するポケモン</h2>"
            f"<ul class='related-list'>{links}</ul>"
            f"</div>"
        )

    # slug_js for GA4 page_path
    slug_js = json.dumps(slug)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical_url)}">

  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(og_title)}">
  <meta property="og:description" content="{escape(og_desc)}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(og_title)}">
  <meta name="twitter:description" content="{escape(og_desc)}">
  <meta name="twitter:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <script type="application/ld+json">
{jsonld_str}
  </script>

  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}', {{
      'page_path': '/pokemon/' + {slug_js} + '/'
    }});
    gtag('event', 'view_pokemon_lp', {{
      pokemon_slug: {slug_js},
      manhole_count: {count}
    }});
    function trackEvent(action, params) {{
      gtag('event', action, params);
    }}
  </script>

  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #fff8ec;
      padding: 16px;
    }}
    .container {{
      max-width: 800px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }}
    .back-link {{
      display: inline-block;
      color: #6F55A3;
      text-decoration: none;
      font-size: 14px;
      margin-bottom: 16px;
    }}
    .back-link:hover {{ text-decoration: underline; }}
    .poke-hero {{
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 26px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 8px;
    }}
    .poke-multilang {{
      color: #666;
      font-size: 14px;
      margin-bottom: 8px;
    }}
    .type-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 6px;
    }}
    .type-badge {{
      background: #6F55A3;
      color: white;
      font-size: 12px;
      padding: 2px 10px;
      border-radius: 12px;
      font-weight: bold;
    }}
    .poke-gen {{
      font-size: 13px;
      color: #888;
    }}
    .section-card {{
      margin-top: 24px;
      padding: 16px;
      background: #fafafa;
      border-radius: 8px;
      border: 1px solid #e8e8e8;
    }}
    .count-text {{
      font-size: 15px;
      color: #555;
      margin-bottom: 16px;
    }}
    .pref-section {{
      margin-bottom: 20px;
    }}
    .pref-section h2 {{
      font-size: 16px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 2px solid #e0e0e0;
    }}
    .manhole-list {{
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
    }}
    .manhole-item a {{
      display: block;
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 10px 14px;
      text-decoration: none;
      color: #333;
      transition: border-color 0.15s, box-shadow 0.15s;
      overflow: hidden;
    }}
    .manhole-item a:hover {{
      border-color: #6F55A3;
      box-shadow: 0 2px 8px rgba(111,85,163,0.15);
    }}
    .manhole-item a img {{
      display: block;
      width: calc(100% + 28px);
      margin: -10px -14px 8px;
      height: 160px;
      object-fit: cover;
    }}
    .manhole-location {{
      display: block;
      font-size: 14px;
      font-weight: bold;
      color: #1a1a1a;
    }}
    .manhole-poke {{
      display: block;
      font-size: 12px;
      color: #888;
      margin-top: 2px;
    }}
    .related-section h2 {{
      font-size: 16px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 2px solid #e0e0e0;
    }}
    .related-list {{
      list-style: none;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .related-list a {{
      display: inline-block;
      padding: 4px 14px;
      background: #f0ebfa;
      color: #6F55A3;
      border-radius: 16px;
      text-decoration: none;
      font-size: 14px;
      font-weight: bold;
    }}
    .related-list a:hover {{ background: #e0d8f5; }}
    .cta-map {{
      display: block;
      background: #6F55A3;
      color: white;
      text-align: center;
      padding: 16px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 17px;
      font-weight: bold;
      margin-top: 24px;
      transition: background 0.2s;
    }}
    .cta-map:hover {{ background: #5a4480; }}
    footer {{
      margin-top: 32px;
      text-align: center;
      font-size: 13px;
      color: #aaa;
    }}
    footer a {{ color: #6F55A3; text-decoration: none; }}
  </style>
</head>
<body>
<div class="container">
  <a href="{escape(map_url)}" class="back-link"
     onclick="trackEvent('click_back_to_map', {{pokemon_slug: {slug_js}}})">← 全国マップへ戻る</a>

  <div class="poke-hero">
    <h1>{escape(name_ja)}のポケふた一覧</h1>
    {multilang_html}
    {type_html}
    {gen_html}
  </div>

  <div class="section-card">
    <p class="count-text">全国に <strong>{count}</strong> 枚の{escape(name_ja)}のポケふたがあります。</p>
    {sections_html}
  </div>

  {related_html}

  <a href="{escape(map_url)}" class="cta-map"
     onclick="trackEvent('click_map_cta', {{pokemon_slug: {slug_js}}})">
    地図で全国のポケふたを探す →
  </a>

  <footer>
    <p><a href="{escape(BASE_URL)}">data.pokefuta.com</a> &mdash; ポケモンマンホール全国マップ</p>
  </footer>
</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manholes", default="docs/pokefuta.ndjson",
        help="Path to pokefuta NDJSON",
    )
    parser.add_argument(
        "--pokemon", default="docs/pokemon_metadata.json",
        help="Path to pokemon_metadata.json",
    )
    parser.add_argument(
        "--images", default="dataset/manhole/image",
        help="Directory containing {id}_latest.jpeg files",
    )
    parser.add_argument(
        "--output", default="dist/pokemon",
        help="Output directory (dist/pokemon)",
    )
    args = parser.parse_args()

    metadata = load_pokemon_metadata(Path(args.pokemon))
    if not metadata:
        logger.error("No Pokemon metadata loaded — aborting")
        return 1

    manholes = read_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manhole records loaded — aborting")
        return 1

    index = build_pokemon_index(manholes, metadata)
    logger.info(f"Pokemon with pokefuta: {len(index)}")

    related_map = build_related_map(index, metadata)
    image_dir = Path(args.images)

    output_root = Path(args.output)
    generated = 0
    for slug, (pokemon, poke_manholes) in sorted(index.items()):
        out_dir = output_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        html = generate_html(
            slug, pokemon, poke_manholes,
            related=related_map.get(slug, []),
            image_dir=image_dir,
        )
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        generated += 1

    logger.info(f"[generate_pokemon_pages] wrote {generated} pages to {output_root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
