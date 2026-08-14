#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared address extraction logic for pokefuta scrapers.

Used by:
  - update_pokefuta.py  (daily CI crawler)
  - update_address_only.py  (manual address fill tool)
"""
import re

from bs4 import BeautifulSoup


# 詳細ページは <div class="block map"><h2>マンホール場所</h2><p>住所</p> という
# 構造で住所を持つ。全文正規表現より確実なのでこちらを最優先で使う。
ADDRESS_HEADING = "マンホール場所"

# 都道府県プレフィクス。「県」「府」だけにマッチさせると県名が落ちるので
# 必ず名前ごと拾う（例: 「滋賀県大津市…」→「県大津市…」になる事故を防ぐ）。
PREF_PREFIX = r'(?:北海道|東京都|大阪府|京都府|[一-鿿]{2,3}[県道府])'


def extract_address_from_dom(html: str) -> str:
    """Extract the address from the labelled DOM node. Returns "" if absent."""
    soup = BeautifulSoup(html, "html.parser")
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) != ADDRESS_HEADING:
            continue
        p = h2.find_next_sibling("p")
        if p is None:
            continue
        # 全角スペースを含む連続空白を単一の半角スペースに畳む
        return " ".join(p.get_text(" ", strip=True).split())
    return ""


def extract_address_from_html(html: str) -> str:
    """Extract Japanese address from manhole detail page HTML.

    Tier 0 reads the labelled DOM node (`マンホール場所` の直後の <p>), which is
    what the site actually renders. The regex cascade below only runs when that
    node is missing:
      1. Specific detail (numbers, stations, parks)
      2. Town + number suffix
      3. Prefecture + city + place name
      4. Broad range (up to 100 chars after city)
      5. Fallback: prefecture + city only
    """
    dom_address = extract_address_from_dom(html)
    if dom_address:
        return dom_address

    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text()

    noise = ['｜', 'ポケモン', 'マンホール', 'ポケふた']

    specific_detail = (
        r'([一-鿿]*.{0,3}?(?:県|府|道|都).{0,20}?(?:市|区|町|村).{0,80}?'
        r'(?:[一-鿿]+町[一-鿿]*(?:\d+丁目(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+)?|\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+)?'
        r'|大字[一-鿿]+\d+|字[一-鿿]+\d+'
        r'|\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+)?'
        r'|[一-鿿]+駅|[一-鿿]+センター'
        r'|[一-鿿]+公園))'
    )
    town_num     = r'([一-鿿]*.{0,3}?(?:県|府|道|都).{0,20}?(?:市|区|町|村)[一-鿿]+\d+)'
    # tier3/5 は県名から拾い、町名以降を打ち切らない。`/` を挟む形は
    # 「高知県/三原村」のような見出し行なので候補から除外する。
    place_name   = r'(' + PREF_PREFIX + r'[^\n。/]*?(?:市|区|町|村)[一-鿿]{2,}(?=[^\n。\s]|$))'
    broad        = r'([一-鿿]*.{0,3}?(?:県|府|道|都).{0,20}?(?:市|区|町|村).{0,100}?[^\n。\s](?:\s|$))'
    fallback     = r'(' + PREF_PREFIX + r'[^\n。/]*?(?:市|区|町|村))'

    lines = text_content.split('\n')

    for pattern, min_len in [
        (specific_detail, 0),
        (town_num,        0),
        (place_name,      0),
        (broad,          10),
        (fallback,        0),
    ]:
        for line in lines:
            for candidate in re.findall(pattern, line):
                candidate = candidate.strip()
                if len(candidate) > min_len and not any(kw in candidate for kw in noise):
                    return candidate

    return ""
