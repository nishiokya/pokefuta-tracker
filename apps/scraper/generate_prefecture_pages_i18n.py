#!/usr/bin/env python3
"""多言語版の都道府県ページ（/<lang>/prefectures/ と /<lang>/prefectures/<slug>/）を作る。

日本語版（generate_prefecture_pages.py）のデータ部分だけを訳して出す。
見出し・地図・写真・マンホール一覧・会えるポケモン・近くの県。トリビア・回り方ガイド・
イベント・ルートの文章は日本語だけにあり、ここでは日本語版へのリンクにとどめる
（日本語を直すたびに訳を直す手間を増やさないため）。

- 施設名は訳さない。一覧では英語の自治体名の下に日本語の正式名を lang="ja" で添える
  （現地の看板や Google マップと照らし合わせられるように）
- 自治体名は dataset/municipality_names.json。訳の無い自治体は日本語名のまま出し、警告する
- page_path は日本語版と同じ /prefectures/<slug>/。言語は analytics.js が URL から付ける

Usage:
  python3 apps/scraper/generate_prefecture_pages_i18n.py --lang en
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper import generate_prefecture_pages as ja
    from apps.scraper.display_names import compose_display_name, municipality_label
    from apps.scraper.generate_top_page_en import Locale
    from apps.scraper.manhole_tile_image import tile_image_url
    from apps.scraper.municipalities import complete_prefectures, prefecture_coverage
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS, PREFECTURES, REGIONS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_prefecture_pages as ja
    from display_names import compose_display_name, municipality_label
    from generate_top_page_en import Locale
    from manhole_tile_image import tile_image_url
    from municipalities import complete_prefectures, prefecture_coverage
    from prefectures import PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS, PREFECTURES, REGIONS

ROOT = ja.ROOT
BASE_URL = ja.BASE_URL
DEFAULT_MUNICIPALITY_NAMES = ROOT / "dataset" / "municipality_names.json"
# 県ページを訳してある言語。日本語版の hreflang・サイトマップもこれを見る
LANGS = PREFECTURE_PAGE_LANGS

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "og_locale": "en_US",
        "site_name": "Pokéfuta Directory",
        "title": "Poké Lids in {pref}: Map of {count} Pokémon Manholes | Pokéfuta Directory",
        "title_empty": "Poké Lids in {pref}: None Yet — Nearest Pokémon Manholes | Pokéfuta Directory",
        "description": (
            "All {count} Poké Lids (Pokémon manhole covers) in {pref}, Japan, across {municipalities}: "
            "a map with directions, fan photos, and the Pokémon you can find."
        ),
        "description_empty": (
            "No Poké Lids (Pokémon manhole covers) have been installed in {pref} yet. "
            "See the nearest ones in neighboring prefectures."
        ),
        "h1": "Poké Lids (Pokémon Manholes) in {pref}",
        "kicker": "Prefecture guide",
        "intro": "{pref} has {count} Poké Lids in {municipalities}{rank_part}{complete_part}.",
        "intro_complete": " — every municipality in the prefecture has one",
        "rank_part": ", ranking #{rank} in Japan",
        "intro_empty": "No Poké Lids have been confirmed in {pref} yet. The nearest ones are in neighboring prefectures.",
        "municipality_one": "1 municipality",
        "municipality_many": "{n} municipalities",
        "stat_count": "Poké Lids",
        "stat_rank": "Rank in Japan",
        "stat_rank_value": "#{rank}",
        "stat_rank_none": "None yet",
        "stat_coverage": "Municipalities",
        "stat_coverage_all": "All of them",
        "stats_aria": "{pref} at a glance",
        "button_map": "See the map",
        "button_list": "Browse the list",
        "button_ja": "Japanese page",
        "button_summary": "All Poké Lids in Japan",
        "breadcrumb_aria": "Breadcrumb",
        "breadcrumb_top": "Map of Japan",
        "breadcrumb_prefs": "Prefectures",
        "map_heading": "Map of Poké Lids in {pref}",
        "map_lead": "Tap a pin for a photo and directions.",
        "legend_aria": "Map legend",
        "legend_photo": "Fan photo",
        "legend_no_photo": "No photo yet",
        "legend_preinstall": "Coming soon",
        "map_note": "Drag or pinch to move the map. Mouse-wheel zoom is off so the page scrolls normally.",
        "map_empty": "No locations to show yet.",
        "popup_details": "Details",
        "popup_directions": "Directions",
        "popup_preinstall": "This Poké Lid is not installed yet.",
        "popup_no_photo": "No photo yet",
        "popup_photo_alt": "Fan photo of the Poké Lid in {place}",
        "marker_title": "Poké Lid in {place}",
        "photos_heading": "Fan photos from {pref}",
        "photos_lead": "Photos posted by visitors. Tap one for the location details.",
        "photos_empty": "No fan photos yet.",
        "photo_by": "Photo by {name}",
        "list_heading": "All Poké Lids in {pref}",
        "list_lead": "The Japanese name under each place is how it appears on local signs and Google Maps.",
        "badge_preinstall": "Coming soon",
        "badge_photo": "Fan photo",
        "badge_no_photo": "No photo yet",
        "card_directions": "Directions",
        "lid_alt": "Poké Lid in {place}",
        "pokemon_heading": "Pokémon you can find in {pref}",
        "pokemon_count_one": "On 1 Poké Lid",
        "pokemon_count_many": "On {n} Poké Lids",
        "pokemon_more": "{n} more Pokémon",
        "nearest_heading": "Nearest Poké Lids from {pref}",
        "nearest_lead": "Straight-line distance from the prefectural capital.",
        "nearest_km": "{km} km away",
        "related_label": "Poké Lids in {region}",
        "related_heading": "Nearby prefectures",
        "ja_heading": "More in Japanese",
        "ja_text": (
            "Trivia, suggested routes, and event information for {pref} are on the Japanese page. "
            "Your browser's translate feature works on it."
        ),
        "ja_link": "Open the Japanese page for {pref}",
        "footer": "Back to all prefectures",
        "pokemon_fallback": "Pokémon",
        "sep": ", ",
        "index_title": "Poké Lids by Prefecture: All 47 Prefectures of Japan | Pokéfuta Directory",
        "index_description": (
            "{total} Poké Lids (Pokémon manhole covers) in {prefs} of Japan's 47 prefectures. "
            "Pick a prefecture for its map, fan photos, and Pokémon."
        ),
        "index_h1": "Poké Lids by Prefecture",
        "index_intro": "{total} Poké Lids are installed in {prefs} of Japan's 47 prefectures. Pick a prefecture for its map, fan photos, and Pokémon.",
        "index_count": "{n}",
        "index_none": "none yet",
        "index_regions_aria": "Prefectures by region",
    },
    # 用語は繁體中文版トップ（top_page_i18n_text.py）に合わせる：寶可夢人孔蓋・寶可夢人孔蓋圖鑑・「個」
    "zh-TW": {
        "html_lang": "zh-TW",
        "og_locale": "zh_TW",
        "site_name": "寶可夢人孔蓋圖鑑",
        "title": "{pref}的寶可夢人孔蓋：{count}個設置地點地圖｜寶可夢人孔蓋圖鑑",
        "title_empty": "{pref}的寶可夢人孔蓋：尚未設置・最近的寶可夢人孔蓋｜寶可夢人孔蓋圖鑑",
        "description": (
            "日本{pref}的{count}個寶可夢人孔蓋（Pokéfuta）全收錄，分布於{municipalities}。"
            "附交通指引的地圖、粉絲照片，以及可以見到的寶可夢。"
        ),
        "description_empty": "{pref}目前尚未設置寶可夢人孔蓋（Pokéfuta）。可查看鄰近都道府縣最近的寶可夢人孔蓋。",
        "h1": "{pref}的寶可夢人孔蓋",
        "kicker": "都道府縣導覽",
        "intro": "{pref}共有{count}個寶可夢人孔蓋，分布於{municipalities}{rank_part}{complete_part}。",
        "intro_complete": "，縣內所有市町村都有設置",
        "rank_part": "，全國第{rank}名",
        "intro_empty": "{pref}目前尚未確認設置寶可夢人孔蓋。最近的寶可夢人孔蓋位於鄰近的都道府縣。",
        "municipality_one": "1個市町村",
        "municipality_many": "{n}個市町村",
        "stat_count": "寶可夢人孔蓋",
        "stat_rank": "全國排名",
        "stat_rank_value": "第{rank}名",
        "stat_rank_none": "尚未設置",
        "stat_coverage": "設置市町村",
        "stat_coverage_all": "全部市町村",
        "stats_aria": "{pref}概要",
        "button_map": "查看地圖",
        "button_list": "查看列表",
        "button_ja": "日文頁面",
        "button_summary": "日本全國的寶可夢人孔蓋",
        "breadcrumb_aria": "導覽路徑",
        "breadcrumb_top": "日本全國地圖",
        "breadcrumb_prefs": "都道府縣",
        "map_heading": "{pref}的寶可夢人孔蓋地圖",
        "map_lead": "點選圖釘可查看照片與交通指引。",
        "legend_aria": "地圖圖例",
        "legend_photo": "有粉絲照片",
        "legend_no_photo": "尚無照片",
        "legend_preinstall": "即將設置",
        "map_note": "可拖曳或用兩指縮放地圖。為了讓頁面正常捲動，已關閉滑鼠滾輪縮放。",
        "map_empty": "目前沒有可顯示的設置地點。",
        "popup_details": "詳細資訊",
        "popup_directions": "交通指引",
        "popup_preinstall": "這個寶可夢人孔蓋尚未設置。",
        "popup_no_photo": "尚無照片",
        "popup_photo_alt": "{place}的寶可夢人孔蓋粉絲照片",
        "marker_title": "{place}的寶可夢人孔蓋",
        "photos_heading": "{pref}的粉絲照片",
        "photos_lead": "訪客投稿的照片。點選可查看設置地點的詳細資訊。",
        "photos_empty": "目前還沒有粉絲照片。",
        "photo_by": "攝影：{name}",
        "list_heading": "{pref}的寶可夢人孔蓋一覽",
        "list_lead": "各地點下方的日文名稱，與當地標示及 Google 地圖上的寫法相同。",
        "badge_preinstall": "即將設置",
        "badge_photo": "有粉絲照片",
        "badge_no_photo": "尚無照片",
        "card_directions": "交通指引",
        "lid_alt": "{place}的寶可夢人孔蓋",
        "pokemon_heading": "在{pref}可以見到的寶可夢",
        "pokemon_count_one": "出現在1個人孔蓋上",
        "pokemon_count_many": "出現在{n}個人孔蓋上",
        "pokemon_more": "其他{n}種寶可夢",
        "nearest_heading": "離{pref}最近的寶可夢人孔蓋",
        "nearest_lead": "以縣廳所在地為起點的直線距離。",
        "nearest_km": "距離{km}公里",
        "related_label": "{region}的寶可夢人孔蓋",
        "related_heading": "鄰近的都道府縣",
        "ja_heading": "更多資訊（日文）",
        "ja_text": "{pref}的小知識、建議路線與活動資訊在日文頁面上，可使用瀏覽器的翻譯功能閱讀。",
        "ja_link": "開啟{pref}的日文頁面",
        "footer": "回到都道府縣一覽",
        "pokemon_fallback": "寶可夢",
        "sep": "、",
        "index_title": "依都道府縣查看寶可夢人孔蓋：日本47個都道府縣一覽｜寶可夢人孔蓋圖鑑",
        "index_description": (
            "日本47個都道府縣中，有{prefs}個設有共{total}個寶可夢人孔蓋（Pokéfuta）。"
            "選擇都道府縣即可查看地圖、粉絲照片與寶可夢。"
        ),
        "index_h1": "依都道府縣查看寶可夢人孔蓋",
        "index_intro": "日本47個都道府縣中，有{prefs}個設有共{total}個寶可夢人孔蓋。選擇都道府縣即可查看地圖、粉絲照片與寶可夢。",
        "index_count": "{n}",
        "index_none": "尚未設置",
        "index_regions_aria": "依地區排列的都道府縣",
    },
}


def _t(lang: str, key: str, **values: object) -> str:
    return TEXT[lang][key].format(**values)


def load_municipality_names(path: Path = DEFAULT_MUNICIPALITY_NAMES) -> dict[str, dict[str, dict[str, str]]]:
    """県 → 自治体（municipality_label の表記）→ 言語 → 名前。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {pref: names for pref, names in data.items() if not pref.startswith("_")}


def missing_municipalities(records: list[dict], names: dict, lang: str) -> list[str]:
    """訳の無い自治体（「県/自治体」）。あると、その自治体だけ日本語名で出る。"""
    missing = set()
    for record in records:
        label = municipality_label(record)
        if label and not (names.get(record.get("prefecture", ""), {}).get(label) or {}).get(lang):
            missing.add(f'{record.get("prefecture", "")}/{label}')
    return sorted(missing)


class Page:
    """1言語ぶんの表記。ポケモン名・県名は英語版トップと同じ Locale を使う。"""

    def __init__(self, lang: str, municipality_names: dict, locale: Locale | None = None) -> None:
        self.lang = lang
        self.loc = locale or Locale(lang)
        self.names = municipality_names

    def t(self, key: str, **values: object) -> str:
        return _t(self.lang, key, **values)

    def pref(self, prefecture: str) -> str:
        return self.loc.pref(prefecture)

    def region(self, region: str) -> str:
        return str(self.loc.text["regions"].get(region, region))

    def municipality(self, record: dict) -> str:
        label = municipality_label(record)
        return (self.names.get(record.get("prefecture", ""), {}).get(label) or {}).get(self.lang) or label

    def municipalities(self, n: int) -> str:
        return self.t("municipality_one") if n == 1 else self.t("municipality_many", n=n)

    def pokemon_name(self, name: str) -> str:
        # データには「ゴンべ」のように末尾がひらがなの表記があるので、カタカナにそろえて引き直す
        return self.loc.pokemon.get(name) or self.loc.pokemon_name(ja._normalize_katakana(name))

    def pokemons(self, record: dict) -> str:
        names = [self.pokemon_name(p) for p in ja._clean_pokemons(record)]
        return self.t("sep").join(names) or self.t("pokemon_fallback")

    def prefix(self) -> str:
        return f"/{self.lang}/"


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _json(value: object) -> str:
    return ja._json_for_script(value)


def _ja_name(record: dict) -> str:
    return compose_display_name(record) or municipality_label(record)


def _photo_url(record: dict, photos: dict[str, dict]) -> str:
    mid = str(record.get("id", ""))
    if record.get("installed") is False or mid not in photos:
        return ""
    return ja._photo_asset_url(record, photos[mid])


def _head(page: Page, *, title: str, description: str, path: str, json_ld: dict, leaflet: bool) -> str:
    canonical = f"{BASE_URL}{page.prefix()}{path}"
    leaflet_css = (
        '\n  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"\n'
        '    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">'
        if leaflet else ""
    )
    return f"""<!doctype html>
<html lang="{page.t("html_lang")}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{_attr(description)}">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="{page.t("og_locale")}">
  <meta property="og:site_name" content="{_attr(page.t("site_name"))}">
  <meta property="og:title" content="{_attr(title)}">
  <meta property="og:description" content="{_attr(description)}">
  <meta property="og:url" content="{_attr(canonical)}">
  <meta property="og:image" content="{ja.OG_IMAGE}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_attr(title)}">
  <meta name="twitter:description" content="{_attr(description)}">
  <meta name="twitter:image" content="{ja.OG_IMAGE}">
  <link rel="canonical" href="{_attr(canonical)}">
  {ja.hreflang_links(path)}
  <link rel="icon" href="/assets/pokefuta-marker.svg" type="image/svg+xml">{leaflet_css}
  <script type="application/ld+json">{_json(json_ld)}</script>
  <style>
{ja.PAGE_CSS}    /* 英語版のカードは日本語の正式名で1行多いので、影を濃く長くして読めるようにする */
    .manhole-shade {{ background: linear-gradient(to top, rgba(30,22,10,.8) 0%, rgba(30,22,10,0) 60%); }}
    .ja-name {{ display: block; margin-top: 2px; font-size: .72rem; font-weight: 650; }}
    .related-links a small {{ margin-left: 6px; color: #6b4aa2; font-size: .75rem; }}
  </style>
</head>"""


def _analytics(slug: str, prefecture: str, page_type: str) -> str:
    """日本語版と同じイベント名・page_path で送る（言語は analytics.js が URL から付ける）。"""
    page_path = f"/prefectures/{slug}/" if slug else "/prefectures/"
    return f"""  <script src="/assets/analytics.js?v=20261018a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': {_json(page_path)},
      site_type: 'map',
      page_type: {_json(page_type)},
      prefecture: {_json(slug)}
    }});
    const prefectureEventDefaults = {{
      event_category: 'prefecture_growth',
      surface: 'prefecture_page',
      prefecture: {_json(slug)},
      prefecture_name: {_json(prefecture)}
    }};
    function trackPrefectureEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{}}, prefectureEventDefaults, params || {{}}));
    }}
    window.PokefutaAnalytics.bindClickTracking(prefectureEventDefaults, {{ detail: true }});
  </script>"""


def _map_script(page: Page, points: list[dict]) -> str:
    """日本語版の設置マップと同じ Leaflet の地図。写真館（日本語のみ）への投稿リンクは出さない。"""
    labels = {
        "empty": page.t("map_empty"),
        "details": page.t("popup_details"),
        "directions": page.t("popup_directions"),
        "preinstall": page.t("popup_preinstall"),
        "noPhoto": page.t("popup_no_photo"),
        "photoAlt": page.t("popup_photo_alt", place="{place}"),
        "markerTitle": page.t("marker_title", place="{place}"),
        "legendPhoto": page.t("legend_photo"),
        "legendNoPhoto": page.t("legend_no_photo"),
        "legendPreinstall": page.t("legend_preinstall"),
    }
    return f"""  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const points = {_json(points)};
    const labels = {_json(labels)};
    const mapElement = document.getElementById('prefecture-map');
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, function(char) {{
        return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char];
      }});
    }}
    if (!mapElement) {{
      /* ポケふたが無い県では地図セクション自体を出していない */
    }} else if (!points.length) {{
      mapElement.textContent = labels.empty;
    }} else {{
      const map = L.map(mapElement, {{ scrollWheelZoom: false }});
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }}).addTo(map);
      const bounds = [];
      points.forEach(function(point) {{
        const latlng = [point.lat, point.lng];
        bounds.push(latlng);
        const photoState = point.is_preinstall ? 'preinstall' : (point.photo_url ? 'has_photo' : 'missing');
        const markerClass = point.is_preinstall ? 'preinstall' : (point.photo_url ? 'has-photo' : 'needs-photo');
        const photoHtml = point.is_preinstall
          ? '<div class="map-popup-preinstall">' + escapeHtml(labels.preinstall) + '</div>'
          : (point.photo_url
            ? '<img src="' + escapeHtml(point.photo_url) + '" alt="' +
              escapeHtml(labels.photoAlt.replace('{{place}}', point.place)) + '" ' +
              'loading="lazy" decoding="async" width="320" height="240">'
            : '<div class="map-popup-photo-missing">' + escapeHtml(labels.noPhoto) + '</div>');
        const popupHtml = '<div class="map-popup"><strong>' + escapeHtml(point.pokemons) + '</strong><br>' +
          escapeHtml(point.place) + '<br><span lang="ja">' + escapeHtml(point.ja_name) + '</span>' + photoHtml +
          '<div class="map-popup-actions' + (point.is_preinstall ? ' preinstall-actions' : '') + '">' +
          '<a href="' + {_json(page.prefix() + "manholes/")} + encodeURIComponent(point.id) + '/" ' +
          'data-track="prefecture_manhole_click" data-destination="' + escapeHtml(point.id) + '" ' +
          'data-content-id="' + escapeHtml(point.id) + '" data-surface="map_popup">' + escapeHtml(labels.details) + '</a>' +
          '<a href="https://www.google.com/maps?q=' + point.lat + ',' + point.lng + '" target="_blank" ' +
          'rel="noopener noreferrer" data-track="prefecture_google_maps_click" data-destination="google_maps" ' +
          'data-content-id="' + escapeHtml(point.id) + '" data-surface="map_popup">' + escapeHtml(labels.directions) + '</a>' +
          '</div></div>';
        const state = point.is_preinstall ? labels.legendPreinstall : (point.photo_url ? labels.legendPhoto : labels.legendNoPhoto);
        const title = labels.markerTitle.replace('{{place}}', point.place);
        const marker = L.marker(latlng, {{
          title: title,
          alt: title + ' — ' + state,
          icon: L.divIcon({{
            className: '',
            html: '<div class="prefecture-marker ' + markerClass + '"></div>',
            iconSize: [28, 34],
            iconAnchor: [14, 31],
            popupAnchor: [0, -30]
          }})
        }}).addTo(map).bindPopup(popupHtml, {{ maxWidth: 300 }});
        marker.on('click', function() {{
          trackPrefectureEvent('prefecture_map_pin_click', {{
            surface: 'prefecture_map',
            content_id: point.id,
            photo_state: photoState
          }});
        }});
      }});
      if (bounds.length === 1) map.setView(bounds[0], 13);
      else map.fitBounds(bounds, {{ padding: [28, 28], maxZoom: 13 }});
    }}
  </script>"""


def _sorted_records(page: Page, records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: (page.municipality(r), str(r.get("id", "")).zfill(6)))


def _manhole_cards(page: Page, records: list[dict], photos: dict[str, dict], distances: dict[str, float] | None = None) -> str:
    cards = []
    for position, record in enumerate(records, start=1):
        mid = str(record.get("id", "")).strip()
        place = page.municipality(record)
        tile_url = tile_image_url(mid, ROOT / "dataset" / "manhole" / "image")
        image_html = (
            f'<img src="{_attr(tile_url)}" alt="{_attr(page.t("lid_alt", place=place))}" '
            'loading="lazy" decoding="async" width="720" height="720">'
            if tile_url
            else '<span class="manhole-placeholder" aria-hidden="true"></span>'
        )
        is_preinstall = record.get("installed") is False
        has_photo = bool(_photo_url(record, photos))
        if is_preinstall:
            badge = f'<b class="photo-status photo-pending">{escape(page.t("badge_preinstall"))}</b>'
        elif has_photo:
            badge = f'<b class="photo-status photo-ready">{escape(page.t("badge_photo"))}</b>'
        else:
            badge = f'<b class="photo-status photo-needed">{escape(page.t("badge_no_photo"))}</b>'
        sub = escape(place)
        if distances and mid in distances:
            sub = f'{escape(page.pref(record.get("prefecture", "")))} · {sub} · {escape(page.t("nearest_km", km=round(distances[mid])))}'
        maps_url = ja._google_maps_url(record)
        actions = (
            f'<div class="manhole-actions"><a href="{_attr(maps_url)}" target="_blank" rel="noopener noreferrer" '
            f'data-track="prefecture_google_maps_click" data-position="{position}" '
            f'data-destination="google_maps" data-content-id="{_attr(mid)}" '
            f'data-surface="manhole_actions">{escape(page.t("card_directions"))}</a></div>'
            if maps_url else ""
        )
        cards.append(
            f'<article class="manhole-card" data-manhole-id="{_attr(mid)}" id="manhole-{_attr(mid)}">'
            f'<a class="manhole-detail" href="{page.prefix()}manholes/{quote(mid)}/" '
            f'data-track="prefecture_manhole_click" data-position="{position}" '
            f'data-destination="{_attr(mid)}" data-content-id="{_attr(mid)}" data-surface="manhole_card">'
            f'{image_html}<span class="manhole-shade" aria-hidden="true"></span>'
            f'<span class="manhole-badges">{badge}</span>'
            f'<span class="manhole-copy"><strong>{escape(page.pokemons(record))}</strong>'
            f'<small>{sub}<span class="ja-name" lang="ja">{escape(_ja_name(record))}</span></small></span></a>'
            f"{actions}</article>"
        )
    return "".join(cards)


def _photo_cards(page: Page, records: list[dict], photos: dict[str, dict]) -> str:
    installed = [r for r in records if r.get("installed") is not False]
    entries = ja._photo_entries(installed, photos)[: ja.PHOTO_SHOWCASE_LIMIT]
    if not entries:
        return f'<p class="empty-state">{escape(page.t("photos_empty"))}</p>'
    cards = []
    for position, (record, photo) in enumerate(entries, start=1):
        mid = str(record.get("id", "")).strip()
        place = page.municipality(record)
        poster = str(photo.get("display_name", "") or "").strip()
        # 投稿者の表示名は本人が付けたもので訳さない（ブラウザ翻訳にもかけない）
        name_html = f'<bdi translate="no">{escape(poster)}</bdi>'
        poster_html = (
            f'<small class="photo-card-poster">{escape(page.t("photo_by", name="{name}")).format(name=name_html)}</small>'
            if poster else ""
        )
        cards.append(
            '<article class="photo-card">'
            f'<a class="photo-card-image" href="{page.prefix()}manholes/{quote(mid)}/" '
            f'data-track="prefecture_photo_click" data-position="{position}" '
            f'data-destination="{_attr(mid)}" data-surface="photo_gallery">'
            f'<img src="{_attr(ja._photo_asset_url(record, photo))}" '
            f'alt="{_attr(page.t("popup_photo_alt", place=place))}" '
            'loading="lazy" decoding="async" width="640" height="480">'
            f'<span><strong>{escape(page.pokemons(record))}</strong><small>{escape(place)}</small></span></a>'
            f"{poster_html}</article>"
        )
    return f'<div class="photo-showcase-grid">{"".join(cards)}</div>'


def _pokemon_cards(page: Page, records: list[dict], pokemon_slugs: dict[str, str]) -> str:
    counts = Counter(p for record in records for p in set(ja._clean_pokemons(record)))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def card(name: str, n: int) -> str:
        slug = pokemon_slugs.get(name) or pokemon_slugs.get(ja._normalize_katakana(name))
        label = page.t("pokemon_count_one") if n == 1 else page.t("pokemon_count_many", n=n)
        content = f"<strong>{escape(page.pokemon_name(name))}</strong><span>{escape(label)}</span>"
        if not slug:
            return f'<article class="pokemon-card">{content}</article>'
        return (
            f'<a class="pokemon-card" href="{page.prefix()}pokemon/{quote(slug)}/" '
            f'data-track="prefecture_pokemon_click" data-destination="{_attr(slug)}">{content}</a>'
        )

    featured = "".join(card(name, n) for name, n in ranked[:12])
    rest = ranked[12:]
    if not rest:
        return featured
    more = "".join(card(name, n) for name, n in rest)
    return (
        f'{featured}<details class="pokemon-more"><summary>{escape(page.t("pokemon_more", n=len(rest)))}</summary>'
        f'<div class="pokemon-more-grid">{more}</div></details>'
    )


def _related(page: Page, prefecture: str, empty: set[str]) -> str:
    for region, prefectures in REGIONS:
        if prefecture not in prefectures:
            continue
        links = "".join(
            f'<a href="{page.prefix()}prefectures/{PREFECTURE_SLUGS[name]}/" '
            f'data-track="prefecture_related_click" data-destination="{PREFECTURE_SLUGS[name]}">'
            f"{escape(page.pref(name))}</a>"
            for name in prefectures
            if name != prefecture and name not in empty
        )
        if not links:
            return ""
        return (
            f'<section aria-labelledby="related-heading"><h2 id="related-heading">{escape(page.t("related_heading"))}</h2>'
            f'<p class="related-label">{escape(page.t("related_label", region=page.region(region)))}</p>'
            f'<div class="related-links">{links}</div></section>'
        )
    return ""


def build_page(
    page: Page,
    prefecture: str,
    slug: str,
    records: list[dict],
    rank: int | None,
    pokemon_slugs: dict[str, str],
    photos: dict[str, dict],
    empty_prefectures: set[str],
    all_records: list[dict],
    coverage=None,
    complete: list[str] | None = None,
) -> str:
    pref = page.pref(prefecture)
    count = len(records)
    covered = coverage.covered if coverage and coverage.covered else len({municipality_label(r) for r in records})
    municipalities = page.municipalities(covered)
    path = f"prefectures/{slug}/"
    canonical = f"{BASE_URL}{page.prefix()}{path}"
    ja_url = f"/{path}"

    if count:
        title = page.t("title", pref=pref, count=count)
        description = page.t("description", pref=pref, count=count, municipalities=municipalities)
        rank_part = page.t("rank_part", rank=rank) if rank else ""
        complete_part = page.t("intro_complete") if coverage and coverage.is_complete else ""
        intro = page.t(
            "intro", pref=pref, count=count, municipalities=municipalities,
            rank_part=rank_part, complete_part=complete_part,
        )
        actions = (
            f'<a class="button primary" href="#prefecture-map" data-track="prefecture_map_click" '
            f'data-surface="hero" data-destination="prefecture_map">{escape(page.t("button_map"))}</a>'
            f'<a class="button secondary" href="#manhole-list" data-track="prefecture_list_click" '
            f'data-surface="hero" data-destination="manhole_list">{escape(page.t("button_list"))}</a>'
            f'<a class="button tertiary" href="{ja_url}" hreflang="ja" lang="ja" data-track="prefecture_language_click" '
            f'data-surface="hero" data-destination="ja">日本語</a>'
        )
    else:
        title = page.t("title_empty", pref=pref)
        description = page.t("description_empty", pref=pref)
        intro = page.t("intro_empty", pref=pref)
        actions = (
            f'<a class="button primary" href="{page.prefix()}summary/" data-track="prefecture_summary_click" '
            f'data-surface="hero" data-destination="summary">{escape(page.t("button_summary"))}</a>'
        )

    stats = [
        f'<div class="stat"><span>{escape(page.t("stat_count"))}</span><strong>{count}</strong></div>',
        f'<div class="stat"><span>{escape(page.t("stat_rank"))}</span>'
        f'<strong>{escape(page.t("stat_rank_value", rank=rank) if rank else page.t("stat_rank_none"))}</strong></div>',
    ]
    if coverage and coverage.covered and count:
        small = page.t("stat_coverage_all") if coverage.is_complete else f"{coverage.percent}%"
        stats.append(
            f'<div class="stat"><span>{escape(page.t("stat_coverage"))}</span>'
            f"<strong>{coverage.covered}/{coverage.total}</strong><small>{escape(small)}</small></div>"
        )

    points = [
        {
            "id": str(r.get("id", "")),
            "lat": r["lat"],
            "lng": r["lng"],
            "place": page.municipality(r),
            "ja_name": _ja_name(r),
            "pokemons": page.pokemons(r),
            "is_preinstall": r.get("installed") is False,
            "photo_url": _photo_url(r, photos),
        }
        for r in records
        if isinstance(r.get("lat"), (int, float)) and isinstance(r.get("lng"), (int, float))
    ]

    ja_section = (
        f'<section aria-labelledby="ja-heading"><h2 id="ja-heading">{escape(page.t("ja_heading"))}</h2>'
        f'<p>{escape(page.t("ja_text", pref=pref))}</p>'
        f'<p><a class="inline-link" href="{ja_url}" hreflang="ja" data-track="prefecture_language_click" '
        f'data-surface="ja_more" data-destination="ja">{escape(page.t("ja_link", pref=pref))}</a></p></section>'
    )
    related = _related(page, prefecture, empty_prefectures)
    if count:
        sections = f"""    <section aria-labelledby="map-heading">
      <div class="section-heading-row">
        <h2 id="map-heading">{escape(page.t("map_heading", pref=pref))}</h2>
        <p>{escape(page.t("map_lead"))}</p>
      </div>
      <div class="map-toolbar">
        <div class="map-legend" aria-label="{_attr(page.t("legend_aria"))}">
          <span><i class="legend-dot has-photo"></i>{escape(page.t("legend_photo"))}</span>
          <span><i class="legend-dot needs-photo"></i>{escape(page.t("legend_no_photo"))}</span>
          <span><i class="legend-dot preinstall"></i>{escape(page.t("legend_preinstall"))}</span>
        </div>
      </div>
      <div id="prefecture-map"></div>
      <p class="map-note">{escape(page.t("map_note"))}</p>
    </section>

    <section id="prefecture-photos" aria-labelledby="photo-heading">
      <div class="section-heading-row">
        <h2 id="photo-heading">{escape(page.t("photos_heading", pref=pref))}</h2>
        <p>{escape(page.t("photos_lead"))}</p>
      </div>
      {_photo_cards(page, records, photos)}
    </section>

    <section id="manhole-list" aria-labelledby="manhole-heading">
      <div class="section-heading-row">
        <h2 id="manhole-heading">{escape(page.t("list_heading", pref=pref))}</h2>
        <p>{escape(page.t("list_lead"))}</p>
      </div>
      <div class="manhole-grid">{_manhole_cards(page, _sorted_records(page, records), photos)}</div>
    </section>

    <section aria-labelledby="pokemon-heading">
      <h2 id="pokemon-heading">{escape(page.t("pokemon_heading", pref=pref))}</h2>
      <div class="pokemon-grid">{_pokemon_cards(page, records, pokemon_slugs)}</div>
    </section>

    {ja_section}
    {related}"""
    else:
        nearest = ja._nearest_pokefuta(prefecture, all_records)
        distances = {str(r.get("id", "")): km for km, r in nearest}
        sections = f"""    <section aria-labelledby="nearest-heading">
      <div class="section-heading-row">
        <h2 id="nearest-heading">{escape(page.t("nearest_heading", pref=pref))}</h2>
        <p>{escape(page.t("nearest_lead"))}</p>
      </div>
      <div class="manhole-grid">{_manhole_cards(page, [r for _, r in nearest], photos, distances)}</div>
    </section>

    {related}"""

    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "inLanguage": page.t("html_lang"),
        "isPartOf": {"@type": "WebSite", "name": page.t("site_name"), "url": f"{BASE_URL}{page.prefix()}"},
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": page.t("breadcrumb_top"), "item": f"{BASE_URL}{page.prefix()}"},
                {"@type": "ListItem", "position": 2, "name": page.t("breadcrumb_prefs"), "item": f"{BASE_URL}{page.prefix()}prefectures/"},
                {"@type": "ListItem", "position": 3, "name": pref, "item": canonical},
            ],
        },
    }
    head = _head(page, title=title, description=description, path=path, json_ld=json_ld, leaflet=bool(count))
    return f"""{head}
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="{_attr(page.t("breadcrumb_aria"))}">
      <a href="{page.prefix()}">{escape(page.t("breadcrumb_top"))}</a><span>›</span>
      <a href="{page.prefix()}prefectures/">{escape(page.t("breadcrumb_prefs"))}</a><span>›</span>
      <span>{escape(pref)}</span>
    </nav>
    <header class="hero prefecture-hero">
      <div class="hero-heading">
        <p class="hero-kicker">{escape(page.t("kicker"))}</p>
        <h1>{escape(page.t("h1", pref=pref))}</h1>
      </div>
      <div class="hero-main">
        <p>{escape(intro)}</p>
        <div class="{"stats stats-3" if len(stats) == 3 else "stats"}" aria-label="{_attr(page.t("stats_aria", pref=pref))}">
          {"".join(stats)}
        </div>
        <div class="hero-actions">{actions}</div>
      </div>
    </header>

{sections}
    <footer><a href="{page.prefix()}prefectures/">{escape(page.t("footer"))}</a></footer>
  </main>
{_analytics(slug, prefecture, "prefecture")}
{_map_script(page, points) if count else ""}
</body>
</html>
"""


def build_index_page(page: Page, records_by_pref: dict[str, list[dict]]) -> str:
    # 「installed」と書くので設置予定（installed: false）は数えない
    installed = {
        pref: [r for r in items if r.get("installed") is not False] for pref, items in records_by_pref.items()
    }
    total = sum(len(v) for v in installed.values())
    prefs = sum(1 for v in installed.values() if v)
    title = page.t("index_title")
    description = page.t("index_description", total=total, prefs=prefs)
    regions = []
    for region, prefectures in REGIONS:
        links = "".join(
            f'<a href="{page.prefix()}prefectures/{PREFECTURE_SLUGS[name]}/" '
            f'data-track="prefecture_index_click" data-destination="{PREFECTURE_SLUGS[name]}">'
            f'{escape(page.pref(name))}<small>{escape(page.t("index_count", n=len(records_by_pref[name])) if records_by_pref[name] else page.t("index_none"))}</small></a>'
            for name in prefectures
        )
        regions.append(
            f'<section aria-labelledby="region-{PREFECTURE_SLUGS[prefectures[0]]}">'
            f'<h2 id="region-{PREFECTURE_SLUGS[prefectures[0]]}" class="region-heading">{escape(page.region(region))}</h2>'
            f'<div class="related-links">{links}</div></section>'
        )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": f"{BASE_URL}{page.prefix()}prefectures/",
        "inLanguage": page.t("html_lang"),
    }
    head = _head(page, title=title, description=description, path="prefectures/", json_ld=json_ld, leaflet=False)
    return f"""{head}
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="{_attr(page.t("breadcrumb_aria"))}">
      <a href="{page.prefix()}">{escape(page.t("breadcrumb_top"))}</a><span>›</span>
      <span>{escape(page.t("breadcrumb_prefs"))}</span>
    </nav>
    <header class="hero">
      <div class="hero-heading">
        <p class="hero-kicker">{escape(page.t("kicker"))}</p>
        <h1>{escape(page.t("index_h1"))}</h1>
      </div>
      <div class="hero-main"><p>{escape(page.t("index_intro", total=total, prefs=prefs))}</p></div>
    </header>
    <div aria-label="{_attr(page.t("index_regions_aria"))}">
{"".join(regions)}
    </div>
  </main>
{_analytics("", "", "prefecture_index")}
</body>
</html>
"""


def generate_all(
    lang: str,
    records: list[dict],
    pokemon_slugs: dict[str, str],
    photos: dict[str, dict],
    municipality_names: dict,
    output_dir: Path,
    locale: Locale | None = None,
) -> int:
    # 訳の無い自治体は日本語名のまま出す。ここで止めると、新しい自治体に設置された日に
    # サイト全体のデプロイが止まるので、警告だけにして日次データの PR のレポートで拾う
    missing = missing_municipalities(records, municipality_names, lang)
    if missing:
        print(
            f"[prefecture-pages-{lang}] WARN dataset/municipality_names.json に訳の無い自治体: {', '.join(missing)}",
            file=sys.stderr,
        )
    page = Page(lang, municipality_names, locale)
    records_by_pref: dict[str, list[dict]] = {pref: [] for pref in PREFECTURE_ORDER}
    for record in records:
        if record.get("prefecture") in records_by_pref:
            records_by_pref[record["prefecture"]].append(record)
    rankings = ja.build_rankings(records)
    empty = {pref for pref, items in records_by_pref.items() if not items}
    coverage = prefecture_coverage(records)
    complete = complete_prefectures(coverage)
    for prefecture, slug in PREFECTURES:
        out = output_dir / slug
        out.mkdir(parents=True, exist_ok=True)
        html = build_page(
            page, prefecture, slug, records_by_pref[prefecture], rankings[prefecture],
            pokemon_slugs, photos, empty, records, coverage[prefecture], complete,
        )
        (out / "index.html").write_text(html, encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(build_index_page(page, records_by_pref), encoding="utf-8")
    return len(PREFECTURES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=LANGS, required=True)
    parser.add_argument("--manholes", type=Path, default=ja.DEFAULT_MANHOLES)
    parser.add_argument("--pokemon", type=Path, default=ja.DEFAULT_POKEMON)
    parser.add_argument("--photos", type=Path, default=ja.DEFAULT_PHOTOS)
    parser.add_argument("--municipality-names", type=Path, default=DEFAULT_MUNICIPALITY_NAMES)
    parser.add_argument("--output", type=Path, help="省略時は dist/<lang>/prefectures")
    args = parser.parse_args(argv)
    output = args.output or ROOT / "dist" / args.lang / "prefectures"
    count = generate_all(
        args.lang,
        ja.load_records(args.manholes),
        ja.load_pokemon_slugs(args.pokemon),
        ja.load_photos(args.photos),
        load_municipality_names(args.municipality_names),
        output,
    )
    print(f"[prefecture-pages-{args.lang}] wrote {count} pages to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
