import json
import unittest
from pathlib import Path

from apps.scraper.manhole_titles import build_title_context, compute_titles

TITLES_PATH = Path(__file__).resolve().parents[2] / "dataset" / "manhole_titles.json"


def _ids_with_tag(master: dict, tag: str) -> set[str]:
    return {mid for mid, meta in master["manholes"].items() if tag in meta.get("tags", [])}


class HeritageTitleTest(unittest.TestCase):
    master = {
        "vocabulary": {
            "world_heritage": {
                "enabled": True,
                "emoji": "🌐",
                "label": "世界遺産エリアのポケふた（{heritage}）",
                "hashtag": "#世界遺産ポケふた",
                "hashtag_extra": "#{heritage}",
                "priority": 85,
            },
        },
        "islands": [],
        "lakes": [],
        "heritages": [{"heritage": "石見銀山", "ids": ["379"]}],
    }

    def _titles(self, manhole: dict) -> dict:
        titles = compute_titles(manhole, build_title_context([manhole], self.master), nc50=0, nc100=0)
        return {title["key"]: title for title in titles}

    def test_heritage_name_goes_into_label_and_hashtag(self):
        manhole = {"id": "379", "status": "active", "prefecture": "島根県", "city": "大田",
                   "tags": ["world_heritage"]}
        title = self._titles(manhole)["world_heritage"]
        self.assertEqual(title["label"], "世界遺産エリアのポケふた（石見銀山）")
        self.assertEqual(title["hashtag"], "#世界遺産ポケふた #石見銀山")

    def test_tag_without_heritage_entry_gets_no_title(self):
        # 名前の付かない世界遺産称号は出さない
        manhole = {"id": "1", "status": "active", "prefecture": "島根県", "city": "大田",
                   "tags": ["world_heritage"]}
        self.assertNotIn("world_heritage", self._titles(manhole))


class TitleMasterConsistencyTest(unittest.TestCase):
    """タグページ（tags）と称号（islands / heritages）が同じポケふたを指していること。"""

    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(TITLES_PATH.read_text(encoding="utf-8"))

    def test_world_heritage_tag_matches_heritages(self):
        heritage_ids = {str(i) for e in self.master["heritages"] for i in e["ids"]}
        self.assertEqual(_ids_with_tag(self.master, "world_heritage"), heritage_ids)

    def test_remote_island_tag_matches_islands(self):
        # prefecture+city 一致の島エントリは ids で書き、タグと突き合わせられるようにしておく
        for entry in self.master["islands"]:
            self.assertTrue(entry.get("ids"), entry["island"])
        island_ids = {str(i) for e in self.master["islands"] for i in e["ids"]}
        self.assertEqual(_ids_with_tag(self.master, "remote_island"), island_ids)


if __name__ == "__main__":
    unittest.main()
