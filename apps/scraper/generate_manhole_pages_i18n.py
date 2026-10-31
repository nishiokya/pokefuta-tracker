#!/usr/bin/env python3
"""多言語版の詳細ページ（/<lang>/manholes/<id>/）を作る。

日本語版（generate_manhole_pages.py）のデータ部分だけを訳して出す。
写真・ポケモン・設置場所・Google マップの行き方・近くのポケふた・同じポケモン・同じ県。
称号・ポケふた旅のエリア・近くのデザインマンホール・共有ボタン・写真館への投稿導線は
日本語だけにあり、ここでは日本語版へのリンクにとどめる（県ページの訳と同じ考え方）。

- 施設名・住所・アクセスは訳さず、日本語のまま lang="ja" で出す
  （現地の看板や Google マップ、タクシーで見せるときにそのまま使えるように）
- 自治体名は dataset/municipality_names.json。訳の無い自治体は日本語名のまま出し、警告する
- page_path・イベントは日本語版と同じ。言語は analytics.js が URL から付ける

Usage:
  python3 apps/scraper/generate_manhole_pages_i18n.py --lang en
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from html import escape
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper import generate_manhole_pages as ja
    from apps.scraper import generate_prefecture_pages_i18n as pref_i18n
    from apps.scraper.display_names import compose_display_name, municipality_label
    from apps.scraper.generate_pokemon_pages import load_pokemon_metadata
    from apps.scraper.generate_top_page_en import Locale
    from apps.scraper.photo_caption import format_display_name, format_photo_date
    from apps.scraper.prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_manhole_pages as ja
    import generate_prefecture_pages_i18n as pref_i18n
    from display_names import compose_display_name, municipality_label
    from generate_pokemon_pages import load_pokemon_metadata
    from generate_top_page_en import Locale
    from photo_caption import format_display_name, format_photo_date
    from prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS

BASE_URL = ja.BASE_URL
ROOT = Path(__file__).resolve().parents[2]
LANGS = MANHOLE_PAGE_LANGS

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "og_locale": "en_US",
        "site_name": "Pokéfuta Directory",
        "title": "{pokemons} Poké Lid in {place}, {pref} | Pokéfuta Directory",
        "description": (
            "A Poké Lid (Pokémon manhole cover) featuring {pokemons} in {place}, {pref}, Japan: "
            "location map, directions, fan photos, and nearby Poké Lids."
        ),
        "h1": "{pokemons} Poké Lid in {place}",
        "breadcrumb_aria": "Breadcrumb",
        "breadcrumb_top": "Map of Japan",
        "back": "← Back to the map of Japan",
        "photo_alt": "Photo of the {h1}",
        "photo_by": "Photo by {name}",
        "no_photo": "No photo yet",
        "no_photo_sub": "Fan photos appear here once someone visits.",
        "preinstall": "Not installed yet",
        "preinstall_sub": "Installation is planned.",
        "badge_preinstall": "🚧 Coming soon",
        "badge_new": "NEW · installed {year}",
        "badge_pref": "{n} in {pref}",
        "badge_city": "{n} in {place}",
        "badge_same_pokemon": "{n} with the same Pokémon",
        "badge_nearby": "{n} within 30 km",
        "gallery_heading": "Fan photos",
        "directions_main": "Get directions in Google Maps",
        "directions_sub": "Plan your route to this Poké Lid",
        "location_heading": "Location",
        "location_pref": "Prefecture",
        "location_city": "Municipality",
        "location_place": "Place (Japanese)",
        "location_address": "Address (Japanese)",
        "location_access": "Access (Japanese)",
        "nearby_heading": "Poké Lids nearby",
        "distance_km": "{km} km",
        "pokemon_heading": "Pokémon on this lid",
        "pokemon_types": "Type: {types}",
        "pokemon_generation": "Generation {n}",
        "pokemon_same_link": "Other Poké Lids with this Pokémon →",
        "same_pokemon_heading": "The same Pokémon in other prefectures",
        "pref_heading": "Poké Lids in {pref}",
        "pref_lead": "{pref} has {n} Poké Lids.",
        "links_heading": "Links",
        "link_ja": "日本語のページ",
        "link_pref": "All Poké Lids in {pref}",
        "link_map": "Map of Japan",
        "link_official": "Official site (Japanese)",
        "ja_note": (
            "Badges, suggested routes, and nearby design manholes are on the Japanese page. "
            "Your browser's translate feature works on it."
        ),
        "footer": "Poké Lid information is based on the official Pokémon website",
        "pokemon_fallback": "Pokémon",
        "sep": ", ",
        "types_sep": ", ",
    },
    # 用語は繁體中文版の県ページ・トップに合わせる：寶可夢人孔蓋・寶可夢人孔蓋圖鑑・「個」
    "zh-TW": {
        "html_lang": "zh-TW",
        "og_locale": "zh_TW",
        "site_name": "寶可夢人孔蓋圖鑑",
        "title": "{pref}{place}的寶可夢人孔蓋｜{pokemons}｜寶可夢人孔蓋圖鑑",
        "description": (
            "日本{pref}{place}的寶可夢人孔蓋（Pokéfuta），圖案是{pokemons}。"
            "提供設置地點地圖、交通指引、粉絲照片，以及附近的寶可夢人孔蓋。"
        ),
        "h1": "{place}的寶可夢人孔蓋（{pokemons}）",
        "breadcrumb_aria": "導覽路徑",
        "breadcrumb_top": "日本全國地圖",
        "back": "← 回到日本全國地圖",
        "photo_alt": "{h1}的照片",
        "photo_by": "攝影：{name}",
        "no_photo": "尚無照片",
        "no_photo_sub": "有人造訪後，粉絲照片會顯示在這裡。",
        "preinstall": "尚未設置",
        "preinstall_sub": "預定設置。",
        "badge_preinstall": "🚧 即將設置",
        "badge_new": "NEW・{year}年設置",
        "badge_pref": "{pref}共{n}個",
        "badge_city": "{place}共{n}個",
        "badge_same_pokemon": "相同寶可夢{n}個",
        "badge_nearby": "30公里內{n}個",
        "gallery_heading": "粉絲照片",
        "directions_main": "在 Google 地圖查看交通方式",
        "directions_sub": "確認前往這個寶可夢人孔蓋的路線",
        "location_heading": "設置地點",
        "location_pref": "都道府縣",
        "location_city": "市町村",
        "location_place": "地點（日文）",
        "location_address": "地址（日文）",
        "location_access": "交通（日文）",
        "nearby_heading": "附近的寶可夢人孔蓋",
        "distance_km": "{km}公里",
        "pokemon_heading": "人孔蓋上的寶可夢",
        "pokemon_types": "屬性：{types}",
        "pokemon_generation": "第{n}世代",
        "pokemon_same_link": "查看相同寶可夢的人孔蓋 →",
        "same_pokemon_heading": "其他都道府縣的相同寶可夢",
        "pref_heading": "{pref}的寶可夢人孔蓋",
        "pref_lead": "{pref}共有{n}個寶可夢人孔蓋。",
        "links_heading": "連結",
        "link_ja": "日本語のページ",
        "link_pref": "{pref}的寶可夢人孔蓋一覽",
        "link_map": "日本全國地圖",
        "link_official": "官方網站（日文）",
        "ja_note": "稱號、建議路線與附近的設計人孔蓋在日文頁面上，可使用瀏覽器的翻譯功能閱讀。",
        "footer": "寶可夢人孔蓋資訊參考自寶可夢官方網站",
        "pokemon_fallback": "寶可夢",
        "sep": "、",
        "types_sep": "、",
    },
}

# ポケモンのタイプ。pokemon_metadata.json は日本語と英語だけを持つので、英語名から引く
TYPE_NAMES: dict[str, dict[str, str]] = {
    "zh-TW": {
        "Normal": "一般", "Fire": "火", "Water": "水", "Grass": "草", "Electric": "電", "Ice": "冰",
        "Fighting": "格鬥", "Poison": "毒", "Ground": "地面", "Flying": "飛行", "Psychic": "超能力",
        "Bug": "蟲", "Rock": "岩石", "Ghost": "幽靈", "Dragon": "龍", "Dark": "惡", "Steel": "鋼",
        "Fairy": "妖精",
    },
}

EXTRA_CSS = """
    /* 見出しが日本語版より長い（Municipality など）。値と重ならないよう見出しの列を広げる（「(Japanese)」は折り返す） */
    .location-section dl {
      grid-template-columns: minmax(5em, 8.5em) 1fr;
      column-gap: 12px;
    }
    .location-section dd {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .hero-ja-name {
      margin-top: 4px;
      font-size: 13px;
      color: #6b5b45;
    }
    .location-section dd small {
      margin-left: 6px;
      color: #6b5b45;
    }
    .related-card-text {
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      min-width: 0;
    }
    .related-card-text a {
      white-space: normal;
      overflow-wrap: break-word;
    }
    .related-card-text small {
      font-size: 12px;
      color: #6b5b45;
      overflow-wrap: anywhere;
    }
    .ja-note {
      margin-top: 12px;
      font-size: 13px;
      color: #6b5b45;
    }
"""


class DetailPage(pref_i18n.Page):
    """1言語ぶんの表記。自治体名・ポケモン名・県名は県ページの訳と同じものを使う。"""

    def t(self, key: str, **values: object) -> str:
        return TEXT[self.lang][key].format(**values)

    def pokemons(self, record: dict) -> str:
        names = [self.pokemon_name(p) for p in ja.filter_pokemons(record.get("pokemons", []))]
        return self.t("sep").join(names) or self.t("pokemon_fallback")

    def type_name(self, type_data: dict) -> str:
        en = str(type_data.get("en", ""))
        return TYPE_NAMES.get(self.lang, {}).get(en, en) if self.lang != "en" else en

    def detail_path(self, manhole_id: str) -> str:
        return f"{self.prefix()}manholes/{quote(manhole_id, safe='')}/"


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _onclick(event: str, params: dict) -> str:
    """onclick の trackEvent。params は必ず surface を持つ（GA4 で発生箇所を分けるため）。"""
    assert "surface" in params, event
    return f' onclick="trackEvent(\'{event}\', {ja._attr_json(params)})"'


def _ja_name(record: dict) -> str:
    return compose_display_name(record) or municipality_label(record)


def _related_card(page: DetailPage, other: dict, id_to_image_url: dict[str, str], event: str, params: dict,
                  extra_html: str = "") -> str:
    oid = str(other.get("id", "")).strip()
    # 日本語版と同じく 180px の WebP（ja._render_related_card）
    thumb_url = ja.small_image_url(id_to_image_url.get(oid, ""), 180)
    thumb_html = (
        f'<div class="related-card-thumb">'
        f'<img src="{_attr(thumb_url)}" alt="" loading="lazy" decoding="async" width="60" height="60"'
        f' onerror="this.closest(\'.related-card-thumb\').remove()">'
        f"</div>"
    ) if thumb_url else ""
    return (
        f"<li class='related-card'>{thumb_html}"
        f"<div class='related-card-body'>"
        f'{ja._icon("icon-detail-location", "icon-sm")}'
        # 訳と日本語名は縦に積む（横並びだとスマホ幅で日本語名がリンクの幅を食いつぶす）
        f"<span class='related-card-text'>"
        f"<a href='{_attr(page.detail_path(oid))}'{_onclick(event, {**params, 'to_manhole_id': oid})}>"
        f"{escape(page.pokemons(other))} · {escape(page.municipality(other))}</a>"
        f"<small lang='ja'>{escape(_ja_name(other))}</small></span>"
        f"</div>{extra_html}</li>"
    )


def _related_section(page: DetailPage, *, section_id: str, css: str, heading: str, lead: str, items: str) -> str:
    id_attr = f" id='{section_id}'" if section_id else ""
    lead_html = f"<p>{escape(lead)}</p>" if lead else ""
    return (
        f"<section{id_attr} class='{css} section-card'><h2>{heading}</h2>{lead_html}"
        f"<ul class='related-list related-list--cards'>{items}</ul></section>"
    )


def build_page(
    page: DetailPage,
    manhole: dict,
    photo: Optional[dict],
    pokemon_meta: dict[str, dict],
    related: dict,
    id_to_image_url: dict[str, str],
    ja_to_slug: dict[str, str],
    ogp_dir: Optional[Path] = None,
) -> str:
    manhole_id = str(manhole.get("id", "")).strip()
    prefecture = manhole.get("prefecture", "")
    pref = page.pref(prefecture)
    place = page.municipality(manhole)
    pokemons = ja.filter_pokemons(manhole.get("pokemons", []))
    pokemon_text = page.pokemons(manhole)
    lat, lng = manhole.get("lat"), manhole.get("lng")
    is_preinstall = manhole.get("installed") is False

    title = page.t("title", pokemons=pokemon_text, place=place, pref=pref)
    description = page.t("description", pokemons=pokemon_text, place=place, pref=pref)
    h1 = page.t("h1", pokemons=pokemon_text, place=place)
    path = f"manholes/{quote(manhole_id, safe='')}/"
    canonical = f"{BASE_URL}{page.lang}/{path}"
    ja_url = f"/{path}"
    slug = PREFECTURE_SLUGS.get(prefecture, "")
    # 県ページを訳していない言語では日本語版の県ページへ
    pref_url = (
        (f"{page.prefix()}prefectures/{slug}/" if page.lang in PREFECTURE_PAGE_LANGS else f"/prefectures/{slug}/")
        if slug else ""
    )
    base = {"manhole_id": manhole_id, "prefecture": prefecture, "city": manhole.get("city", "")}

    # ---- hero
    photo_url = (photo.get("url", "") or photo.get("original_url", "")) if photo else ""
    if is_preinstall:
        note = manhole.get("installation_note") or ""
        sub = f'<span class="placeholder-sub" lang="ja">{escape(note)}</span>' if note else (
            f'<span class="placeholder-sub">{escape(page.t("preinstall_sub"))}</span>'
        )
        hero_photo_html = (
            "<div class='hero-photo-placeholder hero-photo-preinstall'>"
            "<span class='placeholder-camera' aria-hidden='true'>🚧</span>"
            f"<span class='placeholder-title'>{escape(page.t('preinstall'))}</span>{sub}</div>"
        )
    elif photo_url:
        credit_parts = []
        poster = format_display_name(photo.get("display_name"))
        if poster:
            # 投稿者の表示名は本人が付けたもので訳さない（ブラウザ翻訳にもかけない）
            name_html = f'<bdi translate="no">{escape(poster)}</bdi>'
            credit_parts.append(f'📷 {escape(page.t("photo_by", name="{name}")).format(name=name_html)}')
        shot = format_photo_date(photo.get("shot_at") or photo.get("created_at"), page.lang, with_year=True)
        if shot:
            credit_parts.append(escape(shot))
        credit_html = (
            "<div class='photo-credit'>" + "".join(f"<span>{p}</span>" for p in credit_parts) + "</div>"
            if credit_parts else ""
        )
        hero_photo_html = (
            "<div class='hero-photo'>"
            f'<img src="{_attr(photo_url)}" alt="{_attr(page.t("photo_alt", h1=h1))}"'
            ' loading="eager" fetchpriority="high">'
            f"{credit_html}</div>"
        )
    else:
        hero_photo_html = (
            "<div class='hero-photo-placeholder'>"
            "<span class='placeholder-camera' aria-hidden='true'>📷</span>"
            f"<span class='placeholder-title'>{escape(page.t('no_photo'))}</span>"
            f"<span class='placeholder-sub'>{escape(page.t('no_photo_sub'))}</span></div>"
        )

    region_parts = [
        f'<a href="{_attr(pref_url)}">{escape(pref)}</a>' if pref_url else f"<span>{escape(pref)}</span>",
        f"<span>{escape(place)}</span>",
    ]
    pokemon_tags = []
    for name in pokemons:
        poke_slug = ja_to_slug.get(name) or ja_to_slug.get(ja._normalize_katakana(name), "")
        local = escape(page.pokemon_name(name))
        pokemon_tags.append(
            f"<a class='hero-tag' href='{page.prefix()}pokemon/{quote(poke_slug)}/'>{local}</a>"
            if poke_slug else f"<span class='hero-tag'>{local}</span>"
        )
    badges = []
    if is_preinstall:
        badges.append(f"<span class='hero-badge hero-badge-pre'>{escape(page.t('badge_preinstall'))}</span>")
    try:
        added_year = datetime.date.fromisoformat((manhole.get("added_at") or "")[:10]).year
        if added_year >= datetime.date.today().year:
            badges.append(f"<span class='hero-badge hero-badge-new'>{escape(page.t('badge_new', year=added_year))}</span>")
    except (ValueError, TypeError):
        pass
    if related["pref_total"] > 0 and prefecture:
        badges.append(f"<span class='hero-badge'>{escape(page.t('badge_pref', n=related['pref_total'], pref=pref))}</span>")
    if related["city_total"] >= 2:
        badges.append(f"<span class='hero-badge'>{escape(page.t('badge_city', n=related['city_total'], place=place))}</span>")
    if related["same_pokemon_total"] > 0:
        badges.append(f"<span class='hero-badge'>{escape(page.t('badge_same_pokemon', n=related['same_pokemon_total']))}</span>")
    if related["nearby_count"] > 0:
        badges.append(f"<span class='hero-badge'>{escape(page.t('badge_nearby', n=related['nearby_count']))}</span>")

    hero_html = f"""
<div class="hero-card">
  {hero_photo_html}
  <div class="hero-body">
    <nav class="hero-region" aria-label="{_attr(page.t("breadcrumb_aria"))}">{"".join(region_parts)}</nav>
    <h1 class="hero-title">{escape(h1)}</h1>
    <p class="hero-ja-name" lang="ja">{escape(prefecture)}{escape(_ja_name(manhole))}</p>
    {f"<div class='hero-pokemon-tags'>{''.join(pokemon_tags)}</div>" if pokemon_tags else ""}
    {f"<div class='hero-stats'>{''.join(badges)}</div>" if badges else ""}
  </div>
</div>
"""

    # ---- gallery
    gallery_html = ""
    gallery_items = (photo.get("gallery_local") or []) if photo else []
    if gallery_items:
        thumbs = []
        for g in gallery_items:
            name = format_display_name(g.get("display_name"))
            date = format_photo_date(g.get("shot_at") or g.get("created_at"), page.lang)
            label = " · ".join(
                part for part in (f'<bdi translate="no">{escape(name)}</bdi>' if name else "", escape(date)) if part
            )
            credit = f"<span class='gallery-credit'>📷 {label}</span>" if label else ""
            thumbs.append(
                "<figure class='gallery-item'>"
                f'<img src="{_attr(g["url"])}" alt="{_attr(page.t("photo_alt", h1=h1))}" loading="lazy">'
                f"{credit}</figure>"
            )
        gallery_html = (
            f"<section class='gallery-section section-card'><h2>{escape(page.t('gallery_heading'))}</h2>"
            f"<div class='gallery-grid'>{''.join(thumbs)}</div></section>"
        )

    # ---- directions
    visit_html = ""
    if lat is not None and lng is not None:
        gmaps_params = {**base, "surface": "hero"}
        visit_html = (
            f'<a href="https://www.google.com/maps?q={lat},{lng}" class="visit-cta" target="_blank"'
            f' rel="noopener noreferrer"{_onclick("click_google_maps", gmaps_params)}>'
            f'<span class="visit-cta-icon">{ja._icon("icon-link-google-map", "visit-cta-map-icon")}</span>'
            f'<span class="visit-cta-body"><span class="visit-cta-main">{escape(page.t("directions_main"))}</span>'
            f'<span class="visit-cta-sub">{escape(page.t("directions_sub"))}</span></span></a>'
        )

    # ---- location
    def _with_ja(local: str, ja_name: str) -> str:
        # 繁體字では日本語と同じ表記の自治体が多い。同じなら日本語を重ねない
        return escape(local) + (f"<small lang='ja'>{escape(ja_name)}</small>" if ja_name != local else "")

    rows = [
        (page.t("location_pref"), _with_ja(pref, prefecture)),
        (page.t("location_city"), _with_ja(place, municipality_label(manhole))),
    ]
    building = ja.landmark_label(manhole, municipality_label(manhole))
    for key, value in (("location_place", building), ("location_address", manhole.get("address", "")),
                       ("location_access", manhole.get("access", ""))):
        if value:
            rows.append((page.t(key), f"<span lang='ja'>{escape(value)}</span>"))
    location_html = (
        f"<section class='location-section section-card'><h2>{escape(page.t('location_heading'))}</h2><dl>"
        + "".join(f"<dt>{escape(dt)}</dt><dd>{dd}</dd>" for dt, dd in rows)
        + "</dl></section>"
    )

    # ---- nearby（ポケふた旅のエリアの説明文は日本語だけなので、訳では距離順の5枚を出す）
    nearby_html = ""
    if related["nearby"]:
        items = "".join(
            _related_card(
                page, other, id_to_image_url, "click_nearby_manhole",
                {"surface": "manhole_related_nearby", "from_manhole_id": manhole_id, "distance_km": round(dist, 1)},
                extra_html=f"<span class='distance'>{escape(page.t('distance_km', km=f'{dist:.1f}'))}</span>",
            )
            for other, dist in related["nearby"]
        )
        nearby_html = _related_section(
            page, section_id="", css="nearby-section",
            heading=f"{ja._icon('icon-detail-nearby', 'icon-lg')} {escape(page.t('nearby_heading'))}",
            lead="", items=items,
        )

    # ---- pokemon
    pokemon_html = ""
    if pokemons:
        cards = []
        for name in pokemons:
            meta = pokemon_meta.get(name) or pokemon_meta.get(ja._normalize_katakana(name)) or {}
            poke_slug = ja_to_slug.get(name) or ja_to_slug.get(ja._normalize_katakana(name), "")
            local = escape(page.pokemon_name(name))
            card = "<div class='pokemon-card'>"
            card += (
                f"<h3><a href='{page.prefix()}pokemon/{quote(poke_slug)}/'>{local}</a></h3>"
                if poke_slug else f"<h3>{local}</h3>"
            )
            card += f"<p class='multilingual-names' lang='ja'>{escape(name)}</p>"
            types = [page.type_name(t) for t in meta.get("types", []) if isinstance(t, dict) and t.get("en")]
            if types:
                card += f"<p class='types'>{escape(page.t('pokemon_types', types=page.t('types_sep').join(types)))}</p>"
            if meta.get("generation"):
                card += f"<p class='generation'>{escape(page.t('pokemon_generation', n=meta['generation']))}</p>"
            if related["same_pokemon"]:
                card += f"<a class='pokemon-same-link' href='#same-pokemon'>{escape(page.t('pokemon_same_link'))}</a>"
            cards.append(card + "</div>")
        pokemon_html = (
            f"<section class='pokemon-section section-card'><h2>{escape(page.t('pokemon_heading'))}</h2>"
            f"<div class='pokemon-list'>{''.join(cards)}</div></section>"
        )

    same_pokemon_html = ""
    if related["same_pokemon"]:
        current = set(pokemons)
        items = "".join(
            _related_card(
                page, other, id_to_image_url, "click_same_pokemon_manhole",
                {
                    "surface": "manhole_related_pokemon", "from_manhole_id": manhole_id,
                    "pokemon_names": ",".join(p for p in ja.filter_pokemons(other.get("pokemons", [])) if p in current),
                },
            )
            for other in related["same_pokemon"]
        )
        same_pokemon_html = _related_section(
            page, section_id="same-pokemon", css="same-pokemon-section",
            heading=escape(page.t("same_pokemon_heading")), lead="", items=items,
        )

    pref_section_html = ""
    if prefecture and related["same_pref"]:
        items = "".join(
            _related_card(
                page, other, id_to_image_url, "click_prefecture_manhole",
                {"surface": "manhole_related_prefecture", "from_manhole_id": manhole_id, "prefecture": prefecture},
            )
            for other in related["same_pref"]
        )
        pref_section_html = _related_section(
            page, section_id="", css="prefecture-section",
            heading=f"{ja._icon('icon-detail-same-pref', 'icon-lg')} {escape(page.t('pref_heading', pref=pref))}",
            lead=page.t("pref_lead", pref=pref, n=related["pref_total"]), items=items,
        )

    # ---- links
    link_cards = [
        f"<a class='link-card link-card--internal' href='{_attr(ja_url)}' hreflang='ja' lang='ja'"
        f"{_onclick('manhole_language_click', {**base, 'surface': 'links', 'destination': 'ja'})}>"
        f"{ja._icon('icon-link-official', 'link-card-icon')}<span>{escape(page.t('link_ja'))}</span></a>",
    ]
    if pref_url:
        link_cards.append(
            f"<a class='link-card link-card--internal' href='{_attr(pref_url)}'>"
            f"{ja._icon('icon-detail-same-pref', 'link-card-icon')}<span>{escape(page.t('link_pref', pref=pref))}</span></a>"
        )
    map_url = f"{page.prefix()}map.html?manhole={quote(manhole_id, safe='')}"
    link_cards.append(
        f"<a class='link-card link-card--internal' href='{_attr(map_url)}'"
        f"{_onclick('click_map_internal', {'manhole_id': manhole_id, 'surface': 'links_map'})}>"
        f"{ja._icon('icon-link-map', 'link-card-icon')}<span>{escape(page.t('link_map'))}</span></a>"
    )
    detail_url = manhole.get("detail_url", "")
    parsed = urlparse(detail_url) if detail_url else None
    if parsed and parsed.scheme == "https" and parsed.hostname == "local.pokemon.jp":
        link_cards.append(
            f"<a class='link-card link-card--official' href='{_attr(detail_url)}' hreflang='ja'"
            f" target='_blank' rel='noopener noreferrer'"
            f"{_onclick('click_official_site', {**base, 'surface': 'manhole_links'})}>"
            f"{ja._icon('icon-link-official', 'link-card-icon')}<span>{escape(page.t('link_official'))}</span></a>"
        )
    links_html = (
        f"<section class='links-section section-card'><h2>{escape(page.t('links_heading'))}</h2>"
        f"<div class='link-grid'>{''.join(link_cards)}</div>"
        f"<p class='ja-note'>{escape(page.t('ja_note'))}</p></section>"
    )

    back_html = (
        f'<a href="{_attr(map_url)}" class="back-btn"'
        f'{_onclick("click_map_internal", {"manhole_id": manhole_id, "surface": "back_btn"})}>'
        f"{escape(page.t('back'))}</a>"
    )

    # ---- head
    og_image = photo_url or f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"
    if ogp_dir is not None and (ogp_dir / f"{manhole_id}.png").exists():
        og_image = f"{BASE_URL}assets/ogp/manholes/{manhole_id}.png"
    breadcrumb = [{"name": page.t("breadcrumb_top"), "item": f"{BASE_URL}{page.lang}/"}]
    if pref_url:
        breadcrumb.append({"name": pref, "item": f"{BASE_URL}{pref_url.lstrip('/')}"})
    breadcrumb.append({"name": h1})
    attraction: dict = {
        "@context": "https://schema.org",
        "@type": "TouristAttraction",
        "name": h1,
        "description": description,
        "url": canonical,
        "inLanguage": page.t("html_lang"),
        "address": {
            "@type": "PostalAddress",
            "addressCountry": "JP",
            "addressRegion": prefecture,
            "addressLocality": manhole.get("city", ""),
            "streetAddress": manhole.get("address", ""),
        },
    }
    if lat is not None and lng is not None:
        attraction["geo"] = {"@type": "GeoCoordinates", "latitude": lat, "longitude": lng}
    if photo_url:
        attraction["image"] = photo_url
    jsonld = [
        attraction,
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i, **e} for i, e in enumerate(breadcrumb, 1)],
        },
    ]
    pref_slug = ja.PREFECTURE_EN.get(prefecture, "").lower().replace(" prefecture", "")
    year = datetime.date.today().year

    return f"""<!doctype html>
<html lang="{page.t("html_lang")}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{_attr(description)}">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <link rel="canonical" href="{_attr(canonical)}">
  {ja.hreflang_links(manhole_id)}

  <meta property="og:type" content="article">
  <meta property="og:locale" content="{page.t("og_locale")}">
  <meta property="og:site_name" content="{_attr(page.t("site_name"))}">
  <meta property="og:title" content="{_attr(title)}">
  <meta property="og:description" content="{_attr(description)}">
  <meta property="og:url" content="{_attr(canonical)}">
  <meta property="og:image" content="{_attr(og_image)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_attr(title)}">
  <meta name="twitter:description" content="{_attr(description)}">
  <meta name="twitter:image" content="{_attr(og_image)}">

  <script type="application/ld+json">
{ja._js_json(jsonld)}
  </script>

  <!-- Google Analytics: 日本語版と同じ page_path・イベント（言語は analytics.js が URL から付ける） -->
  <script src="/assets/analytics.js?v=20261018a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': '/manholes/' + {ja._js_json(manhole_id)} + '/',
      site_type: 'map',
      page_type: 'map_manhole',
      prefecture: {ja._js_json(pref_slug)},
    }});
    gtag('event', 'view_manhole_detail', {{
      surface: 'manhole_detail',
      manhole_id: {ja._js_json(manhole_id)},
      prefecture: {ja._js_json(prefecture)},
      city: {ja._js_json(manhole.get("city", ""))},
      pokemon_count: {len(pokemons)},
      has_photo: {json.dumps(bool(photo_url))}
    }});
  </script>

  <style>
{ja.PAGE_CSS}{EXTRA_CSS}  </style>
</head>
<body>
  {ja._SVG_DEFS}
  <div class="container">
    {back_html}

    {hero_html}

    {gallery_html}

    {visit_html}

    {location_html}

    {nearby_html}

    {pokemon_html}

    {same_pokemon_html}

    {pref_section_html}

    {links_html}

    <footer class="page-credit">
      <p>&copy; 2025-{year} data.pokefuta.com | {escape(page.t("footer"))}</p>
    </footer>
  </div>
</body>
</html>
"""


def generate_all(
    lang: str,
    manholes: list[dict],
    photos: dict[str, dict],
    pokemon_meta: dict[str, dict],
    ja_to_slug: dict[str, str],
    municipality_names: dict,
    image_dir: Path,
    output_dir: Path,
    locale: Locale | None = None,
    ogp_dir: Optional[Path] = None,
) -> int:
    # 訳の無い自治体は日本語名のまま出す（県ページの訳と同じ。デプロイは止めない）
    missing = pref_i18n.missing_municipalities(manholes, municipality_names, lang)
    if missing:
        print(
            f"[manhole-pages-{lang}] WARN dataset/municipality_names.json に訳の無い自治体: {', '.join(missing)}",
            file=sys.stderr,
        )
    page = DetailPage(lang, municipality_names, locale)
    index = ja.RelatedIndex(manholes)
    id_to_image_url = ja.local_image_urls(manholes, image_dir)
    total = 0
    for manhole in manholes:
        manhole_id = str(manhole.get("id", "")).strip()
        if not manhole_id:
            continue
        photo = ja.page_photo(manhole_id, photos, image_dir, id_to_image_url)
        html = build_page(
            page, manhole, photo, pokemon_meta, index.related(manhole), id_to_image_url, ja_to_slug, ogp_dir,
        )
        out = output_dir / manhole_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        total += 1
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=LANGS, required=True)
    parser.add_argument("--manholes", type=Path, default=ROOT / "docs" / "pokefuta.ndjson")
    parser.add_argument("--photos", type=Path, default=ROOT / "docs" / "latest-manhole-photos.json")
    parser.add_argument("--pokemon", type=Path, default=ROOT / "docs" / "pokemon_metadata.json")
    parser.add_argument("--image-dir", type=Path, default=ROOT / "dataset" / "manhole" / "image")
    parser.add_argument("--municipality-names", type=Path, default=pref_i18n.DEFAULT_MUNICIPALITY_NAMES)
    parser.add_argument("--output", type=Path, help="省略時は dist/<lang>/manholes")
    args = parser.parse_args(argv)
    output = args.output or ROOT / "dist" / args.lang / "manholes"
    manholes = ja.load_manholes(args.manholes)
    raw_pokemon = json.loads(args.pokemon.read_text(encoding="utf-8")) if args.pokemon.exists() else []
    count = generate_all(
        args.lang,
        manholes,
        ja.load_photos(args.photos),
        # リージョンフォーム（アローラロコン など）も引ける索引。ポケモンページと同じもの
        load_pokemon_metadata(args.pokemon),
        ja.build_ja_to_slug(raw_pokemon),
        pref_i18n.load_municipality_names(args.municipality_names),
        args.image_dir,
        output,
        # 日本語版と同じ OGP 画像（generate_manhole_ogp.py が先に dist に作る）
        ogp_dir=ja.manhole_ogp_dir(ROOT / "dist"),
    )
    print(f"[manhole-pages-{args.lang}] wrote {count} pages to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
