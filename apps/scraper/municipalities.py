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
import re
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
DEFAULT_TOTALS = ROOT / "dataset" / "prefecture_municipality_totals.json"

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


# ---------------------------------------------------------------------------
# 自治体カバー率（都道府県ページ・市区町村ランキングで使う）
#
# 「ポケふたの枚数」だけでは見えない、県としての展開の違いを出す。宮城・岩手・三重・
# 鳥取・香川・福井・宮崎の7県は県内のすべての市町村に1枚以上あり（2026-10 時点）、
# 北海道は50枚あっても179市町村のうち50にとどまる。どちらも市区町村ページや
# 自治体の公式サイトには無い、県単位でしか言えない情報。
# ---------------------------------------------------------------------------

# 政令市の区まで入ったラベル（名古屋市中区）は市で数える。市町村数の分母は区を数えないため
_DESIGNATED_CITY_WARD = re.compile(r"^(.+?市).+区$")


def coverage_name(record: dict) -> str:
    """カバー率を数えるときの自治体名。municipality_label の揺れを数え方の単位に揃える。

    - 「名古屋市中区」→「名古屋市」（政令市の区は分母に入らない）
    - 「台東区上野」→「台東区」（東京23区。city に町名まで入っている実データがある）
    """
    name = municipality_label(record)
    ward = _DESIGNATED_CITY_WARD.match(name)
    if ward:
        return ward.group(1)
    if record.get("prefecture") == "東京都" and "区" in name:
        head = name[: name.index("区") + 1]
        if not re.search(r"[市町村]", head):
            return head
    return name


@dataclass
class PrefectureCoverage:
    prefecture: str
    total: int
    # 市町村名 → 枚数
    counts: dict[str, int] = field(default_factory=dict)
    # 設置市町村の数で並べた全国順位（同数は同順位）
    covered_rank: int = 0

    @property
    def covered(self) -> int:
        return len(self.counts)

    @property
    def uncovered(self) -> int:
        return max(self.total - self.covered, 0)

    @property
    def percent(self) -> int:
        return round(self.covered / self.total * 100) if self.total else 0

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and self.covered >= self.total

    @property
    def multi(self) -> list[tuple[str, int]]:
        """2枚以上ある市町村（多い順・名前順）。"""
        return sorted(
            ((name, count) for name, count in self.counts.items() if count >= 2),
            key=lambda item: (-item[1], item[0]),
        )


def load_municipality_totals(path: Path = DEFAULT_TOTALS) -> dict[str, int]:
    """都道府県ごとの市町村数。手で更新するファイルなので、壊れていたらビルドを止める。"""
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    if set(totals) != set(PREFECTURE_ORDER):
        raise ValueError("prefecture_municipality_totals.json: 47都道府県が揃っていない")
    if any(not isinstance(v, int) or v <= 0 for v in totals.values()):
        raise ValueError("prefecture_municipality_totals.json: 市町村数は正の整数")
    return totals


def prefecture_coverage(
    records: list[dict], totals: dict[str, int] | None = None
) -> dict[str, PrefectureCoverage]:
    """都道府県 → カバー率。ポケふたが1枚も無い県も covered=0 で返す。

    枚数は active な蓋（設置予定を含む）で数える。都道府県ページの設置枚数と揃えるため。
    """
    if totals is None:
        totals = load_municipality_totals()
    result = {pref: PrefectureCoverage(prefecture=pref, total=totals[pref]) for pref in PREFECTURE_ORDER}
    for record in records:
        if record.get("status", "active") != "active":
            continue
        coverage = result.get(str(record.get("prefecture") or ""))
        if coverage is None:
            continue
        name = coverage_name(record)
        if name and name != coverage.prefecture:
            coverage.counts[name] = coverage.counts.get(name, 0) + 1
    for coverage in result.values():
        coverage.covered_rank = 1 + sum(
            1 for other in result.values() if other.covered > coverage.covered
        )
    return result


def complete_prefectures(coverage: dict[str, PrefectureCoverage]) -> list[str]:
    """全市町村にポケふたがある都道府県（北から順）。"""
    return [pref for pref in PREFECTURE_ORDER if coverage[pref].is_complete]
