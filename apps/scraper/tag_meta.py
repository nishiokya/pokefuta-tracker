"""テーマタグのメタデータ（`dataset/tag_meta.json`）の読み込みと選定ルール。

トップの「目的から探す」・地図のテーマ絞り込み・`/tags/` のテーマページは
以前それぞれ手書きのリストを持っていて、載せるタグもラベルも絵文字も食い違っていた
（史跡11枚がトップにあって公園46枚が無い、ガンダムがトップだけ絵文字なし、など）。
選定ルールをここに1つだけ置き、各面はこのモジュール（と生成された
`assets/tag-meta.js`）を読む。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAG_META = ROOT / "dataset" / "tag_meta.json"


class TagMeta:
    """タグ定義と、どの面に何を出すかの判定をまとめたもの。"""

    def __init__(self, payload: dict) -> None:
        self.min_count: int = int(payload.get("min_count", 0))
        self.top_chip_limit: int = int(payload.get("top_chip_limit", 0))
        self.priority: list[str] = list(payload.get("priority", []))
        self.tags: list[dict] = [
            tag for tag in payload.get("tags", [])
            if isinstance(tag, dict) and tag.get("slug")
        ]
        self.by_slug: dict[str, dict] = {tag["slug"]: tag for tag in self.tags}

    def label(self, slug: str) -> str:
        return self.by_slug.get(slug, {}).get("label", slug)

    def emoji(self, slug: str) -> str:
        return self.by_slug.get(slug, {}).get("emoji", "")

    def chip_label(self, slug: str) -> str:
        """絵文字＋ラベル。どの面でも同じ見え方になるようここで組み立てる。"""
        emoji = self.emoji(slug)
        label = self.label(slug)
        return f"{emoji} {label}".strip()

    def page_slugs(self) -> list[str]:
        """静的ページ（/tags/<slug>/）を持つタグ。"""
        return [tag["slug"] for tag in self.tags if tag.get("page")]

    def featured_slugs(self) -> list[str]:
        return [
            tag["slug"] for tag in self.tags
            if tag.get("featured") and tag.get("public", True)
        ]

    def public_slugs(self) -> list[str]:
        """トップと地図のテーマ一覧に公開するタグ。"""
        return [tag["slug"] for tag in self.tags if tag.get("public", True)]

    def _sort_key(self, slug: str, counts: dict[str, int]):
        """地図のテーマ一覧と同じ並び: priority 順 → 残りは枚数降順。"""
        if slug in self.priority:
            return (0, self.priority.index(slug), 0)
        return (1, 0, -counts.get(slug, 0))

    def visible_slugs(self, counts: dict[str, int]) -> list[str]:
        """min_count を満たすタグを、地図と同じ順序で返す。"""
        return sorted(
            (
                tag["slug"] for tag in self.tags
                if tag.get("public", True)
                and counts.get(tag["slug"], 0) >= self.min_count
            ),
            key=lambda slug: self._sort_key(slug, counts),
        )

    def top_chip_slugs(self, counts: dict[str, int]) -> list[str]:
        """トップに並べるタグ。featured を先に、残りは枚数降順で上限まで。

        以前は手書きだったので、史跡（11枚）が載って公園（46枚）が落ちていた。
        """
        visible = self.visible_slugs(counts)
        featured = [slug for slug in visible if self.by_slug[slug].get("featured")]
        rest = sorted(
            (slug for slug in visible if slug not in featured),
            key=lambda slug: (-counts.get(slug, 0), slug),
        )
        return (featured + rest)[: self.top_chip_limit]

    def href(self, slug: str) -> str:
        """その面からの遷移先。ページを持つタグは静的ページ、無ければ地図の絞り込み。"""
        if self.by_slug.get(slug, {}).get("page"):
            return f"/tags/{slug}/"
        return f"/map.html?tag={slug}"

    def as_client_payload(self) -> dict:
        """地図の JS に渡す形。読み手が使わない `_comment` は落とす。"""
        return {
            "min_count": self.min_count,
            "top_chip_limit": self.top_chip_limit,
            "priority": self.priority,
            "tags": self.tags,
        }


def load_tag_meta(path: Path | None = None) -> TagMeta:
    payload = json.loads((path or DEFAULT_TAG_META).read_text(encoding="utf-8"))
    return TagMeta(payload)


def count_tags(records: list[dict]) -> dict[str, int]:
    """レコードの `tags` を数える。`titles` は付与ルールが別なので使わない。"""
    counts: dict[str, int] = {}
    for record in records:
        for tag in record.get("tags") or []:
            if isinstance(tag, str) and tag:
                counts[tag] = counts.get(tag, 0) + 1
    return counts
