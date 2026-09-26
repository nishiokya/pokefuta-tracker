#!/usr/bin/env python3
"""英語版トップ（/en/index.html）を日本語トップと同じ構成で生成する。

データの読み込みと写真・イベントの選び方は generate_top_page.py と共有し、
ここでは英語の文言と、/en/ から見たリンク先だけを持つ。

- /en/ にあるページ（map.html・pokemon/）は `./` で、日本語にしか無いページ
  （都道府県・マンホール詳細・写真）は `../` で参照する。日本語ページへ飛ぶ導線には
  「Japanese」と書き添える
- テーマのラベルは strings.en.json の TAG_* を使う（dataset/tag_meta.json は日本語のみ）
- イベント名は日本語しか無いので lang="ja" を付けてそのまま出す

多言語版の残り（zh-TW / zh-CN / ko）は従来どおり index.template.html から作る。

Usage:
  python3 apps/scraper/generate_top_page_en.py                   # apps/web/index.en.html を更新
  python3 apps/scraper/generate_top_page_en.py dist/en/index.html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper import generate_top_page as ja
    from apps.scraper.photo_caption import JST, format_photo_date
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_top_page as ja
    from photo_caption import JST, format_photo_date
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS

ROOT = ja.ROOT
DEFAULT_TARGET = ROOT / "apps" / "web" / "index.en.html"
PREFECTURE_NAMES = ROOT / "apps" / "web" / "i18n" / "prefectures.json"
STRINGS_EN = ROOT / "apps" / "web" / "i18n" / "strings.en.json"

BASE_URL = "https://data.pokefuta.com/"
PAGE_URL = f"{BASE_URL}en/"
SITE_NAME = "Pokéfuta Directory"
PAGE_TITLE = "Poké Lids Directory — Every Pokémon Manhole in Japan"
ROOT_PATH = "../"  # /en/ から日本語のみのページ・画像へ

REGION_NAMES = {
    "北海道・東北": "Hokkaido & Tohoku",
    "関東": "Kanto",
    "中部": "Chubu",
    "近畿": "Kinki",
    "中国": "Chugoku",
    "四国": "Shikoku",
    "九州・沖縄": "Kyushu & Okinawa",
}
TAG_STRING_KEYS = {
    "roadside": "TAG_ROADSIDE",
    "remote_island": "TAG_ISLAND",
    "world_heritage": "TAG_WORLD_HERITAGE",
    "near_gundam_manhole": "TAG_GUNDAM",
    "seaside": "TAG_SEASIDE",
    "tourism": "TAG_TOURISM",
    "park": "TAG_PARK",
    "history": "TAG_HISTORY",
}
FORM_PREFIX_EN = {"alola": "Alolan ", "galar": "Galarian ", "hisui": "Hisuian ", "paldea": "Paldean "}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


class English:
    """英語表記の辞書（都道府県名・ポケモン名・テーマ名）。"""

    def __init__(self, prefecture_names: Path = PREFECTURE_NAMES, strings: Path = STRINGS_EN,
                 pokemon_metadata: Path | None = ja.DEFAULT_POKEMON_METADATA) -> None:
        prefs = json.loads(prefecture_names.read_text(encoding="utf-8"))
        self.prefectures = {name: str(v.get("en") or name) for name, v in prefs.items()}
        self.strings = json.loads(strings.read_text(encoding="utf-8"))
        self.pokemon: dict[str, str] = {}
        self.pokemon_by_slug: dict[str, str] = {}
        if pokemon_metadata and pokemon_metadata.exists():
            for meta in json.loads(pokemon_metadata.read_text(encoding="utf-8")):
                names = meta.get("names") or {}
                if not names.get("ja") or not names.get("en"):
                    continue
                form = meta.get("form") or ""
                en = FORM_PREFIX_EN.get(form, "") + names["en"]
                self.pokemon.setdefault(ja.FORM_PREFIX.get(form, "") + names["ja"], en)
                if meta.get("slug"):
                    self.pokemon_by_slug[meta["slug"]] = en

    def pref(self, name: str) -> str:
        return self.prefectures.get(name, name)

    def pokemon_name(self, name: str) -> str:
        return self.pokemon.get(name, name)

    def tag(self, slug: str) -> str:
        return self.strings.get(TAG_STRING_KEYS.get(slug, ""), slug)


# ── 部品 ──────────────────────────────────────────────────────────────────


def _names(photo: ja.Photo, en: English) -> str:
    return ", ".join(en.pokemon_name(p) for p in photo.pokemons[:2])


def _alt(photo: ja.Photo, en: English) -> str:
    names = _names(photo, en)
    where = en.pref(photo.prefecture)
    return f"Fan photo of the Poké Lid in {where} ({names})" if names else f"Fan photo of a Poké Lid in {where}"


def _img(photo: ja.Photo, en: English, *, eager: bool = False, priority: bool = False) -> str:
    loading = 'loading="eager"' if eager else 'loading="lazy"'
    fetch = ' fetchpriority="high"' if priority else ""
    return (
        f'<img src="{ROOT_PATH}{escape(photo.src)}" alt="{escape(_alt(photo, en))}" '
        f'width="{ja.PHOTO_SIZE}" height="{ja.PHOTO_SIZE}" {loading} decoding="async"{fetch}>'
    )


def _photo_href(photo: ja.Photo) -> str:
    return f"{ROOT_PATH}{photo.href}"


def _pref_href(pref: str) -> str:
    return f"{ROOT_PATH}prefectures/{PREFECTURE_SLUGS[pref]}/"


def description(data: ja.TopData) -> str:
    return (
        f"Find all {data.total:,} Poké Lids (Pokéfuta, Pokémon manhole covers) across "
        f"{len(data.installed_prefectures)} prefectures in Japan — with fan photos, a map, "
        "a prefecture list and a Pokémon index to plan your trip."
    )


def short_description(data: ja.TopData) -> str:
    return (
        f"{data.total:,} Poké Lids (Pokémon manhole covers) in {len(data.installed_prefectures)} "
        "prefectures of Japan, with fan photos and a map."
    )


def json_ld(data: ja.TopData, en: English) -> dict:
    counts = data.pref_counts
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}#website",
                "url": BASE_URL,
                "name": "ポケふた図鑑",
                "alternateName": SITE_NAME,
            },
            {
                "@type": "CollectionPage",
                "@id": f"{PAGE_URL}#webpage",
                "url": PAGE_URL,
                "name": PAGE_TITLE,
                "description": description(data),
                "inLanguage": "en",
                "isPartOf": {"@id": f"{BASE_URL}#website"},
                "breadcrumb": {"@id": f"{PAGE_URL}#breadcrumb"},
                "mainEntity": {"@id": f"{PAGE_URL}#prefectures"},
                "hasPart": [
                    {"@type": "WebPage", "name": "Poké Lids map", "url": f"{PAGE_URL}map.html"},
                    {"@type": "CollectionPage", "name": "Poké Lids by Pokémon", "url": f"{PAGE_URL}pokemon/"},
                    {"@type": "CollectionPage", "name": "Poké Lids statistics", "url": f"{PAGE_URL}summary/"},
                ],
            },
            {
                "@type": "ItemList",
                "@id": f"{PAGE_URL}#prefectures",
                "name": "Prefectures with Poké Lids",
                "numberOfItems": len(data.installed_prefectures),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": f"Poké Lids in {en.pref(pref)} ({counts[pref]})",
                        "url": f"{BASE_URL}prefectures/{PREFECTURE_SLUGS[pref]}/",
                    }
                    for i, pref in enumerate(data.installed_prefectures, start=1)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{PAGE_URL}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": PAGE_URL},
                ],
            },
        ],
    }


# ── ブロック ──────────────────────────────────────────────────────────────


def render_head(data: ja.TopData, en: English, indent: str) -> str:
    desc = escape(description(data), quote=True)
    short = escape(short_description(data), quote=True)
    ld = json.dumps(json_ld(data, en), ensure_ascii=False, indent=1).replace("<", "\\u003c")
    lines = [
        f'<meta name="description" content="{desc}">',
        f'<meta property="og:description" content="{short}">',
        f'<meta name="twitter:description" content="{short}">',
        '<script type="application/ld+json">',
        ld,
        "</script>",
    ]
    return "\n".join(indent + line if line else line for line in lines)


def render_hero(data: ja.TopData, en: English) -> str:
    photos = ja.select_hero_photos(data.photos)
    popular = [en.pokemon_by_slug.get(e.slug, e.name) for e in data.popular_pokemon[:3]]
    posts = data.stats.get("posts") if isinstance(data.stats.get("posts"), int) else None
    stats = [
        (f"{data.total:,}", "Poké Lids"),
        (str(len(data.installed_prefectures)), "Prefectures"),
        (f"{len(data.pokemon_counts):,}", "Pokémon"),
    ]
    if posts:
        stats.append((f"{posts:,}", "Fan photos"))
    stats_html = "".join(
        f'<div class="home-stat"><dt>{escape(label)}</dt><dd>{escape(num)}</dd></div>' for num, label in stats
    )
    quick = [
        ("map", "map.html", "Map & nearby", "home-quick__link--primary"),
        ("prefecture", "#home-pref", "By prefecture", ""),
        ("pokemon", "pokemon/", "By Pokémon", ""),
    ]
    quick_html = "".join(
        f'<a class="home-quick__link {cls}" href="{href}" '
        f'onclick="{ja._track("click_search_way", surface="top_hero_quick", way=way)}">{escape(label)}</a>'
        for way, href, label, cls in quick
    )
    lead = (
        "Poké Lids (<i>Pokéfuta</i>) are Pokémon-themed manhole covers. "
        f"{data.total:,} of them are installed in {len(data.installed_prefectures)} of Japan's 47 prefectures, "
        "from Hokkaido to Okinawa. This directory collects every location, the Pokémon on each lid "
        "and photos taken by fans"
        + (f" — <b>{escape(', '.join(popular))}</b> and {len(data.pokemon_counts):,} Pokémon in all." if popular else ".")
    )
    if photos:
        items = "".join(
            f'<li class="home-mosaic__item"><a href="{_photo_href(p)}" '
            f'onclick="{ja._track("click_hero_photo", surface="top_hero_photo", manhole=p.manhole_id, position=i)}">'
            f"{_img(p, en, eager=True, priority=(i == 0))}"
            f'<span class="home-mosaic__cap"><b>{escape(_names(p, en) or "Poké Lid")}</b>{escape(en.pref(p.prefecture))}</span>'
            "</a></li>"
            for i, p in enumerate(photos)
        )
        mosaic = (
            '<figure class="home-mosaic">'
            f'<ul class="home-mosaic__grid">{items}</ul>'
            f'<figcaption class="home-mosaic__note">Latest fan photos (updated {MONTHS[data.today.month - 1][:3]} {data.today.day})</figcaption>'
            "</figure>"
        )
        cls = "home-hero"
    else:
        mosaic = ""
        cls = "home-hero home-hero--no-photos"
    return (
        f'<section class="{cls}" id="home-hero" aria-labelledby="home-h1">'
        '<div class="home-hero__copy">'
        '<p class="home-eyebrow">POKÉMON MANHOLE DIRECTORY</p>'
        f'<h1 class="home-h1" id="home-h1">Find all {data.total:,} Poké Lids in Japan</h1>'
        f'<p class="home-lead">{lead}</p>'
        f'<nav class="home-quick" aria-label="Main ways to search">{quick_html}</nav>'
        f'<dl class="home-stats">{stats_html}</dl>'
        "</div>"
        f"{mosaic}"
        "</section>"
    )


def render_ways(data: ja.TopData, en: English) -> str:
    counts = data.pref_counts
    top_prefs = sorted(data.installed_prefectures, key=lambda p: (-counts[p], PREFECTURE_ORDER.index(p)))[:3]
    theme_slugs = [s for s in data.tag_meta.top_chip_slugs(data.tag_counts) if s in TAG_STRING_KEYS][:3]

    def sub(links: list[tuple[str, str]], way: str) -> str:
        return "".join(
            f'<li><a href="{href}" onclick="{ja._track("click_search_way", surface="top_search_ways", way=way)}">{label}</a></li>'
            for href, label in links
        )

    cards = [
        ("map", "map.html", "icon-map.svg", "Map & your location",
         "See every spot on a map of Japan and find the Poké Lids closest to you.",
         [("map.html", "Open the map"), ("map.html?view=theme", "Filter by theme")]),
        ("prefecture", "#home-pref", "icon-pin.svg", "By prefecture",
         f"Browse the {len(data.installed_prefectures)} prefectures with Poké Lids, grouped by region. "
         "Prefecture pages are in Japanese.",
         [(_pref_href(p), f"{escape(en.pref(p))} {counts[p]}") for p in top_prefs]),
        ("pokemon", "pokemon/", "pokefuta-marker.svg", "By Pokémon",
         f"Look up your favourite among {len(data.pokemon_counts):,} Pokémon featured on the lids.",
         [(e.href, f"{escape(en.pokemon_by_slug.get(e.slug, e.name))} {len(e.manhole_ids)}")
          for e in data.popular_pokemon[:3]]),
        ("theme", "map.html?view=theme", "icon-tag.svg", "By theme",
         "Roadside stations, World Heritage sites, remote islands and more.",
         [(f"map.html?tag={quote(s)}", escape(en.tag(s))) for s in theme_slugs]),
    ]
    cards_html = "".join(
        '<li class="home-way">'
        f'<a class="home-way__main" href="{href}" onclick="{ja._track("click_search_way", surface="top_search_ways", way=way)}">'
        f'<img class="home-way__icon" src="{ROOT_PATH}assets/{icon}" alt="" width="28" height="28">'
        f'<span class="home-way__title">{escape(title)}</span>'
        f'<span class="home-way__text">{escape(text)}</span>'
        "</a>"
        f'<ul class="home-way__links">{sub(links, way)}</ul>'
        "</li>"
        for way, href, icon, title, text, links in cards
    )
    return (
        '<section class="home-section" id="home-ways" aria-labelledby="home-ways-title">'
        '<h2 class="home-h2" id="home-ways-title">Choose how to search</h2>'
        f'<ul class="home-ways">{cards_html}</ul>'
        "</section>"
    )


def render_newrelease(data: ja.TopData, en: English) -> str:
    cutoff = datetime.combine(data.today - timedelta(days=ja.NEW_RELEASE_DAYS), datetime.min.time(), JST)
    fresh = []
    for record in data.records:
        try:
            added_at = datetime.fromisoformat(str(record.get("added_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if added_at >= cutoff:
            fresh.append((added_at, record))
    if not fresh:
        return ""
    fresh.sort(key=lambda item: (item[0], str(item[1].get("id"))), reverse=True)
    cards = []
    for i, (_, record) in enumerate(fresh):
        mid = str(record.get("id"))
        names = ", ".join(en.pokemon_name(p) for p in ja.pokemons_of(record)) or "Poké Lid"
        cards.append(
            f'<li><a class="home-newrel__card" href="{ROOT_PATH}manholes/{quote(mid, safe="")}/" '
            f'onclick="{ja._track("click_newrelease", surface="top_newrelease", manhole=mid, position=i)}">'
            f'<b>{escape(names)}</b><span>{escape(en.pref(str(record.get("prefecture", ""))))}</span></a></li>'
        )
    return (
        '<section class="home-section" id="home-newrelease" aria-labelledby="home-newrelease-title">'
        f'<h2 class="home-h2" id="home-newrelease-title">New Poké Lids <small>{len(fresh)} in the last {ja.NEW_RELEASE_DAYS} days</small></h2>'
        f'<ul class="home-newrel">{"".join(cards)}</ul>'
        "</section>"
    )


def render_photos(data: ja.TopData, en: English) -> str:
    photos = ja.select_gallery_photos(data.photos, ja.select_hero_photos(data.photos))
    upload = (
        f'<a class="home-cta" href="{ja.UPLOAD_URL}" '
        f'onclick="{ja._track("click_photo_post_cta", surface="top_photo_gallery")}">Post your photo on Pokéfuta Album</a>'
    )
    if not photos:
        return (
            '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
            '<h2 class="home-h2" id="home-photos-title">Latest fan photos</h2>'
            f'<p class="home-text">No photos yet. Be the first to post one.</p>{upload}'
            "</section>"
        )
    items = "".join(
        f'<li class="home-gallery__item"><a href="{_photo_href(p)}" '
        f'onclick="{ja._track("click_top_photo", surface="top_photo_gallery", manhole=p.manhole_id, position=i)}">'
        f"{_img(p, en)}"
        f'<span class="home-gallery__cap"><b>{escape(_names(p, en) or "Poké Lid")}</b>'
        f'<span>{escape(en.pref(p.prefecture))}</span>'
        f'<time datetime="{escape(ja._jst_iso(p.created_at))}">{escape(format_photo_date(p.created_at, "en"))}</time></span>'
        "</a></li>"
        for i, p in enumerate(photos)
    )
    with_photos = data.stats.get("manholes_with_photos")
    coverage = (
        f" Fans have photographed {with_photos:,} locations so far."
        if isinstance(with_photos, int) and with_photos else ""
    )
    return (
        '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
        '<h2 class="home-h2" id="home-photos-title">Latest fan photos</h2>'
        f'<p class="home-text">Recent posts, picked region by region from north to south so no single area dominates.{coverage}</p>'
        f'<ul class="home-gallery">{items}</ul>'
        f"{upload}"
        "</section>"
    )


def _event_card(event: dict, data: ja.TopData, en: English) -> str:
    pref = event["prefecture"]
    ongoing = event["start"] <= data.today
    status = en.strings.get("EVENTS_ONGOING", "Ongoing") if ongoing else en.strings.get("EVENTS_UPCOMING", "Starting soon")
    period = f'{event["start"]:%Y/%m/%d} – {event["end"]:%Y/%m/%d}'
    return (
        f'<li class="home-event" data-end="{event["end"].isoformat()}">'
        f'<a href="{_pref_href(pref)}" '
        f'onclick="{ja._track("click_event_notice", surface="top_event_notice", prefecture=pref, destination="prefecture_page")}">'
        f'<span class="home-event__badge{"" if ongoing else " is-upcoming"}">{escape(status)}</span>'
        f'<span class="home-event__copy"><b lang="ja">{escape(event["title"])}</b>'
        f'<small>{escape(en.pref(pref))} · {period}</small></span>'
        "</a></li>"
    )


def render_events(data: ja.TopData, en: English) -> str:
    if not data.events:
        return ""
    visible = data.events[:ja.EVENT_VISIBLE_LIMIT]
    rest = data.events[ja.EVENT_VISIBLE_LIMIT:]
    more = ""
    if rest:
        more = (
            '<details class="home-events__more">'
            f'<summary onclick="{ja._track("click_event_show_all", surface="top_event_notice", count=len(data.events))}">'
            f"Show all ({len(data.events)})</summary>"
            f'<ul class="home-events">{"".join(_event_card(e, data, en) for e in rest)}</ul>'
            "</details>"
        )
    return (
        '<section class="home-section" id="home-events" aria-labelledby="home-events-title">'
        f'<h2 class="home-h2" id="home-events-title">{escape(en.strings.get("EVENTS_TITLE", "Ongoing Events & Stamp Rallies"))}</h2>'
        '<p class="home-text">Event names and details are in Japanese.</p>'
        f'<ul class="home-events">{"".join(_event_card(e, data, en) for e in visible)}</ul>'
        f"{more}"
        "</section>"
    )


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def render_pref(data: ja.TopData, en: English) -> str:
    counts = data.pref_counts
    regions = []
    for name, prefs in ja.REGIONS:
        installed = [p for p in prefs if counts.get(p)]
        if not installed:
            continue
        links = "".join(
            f'<li><a href="{_pref_href(p)}" hreflang="ja" '
            f'onclick="{ja._track("click_pref_link", surface="top_prefecture_list", prefecture=p)}">'
            f'<span class="home-pref__name">{escape(en.pref(p))}</span><span class="home-pref__count">{counts[p]}</span></a></li>'
            for p in installed
        )
        regions.append(
            '<div class="home-region">'
            f'<h3 class="home-region__title">{escape(REGION_NAMES[name])} <small>{sum(counts[p] for p in installed)}</small></h3>'
            f'<ul class="home-pref">{links}</ul>'
            "</div>"
        )
    empty = data.empty_prefectures
    note = ""
    if empty:
        empty_links = [f'<a href="{_pref_href(p)}" hreflang="ja">{escape(en.pref(p))}</a>' for p in empty]
        note = (
            f'<p class="home-pref-note">As of {MONTHS[data.today.month - 1]} {data.today.year}, '
            f"there are no Poké Lids in {_join(empty_links)}.</p>"
        )
    return (
        '<section class="home-section" id="home-pref" aria-labelledby="home-pref-title">'
        f'<h2 class="home-h2" id="home-pref-title">{escape(en.strings.get("SEC4_TITLE", "Search by Prefecture"))}</h2>'
        f'<p class="home-text">Poké Lids are installed in {len(data.installed_prefectures)} of Japan\'s 47 prefectures. '
        "They are listed by region from north to south, with the number of lids in each. "
        "Prefecture pages are in Japanese.</p>"
        f'<div class="home-regions">{"".join(regions)}</div>'
        f"{note}"
        f'<a class="home-more" href="{ROOT_PATH}prefectures/" hreflang="ja" '
        f'onclick="{ja._track("click_pref_link", surface="top_prefecture_list", prefecture="all")}">'
        "All 47 prefectures (Japanese)</a>"
        "</section>"
    )


def render_themes(data: ja.TopData, en: English) -> str:
    slugs = [s for s in data.tag_meta.top_chip_slugs(data.tag_counts) if s in TAG_STRING_KEYS]
    return "".join(
        f'<a class="hub-chip" href="map.html?tag={quote(s)}" '
        f"onclick=\"trackEvent('click_hub_tag',{{surface:'top_hub_tag',tag:'{s}',destination:'map_tag_filter'}})\">"
        f'{escape(en.tag(s))} <span class="chip-count">{data.tag_counts.get(s, 0)}</span></a>'
        for s in slugs
    )


def render_pokemon(data: ja.TopData, en: English) -> str:
    cards = []
    used: set[str] = set()
    for entry in data.popular_pokemon:
        name = en.pokemon_by_slug.get(entry.slug, entry.name)
        ids = set(entry.manhole_ids)
        candidates = [p for p in data.photos if p.manhole_id in ids]
        photo = next((p for p in candidates if p.manhole_id not in used), candidates[0] if candidates else None)
        if photo:
            used.add(photo.manhole_id)
        media = (
            f'<img src="{ROOT_PATH}{escape(photo.src)}" alt="{escape(name)} Poké Lid in {escape(en.pref(photo.prefecture))}" '
            f'width="{ja.PHOTO_SIZE}" height="{ja.PHOTO_SIZE}" loading="lazy" decoding="async">'
            if photo else '<span class="home-poke__placeholder" aria-hidden="true"></span>'
        )
        cards.append(
            f'<li class="home-poke"><a href="{entry.href}" '
            f'onclick="{ja._track("click_hub_pokemon", surface="top_hub_pokemon", pokemon=entry.name)}">'
            f'{media}<span class="home-poke__name">{escape(name)}</span>'
            f'<span class="home-poke__count">{len(entry.manhole_ids)} lids</span></a></li>'
        )
    cards.append(
        '<li class="home-poke home-poke--all"><a href="pokemon/" '
        f'onclick="{ja._track("click_hub_pokemon_all", surface="top_hub_pokemon")}">'
        f'<span class="home-poke__name">All Pokémon</span><span class="home-poke__count">{len(data.pokemon_counts):,}</span></a></li>'
    )
    return f'<ul class="home-pokes">{"".join(cards)}</ul>'


RENDERERS = {
    "hero": render_hero,
    "ways": render_ways,
    "newrelease": render_newrelease,
    "photos": render_photos,
    "events": render_events,
    "pref": render_pref,
    "themes": render_themes,
    "pokemon": render_pokemon,
}


def apply_blocks(html: str, data: ja.TopData, en: English) -> str:
    def replace(match) -> str:
        name, indent = match.group("name"), match.group("indent")
        if name == "head":
            body = render_head(data, en, indent)
        elif name in RENDERERS:
            content = RENDERERS[name](data, en)
            body = f"{indent}{content}" if content else ""
        else:
            return match.group(0)
        start, end = f"<!-- home:{name}:start -->", f"<!-- home:{name}:end -->"
        return f"{indent}{start}\n{body}\n{indent}{end}" if body else f"{indent}{start}\n{indent}{end}"

    return ja.MARKER_RE.sub(replace, html)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path, nargs="?", default=DEFAULT_TARGET)
    parser.add_argument("--source", type=Path, default=DEFAULT_TARGET,
                        help="英語版の雛形（省略時は apps/web/index.en.html）")
    args = parser.parse_args(argv)

    html = args.source.read_text(encoding="utf-8")
    missing = [name for name in ["head", *RENDERERS] if f"<!-- home:{name}:start -->" not in html]
    if missing:
        print(f"[top-page-en] markers missing in {args.source}: {', '.join(missing)}", file=sys.stderr)
        return 1
    data = ja.load_data()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(apply_blocks(html, data, English()), encoding="utf-8")
    print(f"[top-page-en] wrote {args.target}: {data.total} manholes, {len(data.installed_prefectures)} prefectures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
