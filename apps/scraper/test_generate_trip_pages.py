from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_sitemap as SITEMAP
from apps.scraper import generate_trip_pages as MODULE
from apps.scraper import visit_durations as VD


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
    "entries": [{"manhole_ids": ["206", "207", "208", "209", "210"], "people": 11,
                 "p25_minutes": 84, "p75_minutes": 150,
                 "common_order": ["206", "210", "209", "207", "208"], "common_order_people": 4}],
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
            self.assertIn('href="/trip/ikaruga/"', area)  # あわせて回るなら
            self.assertIn('"@type": "TouristTrip"', area)
            ikaruga = (out / "ikaruga" / "index.html").read_text(encoding="utf-8")
            self.assertIn("所要時間は出していません", ikaruga)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("実際に回った人の目安があるエリア", index)
            self.assertIn("目安を集計中のエリア", index)
            self.assertIn("吹田市", index)
            self.assertIn("PokefutaAnalytics.bindClickTracking(", area)


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


if __name__ == "__main__":
    unittest.main()
