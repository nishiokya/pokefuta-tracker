from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from apps.scraper.character_manhole_works import WORK_PAGES, gundam_work_records, page_for_work
from apps.scraper.generate_character_work_pages import generate_html, generate_index_html, load_events, write_pages
from apps.scraper.generate_character_manhole_page import _is_active, load_ndjson
from apps.scraper.photo_caption import JST


IDOLMASTER = next(page for page in WORK_PAGES if page.slug == "idolmaster")
EVENT = {
    "idolmaster": {
        "type": "idolmaster_20th_checkin",
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
        "address": "北海道河東郡鹿追町東町3丁目2-7", "lat": 43.0965648, "lng": 142.9902339,
        "source_url": "https://example.com/shikaoi", "status": "active", "installation_status": "installed",
    },
    {
        "id": "removed", "work": "アイドルマスター", "title": "撤去済み",
        "character": "撤去済み", "prefecture": "東京都", "city": "町田市", "status": "active",
        "installation_status": "removed",
    },
]


GUNDAM = next(page for page in WORK_PAGES if page.slug == "gundam")
GUNDAM_RECORDS = [
    {"id": "1", "title": "豊富町観光情報センター", "prefecture": "北海道", "city": "豊富町",
     "address": "北海道天塩郡豊富町字豊富駅前通", "image_urls": ["../img/about/img1/img_manhole1.png"],
     "franchise": "gundam", "characters": [], "lat": 45.10487, "lng": 141.772842,
     "detail_url": "https://www.g-manhole.net/about/detail.php?id=1", "status": "active"},
    {"id": "2", "title": "壊れた行", "prefecture": "", "status": "invalid",
     "detail_url": "https://www.g-manhole.net/about/detail.php?id=2"},
]


class GundamGuideTest(unittest.TestCase):
    """ガンダムは別データセット（gmanhole.ndjson）から作品ガイドを作る。"""

    def setUp(self) -> None:
        self.html = generate_html(GUNDAM, gundam_work_records(GUNDAM_RECORDS), {})

    def test_title_targets_the_gundam_manhole_query(self) -> None:
        self.assertIn("<title>ガンダムマンホール一覧｜設置場所・地図</title>", self.html)

    def test_lists_only_active_spots_with_the_official_source(self) -> None:
        self.assertEqual(1, self.html.count('class="cw-spot"'))
        self.assertIn('href="https://www.g-manhole.net/about/detail.php?id=1"', self.html)
        self.assertNotIn("壊れた行", self.html)

    def test_does_not_hotlink_images_from_the_source_site(self) -> None:
        self.assertNotIn("img_manhole1.png", self.html)

    def test_place_name_is_not_repeated_as_the_location_line(self) -> None:
        self.assertEqual(1, self.html.count("豊富町観光情報センター</h4>"))
        self.assertNotIn('<p class="cw-location">豊富町観光情報センター</p>', self.html)

    def test_skips_the_character_index_when_there_are_no_characters(self) -> None:
        self.assertNotIn('class="cw-index"', self.html)
        idolmaster = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertIn('class="cw-index"', idolmaster)

    def test_maps_use_the_gundam_filter(self) -> None:
        self.assertIn('gmanhole_map.html?work=gundam', self.html)
        self.assertNotIn('?work=%E6%A9%9F%E5%8B%95', self.html)  # 作品名そのままでは地図が絞り込めない

    def test_hero_uses_the_gundam_lid_and_generic_cta(self) -> None:
        self.assertIn('style="--c:#0044aa" aria-hidden="true">G</span>', self.html)
        self.assertIn(">設置場所を探す ↓</a>", self.html)
        self.assertNotIn("アイドル・設置場所", self.html)


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

    def test_all_verified_coordinates_are_mapped(self) -> None:
        self.assertNotIn("正確な座標は確認中です", self.html)
        self.assertNotIn("地図のピンは座標確認済み", self.html)

    def test_event_copy_changes_after_deadline(self) -> None:
        html = generate_html(
            IDOLMASTER, RECORDS, EVENT,
            now=datetime(2027, 7, 25, 10, tzinfo=JST),
        )
        self.assertIn("チェックイン企画の掲載期間は終了しました", html)
        self.assertIn("公式プロジェクトの最新情報を見る", html)
        self.assertNotIn("ふたマスの対象スポットを訪ねると、公式ポータルのチェックイン企画に参加できます。", html)
        self.assertNotIn("バンダイナムコIDを用意", html)
        self.assertNotIn("公式でチェックイン", html)
        self.assertNotIn("公式スポット案内（ログインが必要）", html)
        self.assertNotIn("チェックインの参加方法", html)
        self.assertNotIn("担当アイドルのふたを訪ねて、公式チェックインへ。", html)

    def test_event_url_with_trailing_slash_has_one_separator(self) -> None:
        events = json.loads(json.dumps(EVENT))
        events["idolmaster"]["url"] += "/"
        html = generate_html(IDOLMASTER, RECORDS, events, now=self.now)
        self.assertIn("20th_voyage_manhole/manhole_01", html)
        self.assertNotIn("20th_voyage_manhole//manhole_01", html)

    def test_has_large_social_card(self) -> None:
        self.assertIn('property="og:image"', self.html)
        self.assertIn('name="twitter:card" content="summary_large_image"', self.html)

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
            self.assertEqual([
                output / "characters/index.html",
                output / "characters/idolmaster/index.html",
            ], written)
            self.assertTrue(all(path.exists() for path in written))

    def test_character_index_redirects_to_the_national_list(self) -> None:
        """/characters/ は全国一覧に統合した。旧URLは作品セクションへ転送するだけ。"""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_pages(RECORDS, EVENT, output)
            html = (output / "characters/index.html").read_text(encoding="utf-8")
            self.assertIn('<meta http-equiv="refresh" content="0; url=../character_manholes.html#works">', html)
            self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/character_manholes.html">', html)
            self.assertIn('href="../character_manholes.html#works"', html)

    def test_index_is_not_indexable(self) -> None:
        root = Path(__file__).resolve().parents[2]
        html = generate_index_html(load_ndjson(root / "docs/character_manholes.ndjson"))
        self.assertIn('<meta name="robots" content="noindex,follow">', html)

    def test_work_guides_stay_indexable(self) -> None:
        html = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertIn('<meta name="robots" content="index,follow">', html)

    def test_work_guides_link_back_to_the_national_list_not_the_hub(self) -> None:
        html = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertNotIn('href="../"', html)
        self.assertIn('href="../../character_manholes.html#works"', html)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        crumbs = next(n for n in schema["@graph"] if n["@type"] == "BreadcrumbList")["itemListElement"]
        self.assertEqual(["ポケふた図鑑", "キャラクターマンホール全国一覧", "アイドルマスター"], [c["name"] for c in crumbs])

    def test_work_guide_hero_uses_the_work_marker_color(self) -> None:
        """全国一覧の作品カードと同じ色・同じ字の蓋をヒーローに出す。"""
        records = [dict(r, marker_color="#f97316", marker_label="ア") for r in RECORDS]
        html = generate_html(IDOLMASTER, records, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertIn('<span class="cm-lid cm-lid--lg" style="--c:#f97316" aria-hidden="true">ア</span>', html)

    def test_loaded_event_is_not_validated_twice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps(EVENT), encoding="utf-8")
            loaded = load_events(path)
            with patch("apps.scraper.generate_character_work_pages.validate_event") as validate:
                html = generate_html(IDOLMASTER, RECORDS, loaded, now=datetime(2026, 9, 20, tzinfo=JST))
            validate.assert_not_called()
            self.assertIn("公式チェックイン企画", html)

    def test_map_supports_grouped_idolmaster_filter(self) -> None:
        map_html = (Path(__file__).parents[1] / "web/gmanhole_map.html").read_text(encoding="utf-8")
        self.assertIn("workParam === 'idolmaster'", map_html)
        self.assertIn("work.includes('アイドルマスター')", map_html)

    def test_invalid_optional_event_is_skipped_without_stopping_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            invalid = json.loads(json.dumps(EVENT))
            invalid["idolmaster"]["ends_at"] = "2027-07-25T09:59:00"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            self.assertEqual({}, load_events(path))
            html = generate_html(IDOLMASTER, RECORDS, {}, now=datetime(2026, 9, 20, tzinfo=JST))
            self.assertNotIn("公式チェックイン企画", html)

            path.write_text("{broken", encoding="utf-8")
            self.assertEqual({}, load_events(path))

    def test_event_for_another_work_cannot_emit_idolmaster_copy(self) -> None:
        zombie = next(page for page in WORK_PAGES if page.slug == "zombieland-saga")
        records = [{**RECORDS[0], "id": "zls-test", "work": "ゾンビランドサガ"}]
        events = {"zombieland-saga": EVENT["idolmaster"]}
        html = generate_html(zombie, records, events, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertNotIn("アイドルマスター ポータル", html)


if __name__ == "__main__":
    unittest.main()
