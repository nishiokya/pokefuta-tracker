"""楽天トラベル（宿・レンタカー）のアフィリエイトリンク。

/trip/ と /municipalities/ のページで使う。リンク形式・ID は /trip/ 一覧の既存リンク（#904）と同じ。
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape

AFFILIATE_ID = "59e54b6b.42820fd9.59e54b6c.866c5f88"
# 楽天アフィリエイトのテキストリンク生成ツールが付ける表示パラメータ。
LINK_SUFFIX = "&link_type=text&ut=eyJwYWdlIjoidXJsIiwidHlwZSI6InRleHQiLCJjb2wiOjF9"

HOTEL_JAPAN_URL = "https://travel.rakuten.co.jp/yado/japan.html"
CAR_TOP_URL = "https://travel.rakuten.co.jp/cars/"

# 楽天レンタカーの県別ページは /cars/area/<地方>/<県>/。2026-11 にトップの地図から取った。
# 北海道・沖縄には県別ページが無く、地方ページ（travel.rakuten.co.jp/cars/area/<県>/）だけ。
CAR_REGIONS = {
    **dict.fromkeys(("aomori", "iwate", "miyagi", "akita", "yamagata", "fukushima"), "tohoku"),
    **dict.fromkeys(("ibaraki", "tochigi", "gunma", "saitama", "chiba", "tokyo", "kanagawa"), "kanto"),
    **dict.fromkeys(
        ("niigata", "toyama", "ishikawa", "fukui", "yamanashi", "nagano", "gifu", "shizuoka", "aichi"),
        "chubu",
    ),
    **dict.fromkeys(("mie", "shiga", "kyoto", "osaka", "hyogo", "nara", "wakayama"), "kinki"),
    **dict.fromkeys(
        ("tottori", "shimane", "okayama", "hiroshima", "yamaguchi", "tokushima", "kagawa", "ehime", "kochi"),
        "chu-shikoku",
    ),
    **dict.fromkeys(
        ("fukuoka", "saga", "nagasaki", "kumamoto", "oita", "miyazaki", "kagoshima"), "kyushu"
    ),
}

# 宿は県より狭い楽天トラベルの地区（/yado/<県>/<地区>.html）へ送る。地区は市町村と1対1ではないので、
# 宿の地名がその地区のページに出てくることを確かめて手で対応させる（2026-11-24）。
# 載っていない旅のエリア・市町村は県の宿ページへ。
TRIP_HOTEL_AREAS = {
    "higashiosaka": "osaka/toubu",
    "tokorozawa": "saitama/tokorozawa",
    "ikaruga": "nara/hokubu",  # 法隆寺周辺の宿はこの地区
    "yokohama": "kanagawa/yokohama",
    "machida": "tokyo/nishi",
    "katori": "chiba/choshi",  # 佐原の宿はこの地区
    "noto": "ishikawa/noto",
    "ibusuki": "kagoshima/nansatsu",
    "shimonoseki": "yamaguchi/shimonoseki",
    "dazaifu": "fukuoka/fukuoka",
    "saga": "saga/saga",
    "toyama": "toyama/toyama",
    "uji": "kyoto/nannbu",
    "ojiya": "niigata/kita",  # 小千谷を含む地区が無いので、隣の長岡の地区
    "ogasawara": "tokyo/Ogasawara",
    "awaji": "hyogo/awaji",
    "naruto": "tokushima/tokushima",
    "utsunomiya": "tochigi/utsunomiya",
    "koka": "shiga/shigaraki",
    "kurashiki": "okayama/kurashiki",
    "toyohashi": "aichi/mikawawan",
    "kyoto": "kyoto/shi",
    "kitakyushu": "fukuoka/kitakyusyu",
}
# キーは市町村ページのパス（/municipalities/<県>/<市>/）
MUNICIPALITY_HOTEL_AREAS = {
    "aichi/toyohashi": "aichi/mikawawan",
    "fukuoka/dazaifu": "fukuoka/fukuoka",
    "fukuoka/kitakyushu": "fukuoka/kitakyusyu",
    "kyoto/kyoto": "kyoto/shi",
    "kyoto/uji": "kyoto/nannbu",
    "shiga/koka": "shiga/shigaraki",
    "tokyo/machida": "tokyo/nishi",
    "tokyo/ogasawara": "tokyo/Ogasawara",
}
# 本土のレンタカーが旅の役に立たないところ（船で渡る島）。レンタカーのボタンを出さない。
NO_CAR_TRIPS = {"ogasawara"}
NO_CAR_MUNICIPALITIES = {"tokyo/ogasawara"}

CSS = """
    .rakuten-affiliate { margin: 22px 0; padding: 12px 14px; border: 1px solid #ece4d7; border-radius: 14px;
      background: rgba(255, 255, 255, .42); }
    .rakuten-affiliate small { color: #62564a; font-size: .72rem; letter-spacing: .08em; }
    .rakuten-affiliate p { margin: 2px 0 8px; font-size: .9rem; }
    .rakuten-affiliate-links { display: flex; flex-wrap: wrap; gap: 8px; }
    .rakuten-affiliate-links a { padding: 8px 12px; border-radius: 999px; background: #bf0000; color: #fff;
      font-size: .88rem; font-weight: 800; text-decoration: none; }
"""


def link(url: str) -> str:
    return f"https://hb.afl.rakuten.co.jp/hgc/{AFFILIATE_ID}/_RTLink159064?pc={quote(url, safe='')}{LINK_SUFFIX}"


def hotel_url(pref_slug: str, area: str = "") -> str:
    if area:
        return f"https://travel.rakuten.co.jp/yado/{area}.html"
    return f"https://travel.rakuten.co.jp/yado/{pref_slug}/"


def car_url(pref_slug: str) -> str:
    region = CAR_REGIONS.get(pref_slug)
    if region:
        return f"https://cars.travel.rakuten.co.jp/cars/area/{region}/{pref_slug}/"
    if pref_slug in ("hokkaido", "okinawa"):
        return f"https://travel.rakuten.co.jp/cars/area/{pref_slug}/"
    return CAR_TOP_URL


def block_html(
    lead: str,
    *,
    event: str,
    surface: str,
    prefecture: str = "",
    pref_slug: str = "",
    hotel_area: str = "",
    place: str = "",
    car: bool = True,
) -> str:
    """「広告・楽天トラベル」の枠。県が分かればその県の宿・レンタカー、無ければ全国。

    hotel_area（楽天の地区）があれば、宿だけはその地区へ送り、ボタンの地名を place にする。
    """
    where = prefecture or "旅先"
    hotel = hotel_url(pref_slug, hotel_area) if pref_slug else HOTEL_JAPAN_URL
    hotel_where = place if hotel_area and place else where
    links = (
        ("rakuten_hotel", hotel, f"{hotel_where}の宿を探す"),
        ("rakuten_rental_car", car_url(pref_slug) if pref_slug else CAR_TOP_URL, f"{where}のレンタカーを探す"),
    )[: 2 if car else 1]
    items = "".join(
        f'<a href="{escape(link(url), {chr(34): "&quot;"})}" target="_blank" rel="nofollow sponsored noopener" '
        f'data-track="{escape(event)}" data-surface="{escape(surface)}" data-destination="{destination}">'
        f"{escape(label)}</a>"
        for destination, url, label in links
    )
    return (
        '<aside class="rakuten-affiliate" aria-label="広告">'
        f"<small>広告・楽天トラベル</small><p>{escape(lead)}</p>"
        f'<div class="rakuten-affiliate-links">{items}</div></aside>'
    )
