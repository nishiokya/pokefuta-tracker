#!/usr/bin/env python3
"""Generate static SEO-optimized HTML pages for individual manholes.

This script creates /manholes/{id}/index.html for each manhole in the dataset.
Each page includes unique title, description, h1, canonical URL, JSON-LD,
photos, Pokemon metadata, and CTAs for map navigation with GA4 tracking.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape

# Constants
BASE_URL = "https://data.pokefuta.com/"
GA_MEASUREMENT_ID = "G-K18NR4GZG2"

logger = logging.getLogger(__name__)


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def normalize_id(value: Any) -> str:
    """Normalize manhole ID for consistent joining across datasets."""
    if value is None:
        return ""
    s = str(value).strip()
    # Remove leading zeros for comparison but keep original format
    return s.lstrip('0') or '0'


def load_manholes(path: Path) -> list[dict]:
    """Load manholes from NDJSON file."""
    manholes = []
    if not path.exists():
        logger.warning(f"Manhole data file not found: {path}")
        return manholes

    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            manholes.append(record)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse line {line_num}: {e}")

    logger.info(f"Loaded {len(manholes)} manholes from {path}")
    return manholes


def load_photos(path: Path) -> dict[str, dict]:
    """Load manhole photos data."""
    if not path.exists():
        logger.warning(f"Photos file not found: {path}")
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        photos = data.get("photos", {})
        logger.info(f"Loaded {len(photos)} photo entries from {path}")

        # Normalize keys
        normalized = {}
        for manhole_id, photo_data in photos.items():
            norm_id = normalize_id(manhole_id)
            normalized[norm_id] = photo_data

        return normalized
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse photos JSON: {e}")
        return {}


def load_pokemon_metadata(path: Path) -> dict[str, dict]:
    """Load Pokemon metadata indexed by Japanese name."""
    if not path.exists():
        logger.warning(f"Pokemon metadata file not found: {path}")
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Index by Japanese name for quick lookup
        metadata = {}
        for pokemon in data:
            if isinstance(pokemon, dict):
                names = pokemon.get("names", {})
                ja_name = names.get("ja", "")
                if ja_name:
                    metadata[ja_name] = pokemon

        logger.info(f"Loaded metadata for {len(metadata)} Pokemon")
        return metadata
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Pokemon metadata: {e}")
        return {}


def filter_pokemons(pokemons: list) -> list[str]:
    """Filter out prefecture site links from Pokemon list."""
    if not isinstance(pokemons, list):
        return []

    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def manhole_label(manhole: dict) -> str:
    """Build a plain-text display label for a manhole (for use in link text)."""
    pref = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    pokes = "・".join(filter_pokemons(manhole.get("pokemons", []))) or "ポケモン"
    location = f"{pref}{city}" if (pref or city) else manhole.get("title", "")
    return f"{location}のポケふた（{pokes}）"


def generate_html(
    manhole: dict,
    photo: Optional[dict],
    pokemon_meta: dict[str, dict],
    nearby: list[tuple[dict, float]],
    same_pref: list[dict],
    pref_total: int,
    same_pokemon: list[dict],
) -> str:
    """Generate complete HTML for a manhole detail page."""
    manhole_id = str(manhole.get("id", "")).strip()
    prefecture = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    address = manhole.get("address", "")
    pokemons = filter_pokemons(manhole.get("pokemons", []))
    detail_url = manhole.get("detail_url", "")
    lat = manhole.get("lat")
    lng = manhole.get("lng")

    # Generate unique title and description
    pokemon_text = "・".join(pokemons) if pokemons else "ポケモン"

    title = f"{prefecture}{city}のポケふた｜{pokemon_text} | data.pokefuta.com"

    description = (
        f"{prefecture}{city}に設置されているポケふた。"
        f"{pokemon_text}が描かれています。"
        f"場所・写真・地図・周辺のポケふた情報を掲載。"
    )

    h1 = f"{prefecture}{city}のポケふた"
    if pokemons:
        h1 += f"（{pokemon_text}）"

    canonical_url = f"{BASE_URL}manholes/{quote(manhole_id)}/"
    map_url = f"{BASE_URL}?manhole={quote(manhole_id)}"
    pref_url = f"{BASE_URL}?pref={quote(prefecture)}"

    # Build Pokemon info with metadata
    pokemon_info_html = ""
    if pokemons:
        pokemon_info_html = "<section class='pokemon-section'><h2>登場ポケモン</h2><div class='pokemon-list'>"
        for poke_name in pokemons:
            meta = pokemon_meta.get(poke_name, {})
            names = meta.get("names", {})
            en_name = names.get("en", "")
            types_data = meta.get("types", [])
            types_ja = [t.get("ja", "") for t in types_data if isinstance(t, dict)]
            generation = meta.get("generation")

            pokemon_info_html += f"<div class='pokemon-card'>"
            pokemon_info_html += f"<h3>{escape(poke_name)}</h3>"
            if en_name:
                pokemon_info_html += f"<p class='en-name'>{escape(en_name)}</p>"
            if types_ja:
                pokemon_info_html += f"<p class='types'>タイプ: {escape('・'.join(types_ja))}</p>"
            if generation:
                pokemon_info_html += f"<p class='generation'>第{generation}世代</p>"
            pokemon_info_html += "</div>"

        pokemon_info_html += "</div></section>"

    # Photo section
    photo_html = ""
    og_image = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"

    if photo:
        photo_url = photo.get("url", "") or photo.get("original_url", "")
        if photo_url:
            og_image = photo_url
            photo_html = f"""
<section class='photo-section'>
  <h2>写真</h2>
  <img src="{escape(photo_url)}" alt="{escape(h1)}の写真" loading="lazy">
</section>
"""

    # Location info
    location_html = f"""
<section class='location-section'>
  <h2>設置場所</h2>
  <dl>
    <dt>都道府県</dt>
    <dd>{escape(prefecture)}</dd>
    <dt>市区町村</dt>
    <dd>{escape(city)}</dd>
"""
    if address:
        location_html += f"""
    <dt>住所</dt>
    <dd>{escape(address)}</dd>
"""
    location_html += """
  </dl>
</section>
"""

    # JSON-LD structured data
    jsonld = {
        "@context": "https://schema.org",
        "@type": "TouristAttraction",
        "name": h1,
        "description": description,
        "url": canonical_url,
        "address": {
            "@type": "PostalAddress",
            "addressRegion": prefecture,
            "addressLocality": city,
            "streetAddress": address
        }
    }

    if lat is not None and lng is not None:
        jsonld["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lng
        }

    if photo:
        photo_image_url = photo.get("url") or photo.get("original_url")
        if photo_image_url:
            jsonld["image"] = photo_image_url

    jsonld_str = json.dumps(jsonld, ensure_ascii=False, indent=2)

    # Official site link (if available)
    official_html = ""
    _parsed = urlparse(detail_url) if detail_url else None
    if _parsed and _parsed.scheme == "https" and _parsed.hostname == "local.pokemon.jp":
        official_html = f"""
<p class='official-link'>
  <a href="{escape(detail_url)}" target="_blank" rel="noopener noreferrer">公式サイトを見る</a>
</p>
"""

    # Nearby manholes section
    nearby_html = ""
    if nearby:
        nearby_html = "<section class='nearby-section'><h2>近くのポケふた</h2><ul class='related-list'>"
        for other, dist in nearby:
            oid = str(other.get("id", ""))
            label = manhole_label(other)
            dist_str = f"{dist:.1f} km"
            nearby_html += (
                f"<li>"
                f"<a href='/manholes/{quote(oid, safe='')}/'>{escape(label)}</a>"
                f"<span class='distance'>{escape(dist_str)}</span>"
                f"</li>"
            )
        nearby_html += "</ul></section>"

    # Same pokemon manholes section
    same_pokemon_html = ""
    if same_pokemon:
        same_pokemon_html = "<section class='same-pokemon-section'><h2>同じポケモンのポケふた</h2><ul class='related-list'>"
        for other in same_pokemon:
            oid = str(other.get("id", ""))
            label = manhole_label(other)
            same_pokemon_html += f"<li><a href='/manholes/{quote(oid, safe='')}/'>{escape(label)}</a></li>"
        same_pokemon_html += "</ul></section>"

    # Same prefecture section
    pref_section_html = ""
    if prefecture and same_pref:
        pref_section_html = (
            f"<section class='prefecture-section'>"
            f"<h2>{escape(prefecture)}のポケふた</h2>"
            f"<p>{escape(prefecture)}には現在{pref_total}枚のポケふたがあります。</p>"
            f"<ul class='related-list'>"
        )
        for other in same_pref:
            oid = str(other.get("id", ""))
            label = manhole_label(other)
            pref_section_html += f"<li><a href='/manholes/{quote(oid, safe='')}/'>{escape(label)}</a></li>"
        pref_section_html += "</ul></section>"

    # Safely serialize GA event params for inline onclick attribute.
    # json.dumps handles all JS special chars; escape() makes the JSON safe
    # inside an HTML double-quoted attribute (browser decodes &quot; before eval).
    onclick_params = escape(json.dumps(
        {"manhole_id": manhole_id, "prefecture": prefecture, "city": city},
        ensure_ascii=False,
    ))
    current_year = datetime.date.today().year

    # Complete HTML
    html = f"""<!doctype html>
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
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(og_image)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{escape(og_image)}">

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
      'page_path': '/manholes/{escape(manhole_id)}/'
    }});

    function trackEvent(action, params) {{
      gtag('event', action, params);
    }}
  </script>

  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #f5f5f5;
      padding: 16px;
    }}

    .container {{
      max-width: 800px;
      margin: 0 auto;
      background: white;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }}

    h1 {{
      font-size: 24px;
      margin-bottom: 16px;
      color: #1a1a1a;
    }}

    h2 {{
      font-size: 20px;
      margin: 24px 0 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #e0e0e0;
    }}

    h3 {{
      font-size: 18px;
      margin-bottom: 8px;
    }}

    .cta-primary {{
      display: block;
      background: #dc3545;
      color: white;
      text-align: center;
      padding: 16px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 18px;
      font-weight: bold;
      margin: 24px 0;
      transition: background 0.2s;
    }}

    .cta-primary:hover {{
      background: #c82333;
    }}

    .cta-secondary {{
      display: inline-block;
      background: #007bff;
      color: white;
      padding: 12px 20px;
      border-radius: 6px;
      text-decoration: none;
      margin: 8px 8px 8px 0;
      transition: background 0.2s;
    }}

    .cta-secondary:hover {{
      background: #0056b3;
    }}

    .photo-section img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      margin-top: 12px;
    }}

    .pokemon-list {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 16px;
      margin-top: 12px;
    }}

    .pokemon-card {{
      background: #f8f9fa;
      padding: 16px;
      border-radius: 8px;
      border: 1px solid #e0e0e0;
    }}

    .pokemon-card .en-name {{
      color: #666;
      font-size: 14px;
    }}

    .pokemon-card .types,
    .pokemon-card .generation {{
      font-size: 14px;
      margin-top: 4px;
    }}

    dl {{
      margin-top: 12px;
    }}

    dt {{
      font-weight: bold;
      margin-top: 8px;
    }}

    dd {{
      margin-left: 16px;
      color: #555;
    }}

    .official-link {{
      margin-top: 16px;
    }}

    .official-link a {{
      color: #007bff;
      text-decoration: none;
    }}

    .official-link a:hover {{
      text-decoration: underline;
    }}

    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #e0e0e0;
      text-align: center;
      color: #666;
      font-size: 14px;
    }}

    .related-list {{
      list-style: none;
      margin-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .related-list a {{
      color: #007bff;
      text-decoration: none;
      flex: 1;
    }}

    .related-list a:hover {{
      text-decoration: underline;
    }}

    .related-list li {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      background: #f8f9fa;
      border-radius: 6px;
      border: 1px solid #e0e0e0;
      flex-wrap: wrap;
      gap: 4px;
    }}

    .distance {{
      font-size: 13px;
      color: #666;
      white-space: nowrap;
    }}

    @media (max-width: 600px) {{
      body {{
        padding: 8px;
      }}

      .container {{
        padding: 16px;
      }}

      h1 {{
        font-size: 20px;
      }}

      .pokemon-list {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{escape(h1)}</h1>

    <a href="{escape(map_url)}" class="cta-primary" onclick="trackEvent('manhole_seo_to_map_click', {onclick_params})">
      📍 地図でこのポケふたを見る
    </a>

    {photo_html}

    {pokemon_info_html}

    {location_html}

    {nearby_html}

    {same_pokemon_html}

    {pref_section_html}

    <section class='navigation-section'>
      <h2>他のポケふたを見る</h2>
      <p>
        <a href="{escape(pref_url)}" class="cta-secondary">同じ都道府県のポケふたを見る</a>
        <a href="{BASE_URL}" class="cta-secondary">全国マップを見る</a>
      </p>
    </section>

    {official_html}

    <footer>
      <p>&copy; 2024-{current_year} data.pokefuta.com | ポケふた情報はポケモン公式サイトを参照しています</p>
    </footer>
  </div>
</body>
</html>
"""

    return html


def generate_all_pages(
    manholes: list[dict],
    photos: dict[str, dict],
    pokemon_meta: dict[str, dict],
    output_dir: Path,
    image_dir: Path,
) -> tuple[int, int, int]:
    """Generate HTML pages for all manholes.

    Returns:
        (total_generated, photos_applied, photos_missing)
    """
    total = 0
    photos_applied = 0
    photos_missing = 0

    # Build cross-manhole indexes once
    pref_index: dict[str, list[dict]] = {}
    for m in manholes:
        pref = m.get("prefecture", "")
        if pref:
            pref_index.setdefault(pref, []).append(m)

    pokemon_index: dict[str, list[dict]] = {}
    for m in manholes:
        for pk in filter_pokemons(m.get("pokemons", [])):
            pokemon_index.setdefault(pk, []).append(m)

    for manhole in manholes:
        manhole_id = str(manhole.get("id", "")).strip()
        if not manhole_id:
            logger.warning("Skipping manhole with missing ID")
            continue

        norm_id = normalize_id(manhole_id)
        photo = photos.get(norm_id)

        # Prefer local repo image over Cloudflare URL when available
        local_image = image_dir / f"{manhole_id}_latest.jpeg"
        if local_image.exists():
            local_url = f"{BASE_URL}manhole/image/{manhole_id}_latest.jpeg"
            photo = dict(photo or {}, url=local_url)
            logger.debug(f"Using local image for manhole {manhole_id}")

        if photo:
            photos_applied += 1
        else:
            photos_missing += 1
            logger.debug(f"No photo found for manhole {manhole_id} (normalized: {norm_id})")

        prefecture = manhole.get("prefecture", "")
        lat = manhole.get("lat")
        lng = manhole.get("lng")

        # Nearby manholes (requires lat/lng)
        nearby: list[tuple[dict, float]] = []
        if lat is not None and lng is not None:
            for other in manholes:
                if str(other.get("id", "")) == manhole_id:
                    continue
                olat, olng = other.get("lat"), other.get("lng")
                if olat is None or olng is None:
                    continue
                dist = haversine(float(lat), float(lng), float(olat), float(olng))
                nearby.append((other, dist))
            nearby.sort(key=lambda x: x[1])
            nearby = nearby[:5]

        # Same prefecture manholes (stable sort: city then id)
        same_pref_all = [
            m for m in pref_index.get(prefecture, [])
            if str(m.get("id", "")) != manhole_id
        ]
        same_pref = sorted(
            same_pref_all,
            key=lambda m: (m.get("city", ""), str(m.get("id", "")))
        )[:20]
        pref_total = len(pref_index.get(prefecture, []))

        # Same pokemon manholes (deduplicated: one entry per manhole)
        seen_ids: set[str] = set()
        same_pokemon: list[dict] = []
        for pk in filter_pokemons(manhole.get("pokemons", [])):
            for other in pokemon_index.get(pk, []):
                oid = str(other.get("id", ""))
                if oid != manhole_id and oid not in seen_ids:
                    seen_ids.add(oid)
                    same_pokemon.append(other)
        same_pokemon = same_pokemon[:10]

        html = generate_html(manhole, photo, pokemon_meta, nearby, same_pref, pref_total, same_pokemon)

        page_dir = output_dir / "manholes" / manhole_id
        page_dir.mkdir(parents=True, exist_ok=True)

        index_file = page_dir / "index.html"
        index_file.write_text(html, encoding="utf-8")

        total += 1

    return total, photos_applied, photos_missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manholes",
        default="docs/pokefuta.ndjson",
        help="Path to manholes NDJSON file"
    )
    parser.add_argument(
        "--photos",
        default="docs/latest-manhole-photos.json",
        help="Path to photos JSON file"
    )
    parser.add_argument(
        "--pokemon",
        default="docs/pokemon_metadata.json",
        help="Path to Pokemon metadata JSON file"
    )
    parser.add_argument(
        "--image-dir",
        default="dataset/manhole/image",
        help="Directory containing {id}_latest.jpeg local images"
    )
    parser.add_argument(
        "--output",
        default="dist",
        help="Output directory (will create manholes/ subdirectory)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s"
    )

    manholes = load_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded, exiting")
        return 1

    photos = load_photos(Path(args.photos))
    pokemon_meta = load_pokemon_metadata(Path(args.pokemon))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, photos_applied, photos_missing = generate_all_pages(
        manholes, photos, pokemon_meta, output_dir, Path(args.image_dir)
    )

    print(f"[generate_manhole_pages] total manholes: {len(manholes)}")
    print(f"[generate_manhole_pages] generated manhole pages: {total}")
    print(f"[generate_manhole_pages] photo applied: {photos_applied}")
    print(f"[generate_manhole_pages] photo missing: {photos_missing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
