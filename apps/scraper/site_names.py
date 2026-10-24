"""図鑑（data.pokefuta.com）のサイト名。言語ごとに1つだけ持ち、og:site_name・地図の共有タイトルはここに合わせる。

検索結果のサイト名は、トップの WebSite.name・og:site_name・title と、サイト内での呼ばれ方から
Google が決める。名前がページごとにばらけていると確信が持てず、ドメイン名（pokefuta.com）で出る
（2026-10-24 の検索結果）。test_site_names.py が、多言語トップ・地図の文言ファイルと食い違わないかを見る。
「ポケふた」単体はマンホールの名前で、サイト名には使わない。
"""

from html import escape

SITE_NAMES = {
    "ja": "ポケふた図鑑",
    "en": "Pokéfuta Directory",
    "zh-TW": "寶可夢人孔蓋圖鑑",
    "zh-CN": "宝可梦井盖图鉴",
    "ko": "포켓몬 맨홀 도감",
}

_LANG_OF_LOCALE = {"ja_JP": "ja", "en_US": "en", "zh_TW": "zh-TW", "zh_CN": "zh-CN", "ko_KR": "ko"}


def site_name_for_locale(og_locale: str) -> str:
    return SITE_NAMES[_LANG_OF_LOCALE[og_locale]]


def og_site_name(og_locale: str) -> str:
    """<meta property="og:site_name">。og:locale（ja_JP など）から言語を決める。"""
    return f'<meta property="og:site_name" content="{escape(site_name_for_locale(og_locale), quote=True)}">'
