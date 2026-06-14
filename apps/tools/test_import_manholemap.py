import unittest

from apps.tools.import_manholemap import (
    build_jsonld,
    build_municipality_index,
    detect_municipality,
    record_to_jsonld,
)


class ImportManholeMapTest(unittest.TestCase):
    def setUp(self):
        self.cities = [
            {"pref": "東京都", "city": "渋谷区"},
            {"pref": "北海道", "city": "札幌市中央区"},
            {"pref": "北海道", "city": "札幌市"},
        ]
        self.index = build_municipality_index(self.cities)
        self.record = {
            "id": "123",
            "username": "owner",
            "created": "2020-07-16 22:34:13",
            "updated": "2022-04-09 11:49:16",
            "tag": "3月のライオン",
            "type": "image/jpeg",
            "text": "王さまニャー",
            "lat": 35.6794,
            "lng": 139.7080,
            "nice": 2,
            "width": 480,
            "height": 320,
            "misc": "東京都渋谷区千駄ヶ谷4丁目15",
        }

    def test_detects_longest_municipality(self):
        self.assertEqual(
            detect_municipality("北海道札幌市中央区北一条西", "北海道", self.index),
            "札幌市中央区",
        )

    def test_converts_record_to_schema_org_jsonld(self):
        item = record_to_jsonld(self.record, "東京都", self.index)
        self.assertEqual(item["@type"], "Place")
        self.assertEqual(item["identifier"], "123")
        self.assertEqual(item["address"]["addressLocality"], "渋谷区")
        self.assertEqual(item["geo"]["latitude"], 35.6794)
        self.assertEqual(item["description"], "王さまニャー")
        self.assertEqual(item["image"]["contentUrl"], "https://manholemap.juge.me/get?id=123")

    def test_deduplicates_and_sorts_graph(self):
        second = {**self.record, "id": "99"}
        data = build_jsonld(
            [
                ("東京都", self.record),
                ("東京都", second),
                ("東京都", self.record),
            ],
            self.index,
            "2026-06-14T00:00:00+00:00",
        )
        self.assertEqual(data["numberOfItems"], 2)
        self.assertEqual(
            [item["identifier"] for item in data["@graph"]],
            ["123", "99"],
        )


if __name__ == "__main__":
    unittest.main()
