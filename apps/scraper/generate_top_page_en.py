#!/usr/bin/env python3
"""多言語版トップ（/en/・/zh-TW/・/zh-CN/・/ko/ の index.html）を日本語トップと同じ構成で生成する。

データの読み込みと写真・イベントの選び方は generate_top_page.py と共有し、
ここでは各言語の文言（top_page_i18n_text.py）と、/<lang>/ から見たリンク先だけを持つ。
雛形は英語版の apps/web/index.en.html を全言語で使い、固定の文言は localize_shell() で差し替える。

- /<lang>/ にあるページ（map.html・pokemon/・summary/）は `./` で、日本語にしか無いページ
  （都道府県・マンホール詳細・写真）は `../` で参照する。日本語ページへ飛ぶ導線には
  「日本語」と書き添える
- テーマのラベル・イベントの見出しは strings.<lang>.json を使う（dataset/tag_meta.json は日本語のみ）
- イベント名は日本語しか無いので lang="ja" を付けてそのまま出す

Usage:
  python3 apps/scraper/generate_top_page_en.py                              # apps/web/index.en.html を更新
  python3 apps/scraper/generate_top_page_en.py dist/en/index.html
  python3 apps/scraper/generate_top_page_en.py --lang zh-TW dist/zh-TW/index.html
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
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS
    from apps.scraper.top_page_i18n_text import FORM_PREFIX, NAME_KEYS, TEXT, day_label, join_places, month_label
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_top_page as ja
    from photo_caption import JST, format_photo_date
    from prefectures import PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS
    from top_page_i18n_text import FORM_PREFIX, NAME_KEYS, TEXT, day_label, join_places, month_label

ROOT = ja.ROOT
DEFAULT_TARGET = ROOT / "apps" / "web" / "index.en.html"
PREFECTURE_NAMES = ROOT / "apps" / "web" / "i18n" / "prefectures.json"
I18N_DIR = ROOT / "apps" / "web" / "i18n"
STRINGS_EN = I18N_DIR / "strings.en.json"
LANGS = list(TEXT)

BASE_URL = "https://data.pokefuta.com/"
ROOT_PATH = "../"  # /<lang>/ から日本語のみのページ・画像へ
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


class Locale:
    """1言語ぶんの表記（文言・都道府県名・ポケモン名・テーマ名）。"""

    def __init__(self, lang: str = "en", prefecture_names: Path = PREFECTURE_NAMES, strings: Path | None = None,
                 pokemon_metadata: Path | None = ja.DEFAULT_POKEMON_METADATA) -> None:
        self.lang = lang
        self.text = TEXT[lang]
        self.page_url = f"{BASE_URL}{lang}/"
        key = NAME_KEYS[lang]
        prefs = json.loads(prefecture_names.read_text(encoding="utf-8"))
        self.prefectures = {name: str(v.get(key) or name) for name, v in prefs.items()}
        strings = strings or I18N_DIR / f"strings.{lang}.json"
        self.strings = json.loads(strings.read_text(encoding="utf-8"))
        self.pokemon: dict[str, str] = {}
        self.pokemon_by_slug: dict[str, str] = {}
        if pokemon_metadata and pokemon_metadata.exists():
            for meta in json.loads(pokemon_metadata.read_text(encoding="utf-8")):
                names = meta.get("names") or {}
                if not names.get("ja") or not names.get(key):
                    continue
                form = meta.get("form") or ""
                local = FORM_PREFIX[lang].get(form, "") + names[key]
                self.pokemon.setdefault(ja.FORM_PREFIX.get(form, "") + names["ja"], local)
                if meta.get("slug"):
                    self.pokemon_by_slug[meta["slug"]] = local

    def t(self, key: str, **values: object) -> str:
        return str(self.text[key]).format(**values)

    def pref(self, name: str) -> str:
        return self.prefectures.get(name, name)

    def pokemon_name(self, name: str) -> str:
        return self.pokemon.get(name, name)

    def tag(self, slug: str) -> str:
        return self.strings.get(TAG_STRING_KEYS.get(slug, ""), slug)


class English(Locale):
    """英語版（既存の呼び出し・テストとの互換用）。"""

    def __init__(self, prefecture_names: Path = PREFECTURE_NAMES, strings: Path = STRINGS_EN,
                 pokemon_metadata: Path | None = ja.DEFAULT_POKEMON_METADATA) -> None:
        super().__init__("en", prefecture_names, strings, pokemon_metadata)


SHELL_REPLACEMENTS = [
    # (英語版の雛形にある文字列, 文言キー or 関数)。見つからなければ止める（雛形を直したら気付けるように）
    ('<html lang="en">', lambda loc: f'<html lang="{loc.t("html_lang")}">'),
    ("Poké Lids Directory — Every Pokémon Manhole in Japan", lambda loc: escape(loc.t("page_title"))),
    ('content="Poké Lids,Pokefuta,Pokémon manhole,Japan,travel,map,prefecture"', lambda loc: f'content="{escape(loc.t("keywords"))}"'),
    ('content="en_US"', lambda loc: f'content="{loc.t("og_locale")}"'),
    ('<meta property="og:url" content="https://data.pokefuta.com/en/">', lambda loc: f'<meta property="og:url" content="{loc.page_url}">'),
    ('<link rel="canonical" href="https://data.pokefuta.com/en/">', lambda loc: f'<link rel="canonical" href="{loc.page_url}">'),
    ('<span class="brand-name">Pokéfuta Directory</span>', lambda loc: f'<span class="brand-name">{escape(loc.t("site_name"))}</span>'),
    (">Search by purpose</h2>", lambda loc: f'>{escape(loc.t("purpose_title"))}</h2>'),
    ('<h3 class="home-h3">By theme</h3>', lambda loc: f'<h3 class="home-h3">{escape(loc.t("purpose_theme"))}</h3>'),
    (">Explore on the map</a>", lambda loc: f'>{escape(loc.t("purpose_theme_more"))}</a>'),
    ('<h3 class="home-h3">Most common Pokémon</h3>', lambda loc: f'<h3 class="home-h3">{escape(loc.t("purpose_pokemon"))}</h3>'),
]


def localize_shell(html: str, loc: Locale) -> str:
    """英語版の雛形の固定部分（lang・title・canonical・見出しなど）をその言語に差し替える。"""
    if loc.lang == "en":
        return html
    for old, new in SHELL_REPLACEMENTS:
        if old not in html:
            raise ValueError(f"index.en.html に {old!r} が無い（localize_shell を直す）")
        html = html.replace(old, new(loc))
    return html


# ── 部品 ──────────────────────────────────────────────────────────────────


def _names(photo: ja.Photo, en: Locale) -> str:
    return en.t("sep").join(en.pokemon_name(p) for p in photo.pokemons[:2])


def _alt(photo: ja.Photo, en: Locale) -> str:
    names = _names(photo, en)
    where = en.pref(photo.prefecture)
    return en.t("alt_photo", where=where, names=names) if names else en.t("alt_photo_noname", where=where)


def _img(photo: ja.Photo, en: English, *, eager: bool = False, priority: bool = False) -> str:
    loading = 'loading="eager"' if eager else 'loading="lazy"'
    fetch = ' fetchpriority="high"' if priority else ""
    return (
        f'<img src="{ROOT_PATH}{escape(photo.src)}" alt="{escape(_alt(photo, en))}" '
        f'width="{ja.PHOTO_SIZE}" height="{ja.PHOTO_SIZE}" {loading} decoding="async"{fetch}>'
    )


def _photo_href(photo: ja.Photo) -> str:
    return f"{ROOT_PATH}{photo.href}"


def _has_pref_pages(loc: Locale) -> bool:
    """この言語に訳した県ページ（/<lang>/prefectures/）があるか。無ければ日本語版へ送る。"""
    return loc.lang in PREFECTURE_PAGE_LANGS


def _pref_href(pref: str, loc: Locale | None = None) -> str:
    """loc を渡すと、訳した県ページがある言語ではその言語の県ページを返す。省略時は日本語版。"""
    base = "" if loc and _has_pref_pages(loc) else ROOT_PATH
    return f"{base}prefectures/{PREFECTURE_SLUGS[pref]}/"


def _pref_hreflang(loc: Locale) -> str:
    """日本語版の県ページへ送るリンクに付ける属性。"""
    return "" if _has_pref_pages(loc) else ' hreflang="ja"'


def description(data: ja.TopData, en: Locale | None = None) -> str:
    en = en or English(pokemon_metadata=None)
    return en.t("description", total=f"{data.total:,}", prefs=len(data.installed_prefectures))


def short_description(data: ja.TopData, en: Locale | None = None) -> str:
    en = en or English(pokemon_metadata=None)
    return en.t("short_description", total=f"{data.total:,}", prefs=len(data.installed_prefectures))


def json_ld(data: ja.TopData, en: Locale) -> dict:
    page_url = en.page_url
    counts = data.pref_counts
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}#website",
                "url": BASE_URL,
                "name": "ポケふた図鑑",
                "alternateName": en.t("site_name"),
            },
            {
                "@type": "CollectionPage",
                "@id": f"{page_url}#webpage",
                "url": page_url,
                "name": en.t("page_title"),
                "description": description(data, en),
                "inLanguage": en.t("html_lang"),
                "isPartOf": {"@id": f"{BASE_URL}#website"},
                "breadcrumb": {"@id": f"{page_url}#breadcrumb"},
                "mainEntity": {"@id": f"{page_url}#prefectures"},
                "hasPart": [
                    {"@type": "WebPage", "name": en.t("ld_map"), "url": f"{page_url}map.html"},
                    {"@type": "CollectionPage", "name": en.t("ld_pokemon"), "url": f"{page_url}pokemon/"},
                    {"@type": "CollectionPage", "name": en.t("ld_stats"), "url": f"{page_url}summary/"},
                ],
            },
            {
                "@type": "ItemList",
                "@id": f"{page_url}#prefectures",
                "name": en.t("ld_prefs"),
                "numberOfItems": len(data.installed_prefectures),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": en.t("ld_pref_item", pref=en.pref(pref), count=counts[pref]),
                        "url": f"{page_url if _has_pref_pages(en) else BASE_URL}prefectures/{PREFECTURE_SLUGS[pref]}/",
                    }
                    for i, pref in enumerate(data.installed_prefectures, start=1)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{page_url}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": en.t("site_name"), "item": page_url},
                ],
            },
        ],
    }


# ── ブロック ──────────────────────────────────────────────────────────────


def render_head(data: ja.TopData, en: Locale, indent: str) -> str:
    desc = escape(description(data, en), quote=True)
    short = escape(short_description(data, en), quote=True)
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


def render_hero(data: ja.TopData, en: Locale) -> str:
    photos = ja.select_hero_photos(data.photos)
    popular = [en.pokemon_by_slug.get(e.slug, e.name) for e in data.popular_pokemon[:3]]
    posts = data.stats.get("public_posts") if isinstance(data.stats.get("public_posts"), int) else None
    stats = [
        (f"{data.total:,}", en.t("stat_lids")),
        (str(len(data.installed_prefectures)), en.t("stat_prefs")),
        (f"{len(data.pokemon_counts):,}", en.t("stat_pokemon")),
    ]
    if posts:
        stats.append((f"{posts:,}", en.t("stat_photos")))
    stats_html = "".join(
        f'<div class="home-stat"><dt>{escape(label)}</dt><dd>{escape(num)}</dd></div>' for num, label in stats
    )
    quick = [
        ("map", "map", "map.html", en.t("quick_map"), "home-quick__link--primary home-quick__link--map"),
        ("prefecture", "home_pref_section", "#home-pref", en.t("quick_pref"), ""),
        ("pokemon", "pokemon_index", "pokemon/", en.t("quick_pokemon"), ""),
        # PC だけ。テーマを横いっぱいに出す
        ("theme", "map_theme_directory", "map.html?view=theme", en.t("quick_theme"), "home-quick__link--desktop home-quick__link--wide"),
    ]
    quick_html = "".join(
        f'<a class="home-quick__link {cls}" href="{href}" '
        f'onclick="{ja._track("click_search_way", surface="top_hero_quick", way=way, destination=dest)}">{escape(label)}</a>'
        for way, dest, href, label, cls in quick
    )
    lead = en.t("lead", total=f"{data.total:,}", prefs=len(data.installed_prefectures)) + (
        en.t("lead_popular", names=escape(en.t("sep").join(popular)), npoke=f"{len(data.pokemon_counts):,}")
        if popular else en.t("lead_end")
    )
    if photos:
        items = "".join(
            f'<li class="home-mosaic__item"><a href="{_photo_href(p)}" '
            f'onclick="{ja._track("click_hero_photo", surface="top_hero_photo", manhole=p.manhole_id, position=i)}">'
            f"{ja.mobile_only(_img(p, en, eager=True, priority=(i == 0)))}"
            f'<span class="home-mosaic__cap"><b>{escape(_names(p, en) or en.t("lid"))}</b>{escape(en.pref(p.prefecture))}</span>'
            "</a></li>"
            for i, p in enumerate(photos)
        )
        mosaic = (
            '<figure class="home-mosaic">'
            f'<ul class="home-mosaic__grid">{items}</ul>'
            f'<figcaption class="home-mosaic__note">{escape(en.t("mosaic_note", date=day_label(en.lang, data.today.month, data.today.day)))}</figcaption>'
            "</figure>"
        )
        cls = "home-hero"
    else:
        mosaic = ""
        cls = "home-hero home-hero--no-photos"
    map_html = ja.map_block(
        data,
        pins=ja.map_pins(
            data,
            label=en.pref,
            title=lambda pref, count: en.t("map_pin_title", pref=en.pref(pref), count=count),
        ),
        aria=en.t("map_aria"),
        cta=en.t("map_cta"),
        cta_href="map.html",
    )
    return (
        f'<section class="{cls}" id="home-hero" aria-labelledby="home-h1">'
        '<div class="home-hero__copy">'
        f'<p class="home-eyebrow">{escape(en.t("eyebrow"))}</p>'
        f'<h1 class="home-h1" id="home-h1">{escape(en.t("h1", total=f"{data.total:,}"))}</h1>'
        f'<p class="home-lead">{lead}</p>'
        f'<nav class="home-quick" aria-label="{escape(en.t("quick_aria"))}">{quick_html}</nav>'
        f'<dl class="home-stats">{stats_html}</dl>'
        "</div>"
        f"{map_html}"
        f"{mosaic}"
        "</section>"
    )


def render_ways(data: ja.TopData, en: Locale) -> str:
    counts = data.pref_counts
    top_prefs = sorted(data.installed_prefectures, key=lambda p: (-counts[p], PREFECTURE_ORDER.index(p)))[:3]
    theme_slugs = [s for s in data.tag_meta.top_chip_slugs(data.tag_counts) if s in TAG_STRING_KEYS][:3]

    def sub(links: list[tuple[str, str]], way: str) -> str:
        return "".join(
            f'<li><a href="{href}" onclick="{ja._track("click_search_way", surface="top_search_ways", way=way)}">{label}</a></li>'
            for href, label in links
        )

    cards = [
        ("map", "map.html", "icon-map.svg", en.t("way_map_title"), en.t("way_map_text"),
         [("map.html", escape(en.t("way_map_open"))), ("map.html?view=theme", escape(en.t("way_map_theme")))]),
        ("prefecture", "#home-pref", "icon-pin.svg", en.t("way_pref_title"),
         en.t("way_pref_text", prefs=len(data.installed_prefectures)),
         [(_pref_href(p, en), f"{escape(en.pref(p))} {counts[p]}") for p in top_prefs]),
        ("pokemon", "pokemon/", "pokefuta-marker.svg", en.t("way_pokemon_title"),
         en.t("way_pokemon_text", npoke=f"{len(data.pokemon_counts):,}"),
         [(e.href, f"{escape(en.pokemon_by_slug.get(e.slug, e.name))} {len(e.manhole_ids)}")
          for e in data.popular_pokemon[:3]]),
        ("theme", "map.html?view=theme", "icon-tag.svg", en.t("way_theme_title"), en.t("way_theme_text"),
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
        f'<h2 class="home-h2" id="home-ways-title">{escape(en.t("ways_title"))}</h2>'
        f'<ul class="home-ways">{cards_html}</ul>'
        "</section>"
    )


def render_newrelease(data: ja.TopData, en: Locale) -> str:
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
        names = en.t("sep").join(en.pokemon_name(p) for p in ja.pokemons_of(record)) or en.t("lid")
        cards.append(
            f'<li><a class="home-newrel__card" href="{ROOT_PATH}manholes/{quote(mid, safe="")}/" '
            f'onclick="{ja._track("click_newrelease", surface="top_newrelease", manhole=mid, position=i)}">'
            f'<b>{escape(names)}</b><span>{escape(en.pref(str(record.get("prefecture", ""))))}</span></a></li>'
        )
    return (
        '<section class="home-section" id="home-newrelease" aria-labelledby="home-newrelease-title">'
        f'<h2 class="home-h2" id="home-newrelease-title">{escape(en.t("new_title"))} '
        f'<small>{escape(en.t("new_small", n=len(fresh), days=ja.NEW_RELEASE_DAYS))}</small></h2>'
        f'<ul class="home-newrel">{"".join(cards)}</ul>'
        "</section>"
    )


def render_photos(data: ja.TopData, en: Locale) -> str:
    photos = ja.select_gallery_photos(data.photos, ja.select_hero_photos(data.photos))
    upload = (
        f'<a class="home-cta" href="{ja.UPLOAD_URL}" '
        f'onclick="{ja._track("click_photo_post_cta", surface="top_photo_gallery")}">{escape(en.t("photos_cta"))}</a>'
    )
    if not photos:
        return (
            '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
            f'<h2 class="home-h2" id="home-photos-title">{escape(en.t("photos_title"))}</h2>'
            f'<p class="home-text">{escape(en.t("photos_empty"))}</p>{upload}'
            "</section>"
        )
    items = "".join(
        f'<li class="home-gallery__item"><a href="{_photo_href(p)}" '
        f'onclick="{ja._track("click_top_photo", surface="top_photo_gallery", manhole=p.manhole_id, position=i)}">'
        f"{_img(p, en)}"
        f'<span class="home-gallery__cap"><b>{escape(_names(p, en) or en.t("lid"))}</b>'
        f'<span>{escape(en.pref(p.prefecture))}</span>'
        f'<time datetime="{escape(ja._jst_iso(p.created_at))}">{escape(format_photo_date(p.created_at, en.lang))}</time></span>'
        "</a></li>"
        for i, p in enumerate(photos)
    )
    with_photos = data.stats.get("manholes_with_photos")
    coverage = (
        en.t("photos_coverage", n=f"{with_photos:,}")
        if isinstance(with_photos, int) and with_photos else ""
    )
    return (
        '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
        f'<h2 class="home-h2" id="home-photos-title">{escape(en.t("photos_title"))}</h2>'
        f'<p class="home-text">{escape(en.t("photos_lead") + coverage)}</p>'
        f'<ul class="home-gallery">{items}</ul>'
        f"{upload}"
        "</section>"
    )


def _event_card(event: dict, data: ja.TopData, en: Locale) -> str:
    pref = event["prefecture"]
    ongoing = event["start"] <= data.today
    status = en.strings.get("EVENTS_ONGOING", "Ongoing") if ongoing else en.strings.get("EVENTS_UPCOMING", "Starting soon")
    period = f'{event["start"]:%Y/%m/%d} – {event["end"]:%Y/%m/%d}'
    return (
        f'<li class="home-event" data-end="{event["end"].isoformat()}">'
        # イベントの情報は日本語版の県ページにしか無いので、訳した県ページがあっても日本語版へ送る
        f'<a href="{_pref_href(pref)}" hreflang="ja" '
        f'onclick="{ja._track("click_event_notice", surface="top_event_notice", prefecture=pref, destination="prefecture_page")}">'
        f'<span class="home-event__badge{"" if ongoing else " is-upcoming"}">{escape(status)}</span>'
        f'<span class="home-event__copy"><b lang="ja">{escape(event["title"])}</b>'
        f'<small>{escape(en.pref(pref))} · {period}</small></span>'
        "</a></li>"
    )


def render_events(data: ja.TopData, en: Locale) -> str:
    if not data.events:
        return ""
    visible = data.events[:ja.EVENT_VISIBLE_LIMIT]
    rest = data.events[ja.EVENT_VISIBLE_LIMIT:]
    more = ""
    if rest:
        more = (
            '<details class="home-events__more">'
            f'<summary onclick="{ja._track("click_event_show_all", surface="top_event_notice", count=len(data.events))}">'
            f'{escape(en.t("events_show_all", n=len(data.events)))}</summary>'
            f'<ul class="home-events">{"".join(_event_card(e, data, en) for e in rest)}</ul>'
            "</details>"
        )
    return (
        '<section class="home-section" id="home-events" aria-labelledby="home-events-title">'
        f'<h2 class="home-h2" id="home-events-title">{escape(en.strings.get("EVENTS_TITLE", "Ongoing Events & Stamp Rallies"))}</h2>'
        f'<p class="home-text">{escape(en.t("events_note"))}</p>'
        f'<ul class="home-events">{"".join(_event_card(e, data, en) for e in visible)}</ul>'
        f"{more}"
        "</section>"
    )


def render_pref(data: ja.TopData, en: Locale) -> str:
    counts = data.pref_counts
    regions = []
    for name, prefs in ja.REGIONS:
        installed = [p for p in prefs if counts.get(p)]
        if not installed:
            continue
        links = "".join(
            f'<li><a href="{_pref_href(p, en)}"{_pref_hreflang(en)} '
            f'onclick="{ja._track("click_pref_link", surface="top_prefecture_list", prefecture=p)}">'
            f'<span class="home-pref__name">{escape(en.pref(p))}</span><span class="home-pref__count">{counts[p]}</span></a></li>'
            for p in installed
        )
        regions.append(
            '<div class="home-region">'
            f'<h3 class="home-region__title">{escape(en.text["regions"][name])} <small>{sum(counts[p] for p in installed)}</small></h3>'
            f'<ul class="home-pref">{links}</ul>'
            "</div>"
        )
    empty = data.empty_prefectures
    note = ""
    if empty:
        empty_links = [f'<a href="{_pref_href(p, en)}"{_pref_hreflang(en)}>{escape(en.pref(p))}</a>' for p in empty]
        month = month_label(en.lang, data.today.year, data.today.month)
        note = f'<p class="home-pref-note">{en.t("pref_none", month=month, places=join_places(en.lang, empty_links))}</p>'
    return (
        '<section class="home-section" id="home-pref" aria-labelledby="home-pref-title">'
        f'<h2 class="home-h2" id="home-pref-title">{escape(en.strings.get("SEC4_TITLE", "Search by Prefecture"))}</h2>'
        f'<p class="home-text">{escape(en.t("pref_text", prefs=len(data.installed_prefectures)), quote=False)}</p>'
        f'<div class="home-regions">{"".join(regions)}</div>'
        f"{note}"
        f'<a class="home-more" href="{"" if _has_pref_pages(en) else ROOT_PATH}prefectures/"{_pref_hreflang(en)} '
        f'onclick="{ja._track("click_pref_link", surface="top_prefecture_list", prefecture="all")}">'
        f'{escape(en.t("pref_more"))}</a>'
        "</section>"
    )


def render_themes(data: ja.TopData, en: Locale) -> str:
    slugs = [s for s in data.tag_meta.top_chip_slugs(data.tag_counts) if s in TAG_STRING_KEYS]
    return "".join(
        f'<a class="hub-chip" href="map.html?tag={quote(s)}" '
        f"onclick=\"trackEvent('click_hub_tag',{{surface:'top_hub_tag',tag:'{s}',destination:'map_tag_filter'}})\">"
        f'{escape(en.tag(s))} <span class="chip-count">{data.tag_counts.get(s, 0)}</span></a>'
        for s in slugs
    )


def render_pokemon(data: ja.TopData, en: Locale) -> str:
    cards = []
    used: set[str] = set()
    for entry in data.popular_pokemon:
        name = en.pokemon_by_slug.get(entry.slug, entry.name)
        photo = ja.pick_pokemon_photo(entry, data.photos, used)
        media = (
            f'<img src="{ROOT_PATH}{escape(photo.src)}" alt="{escape(en.t("alt_poke", name=name, pref=en.pref(photo.prefecture)))}" '
            f'width="{ja.PHOTO_SIZE}" height="{ja.PHOTO_SIZE}" loading="lazy" decoding="async">'
            if photo else '<span class="home-poke__placeholder" aria-hidden="true"></span>'
        )
        cards.append(
            f'<li class="home-poke"><a href="{entry.href}" '
            f'onclick="{ja._track("click_hub_pokemon", surface="top_hub_pokemon", pokemon=entry.name)}">'
            f'{media}<span class="home-poke__name">{escape(name)}</span>'
            f'<span class="home-poke__count">{escape(en.t("poke_count", n=len(entry.manhole_ids)))}</span></a></li>'
        )
    cards.append(
        '<li class="home-poke home-poke--all"><a href="pokemon/" '
        f'onclick="{ja._track("click_hub_pokemon_all", surface="top_hub_pokemon")}">'
        f'<span class="home-poke__name">{escape(en.t("poke_all"))}</span><span class="home-poke__count">{len(data.pokemon_counts):,}</span></a></li>'
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


def apply_blocks(html: str, data: ja.TopData, en: Locale) -> str:
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
                        help="雛形（省略時は apps/web/index.en.html。全言語で同じ雛形を使う）")
    parser.add_argument("--lang", choices=LANGS, default="en")
    args = parser.parse_args(argv)

    loc = Locale(args.lang)
    html = localize_shell(args.source.read_text(encoding="utf-8"), loc)
    missing = [name for name in ["head", *RENDERERS] if f"<!-- home:{name}:start -->" not in html]
    if missing:
        print(f"[top-page-en] markers missing in {args.source}: {', '.join(missing)}", file=sys.stderr)
        return 1
    data = ja.load_data()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(apply_blocks(html, data, loc), encoding="utf-8")
    print(f"[top-page-{args.lang}] wrote {args.target}: {data.total} manholes, {len(data.installed_prefectures)} prefectures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
