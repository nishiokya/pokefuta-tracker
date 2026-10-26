from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_sitemap as SITEMAP
from apps.scraper import generate_prefecture_pages as PREF
from apps.scraper import generate_trip_pages as MODULE
from apps.scraper import visit_durations as VD


def _crumbs(html: str) -> list[tuple[str, str]]:
    """ページの JSON-LD からパンくずの (名前, URL) を取り出す。"""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        nodes = data.get("@graph", [data])
        for node in nodes:
            crumb = node if node.get("@type") == "BreadcrumbList" else node.get("breadcrumb")
            if crumb:
                return [(i["name"], i["item"]) for i in crumb["itemListElement"]]
    return []


def _record(mid: str, city: str, lat: float, lng: float, prefecture: str = "大阪府", **extra) -> dict:
    return {
        "id": mid, "prefecture": prefecture, "city": city, "address": f"{prefecture}{city}市{mid}",
        "lat": lat, "lng": lng, "pokemons": ["コイル"], "status": "active", "installed": True,
        **extra,
    }


RECORDS = [
    _record("206", "東大阪", 34.67979, 135.60122),
    _record("210", "東大阪", 34.66949, 135.63059),
    _record("209", "東大阪", 34.66768, 135.62631),
    _record("207", "東大阪", 34.66771, 135.63989),
    _record("208", "東大阪", 34.68068, 135.65079),
    _record("148", "斑鳩", 34.6110, 135.7350, prefecture="奈良県"),
    _record("149", "斑鳩", 34.6120, 135.7370, prefecture="奈良県"),
    # 登録していない、近くにまとまった市（特集ページの「まとまっている場所」に出る）
    _record("1", "吹田", 34.760, 135.520),
    _record("2", "吹田", 34.762, 135.521),
    # 離れた市（出ない）
    _record("3", "堺", 34.50, 135.40),
    _record("4", "堺", 34.60, 135.50),
]
AREAS = [
    {"slug": "higashiosaka", "prefecture": "大阪府", "name": "東大阪",
     "manhole_ids": ["206", "210", "209", "207", "208"]},
    {"slug": "ikaruga", "prefecture": "奈良県", "name": "斑鳩", "manhole_ids": ["148", "149"]},
]
DURATIONS = {
    "measured_on": "2026-10-11",
    "entries": [{"manhole_ids": ["206", "207", "208", "209", "210"], 
                 "p25_minutes": 84, "p75_minutes": 150,
                 "common_order": ["206", "210", "209", "207", "208"]}],
}


class AreaTest(unittest.TestCase):
    def test_area_with_a_missing_or_preinstalled_stop_is_skipped(self) -> None:
        by_id = {r["id"]: r for r in RECORDS}
        self.assertIsNotNone(MODULE.area_records(AREAS[0], by_id))
        self.assertIsNone(MODULE.area_records({**AREAS[0], "manhole_ids": ["206", "999"]}, by_id))
        pre = dict(by_id, **{"210": {**by_id["210"], "installed": False}})
        self.assertIsNone(MODULE.area_records(AREAS[0], pre))

    def test_common_order_wins_over_the_shortest_route(self) -> None:
        records = [r for r in RECORDS if r["city"] == "東大阪"]
        route, common = MODULE.area_route(records, DURATIONS["entries"][0])
        self.assertTrue(common)
        self.assertEqual([r["id"] for r in route], ["206", "210", "209", "207", "208"])
        _, common = MODULE.area_route(records, None)
        self.assertFalse(common)

    def test_compact_places_skip_registered_and_spread_out_ones(self) -> None:
        taken = {frozenset(a["manhole_ids"]) for a in AREAS}
        names = [name for name, *_ in MODULE.compact_places(RECORDS, {}, taken)]
        self.assertIn("大阪府 吹田市", names)
        self.assertNotIn("大阪府 堺市", names)
        self.assertNotIn("大阪府 東大阪市", names)


    def test_compact_place_with_measured_time_does_not_claim_no_data(self) -> None:
        durations = {"entries": [{"manhole_ids": ["1", "2"], "p25_minutes": 20, "p75_minutes": 30}]}
        (name, _, _, _, time), = [
            c for c in MODULE.compact_places(RECORDS, {}, set(), durations) if "吹田" in c[0]
        ]
        self.assertEqual(time, "約20分〜30分")
        index = MODULE.build_index_page([], durations, MODULE.compact_places(RECORDS, {}, set(), durations))
        self.assertNotIn("まだ実績はありません", index)
        self.assertIn("かかる時間の目安は約20分〜30分", index)
        # 市区町村ページと共用の <head> でサイト名が二重にならない
        self.assertIn("<title>ポケふた旅｜1日で回れるルート｜ポケふた図鑑</title>", index)

    def test_description_promises_maps_only_when_the_link_exists(self) -> None:
        """離れた区間（15km超）があると順路リンクを出さないので、説明文でも約束しない。"""
        far = [_record("31", "能登", 37.0, 136.9, prefecture="石川県"),
               _record("32", "能登", 37.4, 137.2, prefecture="石川県")]
        area = {"slug": "noto", "prefecture": "石川県", "name": "能登", "manhole_ids": ["31", "32"]}
        page = MODULE.build_area_page(area, far, {}, {}, [(area, far)], {})
        self.assertNotIn("Googleマップで順路を開けます", page)
        self.assertNotIn("google.com/maps/dir/", page)
        near_page = MODULE.build_area_page(AREAS[0], RECORDS[:5], DURATIONS, {}, [], {})
        self.assertIn("Googleマップで順路を開けます", near_page)

    def test_breadcrumb_json_ld_matches_the_visible_trail(self) -> None:
        page = MODULE.build_area_page(AREAS[0], RECORDS[:5], DURATIONS, {}, [], {})
        self.assertEqual(
            [name for name, _ in _crumbs(page)], ["ポケふた図鑑", "ポケふた旅", AREAS[0]["name"]]
        )
        self.assertEqual(_crumbs(page)[1][1], "https://data.pokefuta.com/trip/")
        index = MODULE.build_index_page([], DURATIONS, [])
        self.assertEqual([name for name, _ in _crumbs(index)], ["ポケふた図鑑", "ポケふた旅"])
        self.assertIn('<a href="/">ポケふた図鑑</a>', index)


    def test_trip_summaries_put_measured_areas_first(self) -> None:
        summaries = MODULE.trip_summaries(RECORDS, list(reversed(AREAS)), DURATIONS)
        self.assertEqual([s[1] for s in summaries], ["/trip/higashiosaka/", "/trip/ikaruga/"])
        self.assertEqual(summaries[0][3], "約1時間20分〜2時間半")
        self.assertEqual(summaries[1][3], "")

    def test_card_thumbs_follow_the_route_and_fold_extras(self) -> None:
        records = [r for r in RECORDS if r["city"] == "東大阪"]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for mid in ("206", "210", "209", "207"):  # 208 は画像なし
                (d / f"{mid}_lid.jpeg").write_bytes(b"x")
            html = MODULE.card_thumbs_html(records, DURATIONS["entries"][0], d)
            self.assertEqual(
                re.findall(r'src="/manhole/image/(\d+)_lid\.jpeg"', html), ["206", "210", "209", "207"]
            )
            self.assertIn('loading="lazy"', html)
            self.assertNotRegex(html, r'alt="[^"]+"')
            self.assertIn("+1", html)  # 画像の無い 208 は「+1」に入る
            self.assertEqual(MODULE.card_thumbs_html(records, None, Path(tmp) / "none"), "")
            many = [_record(str(100 + i), "吹田", 34.76 + i * 0.001, 135.52) for i in range(8)]
            for r in many:
                (d / f"{r['id']}_lid.jpeg").write_bytes(b"x")
            html = MODULE.card_thumbs_html(many, None, d)
            self.assertEqual(html.count("<img"), MODULE.CARD_THUMB_LIMIT)
            self.assertIn("+2", html)

    def test_trips_by_manhole_gives_each_stop_its_own_area_only(self) -> None:
        trips = MODULE.trips_by_manhole(RECORDS, AREAS, DURATIONS)
        osaka = trips["206"]
        self.assertIs(trips["208"], osaka)
        self.assertEqual([r["id"] for r in osaka["route"]], ["206", "210", "209", "207", "208"])
        self.assertEqual(osaka["path"], "/trip/higashiosaka/")
        self.assertIn("たいてい1時間20分〜2時間半ほど", osaka["text"])
        self.assertNotIn("148", [r["id"] for r in osaka["route"]])  # 斑鳩は混ぜない
        self.assertIn("目安はまだありません", trips["148"]["text"])
        self.assertNotIn("1", trips)  # エリアに入っていない蓋

    def test_prefecture_page_links_to_its_trips_without_repeating(self) -> None:
        trips = [("能登半島", "/trip/noto/", 6, ""), ("上野", "/trip/ueno/", 2, "約5分")]
        html = PREF._trip_links_html("石川県", trips)
        self.assertIn("石川県のポケふた旅", html)
        self.assertIn('href="/trip/noto/"', html)
        self.assertEqual(PREF._trip_links_html("石川県", trips[:1], 'x href="/trip/noto/" y'), "")
        self.assertEqual(PREF._trip_links_html("石川県", None), "")

    def test_access_section_is_one_line_each_and_https_only(self):
        area = {**AREAS[0], "access": {
            "train": "荒本駅から徒歩5分の市役所スタート",
            "parking": [{"name": "花園中央公園駐車場", "kind": "公共", "fee": "有料", "note": "30分まで無料"}],
            "sources": [{"label": "公式", "url": "https://example.jp/"}, {"label": "x", "url": "javascript:alert(1)"}],
            "checked_on": "2026-10-11",
        }}
        html = MODULE._access_html(area)
        self.assertIn("🚃 電車</strong> 荒本駅から徒歩5分の市役所スタート", html)
        self.assertIn("花園中央公園駐車場（公共・有料・30分まで無料）", html)
        self.assertIn('href="https://example.jp/"', html)
        self.assertNotIn("javascript:", html)
        self.assertEqual(MODULE._access_html(AREAS[1]), "")
        car_only = MODULE._access_html({**AREAS[1], "access": {"car": "島内は車で回る"}})
        self.assertIn("🚗 車</strong> 島内は車で回る", car_only)
        self.assertNotIn("🚃", car_only)


class HeroSelectionTest(unittest.TestCase):
    def render(self, specs):
        areas, entries = [], []
        for slug, mode, measured in specs:
            # 距離による実際の移動手段判定を使う。
            gap = {"walk": .001, "bus": .03, "car": .2}[mode]
            records = [_record(f"{slug}-1", slug, 35, 135),
                       _record(f"{slug}-2", slug, 35 + gap, 135)]
            self.assertEqual(VD.travel_mode(records), mode)
            ids = [r["id"] for r in records]
            areas.append(({"slug": slug, "name": slug, "prefecture": "大阪府",
                           "manhole_ids": ids}, records))
            if measured:
                entries.append({"manhole_ids": ids, "p25_minutes": 20, "p75_minutes": 40})
        # 登録順と人気順を変え、人気順が同一モード内で維持されることも検証する。
        html = MODULE.build_index_page(list(reversed(areas)), {"entries": entries}, [])
        hero = html[html.index('<header class="hero">'):html.index("</header>")]
        return html, re.findall(r'data-destination="([^"]+)"', hero)

    def test_walks_precede_bus_and_cars_stay_in_the_regular_list(self):
        html, picks = self.render([
            ("awaji", "car", True), ("bus", "bus", True),
            ("hachinohe", "car", True), ("walk-a", "walk", True),
            ("walk-b", "walk", True), ("walk-c", "walk", True),
            ("walk-d", "walk", True), ("pending", "walk", False),
        ])
        self.assertEqual(picks, ["walk-a", "walk-b", "walk-c"])
        start = html.index('<section aria-labelledby="measured-heading">')
        regular = html[start:html.index('</section>', start)]
        for slug in ["awaji", "hachinohe", "bus", "walk-a", "walk-d"]:
            self.assertIn(f'href="/trip/{slug}/"', regular)
        self.assertNotIn('href="/trip/pending/"', regular)
        self.assertIn('href="/trip/pending/"', html[html.index('id="pending-heading"'):])

    def test_bus_fills_available_slots_after_walks(self):
        _, picks = self.render([
            ("bus-a", "bus", True), ("car", "car", True),
            ("walk", "walk", True), ("bus-b", "bus", True),
        ])
        self.assertEqual(picks, ["walk", "bus-a", "bus-b"])

    def test_no_eligible_areas_omits_hero_cards(self):
        for specs in [[], [("car", "car", True)], [("pending", "walk", False)]]:
            with self.subTest(specs=specs):
                html, picks = self.render(specs)
                self.assertEqual(picks, [])
                self.assertNotIn('<div class="hero-picks">', html)


class GenerateTest(unittest.TestCase):
    def test_pages_index_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pages = MODULE.generate_all(RECORDS, AREAS, DURATIONS, {}, {}, out)
            self.assertEqual([a["slug"] for a in pages], ["higashiosaka", "ikaruga"])
            area = (out / "higashiosaka" / "index.html").read_text(encoding="utf-8")
            self.assertIn("東大阪のポケふた5枚を回る", area)
            self.assertIn("約1時間20分〜2時間半", area)
            self.assertIn("よく回られる順番", area)
            cards = area[area.index('id="manhole-list"'):]
            ids = re.findall(r'id="manhole-(\d+)"', cards)
            self.assertEqual(ids[:5], ["206", "210", "209", "207", "208"])  # 「回るポケふた」も回る順
            self.assertIn('href="/trip/ikaruga/"', area)  # あわせて回るなら
            self.assertIn('"@type": "TouristTrip"', area)
            ikaruga = (out / "ikaruga" / "index.html").read_text(encoding="utf-8")
            self.assertIn("かかる時間の目安はまだ出せません", ikaruga)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("かかる時間の目安があるエリア", index)
            self.assertIn("時間の目安がまだのエリア", index)
            self.assertIn("吹田市", index)
            # ヒーローには時間の目安があるエリアだけをカードで出す（まだのエリアは出さない）
            hero = index[index.index('<header class="hero">'):index.index("</header>")]
            self.assertIn('href="/trip/higashiosaka/"', hero)
            self.assertIn('data-surface="trip_hero"', hero)
            self.assertNotIn("/trip/ikaruga/", hero)
            self.assertIn("PokefutaAnalytics.bindClickTracking(", area)
            self.assertNotRegex(area + index, r"\d+人")


class LinkTest(unittest.TestCase):
    def test_duration_text_links_to_the_trip_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "d.json"
            a = Path(tmp) / "a.json"
            d.write_text(json.dumps(DURATIONS), encoding="utf-8")
            a.write_text(json.dumps({"areas": AREAS}), encoding="utf-8")
            durations = VD.load_durations(d, a)
        records = [r for r in RECORDS if r["city"] == "東大阪"]
        self.assertIn('href="/trip/higashiosaka/"', VD.duration_html(records, durations))
        self.assertNotIn("/trip/", VD.duration_html(records, DURATIONS))

    def test_sitemap_lists_trip_pages(self) -> None:
        paths = MODULE.page_paths(RECORDS, AREAS)
        self.assertEqual(paths, ["/trip/", "/trip/higashiosaka/", "/trip/ikaruga/"])
        xml = SITEMAP.build_sitemap(["206"], trip_paths=paths)
        self.assertIn("https://data.pokefuta.com/trip/higashiosaka/", xml)



class ManholePageTest(unittest.TestCase):
    def test_trip_section_replaces_next_stops(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from apps.scraper import generate_manhole_pages as PAGES
        trip = MODULE.trips_by_manhole(RECORDS, AREAS, DURATIONS)["207"]
        html = PAGES._trip_section_html(trip, "207", {})
        self.assertIn("東大阪のポケふた5枚を回る", html)
        self.assertEqual(html.count("このポケふた"), 1)
        self.assertIn("/manholes/207/", html)
        self.assertIn("href='/trip/higashiosaka/'", html)
        self.assertIn("よく回られる順番です。", html)
        self.assertEqual(html.count("次まで"), 4)  # 最後の蓋には付かない

if __name__ == "__main__":
    unittest.main()
