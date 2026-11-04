#!/usr/bin/env python3
"""Point every page's manhole photos at Cloudflare R2 (img.pokefuta.com).

GitHub Pages の配信量を減らすため、蓋の写真は img.pokefuta.com から出す。
pages-deploy.yml がデプロイのたびに dist/manhole/image を同じパスで R2 へ複写している
（「Mirror manhole photos to R2」）。ページの種類ごとに URL の書き方が違うので
（"/manhole/image/…"・"../manhole/image/…"・"manhole/image/…"・data の絶対 URL）、
生成器ごとに直さず、できあがった dist の HTML をここでまとめて書き換える。

- 書き換えない: <meta>（og:image・twitter:image）・<link>・JSON-LD。外へ出す画像の URL は data のまま
- data.pokefuta.com の絶対 URL は <img> / <source> の中だけ書き換える（スクリプトの JSON-LD 組み立てなどに触らない）
- "BASE_PATH + 'manhole/image/'" のような連結は、前にパスが付くので書き換えない
- 戻すときは pages-deploy.yml からこのステップを外す（Pages にも同じパスの画像が残っている）
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


IMAGE_BASE = "https://img.pokefuta.com/manhole/image/"

# 書き換えない範囲: <meta …>・<link …>・<script type="application/ld+json">…</script>
_PROTECTED_RE = re.compile(
    r"<meta\b[^>]*>|<link\b[^>]*>|<script\b[^>]*application/ld\+json[^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)
# 相対パスの写真（"/manhole/image/"・"./"・"../../"・"manhole/image/"）。引用符・空白・カンマ・=・( の直後だけ
_RELATIVE_RE = re.compile(r"""(?<=["'`\s,=(])(?:/|\./|(?:\.\./)+)?manhole/image/""")
_ABSOLUTE_RE = re.compile(r"https://data\.pokefuta\.com/manhole/image/")
_IMG_TAG_RE = re.compile(r"<(?:img|source)\b[^>]*>", re.IGNORECASE)
_CONCAT_RE = re.compile(r"""\+\s*["'`]$""")


def _rewrite_relative(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if _CONCAT_RE.search(text[max(0, match.start() - 8):match.start()]):
            return match.group(0)
        return IMAGE_BASE

    return _RELATIVE_RE.sub(replace, text)


def _rewrite_open(text: str) -> str:
    text = _rewrite_relative(text)
    return _IMG_TAG_RE.sub(lambda m: _ABSOLUTE_RE.sub(IMAGE_BASE, m.group(0)), text)


def use_image_host(html: str) -> str:
    """HTML の中の蓋の写真を img.pokefuta.com に向ける（meta・link・JSON-LD はそのまま）。"""
    out: list[str] = []
    pos = 0
    for match in _PROTECTED_RE.finditer(html):
        out.append(_rewrite_open(html[pos:match.start()]))
        out.append(match.group(0))
        pos = match.end()
    out.append(_rewrite_open(html[pos:]))
    return "".join(out)


def rewrite_dist(dist: Path) -> int:
    """dist の全 HTML を書き換え、変わったファイルの数を返す。"""
    changed = 0
    for path in sorted(dist.rglob("*.html")):
        html = path.read_text(encoding="utf-8")
        new_html = use_image_host(html)
        if new_html != html:
            path.write_text(new_html, encoding="utf-8")
            changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    print(f"[use_image_host] {rewrite_dist(args.dist)} HTML files now read photos from {IMAGE_BASE}")


if __name__ == "__main__":
    main()
