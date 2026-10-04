"""市区町村ページ（/municipalities/）の対象と URL を決める共有ロジック。

市区町村ページ・都道府県ページ・マンホール詳細・サイトマップが同じ判定を使う。
判定が2箇所でズレると、存在しないページへリンクしたり、作ったページがどこからも
辿れなかったりする。

## どの自治体にページを作るか

1. 設置枚数が MIN_MANHOLES 枚以上
2. **県内のポケふたが全部その自治体にあるわけではない**

2 が肝心。指宿市（鹿児島県の9枚すべて）や東大阪市（大阪府の5枚すべて）のように
県の全数が1自治体に集まっている場合、市区町村ページは県ページと地図・一覧・写真が
まったく同じになる。同じ内容の2ページを並べると、すでに検索で評価されている
県ページを自分で薄めるだけなので作らない。ランキングからは県ページへ送る。
（2026-10 時点で3枚以上は22自治体あり、うち14自治体がこれに当たる）
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

try:
    from apps.scraper.display_names import municipality_label
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import municipality_label

try:
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SLUGS = ROOT / "dataset" / "municipality_slugs.json"

# Phase 1 は3枚以上。2枚まで広げるときはここを変える（slug は2枚の自治体ぶんも用意済み）。
MIN_MANHOLES = 3
# ランキングに名前を出す下限。1枚の自治体は数百あるので件数だけ書く。
RANKING_MIN_MANHOLES = 2


@dataclass
class Municipality:
    prefecture: str
    name: str
    records: list[dict] = field(default_factory=list)
    prefecture_total: int = 0
    # 全国の市区町村で、自分より多い自治体の数 + 1（同数は同順位）
    national_rank: int = 0
    # 同じ順位の自治体の数（自分を含む）
    national_tied: int = 1
    slug: str | None = None

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def key(self) -> str:
        return f"{self.prefecture}/{self.name}"

    @property
    def covers_prefecture(self) -> bool:
        """県内のポケふたがすべてこの自治体にある。"""
        return self.count == self.prefecture_total

    @property
    def prefecture_slug(self) -> str:
        return PREFECTURE_SLUGS.get(self.prefecture, "")

    @property
    def has_page(self) -> bool:
        return (
            self.count >= MIN_MANHOLES
            and not self.covers_prefecture
            and bool(self.slug)
            and bool(self.prefecture_slug)
        )

    @property
    def path(self) -> str | None:
        if not self.has_page:
            return None
        return f"/municipalities/{self.prefecture_slug}/{self.slug}/"


def load_slugs(path: Path = DEFAULT_SLUGS) -> dict[str, str]:
    """ローマ字 slug の対応表。壊れていたらビルドを止める（手で編集するファイルなので）。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    slugs = payload["slugs"]
    seen: dict[tuple[str, str], str] = {}
    for key, slug in slugs.items():
        prefecture, _, _name = key.partition("/")
        if prefecture not in PREFECTURE_SLUGS or not _name:
            raise ValueError(f"municipality_slugs.json: 不正なキー {key!r}")
        if not slug or not slug.isascii() or not slug.replace("-", "").isalnum() or slug != slug.lower():
            raise ValueError(f"municipality_slugs.json: 不正な slug {key!r}: {slug!r}")
        if (prefecture, slug) in seen:
            raise ValueError(f"municipality_slugs.json: 同じ県で slug が重複 {seen[(prefecture, slug)]!r} / {key!r}")
        seen[(prefecture, slug)] = key
    return slugs


def build_municipalities(records: list[dict], slugs: dict[str, str]) -> list[Municipality]:
    """設置済み・設置予定を含む active な蓋を自治体ごとにまとめる。多い順、同数は県順→名前順。

    枚数の数え方は都道府県ページ（active なら設置予定も含む）と詳細ページの「町田 6枚」に揃える。
    """
    active = [r for r in records if r.get("status", "active") == "active"]
    prefecture_totals = Counter(r.get("prefecture", "") for r in active)
    groups: dict[tuple[str, str], Municipality] = {}
    for record in active:
        prefecture = str(record.get("prefecture") or "")
        if prefecture not in PREFECTURE_SLUGS:
            continue
        name = municipality_label(record)
        if not name or name == prefecture:
            continue
        group = groups.get((prefecture, name))
        if group is None:
            group = groups[(prefecture, name)] = Municipality(
                prefecture=prefecture,
                name=name,
                prefecture_total=prefecture_totals[prefecture],
                slug=slugs.get(f"{prefecture}/{name}"),
            )
        group.records.append(record)

    items = list(groups.values())
    counts = Counter(item.count for item in items)
    for item in items:
        item.national_rank = 1 + sum(1 for other in items if other.count > item.count)
        item.national_tied = counts[item.count]
    pref_order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    items.sort(key=lambda m: (-m.count, pref_order.get(m.prefecture, 99), m.name))
    return items


def missing_slugs(municipalities: list[Municipality]) -> list[str]:
    """ページを作る条件を満たすのに slug が無い自治体。生成時の警告とテストで使う。"""
    return [
        m.key for m in municipalities
        if m.count >= MIN_MANHOLES and not m.covers_prefecture and not m.slug
    ]


def page_paths(records: list[dict], slugs: dict[str, str] | None = None) -> dict[tuple[str, str], str]:
    """(都道府県, 市区町村名) → ページのパス。ページを作る自治体だけ。"""
    if slugs is None:
        slugs = load_slugs()
    return {
        (m.prefecture, m.name): m.path
        for m in build_municipalities(records, slugs)
        if m.path
    }
