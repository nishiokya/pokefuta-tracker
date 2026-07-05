#!/usr/bin/env python3
"""Inject the shared navigation header into every generated site page."""

from __future__ import annotations

import argparse
from pathlib import Path


STYLESHEET = '<link rel="stylesheet" href="/assets/site-header.css">'
HEADER = """<header class="site-header">
  <div class="site-header__inner">
    <a class="site-header__brand" href="/">
      <span class="site-header__brand-name">ポケふた</span>
      <span class="site-header__brand-sub">DATABASE</span>
    </a>
    <nav class="site-header__nav" aria-label="メインナビゲーション">
      <a class="site-header__link" href="/">トップ</a>
      <a class="site-header__link" href="/map.html">地図</a>
      <a class="site-header__link" href="/summary/">全国一覧</a>
      <a class="site-header__link" href="/pokemon/">ポケモン</a>
      <a class="site-header__link" href="/nearby.html">現在地付近</a>
      <a class="site-header__link" href="/gmanhole_map.html">キャラMH</a>
    </nav>
  </div>
</header>"""


def inject(html: str) -> str:
    """Return HTML with the shared header, or unchanged HTML when unsuitable."""
    lower = html.lower()
    if "<body" not in lower or "http-equiv=\"refresh\"" in lower:
        return html
    if "class=\"top-app-bar\"" in html or "class=\"site-header\"" in html:
        return html

    if STYLESHEET not in html:
        html = html.replace("</head>", f"  {STYLESHEET}\n</head>", 1)

    body_start = html.lower().find("<body")
    body_end = html.find(">", body_start)
    body_tag = html[body_start : body_end + 1]
    if 'class="' in body_tag:
        new_body_tag = body_tag.replace('class="', 'class="has-site-header ', 1)
    else:
        new_body_tag = body_tag[:-1] + ' class="has-site-header">'
    html = html[:body_start] + new_body_tag + html[body_end + 1 :]

    insert_at = body_start + len(new_body_tag)
    return html[:insert_at] + "\n" + HEADER + html[insert_at:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="dist", type=Path)
    args = parser.parse_args()

    updated = 0
    for path in sorted(args.root.rglob("*.html")):
        original = path.read_text(encoding="utf-8")
        result = inject(original)
        if result != original:
            path.write_text(result, encoding="utf-8")
            updated += 1
    print(f"[inject_site_header] updated {updated} HTML files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
