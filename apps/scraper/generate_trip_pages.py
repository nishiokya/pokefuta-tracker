#!/usr/bin/env python3
"""/trip/（ポケふた旅の回り方）の特集ページとエリア別ページを生成する。

- エリアは dataset/trip_areas.json に手で登録する（市区町村をまたいでもよい）
- 所要時間・よく回られる順は dataset/visit_durations.json（apps/tools/build_visit_durations.py の集計）に
  同じ地点の組があるときだけ出す
- 特集ページの「まとまっている場所」は、登録していない市区町村から地図の距離だけで選ぶ（実績は使わない）

旅行計画（複数エリアをつなぐ・泊まりの行程）へ広げるときも、このページの下に足していく。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper import generate_municipality_pages as muni_page
    from apps.scraper import generate_prefecture_pages as pref
    from apps.scraper.municipalities import build_municipalities, load_slugs
    from apps.scraper.visit_durations import (
        DEFAULT_DURATIONS,
        DEFAULT_TRIP_AREAS,
        TRIP_BASE,
        duration_note,
        duration_range,
        duration_text,
        MODE_LABELS,
        farthest_gap_km,
        spread_km,
        travel_mode,
        find_entry,
        load_durations,
        load_trip_areas,
        trip_path,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_municipality_pages as muni_page
    import generate_prefecture_pages as pref
    from municipalities import build_municipalities, load_slugs
    from visit_durations import (
        DEFAULT_DURATIONS,
        DEFAULT_TRIP_AREAS,
        TRIP_BASE,
        duration_note,
        duration_range,
        duration_text,
        MODE_LABELS,
        farthest_gap_km,
        spread_km,
        travel_mode,
        find_entry,
        load_durations,
        load_trip_areas,
        trip_path,
    )

ROOT = pref.ROOT
BASE_URL = pref.BASE_URL
DEFAULT_OUTPUT = ROOT / "dist" / "trip"
# 「あわせて回る」に出す、ほかのエリアまでの距離（エリアの中心どうしの直線）
NEARBY_TRIP_KM = 80.0
# 特集ページの「まとまっている場所」: ほかの地点からいちばん離れた地点でもこの距離以内
COMPACT_GAP_KM = 3.0

_escape_attr = pref._escape_attr
_json_for_script = pref._json_for_script


def _head(title: str, description: str, canonical: str, json_ld: dict, with_map: bool) -> str:
    # 市区町村ページと同じ head に、trip 用の見た目だけ足す
    head = muni_page._head(title, description, canonical, json_ld, with_map)
    return head.replace("  </style>", f"{TRIP_CSS}  </style>", 1)


def _visitable(records: list[dict]) -> list[dict]:
    return [
        r for r in records
        if r.get("installed") is not False
        and r.get("status", "active") == "active"
        and isinstance(r.get("lat"), (int, float))
        and isinstance(r.get("lng"), (int, float))
    ]


def area_records(area: dict, by_id: dict[str, dict]) -> list[dict] | None:
    """登録した地点が全部回れる状態のときだけ返す（撤去・未設置・座標なしが混ざったエリアは出さない）。"""
    ids = [str(i) for i in area["manhole_ids"]]
    records = [by_id.get(i) for i in ids]
    if len(ids) < 2 or len(set(ids)) != len(ids) or any(r is None for r in records):
        return None
    if len(_visitable(records)) != len(records):
        return None
    return records


def page_paths(records: list[dict], areas: list[dict]) -> list[str]:
    """出す /trip/ ページのパス（特集ページを含む）。サイトマップと共有する。"""
    by_id = {str(r.get("id", "")): r for r in records}
    paths = [trip_path(a) for a in areas if area_records(a, by_id) is not None]
    return [TRIP_BASE] + paths if paths else []


def area_route(records: list[dict], entry: dict | None) -> tuple[list[dict], bool]:
    """(順番, よく回られる順かどうか)。集計に順番が無ければ直線距離の合計が最短の順。"""
    order = (entry or {}).get("common_order")
    by_id = {str(r["id"]): r for r in records}
    if order and set(order) == set(by_id):
        return [by_id[i] for i in order], True
    return muni_page.shortest_route(records), False


def _centroid(records: list[dict]) -> tuple[float, float]:
    return (
        sum(r["lat"] for r in records) / len(records),
        sum(r["lng"] for r in records) / len(records),
    )


def _title(area: dict, count: int) -> str:
    return f"{area['name']}のポケふた{count}枚を回る"


def _stop_name(record: dict) -> str:
    return pref._guide_stop_name(record)


def _route_html(area: dict, route: list[dict], common: bool, entry: dict | None) -> str:
    legs = [pref._distance_km(a["lat"], a["lng"], b["lat"], b["lng"]) for a, b in zip(route, route[1:])]
    items = "".join(
        f'<li><a href="#manhole-{_escape_attr(str(r["id"]))}" data-track="trip_stop_click" '
        f'data-surface="route" data-destination="manhole_list" data-position="{i + 1}" '
        f'data-content-id="{_escape_attr(str(r["id"]))}">{escape(_stop_name(r))}</a>'
        f'<span>{escape(str(r.get("address") or ""))}</span>'
        + (f'<span class="route-leg">{muni_page._leg_label(legs[i])}</span>' if i < len(legs) else "")
        + "</li>"
        for i, r in enumerate(route)
    )
    lead = (
        f"実際に全部回った人のうち{entry['common_order_people']}人がこの道筋で回っています（逆回りも含む）。"
        if common and entry else "直線距離の合計がいちばん短くなる順に並べました。"
    )
    lead += f"直線で合計約{sum(legs):.1f}kmです。"
    links = ""
    if max(legs) <= muni_page.ROUTE_LINK_MAX_LEG_KM:
        segments = muni_page._route_segments(route)
        for position, (first, last) in enumerate(segments, start=1):
            label = (
                "この順番でGoogleマップを開く" if len(segments) == 1
                else f"{first + 1}〜{last + 1}番目をGoogleマップで開く"
            )
            links += (
                f'<a class="inline-link" href="{_escape_attr(muni_page._google_route_url(route[first:last + 1]))}" '
                'target="_blank" rel="noopener noreferrer" data-track="trip_route_open" '
                f'data-surface="route" data-destination="google_maps_route" data-position="{position}">{label}</a>'
            )
    return (
        '<section id="route" class="visit-guide" aria-labelledby="route-heading">'
        f'<h2 id="route-heading">{"よく回られる順番" if common else "回る順番"}</h2>'
        f'<p>{escape(lead)}</p>'
        f'<ol class="route-stops">{items}</ol>'
        f'<div class="municipality-actions">{links}'
        '<a class="inline-link" href="#prefecture-map" data-track="trip_map_click" '
        'data-surface="route" data-destination="trip_map">地図で見る</a></div>'
        '<p class="route-note">直線距離で結んだ目安です。実際の道のり・交通手段・営業時間は'
        '地図アプリや公式情報で確認してください。</p>'
        '</section>'
    )


def _time_html(records: list[dict], durations: dict) -> str:
    text = duration_text(records, durations)
    if text:
        body = f'<p class="visit-duration">{escape(text)}</p>' + duration_note(durations)
    else:
        body = (
            '<p>1日で全部回った人の記録がまだ少ないので、所要時間は出していません。'
            f'端から端まで直線約{spread_km(records):.0f}km、'
            f'移動の目安は{MODE_LABELS[travel_mode(records)]}です。'
            '写真を投稿してもらえると、ここに目安が出るようになります。</p>'
        )
    return (
        '<section class="visit-guide" aria-labelledby="time-heading">'
        '<h2 id="time-heading">かかる時間</h2>'
        f'{body}</section>'
    )


def _nearby_html(area: dict, records: list[dict], others: list[tuple[dict, list[dict]]]) -> str:
    here = _centroid(records)
    near = []
    for other, other_records in others:
        if other["slug"] == area["slug"]:
            continue
        there = _centroid(other_records)
        km = pref._distance_km(here[0], here[1], there[0], there[1])
        if km <= NEARBY_TRIP_KM:
            near.append((km, other, other_records))
    if not near:
        return ""
    links = "".join(
        f'<a href="{_escape_attr(trip_path(o))}" data-track="trip_nearby_click" data-surface="nearby" '
        f'data-destination="{_escape_attr(o["slug"])}">{escape(o["name"])} {len(rs)}枚'
        f'<small>直線約{km:.0f}km</small></a>'
        for km, o, rs in sorted(near, key=lambda t: t[0])
    )
    return (
        '<section aria-labelledby="nearby-heading">'
        '<h2 id="nearby-heading">あわせて回るなら</h2>'
        '<p>近くのエリアです。泊まりで回る計画や、2日目の行き先選びに。</p>'
        f'<div class="related-links">{links}</div></section>'
    )


def build_area_page(
    area: dict,
    records: list[dict],
    durations: dict,
    photos: dict[str, dict],
    all_areas: list[tuple[dict, list[dict]]],
    municipality_paths: dict[str, tuple[str, str]],
) -> str:
    entry = find_entry(records, durations)
    route, common = area_route(records, entry)
    count = len(records)
    pref_slug = pref.PREFECTURE_SLUGS[area["prefecture"]]
    path = trip_path(area)
    canonical = f"{BASE_URL}{path}"
    title = f"{_title(area, count)}ルートと所要時間｜ポケふた旅"
    time_phrase = (
        f"実際に回った人の多くは{duration_range(entry['p25_minutes'], entry['p75_minutes'])}。"
        if entry else ""
    )
    description = (
        f"{area['prefecture']}・{area['name']}のポケふた{count}枚を1日で回る順番と目安。"
        f"{time_phrase}Googleマップで順路を開けます。"
    )
    map_points = [
        {
            "id": str(r["id"]),
            "lat": r["lat"],
            "lng": r["lng"],
            "name": pref._manhole_name(r),
            "pokemons": pref._clean_pokemons(r),
            "is_preinstall": False,
            "photo_url": pref._photo_asset_url(r, photos[str(r["id"])]) if str(r["id"]) in photos else "",
        }
        for r in records
    ]
    manhole_html = muni_page._to_municipality_events(pref._manhole_cards(route, photos, pref_slug))
    manhole_html = manhole_html.replace("municipality_", "trip_")
    keys = sorted({f"{r.get('prefecture')}/{r.get('city')}" for r in records})
    muni_links = "".join(
        f'<a class="inline-link" href="{_escape_attr(municipality_paths[k][1])}" '
        'data-track="trip_municipality_click" data-surface="related" '
        f'data-destination="municipality">{escape(municipality_paths[k][0])}のページ</a>'
        for k in keys if k in municipality_paths
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "TouristTrip",
        "name": _title(area, count),
        "description": description,
        "url": canonical,
        "itinerary": {
            "@type": "ItemList",
            "numberOfItems": count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "item": {
                        "@type": "TouristAttraction",
                        "name": f"{pref._manhole_name(r)}のポケふた",
                        "url": f"{BASE_URL}/manholes/{quote(str(r['id']))}/",
                    },
                }
                for i, r in enumerate(route, start=1)
            ],
        },
    }
    return _head(title, description, canonical, json_ld, with_map=True) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <a href="{TRIP_BASE}">ポケふた旅</a><span>›</span>
      <span>{escape(area['name'])}</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">ポケふた旅 {escape(area['prefecture'])}</p>
        <h1>{escape(_title(area, count))}</h1>
        <p>{escape(area.get('intro') or f"{area['name']}にあるポケふた{count}枚を、回る順番と時間の目安つきでまとめました。")}</p>
        <div class="hero-actions">
          <a class="button primary" href="#route" data-track="trip_route_click"
            data-surface="hero" data-destination="route">回る順番を見る</a>
          <a class="button tertiary" href="#prefecture-map" data-track="trip_map_click"
            data-surface="hero" data-destination="trip_map">地図で見る</a>
        </div>
      </div>
    </header>

    {_time_html(records, durations)}

    {_route_html(area, route, common, entry)}

    <section aria-labelledby="map-heading">
      <h2 id="map-heading">{escape(area['name'])}のポケふたマップ</h2>
      <div id="prefecture-map"></div>
    </section>

    <section id="manhole-list" aria-labelledby="manhole-heading">
      <h2 id="manhole-heading">回るポケふた</h2>
      <div class="manhole-grid">{manhole_html}</div>
    </section>

    {_nearby_html(area, records, all_areas)}

    <section aria-labelledby="related-heading">
      <h2 id="related-heading">{escape(area['prefecture'])}のポケふた</h2>
      <div class="municipality-actions">
        <a class="inline-link" href="/prefectures/{quote(pref_slug)}/" data-track="trip_prefecture_click"
          data-surface="related" data-destination="{_escape_attr(pref_slug)}">{escape(area['prefecture'])}のページ</a>
        {muni_links}
        <a class="inline-link" href="{TRIP_BASE}" data-track="trip_index_click"
          data-surface="related" data-destination="trip_index">ほかのポケふた旅</a>
      </div>
    </section>
    <footer><a href="{TRIP_BASE}">ポケふた旅の一覧へ戻る</a></footer>
  </main>
{_analytics_script(path, "trip", pref_slug)}  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
{pref._map_script(map_points, pref._campaign_params(pref_slug), "trip", "trackTripEvent")}
</body>
</html>
"""


def _analytics_script(page_path: str, page_type: str, prefecture_slug: str = "") -> str:
    context = {"page_path": page_path, "site_type": "map", "page_type": page_type}
    if prefecture_slug:
        context["prefecture"] = prefecture_slug
    defaults = {"event_category": "trip", "surface": f"{page_type}_page"}
    return f"""  <script src="/assets/analytics.js?v=20260929a"></script>
  <script>
    window.PokefutaAnalytics.init({_json_for_script(context)});
    const tripEventDefaults = {_json_for_script(defaults)};
    function trackTripEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{}}, tripEventDefaults, params || {{}}));
    }}
    window.PokefutaAnalytics.bindClickTracking(tripEventDefaults, {{ detail: true }});
  </script>
"""


def compact_places(
    records: list[dict], slugs: dict[str, str], taken: set[frozenset[str]]
) -> list[tuple[str, str, int, float]]:
    """登録していない市区町村のうち、地点が近くにまとまっているところ。(名前, リンク先, 枚数, 合計km)。"""
    out = []
    for m in build_municipalities(records, slugs):
        points = _visitable(m.records)
        if len(points) < 2 or frozenset(str(r["id"]) for r in points) in taken:
            continue
        if farthest_gap_km(points) > COMPACT_GAP_KM:
            continue
        route = muni_page.shortest_route(points)
        total = sum(
            pref._distance_km(a["lat"], a["lng"], b["lat"], b["lng"]) for a, b in zip(route, route[1:])
        )
        link = m.path or f"/prefectures/{quote(m.prefecture_slug)}/"
        out.append((f"{m.prefecture} {m.name}", link, len(points), total))
    return sorted(out, key=lambda t: (-t[2], t[3]))


def build_index_page(
    areas: list[tuple[dict, list[dict]]], durations: dict, compact: list[tuple[str, str, int, float]]
) -> str:
    title = "ポケふた旅｜1日で回れるポケふたと所要時間の目安"
    description = (
        "ポケふた（ポケモンマンホール）を1日で回れるエリアを、実際に回った人の所要時間と"
        "回る順番つきでまとめています。旅行やおでかけの計画に。"
    )
    canonical = f"{BASE_URL}{TRIP_BASE}"

    def card(area: dict, records: list[dict]) -> str:
        entry = find_entry(records, durations)
        mode = MODE_LABELS[travel_mode(records)]
        time = (
            f'<strong>{escape(duration_range(entry["p25_minutes"], entry["p75_minutes"]))}</strong>'
            f'<small>{entry["people"]}人の実績</small>'
            if entry else '<strong>目安を集計中</strong>'
        )
        return (
            f'<a class="trip-card" href="{_escape_attr(trip_path(area))}" data-track="trip_card_click" '
            f'data-surface="trip_index" data-destination="{_escape_attr(area["slug"])}">'
            f'<span class="trip-pref">{escape(area["prefecture"])}</span>'
            f'<span class="trip-name">{escape(area["name"])} {len(records)}枚</span>'
            f'{time}<small>移動の目安：{mode}</small></a>'
        )

    measured = [(a, rs) for a, rs in areas if find_entry(rs, durations)]
    pending = [(a, rs) for a, rs in areas if not find_entry(rs, durations)]
    measured.sort(key=lambda t: -find_entry(t[1], durations)["people"])
    pending_html = (
        '<section aria-labelledby="pending-heading"><h2 id="pending-heading">目安を集計中のエリア</h2>'
        '<p>回る順番は見られます。1日で全部回った人が増えると、所要時間の目安が出ます。</p>'
        f'<div class="trip-grid">{"".join(card(a, rs) for a, rs in pending)}</div></section>'
        if pending else ""
    )
    compact_html = (
        '<section aria-labelledby="compact-heading"><h2 id="compact-heading">近くにまとまっている場所</h2>'
        f'<p>まだ実績はありませんが、どの地点もほかの地点から直線{COMPACT_GAP_KM:.0f}km以内にあり、'
        '1日で回りやすそうな市区町村です。</p><ul class="compact-list">'
        + "".join(
            f'<li><a href="{_escape_attr(link)}" data-track="trip_compact_click" data-surface="compact" '
            f'data-destination="place">{escape(name)}</a><span>{n}枚・直線で合計約{km:.1f}km</span></li>'
            for name, link, n, km in compact
        )
        + "</ul></section>"
        if compact else ""
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(areas),
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": _title(a, len(rs)),
                 "url": f"{BASE_URL}{trip_path(a)}"}
                for i, (a, rs) in enumerate(measured + pending, start=1)
            ],
        },
    }
    return _head(title, description, canonical, json_ld, with_map=False) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span><span>ポケふた旅</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">ポケふた旅</p>
        <h1>1日で回れるポケふた</h1>
        <p>実際に回った人の撮影時刻から、エリアごとの所要時間の目安と回る順番をまとめました。旅行やおでかけの計画に使ってください。</p>
      </div>
    </header>

    <section aria-labelledby="measured-heading">
      <h2 id="measured-heading">実際に回った人の目安があるエリア</h2>
      <div class="trip-grid">{"".join(card(a, rs) for a, rs in measured)}</div>
      {duration_note(durations) if measured else ""}
    </section>

    {pending_html}

    {compact_html}
    <footer><a href="/">全国マップへ戻る</a></footer>
  </main>
{_analytics_script(TRIP_BASE, "trip_index")}</body>
</html>
"""


TRIP_CSS = """
    .trip-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr)); gap: 10px; }
    .trip-card { display: grid; gap: 2px; padding: 12px 14px; border-radius: 14px; background: #fffaf0;
      border: 1px solid #ece4d7; color: inherit; text-decoration: none; }
    .trip-card .trip-pref { color: #75685c; font-size: .75rem; }
    .trip-card .trip-name { font-weight: 850; }
    .trip-card strong { color: #6b4aa2; }
    .trip-card small { color: #62564a; font-size: .78rem; }
    .compact-list { margin: 10px 0 0; padding-left: 1.2em; display: grid; gap: 6px; }
    .compact-list span { margin-left: 8px; color: #62564a; font-size: .82rem; }
    .related-links small { margin-left: 6px; color: #75685c; font-size: .75rem; }
"""


def generate_all(
    records: list[dict],
    areas: list[dict],
    durations: dict,
    photos: dict[str, dict],
    slugs: dict[str, str],
    output_dir: Path,
) -> list[dict]:
    by_id = {str(r.get("id", "")): r for r in records}
    ready: list[tuple[dict, list[dict]]] = []
    for area in areas:
        rs = area_records(area, by_id)
        if rs is None:
            print(f"[generate_trip_pages] WARNING: 地点が揃っていないので出さない: {area.get('slug')}")
            continue
        ready.append((area, rs))
    # 「県/city」→（市区町村名, ページ）。city は ndjson の表記（「町田」）なので records から引く
    municipality_paths = {
        f"{m.prefecture}/{m.records[0].get('city')}": (m.name, m.path)
        for m in build_municipalities(records, slugs) if m.path and m.records
    }
    for area, rs in ready:
        out = output_dir / area["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            build_area_page(area, rs, durations, photos, ready, municipality_paths), encoding="utf-8"
        )
    taken = {frozenset(str(r["id"]) for r in rs) for _, rs in ready}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(
        build_index_page(ready, durations, compact_places(records, slugs, taken)), encoding="utf-8"
    )
    return [a for a, _ in ready]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=pref.DEFAULT_MANHOLES)
    parser.add_argument("--photos", type=Path, default=pref.DEFAULT_PHOTOS)
    parser.add_argument("--areas", type=Path, default=DEFAULT_TRIP_AREAS)
    parser.add_argument("--durations", type=Path, default=DEFAULT_DURATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    pages = generate_all(
        pref.load_records(args.manholes),
        load_trip_areas(args.areas),
        load_durations(args.durations, args.areas),
        pref.load_photos(args.photos),
        load_slugs(),
        args.output,
    )
    print(f"[generate_trip_pages] wrote {len(pages)} trip pages + index to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
