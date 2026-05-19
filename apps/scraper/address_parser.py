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


def extract_address_from_html(html: str) -> str:
    """Extract Japanese address from manhole detail page HTML.

    Uses a 5-tier pattern cascade with noise filtering:
      1. Specific detail (numbers, stations, parks)
      2. Town + number suffix
      3. Prefecture + city + place name
      4. Broad range (up to 100 chars after city)
      5. Fallback: prefecture + city only
    """
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
    place_name   = r'((?:県|府|道|都)[^\n。]*?(?:市|区|町|村)[一-鿿]{2,3}(?=[^\n。\s]|$))'
    broad        = r'([一-鿿]*.{0,3}?(?:県|府|道|都).{0,20}?(?:市|区|町|村).{0,100}?[^\n。\s](?:\s|$))'
    fallback     = r'((?:県|府|道|都)[^\n。]*?(?:市|区|町|村))'

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
