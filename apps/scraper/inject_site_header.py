#!/usr/bin/env python3
"""Inject the shared navigation header into every generated site page."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


STYLESHEET_TEMPLATE = '<link rel="stylesheet" href="{asset_base}assets/site-header.css">'
HEADER_TEMPLATE = """<header class="site-header">
  <div class="site-header__inner">
    <a class="site-header__brand" href="{page_base}">
      <span class="site-header__mark" aria-hidden="true"><span class="site-header__mark-core"></span></span>
      <span class="site-header__brand-name">ポケふた図鑑</span>
    </a>
    <nav class="site-header__nav" aria-label="{nav_aria}">
      <a class="site-header__link" href="{page_base}pokemon/">{nav_pokemon}</a>
      <a class="site-header__link" href="{page_base}map.html"><span class="site-header__label--desktop">{nav_map}</span><span class="site-header__label--mobile">{nav_map_mobile}</span></a>
      <a class="site-header__link" href="{page_base}summary/"><span class="site-header__label--desktop">{nav_summary}</span><span class="site-header__label--mobile">{nav_summary_mobile}</span></a>
      <a class="site-header__link" href="{asset_base}character_manholes.html"><span class="site-header__label--desktop">{nav_character}</span><span class="site-header__label--mobile">{nav_character_mobile}</span></a>
      <a class="site-header__link site-header__auth-link--desktop" data-login-link data-nav-target="login" data-stamp-page="https://pokefuta.com/" data-stamp-label="{nav_stamp}" href="https://pokefuta.com/login?from=data">{nav_login}</a>
      <a class="site-header__link site-header__auth-link--mobile" data-login-link data-nav-target="login" data-stamp-page="https://pokefuta.com/" data-stamp-label="{nav_stamp_mobile}" href="https://pokefuta.com/login?from=data">{nav_login}</a>
    </nav>
  </div>
</header>"""
SESSION_BADGE_SCRIPT_TEMPLATE = (
    '<script src="{asset_base}assets/session-badge.js" defer></script>'
)

NAV_LABELS = {
    "ja": ("メインナビゲーション", "マップ", "サマリー", "ポケモン", "キャラマンホール", "スタンプ帳", "ログイン"),
    "en": ("Main navigation", "Map", "Summary", "Pokémon", "Character Manholes", "Stamp Book", "Login"),
    "zh-TW": ("主導覽", "地圖", "摘要", "神奇寶貝", "角色人孔蓋", "集章冊", "登入"),
    "zh-CN": ("主导航", "地图", "摘要", "宝可梦", "角色井盖", "集章册", "登录"),
    "ko": ("메인 내비게이션", "지도", "요약", "포켓몬", "캐릭터 맨홀", "스탬프북", "로그인"),
}

NAV_MOBILE_LABELS = {
    "ja": ("地図", "集計", "キャラ", "スタンプ帳"),
    "en": ("Map", "Stats", "Characters", "Stamps"),
    "zh-TW": ("地圖", "統計", "角色", "集章"),
    "zh-CN": ("地图", "统计", "角色", "集章"),
    "ko": ("지도", "통계", "캐릭터", "스탬프"),
}

LEGACY_HEADER_RE = re.compile(
    r'<header\s+class="top-app-bar"[^>]*>.*?</header>',
    flags=re.DOTALL,
)


def _prefix(target: Path, parent: Path) -> str:
    relative = os.path.relpath(target, parent).replace(os.sep, "/")
    return "./" if relative == "." else f"{relative}/"


def _language(html: str) -> str:
    match = re.search(r'<html\b[^>]*\blang=["\']([^"\']+)', html, re.IGNORECASE)
    return match.group(1) if match and match.group(1) in NAV_LABELS else "ja"


def inject(html: str, asset_base: str = "./", page_base: str | None = None) -> str:
    """Return HTML with the shared header, or unchanged HTML when unsuitable."""
    lower = html.lower()
    if "<body" not in lower or "http-equiv=\"refresh\"" in lower:
        return html
    if "class=\"site-header\"" in html:
        return html

    page_base = page_base or asset_base
    language = _language(html)
    labels = NAV_LABELS[language]
    mobile_labels = NAV_MOBILE_LABELS[language]
    substitutions = dict(
        zip(
            ("nav_aria", "nav_map", "nav_summary", "nav_pokemon", "nav_character", "nav_stamp", "nav_login"),
            labels,
        )
    )
    substitutions.update(
        zip(
            ("nav_map_mobile", "nav_summary_mobile", "nav_character_mobile", "nav_stamp_mobile"),
            mobile_labels,
        )
    )
    stylesheet = STYLESHEET_TEMPLATE.format(asset_base=asset_base)
    header = HEADER_TEMPLATE.format(asset_base=asset_base, page_base=page_base, **substitutions)
    if "session-badge.js" not in html:
        header += "\n" + SESSION_BADGE_SCRIPT_TEMPLATE.format(asset_base=asset_base)

    if stylesheet not in html:
        html = html.replace("</head>", f"  {stylesheet}\n</head>", 1)

    body_start = html.lower().find("<body")
    body_end = html.find(">", body_start)
    body_tag = html[body_start : body_end + 1]
    if 'class="' in body_tag:
        new_body_tag = body_tag.replace('class="', 'class="has-site-header ', 1)
    else:
        new_body_tag = body_tag[:-1] + ' class="has-site-header">'
    html = html[:body_start] + new_body_tag + html[body_end + 1 :]

    if LEGACY_HEADER_RE.search(html):
        return LEGACY_HEADER_RE.sub(header, html, count=1)

    insert_at = body_start + len(new_body_tag)
    return html[:insert_at] + "\n" + header + html[insert_at:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="dist", type=Path)
    args = parser.parse_args()

    updated = 0
    for path in sorted(args.root.rglob("*.html")):
        original = path.read_text(encoding="utf-8")
        language = _language(original)
        localized_root = args.root / language if language != "ja" else args.root
        asset_base = _prefix(args.root, path.parent)
        page_base = _prefix(localized_root, path.parent)
        result = inject(original, asset_base=asset_base, page_base=page_base)
        if result != original:
            path.write_text(result, encoding="utf-8")
            updated += 1
    print(f"[inject_site_header] updated {updated} HTML files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
