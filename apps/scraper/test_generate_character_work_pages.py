from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from apps.scraper.character_manhole_works import WORK_PAGES, page_for_work
from apps.scraper.generate_character_work_pages import generate_html, write_pages
from apps.scraper.photo_caption import JST


IDOLMASTER = next(page for page in WORK_PAGES if page.slug == "idolmaster")
EVENT = {
    "idolmaster": {
        "name": "ふたマス!!!!!! スポットチェックイン",
        "url": "https://idolmaster-official.jp/mydesk/spot/20th_voyage_manhole",
        "project_url": "https://idolmaster-official.jp/20th_anniversary/manhole",
        "verified_at": "2026-09-20",
        "ends_at": "2027-07-25T09:59:00+09:00",
        "spots": {"imas-a": "manhole_01", "imas-b": "manhole_10"},
    }
}
RECORDS = [
    {
        "id": "imas-a", "work": "アイドルマスター SideM", "title": "渡辺みのり（ふたマス!!!!!!）",
        "character": "渡辺みのり", "landmark": "下館駅北口", "prefecture": "茨城県", "city": "筑西市",
        "address": "茨城県筑西市丙366", "lat": 36.3, "lng": 139.9,
        "source_url": "https://example.com/source?a=1&b=2", "status": "active", "installation_status": "installed",
    },
    {
        "id": "imas-b", "work": "学園アイドルマスター", "title": "倉本千奈（ふたマス!!!!!!）",
        "character": "倉本千奈", "landmark": "道の駅しかおい", "prefecture": "北海道", "city": "鹿追町",
        "address": "北海道河東郡鹿追町東町3丁目2-7", "lat": None, "lng": None,
        "source_url": "https://example.com/shikaoi", "status": "active", "installation_status": "installed",
    },
    {
        "id": "removed", "work": "アイドルマスター", "title": "撤去済み",
        "character": "撤去済み", "prefecture": "東京都", "city": "町田市", "status": "active",
        "installation_status": "removed",
    },
]


class WorkDefinitionsTest(unittest.TestCase):
    def test_idolmaster_brands_share_one_landing_page(self) -> None:
        self.assertIs(IDOLMASTER, page_for_work("アイドルマスター SideM"))
        self.assertIs(IDOLMASTER, page_for_work("学園アイドルマスター"))
        self.assertEqual("idolmaster", IDOLMASTER.map_query)


class IdolmasterPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 20, 12, tzinfo=JST)
        self.html = generate_html(IDOLMASTER, RECORDS, EVENT, now=self.now)

    def test_hero_leads_to_official_checkin(self) -> None:
        self.assertIn("アイマスのマンホール、<br>会いに行こう。", self.html)
        self.assertIn("担当アイドルのふたを訪ねて、公式チェックインへ。", self.html)
        self.assertIn("バンダイナムコID", self.html)
        self.assertIn("位置情報", self.html)
        self.assertIn("同じスポットは1回限り有効", self.html)
        self.assertIn("マイデスクに表示できる称号", self.html)
        self.assertIn("2027年7月25日 9:59", self.html)
        self.assertIn("ふたマス!!!!!!公式プロジェクト", self.html)

    def test_lists_each_active_idol_once(self) -> None:
        schema = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html).group(1)
        item_list = next(node for node in json.loads(schema)["@graph"] if node["@type"] == "ItemList")
        self.assertEqual(2, item_list["numberOfItems"])
        self.assertIn("渡辺みのり", self.html)
        self.assertIn("倉本千奈", self.html)
        self.assertNotIn("撤去済み", self.html)

    def test_links_to_official_spot_pages_and_escapes_urls(self) -> None:
        self.assertIn("20th_voyage_manhole/manhole_01", self.html)
        self.assertIn("20th_voyage_manhole/manhole_10", self.html)
        self.assertIn("source?a=1&amp;b=2", self.html)

    def test_unverified_coordinates_are_disclosed(self) -> None:
        self.assertIn("正確な座標は確認中です", self.html)
        self.assertIn("地図のピンは座標確認済みの1枚", self.html)

    def test_event_copy_changes_after_deadline(self) -> None:
        html = generate_html(
            IDOLMASTER, RECORDS, EVENT,
            now=datetime(2027, 7, 25, 10, tzinfo=JST),
        )
        self.assertIn("チェックイン企画の掲載期間は終了しました", html)
        self.assertIn("公式の最新案内を確認する", html)
        self.assertNotIn("ふたマスの対象スポットを訪ねると、公式ポータルのチェックイン企画に参加できます。", html)

    def test_analytics_uses_shared_loader(self) -> None:
        self.assertIn("assets/analytics.js", self.html)
        self.assertIn("PokefutaAnalytics.init", self.html)
        self.assertNotIn("googletagmanager.com/gtag", self.html)
        self.assertIn('"work": "idolmaster"', self.html)


class GenerateAllPagesTest(unittest.TestCase):
    def test_only_pages_with_active_records_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            written = write_pages(RECORDS, EVENT, output)
            self.assertEqual([output / "characters/idolmaster/index.html"], written)
            self.assertTrue(written[0].exists())

    def test_map_supports_grouped_idolmaster_filter(self) -> None:
        map_html = (Path(__file__).parents[1] / "web/gmanhole_map.html").read_text(encoding="utf-8")
        self.assertIn("workParam === 'idolmaster'", map_html)
        self.assertIn("work.includes('アイドルマスター')", map_html)


if __name__ == "__main__":
    unittest.main()
