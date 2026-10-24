"""図鑑のページ生成器が共通で使う、HTML とリンクの小道具（内部ライブラリ）。"""

from __future__ import annotations

import json
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper.prefectures import PREFECTURE_PAGE_LANGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURE_PAGE_LANGS


BASE_URL = "https://data.pokefuta.com"
OG_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"


def escape_attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;", "'": "&#x27;"})


def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def hreflang_links(path: str) -> str:
    """日本語版と訳した言語の県ページを相互に指す。x-default は日本語版。path は "prefectures/<slug>/" の形。"""
    links = [f'<link rel="alternate" hreflang="ja" href="{BASE_URL}/{path}">']
    links += [
        f'<link rel="alternate" hreflang="{lang}" href="{BASE_URL}/{lang}/{path}">'
        for lang in PREFECTURE_PAGE_LANGS
    ]
    links.append(f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}/{path}">')
    return "\n  ".join(links)


def breadcrumb_list(items: list[tuple[str, str]]) -> dict:
    """パンくずの JSON-LD。items は (表示名, 絶対URL) を上から順に。画面のパンくずと同じ並びにする。"""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(items, start=1)
        ],
    }


def campaign_params(slug: str) -> str:
    """写真館（pokefuta.com）へのリンクに付ける流入元パラメータ。

    `from=data` だけだと写真館側で「図鑑から来た」ことしか分からず、
    どの都道府県ページが投稿・訪問登録に繋がったかを GA4 で追えない。
    `pref` を足して流入元の県を渡す（GA4 への送信は写真館側で別途対応）。

    内部導線を外部キャンペーンとして扱わないよう utm_* は使わず、
    クロスドメインリンカーと独自の流入元パラメータを使う。
    """
    if not slug:
        return "from=data"
    return f"from=data&pref={quote(slug)}"


def upload_url(manhole_id: str, slug: str) -> str:
    return (
        "https://pokefuta.com/upload?"
        f"manhole_id={quote(manhole_id)}&{campaign_params(slug)}"
    )
