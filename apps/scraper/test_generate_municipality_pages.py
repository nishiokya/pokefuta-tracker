from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_municipality_pages as MODULE
from apps.scraper import generate_prefecture_pages as PREF
from apps.scraper import municipalities as MUNI


def _record(mid: str, prefecture: str, city: str, lat: float, lng: float, **extra) -> dict:
    return {
        "id": mid,
        "prefecture": prefecture,
        "city": city,
        "address": f"{prefecture}{city}市1-{mid}",
        "lat": lat,
        "lng": lng,
        "pokemons": ["ピカチュウ"],
        "status": "active",
        "installed": True,
        **extra,
    }


# 東京都: 町田3枚 + 八王子1枚（町田は県の一部）。千葉県: 香取3枚だけ（県の全数）
SYNTHETIC = [
    _record("1", "東京都", "町田", 35.540, 139.440),
    _record("2", "東京都", "町田", 35.560, 139.440),
    _record("3", "東京都", "町田", 35.550, 139.440),
    _record("4", "東京都", "八王子", 35.660, 139.330),
    _record("5", "千葉県", "香取", 35.890, 140.500),
    _record("6", "千葉県", "香取", 35.880, 140.500),
    _record("7", "千葉県", "香取", 35.870, 140.500),
]
SLUGS = {"東京都/町田市": "machida", "千葉県/香取市": "katori"}


class MunicipalitySelectionTest(unittest.TestCase):
    def test_page_only_for_municipalities_that_are_part_of_their_prefecture(self) -> None:
        """県の全数が1自治体にあると県ページと同じ内容になるので、市区町村ページは作らない。"""
        items = {m.name: m for m in MUNI.build_municipalities(SYNTHETIC, SLUGS)}
        self.assertEqual(items["町田市"].path, "/municipalities/tokyo/machida/")
        self.assertTrue(items["香取市"].covers_prefecture)
        self.assertIsNone(items["香取市"].path)
        self.assertIsNone(items["八王子市"].path)  # 1枚

    def test_ties_share_the_same_rank(self) -> None:
        items = {m.name: m for m in MUNI.build_municipalities(SYNTHETIC, SLUGS)}
        self.assertEqual((items["町田市"].national_rank, items["町田市"].national_tied), (1, 2))
        self.assertEqual((items["香取市"].national_rank, items["香取市"].national_tied), (1, 2))
        self.assertEqual(items["八王子市"].national_rank, 3)

    def test_missing_slug_skips_the_page_and_is_reported(self) -> None:
        items = MUNI.build_municipalities(SYNTHETIC, {})
        self.assertEqual(MUNI.missing_slugs(items), ["東京都/町田市"])
        self.assertFalse(any(m.path for m in items))

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない。漏れは generate_municipality_pages.py の WARNING で出る",
    )
    def test_real_data_has_a_slug_for_every_page(self) -> None:
        """今の設置データで条件を満たす自治体は、全部 slug を持っていること。

        本番では slug が無い自治体は警告してページを作らない（デプロイは止めない）。
        データ更新で新しく条件を満たした自治体は、手元でこのテストを回すと気づける。
        pages-deploy.yml では POKEFUTA_PAGES_DEPLOY=1 で飛ばす（日次更新でデプロイ全体を止めないため）。
        """
        records = PREF.load_records(PREF.DEFAULT_MANHOLES)
        self.assertEqual([], MUNI.missing_slugs(MUNI.build_municipalities(records, MUNI.load_slugs())))

    def test_slug_file_rejects_bad_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "slugs.json"
            for slugs in (
                {"東京都/町田市": "Machida"},
                {"東京都/町田市": "まちだ"},
                {"東京都町田市": "machida"},
                {"東京都/町田市": "x", "東京都/八王子市": "x"},
            ):
                with self.subTest(slugs=slugs):
                    path.write_text(json.dumps({"slugs": slugs}, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        MUNI.load_slugs(path)
        self.assertIn("東京都/町田市", MUNI.load_slugs())


class RouteTest(unittest.TestCase):
    def test_shortest_route_visits_points_in_line_order(self) -> None:
        # 緯度順に 1 → 3 → 2 と並ぶので、どちらかの端から順にたどるのが最短
        route = MODULE.shortest_route(SYNTHETIC[:3])
        self.assertIn([r["id"] for r in route], (["1", "3", "2"], ["2", "3", "1"]))

    def test_route_skips_preinstalled_manholes(self) -> None:
        records = SYNTHETIC[:3] + [_record("9", "東京都", "町田", 35.545, 139.44, installed=False)]
        self.assertNotIn("9", [r["id"] for r in MODULE.shortest_route(records)])

    def test_route_links_fit_the_mobile_waypoint_limit(self) -> None:
        """モバイルブラウザの Google マップは経由地3か所まで。5地点ごとに分け、端を共有して全地点を通る。"""
        self.assertEqual(MODULE._route_segments(list(range(5))), [(0, 4)])
        self.assertEqual(MODULE._route_segments(list(range(6))), [(0, 4), (4, 5)])
        self.assertEqual(MODULE._route_segments(list(range(9))), [(0, 4), (4, 8)])
        self.assertEqual(MODULE._route_segments(list(range(10))), [(0, 4), (4, 8), (8, 9)])
        records = [_record(str(i), "東京都", "町田", 35.54 + i * 0.001, 139.44) for i in range(6)]
        records.append(_record("99", "東京都", "八王子", 35.66, 139.33))
        machida = [m for m in MUNI.build_municipalities(records, SLUGS) if m.name == "町田市"][0]
        section = MODULE._route_section(machida)
        urls = re.findall(r'href="(https://www\.google\.com/maps/dir/[^"]+)"', section)
        self.assertEqual(len(urls), 2)
        for url in urls:
            self.assertLessEqual(url.count("%7C") + 1 if "waypoints=" in url else 0, 3)
        self.assertIn("1〜5番目をGoogleマップで開く", section)
        self.assertIn("5〜6番目をGoogleマップで開く", section)

    def test_far_apart_stops_get_no_road_route_link(self) -> None:
        """小笠原（父島と母島）のように離れた区間があると、Google マップの道路ルートは出さない。"""
        near = MUNI.build_municipalities(SYNTHETIC, SLUGS)[0]
        self.assertIn("google.com/maps/dir/", MODULE._route_section(near))
        far_records = [
            _record("1", "東京都", "小笠原", 27.09, 142.19, address="東京都小笠原村1"),
            _record("2", "東京都", "小笠原", 27.08, 142.20, address="東京都小笠原村2"),
            _record("3", "東京都", "小笠原", 26.64, 142.16, address="東京都小笠原村3"),
            _record("4", "東京都", "八王子", 35.66, 139.33),
        ]
        far = [m for m in MUNI.build_municipalities(far_records, {"東京都/小笠原村": "ogasawara"})
               if m.name == "小笠原村"][0]
        section = MODULE._route_section(far)
        self.assertNotIn("google.com/maps/dir/", section)
        self.assertIn("1日で回れるとは限りません", section)


class PageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = MUNI.build_municipalities(SYNTHETIC, SLUGS)
        cls.machida = [m for m in cls.items if m.name == "町田市"][0]
        cls.html = MODULE.build_page(cls.machida, cls.items, {}, {})

    def test_meta_and_breadcrumb(self) -> None:
        html = self.html
        self.assertIn("<title>町田市のポケふた3枚はどこ？場所一覧・地図・巡る順番</title>", html)
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/municipalities/tokyo/machida/">', html)
        self.assertIn('<meta name="robots" content="index,follow">', html)
        self.assertIn("<h1>町田市（東京都）のポケふた3枚</h1>", html)
        self.assertIn("都内4枚のうち3枚", html)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1))
        names = [item["name"] for item in ld["breadcrumb"]["itemListElement"]]
        self.assertEqual(names, ["全国マップ", "全国一覧", "東京都", "町田市"])
        self.assertEqual(ld["mainEntity"]["numberOfItems"], 3)

    def test_events_are_municipality_events(self) -> None:
        """県ページの部品を使っても、イベント名は市区町村ページのものにする。"""
        self.assertNotIn('data-track="prefecture_', self.html)
        self.assertNotIn("'prefecture_map", self.html)
        self.assertIn('data-track="municipality_manhole_click"', self.html)
        self.assertIn("'municipality_map_pin_click'", self.html)
        self.assertIn("PokefutaAnalytics.bindClickTracking(", self.html)

    def test_ranking_sends_whole_prefecture_municipalities_to_the_prefecture_page(self) -> None:
        html = MODULE.build_ranking_page(self.items, 7, "2026年10月4日")
        self.assertIn('href="/municipalities/tokyo/machida/"', html)
        self.assertIn('href="/prefectures/chiba/"', html)
        self.assertIn("県内のポケふたはすべて香取市にあります", html)
        self.assertNotIn("八王子市", html)  # 1枚は件数だけ

    def test_generate_all_writes_pages_and_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            pages = MODULE.generate_all(SYNTHETIC, SLUGS, {}, {}, out, today="2026年10月4日")
            self.assertEqual([m.name for m in pages], ["町田市"])
            self.assertTrue((out / "tokyo" / "machida" / "index.html").exists())
            self.assertTrue((out / "index.html").exists())
            self.assertFalse((out / "chiba").exists())


class CoverageTest(unittest.TestCase):
    TOTALS = {pref: 10 for pref in MUNI.PREFECTURE_ORDER}

    def test_coverage_name_counts_wards_and_towns_as_their_municipality(self) -> None:
        """政令市の区は市で、町名まで入った東京23区は区で数える（分母の市町村数と単位を揃える）。"""
        self.assertEqual(
            MUNI.coverage_name({"prefecture": "愛知県", "city": "名古屋市中区", "address": "愛知県名古屋市中区栄"}),
            "名古屋市",
        )
        self.assertEqual(
            MUNI.coverage_name({"prefecture": "東京都", "city": "台東区上野", "address": "東京都台東区上野公園"}),
            "台東区",
        )
        self.assertEqual(MUNI.coverage_name(SYNTHETIC[0]), "町田市")

    def test_prefecture_coverage(self) -> None:
        totals = {**self.TOTALS, "千葉県": 1}
        coverage = MUNI.prefecture_coverage(SYNTHETIC, totals)
        tokyo, chiba = coverage["東京都"], coverage["千葉県"]
        self.assertEqual((tokyo.covered, tokyo.total, tokyo.percent), (2, 10, 20))
        self.assertEqual(tokyo.multi, [("町田市", 3)])
        self.assertTrue(chiba.is_complete)
        self.assertEqual(MUNI.complete_prefectures(coverage), ["千葉県"])
        self.assertEqual(coverage["北海道"].covered, 0)

    def test_totals_file(self) -> None:
        totals = MUNI.load_municipality_totals()
        self.assertEqual(sum(totals.values()), 1741)
        self.assertEqual(totals["北海道"], 179)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "totals.json"
            path.write_text(json.dumps({"totals": {"北海道": 179}}, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                MUNI.load_municipality_totals(path)

    @unittest.skipIf(
        os.environ.get("POKEFUTA_PAGES_DEPLOY") == "1",
        "デプロイ中は止めない（設置データに依存する）",
    )
    def test_real_data_never_exceeds_the_municipality_total(self) -> None:
        """設置市町村が市町村数を超えたら、名前の揺れ（同じ自治体を2通りに数えている）か、分母が古い。"""
        records = PREF.load_records(PREF.DEFAULT_MANHOLES)
        over = [
            (c.prefecture, c.covered, c.total)
            for c in MUNI.prefecture_coverage(records).values()
            if c.covered > c.total
        ]
        self.assertEqual([], over)

    def test_prefecture_page_says_complete_and_single_municipality(self) -> None:
        coverage = MUNI.prefecture_coverage(SYNTHETIC, {**self.TOTALS, "千葉県": 1})
        chiba = [r for r in SYNTHETIC if r["prefecture"] == "千葉県"]
        html = PREF.build_page(
            "千葉県", "chiba", chiba, 1, {}, None,
            coverage=coverage["千葉県"], complete=["千葉県"],
        )
        self.assertIn("全1市町村にポケふたがある", html)
        self.assertIn("全市町村にポケふたがある全国1県のひとつです", html)
        self.assertIn('class="stats stats-3"', html)

        coverage = MUNI.prefecture_coverage(SYNTHETIC, {**self.TOTALS, "千葉県": 43})
        html = PREF.build_page(
            "千葉県", "chiba", chiba, 1, {}, None, coverage=coverage["千葉県"], complete=[],
        )
        self.assertIn("ポケふたがあるのは香取市だけです", html)  # ヒーローの導入
        # 千葉は「市町村別の設置枚数」が既にあるので、同じことを言う欄は出さない
        self.assertNotIn('aria-labelledby="coverage-heading"', html)

        # 市町村別の案内が無い県では欄を出す。1市町村だけならメーターは出さない
        saga = [_record(str(i), "佐賀県", "佐賀", 33.25, 130.30) for i in range(3)]
        coverage = MUNI.prefecture_coverage(saga, {**self.TOTALS, "佐賀県": 20})
        html = PREF.build_page("佐賀県", "saga", saga, 1, {}, None, coverage=coverage["佐賀県"], complete=[])
        self.assertIn("佐賀のポケふたはすべて佐賀市に", html)
        self.assertNotIn('aria-label="ポケふたがある市町村の割合"', html)

    def test_ranking_page_lists_complete_prefectures(self) -> None:
        items = MUNI.build_municipalities(SYNTHETIC, SLUGS)
        coverage = MUNI.prefecture_coverage(SYNTHETIC, {**self.TOTALS, "千葉県": 1})
        html = MODULE.build_ranking_page(items, 7, "2026年10月4日", coverage)
        self.assertIn("全市町村にポケふたがある1県", html)
        self.assertIn("ポケふたがある市町村が多い都道府県", html)


class InternalLinkTest(unittest.TestCase):
    def test_prefecture_page_links_to_its_municipality_pages(self) -> None:
        records = [r for r in SYNTHETIC if r["prefecture"] == "東京都"]
        html = PREF.build_page(
            "東京都", "tokyo", records, 1, {}, None,
            municipality_paths={"町田市": "/municipalities/tokyo/machida/"},
        )
        self.assertIn('href="/municipalities/tokyo/machida/"', html)
        self.assertIn("東京都の市区町村から探す", html)


if __name__ == "__main__":
    unittest.main()
