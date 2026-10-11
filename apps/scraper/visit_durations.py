"""「1日で回るのにかかる時間」の文（都道府県ページ・市区町村ページ・/trip/ で共有）。

dataset/visit_durations.json は apps/tools/build_visit_durations.py が DB バックアップから作る集計。
載っている manhole_ids がページの回れる地点とぴったり一致するときだけ出す
（蓋が増えた・設置予定が設置されたなど、集計後に地点が変わった自治体では黙って消える）。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DURATIONS = ROOT / "dataset" / "visit_durations.json"
DEFAULT_TRIP_AREAS = ROOT / "dataset" / "trip_areas.json"
TRIP_BASE = "/trip/"
# 移動手段の目安。地点の端から端まで（いちばん離れた2地点の間）の直線距離で決める
WALK_MAX_KM = 2.5
BUS_OR_BIKE_MAX_KM = 6.0
MODE_LABELS = {"walk": "徒歩", "bus": "バス・自転車", "car": "車"}


def load_trip_areas(path: Path = DEFAULT_TRIP_AREAS) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("areas", [])


def trip_path(area: dict) -> str:
    return f"{TRIP_BASE}{area['slug']}/"


def load_durations(path: Path = DEFAULT_DURATIONS, areas_path: Path = DEFAULT_TRIP_AREAS) -> dict:
    """集計（visit_durations.json）に、同じ地点の組の /trip/ ページの URL を添えて返す。"""
    if not path.exists():
        return {}
    durations = json.loads(path.read_text(encoding="utf-8"))
    durations["trip_paths"] = {
        ",".join(sorted(str(i) for i in area["manhole_ids"])): trip_path(area)
        for area in load_trip_areas(areas_path)
    }
    return durations


def _visitable(records: list[dict]) -> list[dict]:
    return [
        record for record in records
        if record.get("installed") is not False
        and record.get("status", "active") == "active"
        and isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]


def _distance_km(a: dict, b: dict) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))


def farthest_gap_km(records: list[dict]) -> float:
    """ほかの地点からいちばん離れた地点の、最寄りの地点までの直線距離。"""
    points = _visitable(records)
    if len(points) < 2:
        return 0.0
    return max(
        min(_distance_km(p, q) for q in points if q is not p)
        for p in points
    )


def spread_km(records: list[dict]) -> float:
    """端から端まで: いちばん離れた2地点の間の直線距離。"""
    points = _visitable(records)
    return max(
        (_distance_km(a, b) for i, a in enumerate(points) for b in points[i + 1:]),
        default=0.0,
    )


def travel_mode(records: list[dict]) -> str:
    km = spread_km(records)
    if km < WALK_MAX_KM:
        return "walk"
    return "bus" if km <= BUS_OR_BIKE_MAX_KM else "car"


def _km_label(km: float) -> str:
    meters = max(100, round(km * 1000, -2))
    if meters < 1000:
        return f"約{meters:.0f}m"
    return f"約{km:.1f}km" if km < 10 else f"約{km:.0f}km"


def format_minutes(minutes: float) -> str:
    """1時間未満は5分単位、1時間以上は10分単位。30分は「半」。"""
    if minutes < 60:
        return f"{max(5, round(minutes / 5) * 5)}分"
    rounded = round(minutes / 10) * 10
    hours, rest = divmod(rounded, 60)
    if rest == 0:
        return f"{hours}時間"
    if rest == 30:
        return f"{hours}時間半"
    return f"{hours}時間{rest}分"


def duration_span(low: float, high: float) -> str:
    """「1時間20分〜2時間半」。両端が同じに丸まったら1つ（「25分」）。"""
    a, b = format_minutes(low), format_minutes(high)
    return a if a == b else f"{a}〜{b}"


def duration_range(low: float, high: float) -> str:
    return f"約{duration_span(low, high)}"


def find_entry(records: list[dict], durations: dict) -> dict | None:
    ids = {str(record.get("id", "")) for record in _visitable(records)}
    if len(ids) < 2:
        return None
    for entry in durations.get("entries", []):
        if set(entry.get("manhole_ids", [])) == ids:
            return entry
    return None


def mode_hint(records: list[dict]) -> str:
    km = _km_label(spread_km(records))
    mode = travel_mode(records)
    if mode == "walk":
        return f"いちばん遠い2か所でも直線で{km}なので、歩いて回れます。"
    if mode == "bus":
        return f"いちばん遠い2か所は直線で{km}離れているので、バスや自転車があると楽です。"
    return f"いちばん遠い2か所は直線で{km}離れているので、車があると回りやすいです。"


def duration_text(records: list[dict], durations: dict) -> str:
    entry = find_entry(records, durations)
    if not entry:
        return ""
    count = len(entry["manhole_ids"])
    return (
        f"{count}か所を1日で回った人は、たいてい"
        f"{duration_span(entry['p25_minutes'], entry['p75_minutes'])}ほどかかっています。"
        + mode_hint(records)
    )


def _date_label(value: str) -> str:
    try:
        y, m, d = (int(x) for x in value.split("-"))
    except ValueError:
        return value
    return f"{y}年{m}月{d}日"


def duration_note(durations: dict) -> str:
    # 「たいてい」の幅は、かかった時間の短い順に並べて25%〜75%（とても速い人・とてもゆっくりな人を除いた範囲）
    measured_on = _date_label(str(durations.get("measured_on", "")))
    return (
        '<p class="visit-duration-note">ポケふた写真館に投稿された写真の撮影時刻から計算しました。'
        '最初の1枚を撮ってから最後の1枚を撮るまでの時間で、1か所目に着くまでの移動は入りません。'
        'とても速い人と、とてもゆっくりな人を除いた範囲です'
        f'（{escape(measured_on)}時点）。</p>'
    )


def duration_html(records: list[dict], durations: dict) -> str:
    text = duration_text(records, durations)
    if not text:
        return ""
    ids = ",".join(sorted(str(r.get("id", "")) for r in _visitable(records)))
    path = durations.get("trip_paths", {}).get(ids, "")
    link = (
        f' <a class="inline-link" href="{escape(path)}" data-track="trip_link_click" '
        'data-surface="visit_duration" data-destination="trip">回り方を詳しく見る</a>'
        if path else ""
    )
    return (
        f'<p class="visit-duration">{escape(text)}{link}</p>'
        + duration_note(durations)
    )
