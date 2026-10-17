#!/usr/bin/env python3
"""gmanhole_map.html にガンダムマンホールの都道府県別一覧を静的に差し込んで dist へ書き出す。

地図は Leaflet で描くので、元の HTML には設置場所の本文が無い。「ガンダムマンホール 一覧 地図」
などの検索はこのページが受けている（作品ガイド /characters/gundam/ より表示・順位とも上）ため、
一覧をこのページの本文として持たせる。テンプレートは apps/web/gmanhole_map.html で、
マーカーの位置にだけ差し込む（件数 <!-- GUNDAM_SUMMARY --> は何か所でも、一覧 <!-- GUNDAM_LIST --> は1か所）。
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote

try:
    from apps.scraper.generate_character_manhole_page import ROOT, _is_active, load_ndjson
    from apps.scraper.generate_character_work_pages import safe_url
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from generate_character_manhole_page import ROOT, _is_active, load_ndjson
    from generate_character_work_pages import safe_url
    from prefectures import PREFECTURE_ORDER

DEFAULT_TEMPLATE = ROOT / "apps/web/gmanhole_map.html"
DEFAULT_GUNDAM = ROOT / "docs/gmanhole.ndjson"
SUMMARY_MARKER = "<!-- GUNDAM_SUMMARY -->"
LIST_MARKER = "<!-- GUNDAM_LIST -->"


def gundam_records(records: list[dict]) -> list[dict]:
    """掲載中で都道府県が分かるものだけ。取り込みに失敗した行（status=invalid）は出さない。"""
    order = {pref: i for i, pref in enumerate(PREFECTURE_ORDER)}
    selected = [r for r in records if _is_active(r) and r.get("prefecture")]
    return sorted(selected, key=lambda r: (order.get(r["prefecture"], 999), str(r.get("city") or ""), str(r.get("id"))))


def summary_html(records: list[dict]) -> str:
    prefs = {r["prefecture"] for r in records}
    return f"{len(records)}基・{len(prefs)}都道府県"


def list_html(records: list[dict]) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["prefecture"]].append(record)
    sections = []
    for pref, rows in groups.items():
        items = []
        for r in rows:
            name = escape(str(r.get("title") or "ガンダムマンホール"))
            # 住所は市町村から始まるので、市町村名を前に重ねない。住所が無い行だけ市町村を出す
            place = escape(str(r.get("address") or r.get("city") or ""))
            source = safe_url(r.get("detail_url"))
            link = (f' <a href="{escape(source)}" target="_blank" rel="noopener noreferrer">出典 ↗</a>'
                    if source else "")
            items.append(f'<li id="gundam-{quote(str(r.get("id")), safe="")}"><strong>{name}</strong>'
                         f'{link}<span>{place}</span></li>')
        sections.append(f'<details class="gundam-pref"><summary>{escape(pref)} <small>{len(rows)}基</small></summary>'
                        f'<ul>{"".join(items)}</ul></details>')
    return (f'<section id="gundam-list" class="gundam-list" aria-labelledby="gundam-list-heading">'
            f'<h2 id="gundam-list-heading">ガンダムマンホール一覧（都道府県別・{summary_html(records)}）</h2>'
            '<p>都道府県を開くと、設置場所の名前・住所と出典（ガンダムマンホール公式サイト）を確認できます。'
            '移設・撤去や施設の開放時間は、訪問前に出典でご確認ください。'
            '回り方や作品の解説は<a href="./characters/gundam/">ガンダムマンホールのガイド</a>にまとめています。</p>'
            f'{"".join(sections)}</section>')


def render(template: str, records: list[dict]) -> str:
    if not records:
        raise ValueError("No active Gundam manholes with a prefecture")
    if template.count(LIST_MARKER) != 1:
        raise ValueError(f"{LIST_MARKER} must appear exactly once in the template")
    if SUMMARY_MARKER not in template:
        raise ValueError(f"{SUMMARY_MARKER} is missing from the template")
    return template.replace(SUMMARY_MARKER, summary_html(records)).replace(LIST_MARKER, list_html(records))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--gundam", type=Path, default=DEFAULT_GUNDAM)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = gundam_records(load_ndjson(args.gundam))
    html = render(args.template.read_text(encoding="utf-8"), records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({summary_html(records)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
