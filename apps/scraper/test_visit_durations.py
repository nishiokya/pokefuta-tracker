from __future__ import annotations

import unittest

from apps.scraper import generate_municipality_pages as MUNI_PAGE
from apps.scraper import generate_prefecture_pages as PREF
from apps.scraper import municipalities as MUNI
from apps.scraper import visit_durations as MODULE


def _record(mid: str, lat: float, lng: float, city: str = "東大阪", **extra) -> dict:
    return {
        "id": mid, "prefecture": "大阪府", "city": city, "address": f"大阪府{city}市{mid}",
        "lat": lat, "lng": lng, "pokemons": ["コイル"], "status": "active", "installed": True,
        **extra,
    }


# 東大阪の5枚に近い並び（西端の1枚だけ約3km離れている）
RECORDS = [
    _record("206", 34.67979, 135.60122),
    _record("210", 34.66949, 135.63059),
    _record("209", 34.66768, 135.62631),
    _record("207", 34.66771, 135.63989),
    _record("208", 34.68068, 135.65079),
]
DURATIONS = {
    "measured_on": "2026-10-11",
    "entries": [{"manhole_ids": ["206", "207", "208", "209", "210"],
                 "p25_minutes": 84, "p75_minutes": 150}],
}


class FormatTest(unittest.TestCase):
    def test_minutes_are_rounded_for_reading(self) -> None:
        self.assertEqual(MODULE.format_minutes(3), "5分")
        self.assertEqual(MODULE.format_minutes(57), "55分")
        self.assertEqual(MODULE.format_minutes(84), "1時間20分")
        self.assertEqual(MODULE.format_minutes(87), "1時間半")
        self.assertEqual(MODULE.format_minutes(118), "2時間")

    def test_distance_labels(self) -> None:
        self.assertEqual(MODULE._km_label(0.04), "約100m")
        self.assertEqual(MODULE._km_label(0.52), "約500m")
        self.assertEqual(MODULE._km_label(0.996), "約1.0km")
        self.assertEqual(MODULE._km_label(18.2), "約18km")

    def test_same_rounded_ends_collapse(self) -> None:
        self.assertEqual(MODULE.duration_range(3, 5), "約5分")
        self.assertEqual(MODULE.duration_range(84, 150), "約1時間20分〜2時間半")


class MatchTest(unittest.TestCase):
    def test_text_for_an_exact_match(self) -> None:
        text = MODULE.duration_text(RECORDS, DURATIONS)
        self.assertIn("5か所を1日で回った人は、たいてい1時間20分〜2時間半ほどかかっています。", text)
        self.assertIn("バスや自転車", text)

    def test_hidden_when_a_manhole_was_added_after_measuring(self) -> None:
        """集計した後に蓋が増えた自治体では、古い所要時間を出さない。"""
        more = RECORDS + [_record("999", 34.67, 135.62)]
        self.assertEqual(MODULE.duration_text(more, DURATIONS), "")

    def test_preinstalled_manholes_do_not_count(self) -> None:
        more = RECORDS + [_record("999", 34.67, 135.62, installed=False)]
        self.assertNotEqual(MODULE.duration_text(more, DURATIONS), "")

    def test_mode_hint_follows_the_spread_from_end_to_end(self) -> None:
        near = [_record(str(i), 34.68 + i * 0.002, 135.60) for i in range(3)]
        # 隣どうしは約9kmでも、端から端は約18km（淡路のような数珠つなぎ）
        chain = [_record(str(i), 34.50 + i * 0.08, 135.00) for i in range(3)]
        entry = {"entries": [{"manhole_ids": ["0", "1", "2"], "p25_minutes": 30, "p75_minutes": 60}]}
        self.assertIn("歩いて回れます", MODULE.duration_text(near, entry))
        text = MODULE.duration_text(chain, entry)
        self.assertIn("いちばん遠い2か所は直線で約18km離れている", text)
        self.assertIn("車があると", text)
        self.assertEqual(MODULE.travel_mode(RECORDS), "bus")

    def test_no_head_count_is_shown(self) -> None:
        self.assertNotRegex(MODULE.duration_text(RECORDS, DURATIONS), r"\d+人")

    def test_html_escapes_and_names_the_basis(self) -> None:
        html = MODULE.duration_html(RECORDS, DURATIONS)
        self.assertIn('class="visit-duration"', html)
        self.assertIn("撮影時刻", html)
        self.assertIn("2026年10月11日", html)
        self.assertEqual(MODULE.duration_html(RECORDS, {}), "")


class PageTest(unittest.TestCase):
    def test_prefecture_page_shows_it_when_the_city_covers_the_prefecture(self) -> None:
        section = PREF._visit_duration_html("大阪府", RECORDS, DURATIONS)
        self.assertIn("大阪府のポケふたを1日で回るには", section)
        self.assertEqual(PREF._visit_duration_html("大阪府", RECORDS, None), "")

    def test_municipality_route_section_includes_it(self) -> None:
        records = [
            _record(str(i), 35.54 + i * 0.002, 139.44, prefecture="東京都", city="町田")
            for i in range(3)
        ] + [_record("99", 35.66, 139.33, prefecture="東京都", city="八王子")]
        machida = [m for m in MUNI.build_municipalities(records, {"東京都/町田市": "machida"})
                   if m.name == "町田市"][0]
        durations = {"entries": [{"manhole_ids": ["0", "1", "2"], "p25_minutes": 20, "p75_minutes": 29}]}
        self.assertIn("たいてい20分〜30分ほど", MUNI_PAGE._route_section(machida, durations))
        self.assertNotIn("visit-duration", MUNI_PAGE._route_section(machida))



class RankingTest(unittest.TestCase):
    def setUp(self) -> None:
        records = [
            _record(str(i), 34.61 + i * 0.001, 135.73, prefecture="奈良県", city="斑鳩") for i in range(3)
        ] + [_record("9", 34.68, 135.60)]
        self.items = MUNI.build_municipalities(records, {})
        self.durations = {"entries": [{"manhole_ids": ["0", "1", "2"], "p25_minutes": 29,
                                       "p75_minutes": 55, "median_minutes": 36}]}

    def test_ranking_row_shows_the_typical_time(self) -> None:
        html = MUNI_PAGE.build_ranking_page(self.items, 4, "2026年10月11日", durations=self.durations)
        self.assertIn("全部のポケふたを見るのにかかった時間は、平均的な人で約35分です", html)
        self.assertNotIn("平均的な人", MUNI_PAGE.build_ranking_page(self.items, 4, "2026年10月11日"))

    def test_ranking_announces_the_trip_pages(self) -> None:
        trips = [("斑鳩", "/trip/ikaruga/", 3, "約30分〜55分")]
        html = MUNI_PAGE.build_ranking_page(self.items, 4, "2026年10月11日", trips=trips)
        self.assertIn("ルート案内「ポケふた旅」をはじめました", html)
        self.assertIn('href="/trip/ikaruga/"', html)
        self.assertIn('href="/trip/"', html)
        self.assertNotIn("ポケふた旅をはじめました", MUNI_PAGE.build_ranking_page(self.items, 4, "x"))

if __name__ == "__main__":
    unittest.main()
