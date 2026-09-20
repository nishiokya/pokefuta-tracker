#!/usr/bin/env python3
"""トップの「目的から探す」テーマチップを `dataset/tag_meta.json` から生成する。

以前は index.html に7個のチップが手書きされていて、地図のテーマ一覧と
顔ぶれもラベルも食い違っていた（史跡11枚が載って公園46枚が落ちている、
ガンダムだけ絵文字が無い、など）。選定は tag_meta.TagMeta.top_chip_slugs に任せ、
ここは描画だけを行う。

チップは内部リンクなので**静的HTMLに入っている必要がある**（クロールされる）。
そのため index.html にはマーカーで囲んだ生成済みブロックをコミットしておき、
ビルド時に dist/index.html を同じ規則で作り直す。両者がずれていないかは
test_generate_top_tag_chips.py が見る。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper.tag_meta import TagMeta, count_tags, load_tag_meta
    from apps.scraper.generate_tag_pages import load_records
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from tag_meta import TagMeta, count_tags, load_tag_meta
    from generate_tag_pages import load_records

DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_SOURCE = ROOT / "apps" / "web" / "index.html"

START_MARKER = "<!-- tag-chips:start -->"
END_MARKER = "<!-- tag-chips:end -->"
INDENT = " " * 10


def render_chips(meta: TagMeta, counts: dict[str, int]) -> str:
    """マーカーの間に入れるチップ列を返す。"""
    lines = []
    for slug in meta.top_chip_slugs(counts):
        href = meta.href(slug)
        destination = "tag_page" if href.startswith("/tags/") else "map_tag_filter"
        count = counts.get(slug, 0)
        lines.append(
            f'{INDENT}<a class="hub-chip" href="{href}" '
            f"onclick=\"trackEvent('click_hub_tag',{{tag:'{slug}',destination:'{destination}'}})\">"
            f'{escape(meta.chip_label(slug))} '
            f'<span class="chip-count">{count}枚</span></a>'
        )
    return "\n".join(lines)


def apply_chips(html: str, chips: str) -> str:
    """マーカー間を差し替える。マーカーが無ければ何もしない（他ページを壊さない）。"""
    start = html.find(START_MARKER)
    end = html.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return html
    head = html[: start + len(START_MARKER)]
    tail = html[end:]  # END_MARKER 以降
    return f"{head}\n{chips}\n{INDENT}{tail}"


def build_chips(manholes: Path, tag_meta: Path | None = None) -> str:
    meta = load_tag_meta(tag_meta)
    counts = count_tags(load_records(manholes))
    return render_chips(meta, counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, nargs="?", default=None,
                        help="書き換える HTML（省略時は apps/web/index.html）")
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--tag-meta", type=Path, default=None)
    parser.add_argument("--check", action="store_true",
                        help="書き換えずに、ずれていたら終了コード1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.target or DEFAULT_SOURCE
    chips = build_chips(args.manholes, args.tag_meta)
    html = target.read_text(encoding="utf-8")
    updated = apply_chips(html, chips)
    if args.check:
        if updated != html:
            print(f"[generate_top_tag_chips] {target} is stale — run without --check")
            return 1
        print(f"[generate_top_tag_chips] {target} is up to date")
        return 0
    if updated == html:
        print(f"[generate_top_tag_chips] {target} unchanged")
        return 0
    target.write_text(updated, encoding="utf-8")
    print(f"[generate_top_tag_chips] updated {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
