"""デザインマンホール投稿に付けるタグ（グループ）の台帳。正は dataset/manhole_groups.json。

グループは2種類ある。
- catalog: 図鑑に設置場所の一覧がある作品（ガンダム・アイマスなど）。``works`` が設置場所データの
  ``work`` と対応し、設置場所に紐付いた投稿（canonical_ref）には自動でこのタグが付く。
- open: 一覧が無いもの（野球など）。投稿に手でタグを付ける（design_manhole_overrides.json の ``tags``）。

写真館は api/design_manhole_tags.json を読む。slug は写真館の URL に入るので英小文字・数字・ハイフンだけ。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KINDS = ("catalog", "open")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GROUPS = ROOT / "dataset/manhole_groups.json"


def validate_groups(raw: object) -> list[dict]:
    """台帳の形を確かめて、そのまま返す。壊れていたら ValueError（デプロイを止める）。"""
    if not isinstance(raw, list):
        raise ValueError("manhole_groups.json must be a list")
    seen: set[str] = set()
    works_owner: dict[str, str] = {}
    for group in raw:
        if not isinstance(group, dict):
            raise ValueError("each group must be an object")
        slug = group.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            raise ValueError(f"invalid group slug: {slug!r}")
        if slug in seen:
            raise ValueError(f"duplicate group slug: {slug}")
        seen.add(slug)
        for key in ("label", "name", "category"):
            if not isinstance(group.get(key), str) or not group[key].strip():
                raise ValueError(f"group {slug}: {key} is required")
        if group.get("kind") not in KINDS:
            raise ValueError(f"group {slug}: kind must be one of {KINDS}")
        works = group.get("works", [])
        if not isinstance(works, list) or not all(isinstance(w, str) and w for w in works):
            raise ValueError(f"group {slug}: works must be a list of strings")
        if group["kind"] == "catalog" and not works:
            raise ValueError(f"group {slug}: catalog group needs works")
        for work in works:
            if work in works_owner:
                raise ValueError(f"work {work!r} is in both {works_owner[work]} and {slug}")
            works_owner[work] = slug
    by_slug = {group["slug"]: group for group in raw}
    for group in raw:
        parent = group.get("parent")
        if parent is None:
            continue
        # 段は2つまで（親の親は作らない）。写真館のチップが2段だから
        if parent not in by_slug or parent == group["slug"] or by_slug[parent].get("parent"):
            raise ValueError(f"group {group['slug']}: invalid parent {parent!r}")
    return raw


def load_groups(path: Path = DEFAULT_GROUPS) -> list[dict]:
    return validate_groups(json.loads(path.read_text(encoding="utf-8")))


def group_for_work(groups: list[dict], work: str) -> dict | None:
    return next((group for group in groups if work in group.get("works", [])), None)


def expand_tags(groups: list[dict], slugs: list[str]) -> list[str]:
    """台帳にあるタグだけを残し、親のタグも足す（子の「カープ」は「野球」にも出す）。順番は渡された順。"""
    by_slug = {group["slug"]: group for group in groups}
    out: list[str] = []
    for slug in slugs:
        group = by_slug.get(slug)
        if group is None:
            continue
        for item in (slug, group.get("parent")):
            if item and item not in out:
                out.append(item)
    return out
