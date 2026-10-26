from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from apps.scraper.character_manhole_works import CHARACTER_CSS_VERSION, WORK_PAGES, gundam_work_records, page_for_work
from apps.scraper.generate_character_work_pages import attach_user_photos, generate_html, generate_index_html, load_events, write_pages
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

    def test_title_leaves_the_list_query_to_the_map(self) -> None:
        self.assertIn("<title>ガンダムマンホールの巡り方ガイド｜地方・都道府県別の設置エリア</title>", self.html)
        # 一覧・地図の検索語は gmanhole_map.html に寄せる。ヒーローからパラメータ無しのURLへ送る
        self.assertIn('href="../../gmanhole_map.html">ガンダムマンホール一覧・地図 →</a>', self.html)

    def test_summarises_areas_instead_of_listing_each_spot(self) -> None:
        # 1基ずつの一覧（名称・住所・出典）は gmanhole_map.html だけが持つ
        self.assertNotIn('class="cw-spot"', self.html)
        self.assertNotIn("豊富町観光情報センター", self.html)
        self.assertNotIn("壊れた行", self.html)
        self.assertIn("<h3>北海道・東北 <small>1都道府県</small></h3>", self.html)
        self.assertIn("<strong>北海道</strong> <small>1基</small>", self.html)
        self.assertIn("<span>豊富町</span>", self.html)
        self.assertIn('gmanhole_map.html?work=gundam&amp;pref=%E5%8C%97%E6%B5%B7%E9%81%93', self.html)

    def test_page_does_not_claim_to_be_a_list(self) -> None:
        self.assertIn('<h1 id="work-heading">ガンダムマンホールを<br>巡る旅のガイド。</h1>', self.html)
        self.assertNotIn("マンホール一覧</h2>", self.html)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html).group(1))
        types = [node["@type"] for node in schema["@graph"]]
        self.assertEqual(["WebPage", "BreadcrumbList"], types)

    def test_records_without_a_prefecture_are_not_dropped_from_the_areas(self) -> None:
        records = gundam_work_records([GUNDAM_RECORDS[0], {**GUNDAM_RECORDS[0], "id": "x", "prefecture": "", "city": ""}])
        html = generate_html(GUNDAM, records, {})
        self.assertIn("<h3>地方未確認 <small>1都道府県</small></h3>", html)
        self.assertIn("<li><strong>都道府県未記録</strong> <small>1基</small><span>市町村未記録</span></li>", html)
        self.assertNotIn("pref=%E9%83%BD%E9%81%93%E5%BA%9C%E7%9C%8C%E6%9C%AA%E8%A8%98%E9%8C%B2", html)

    def test_faq_points_to_the_list_page_instead_of_calling_itself_a_list(self) -> None:
        self.assertIn("1基ずつの名称・住所・出典は「ガンダムマンホール一覧・地図」に載せています。", self.html)
        self.assertNotIn("掲載データに収録した設置場所の一覧です。", self.html)

    def test_equal_counts_per_city_are_explained_only_when_true(self) -> None:
        records = gundam_work_records([
            {**GUNDAM_RECORDS[0], "id": "a"}, {**GUNDAM_RECORDS[0], "id": "b"},
            {**GUNDAM_RECORDS[0], "id": "c", "city": "稚内市"}, {**GUNDAM_RECORDS[0], "id": "d", "city": "稚内市"},
        ])
        self.assertIn("どの市町村にも2基ずつ", generate_html(GUNDAM, records, {}))
        records.append({**records[0], "id": "e", "city": "天塩町"})
        uneven = generate_html(GUNDAM, records, {})
        self.assertNotIn("どの市町村にも", uneven)  # FAQ の「1基ずつの名称」とは別の、そろっているときの説明文
        self.assertIn("天塩町（1基）", uneven)  # 基数がそろわないときだけ市町村ごとに出す

    def test_does_not_hotlink_images_from_the_source_site(self) -> None:
        self.assertNotIn("img_manhole1.png", self.html)

    def test_skips_the_character_index_when_there_are_no_characters(self) -> None:
        self.assertNotIn('class="cw-index"', self.html)
        idolmaster = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertIn('class="cw-index"', idolmaster)

    def test_maps_use_the_gundam_filter(self) -> None:
        self.assertIn('gmanhole_map.html?work=gundam', self.html)
        self.assertNotIn('?work=%E6%A9%9F%E5%8B%95', self.html)  # 作品名そのままでは地図が絞り込めない

    def test_hero_uses_the_gundam_lid_and_generic_cta(self) -> None:
        self.assertIn('style="--c:#0044aa" aria-hidden="true">G</span>', self.html)
        self.assertIn(">設置エリアを見る ↓</a>", self.html)
        self.assertNotIn("アイドル・設置場所", self.html)


TOKAI = next(page for page in WORK_PAGES if page.slug == "tokai-onair")
TOKAI_RECORDS = [
    {"id": f"toa-{i}", "work": "東海オンエア", "title": f"東海オンエア{i}", "character": f"メンバー{i}",
     "landmark": "竜美ヶ丘公園", "prefecture": "愛知県", "city": "岡崎市", "address": "愛知県岡崎市",
     "lat": 34.95 + i / 100, "lng": 137.17, "status": "active"}
    for i in range(2)
]


class OtherWorkPageTest(unittest.TestCase):
    """アイマス・ガンダム以外の作品ページ。「〜 マンホール 地図／マップ」の検索に地図と地名で応える。"""

    def setUp(self) -> None:
        self.html = generate_html(TOKAI, TOKAI_RECORDS, {})

    def test_title_names_the_city_and_the_map(self) -> None:
        self.assertIn("<title>東海オンエアのマンホール一覧・地図｜岡崎市の設置場所マップ</title>", self.html)

    def test_embeds_the_location_map_with_work_specific_labels(self) -> None:
        self.assertIn('<h2 id="map-heading">東海オンエアのマンホールの設置場所マップ</h2>', self.html)
        self.assertIn('character-work-map.js?v=20261026a', self.html)
        payload = re.search(r'id="cw-map-data">(.*?)</script>', self.html).group(1)
        points = json.loads(payload)
        self.assertEqual(2, len(points))
        self.assertEqual("メンバー0（東海オンエアのマンホール）", points[0]["alt"])
        self.assertNotIn("ふたマス", self.html)

    def test_area_merges_wards_into_the_city_and_falls_back_to_the_prefecture(self) -> None:
        wards = [dict(TOKAI_RECORDS[0], city="静岡市葵区"), dict(TOKAI_RECORDS[1], city="静岡市清水区")]
        self.assertIn("｜静岡市の設置場所マップ</title>", generate_html(TOKAI, wards, {}))
        two_cities = [TOKAI_RECORDS[0], dict(TOKAI_RECORDS[1], city="豊田市")]
        self.assertIn("｜愛知県の設置場所マップ</title>", generate_html(TOKAI, two_cities, {}))
        two_prefs = [TOKAI_RECORDS[0], dict(TOKAI_RECORDS[1], prefecture="静岡県", city="浜松市")]
        self.assertIn("<title>東海オンエアのマンホール一覧・地図｜設置場所マップ</title>", generate_html(TOKAI, two_prefs, {}))
        same_name = [dict(TOKAI_RECORDS[0], prefecture="北海道", city="伊達市"),
                     dict(TOKAI_RECORDS[1], prefecture="福島県", city="伊達市")]
        self.assertIn("<title>東海オンエアのマンホール一覧・地図｜設置場所マップ</title>", generate_html(TOKAI, same_name, {}))
        no_pref = [dict(TOKAI_RECORDS[0], prefecture=""), TOKAI_RECORDS[1]]
        self.assertIn("<title>東海オンエアのマンホール一覧・地図｜設置場所マップ</title>", generate_html(TOKAI, no_pref, {}))


class WorkDefinitionsTest(unittest.TestCase):
    def test_idolmaster_brands_share_one_landing_page(self) -> None:
        self.assertIs(IDOLMASTER, page_for_work("アイドルマスター SideM"))
        self.assertIs(IDOLMASTER, page_for_work("学園アイドルマスター"))
        self.assertEqual("idolmaster", IDOLMASTER.map_query)


class IdolmasterPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 20, 12, tzinfo=JST)
        self.html = generate_html(IDOLMASTER, RECORDS, EVENT, now=self.now)

    def test_linked_user_photo_is_used_on_the_encyclopedia_card(self) -> None:
        submissions = [{
            "canonical_ref": "character:imas-a",
            "status": "active",
            "photo_url": "https://pokefuta.com/api/design-manholes/photo-a/photo?size=small",
            "source_url": "https://pokefuta.com/design-manholes/photo-a",
            "created_at": "2026-09-21T00:00:00Z",
        }]
        enriched = attach_user_photos(RECORDS, submissions)
        html = generate_html(IDOLMASTER, enriched, EVENT, now=self.now)
        self.assertIn("photo-a/photo?size=small", html)
        self.assertIn("みんなの投稿写真", html)
        self.assertIn("渡辺みのりのユーザー投稿写真", html)
        points = json.loads(re.search(r'id="cw-map-data">(.*?)</script>', html).group(1))
        self.assertEqual(submissions[0]["photo_url"], next(p for p in points if p["anchor"] == "spot-imas-a")["photo_url"])
        self.assertTrue(any(not p["photo_url"] for p in points))

    def test_unlinked_submission_does_not_replace_a_photo(self) -> None:
        submissions = [{
            "canonical_ref": None,
            "status": "active",
            "photo_url": "https://example.com/unlinked.jpg",
            "created_at": "2026-09-21T00:00:00Z",
        }]
        enriched = attach_user_photos(RECORDS, submissions)
        self.assertFalse(any(record.get("user_photo_url") for record in enriched))

    def test_public_photo_is_used_for_hero_and_social_and_schema(self) -> None:
        records = attach_user_photos(RECORDS, [{
            "canonical_ref": "character:imas-a", "status": "active",
            "photo_url": "https://example.com/public.jpg",
        }, {
            "canonical_ref": "character:imas-a", "status": "hidden",
            "photo_url": "https://example.com/private.jpg", "created_at": "2099-01-01",
        }])
        html = generate_html(IDOLMASTER, records, EVENT, now=self.now)
        hero = html.split('<figure class="cw-hero-photo">')[1].split('</figure>')[0]
        self.assertIn('fetchpriority="high" loading="eager"', hero)
        self.assertIn('href="#spot-imas-a"', hero)
        self.assertIn('茨城県筑西市に設置された渡辺みのり', hero)
        self.assertIn('property="og:image" content="https://example.com/public.jpg"', html)
        self.assertNotIn('private.jpg', html)
        self.assertNotIn('property="og:image:width"', html)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1))
        self.assertEqual('https://example.com/public.jpg', schema['@graph'][0]['primaryImageOfPage']['url'])

    def test_map_excludes_unknown_invalid_and_removed_coordinates(self) -> None:
        records = [dict(RECORDS[0]), dict(RECORDS[1], lat=None),
                   dict(RECORDS[0], id="invalid", lat=91), dict(RECORDS[2], lat=35, lng=139)]
        records[0]['character'] = '</script><script>alert(1)</script>'
        html = generate_html(IDOLMASTER, records, {}, now=self.now)
        payload = re.search(r'<script type="application/json" id="cw-map-data">(.*?)</script>', html).group(1)
        points = json.loads(payload)
        self.assertEqual(['spot-imas-a'], [point['anchor'] for point in points])
        self.assertNotIn('</script>', payload)
        self.assertIn('spot-imas-b', html)  # Unknown location remains in the static list.
        self.assertIn('座標確認済みの1枚', html)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1))
        items = next(n for n in schema['@graph'] if n['@type'] == 'ItemList')['itemListElement']
        self.assertEqual(1, sum('geo' in item['item'] for item in items))

    def test_empty_map_and_other_guides_keep_static_fallback(self) -> None:
        # 座標が1つも無いなら空の地図は出さず、設置場所一覧だけにする
        html = generate_html(IDOLMASTER, [dict(RECORDS[0], lat=None)], {}, now=self.now)
        self.assertNotIn('id="cw-map"', html)
        self.assertNotIn('character-work-map.js', html)
        self.assertIn('id="locations"', html)
        other = generate_html(GUNDAM, gundam_work_records(GUNDAM_RECORDS), {})
        self.assertNotIn('character-work-map.js', other)
        self.assertNotIn('leaflet', other)

    def test_hero_leads_to_official_checkin(self) -> None:
        self.assertIn("ふたマス一覧・設置場所マップ", self.html)
        self.assertIn("担当アイドルのふたを訪ねて、公式チェックインへ。", self.html)
        self.assertIn("バンダイナムコID", self.html)
        self.assertIn("位置情報", self.html)
        self.assertIn("同じスポットは1回限り有効", self.html)
        self.assertIn("マイデスクに表示できる称号", self.html)
        self.assertIn("2027年7月25日 9:59", self.html)
        self.assertIn("ふたマス!!!!!!公式プロジェクト", self.html)
        self.assertIn("フタマスと検索されることもありますが、公式名称は『ふたマス!!!!!!』です。", self.html)

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
        self.assertIn("ふたマス一覧・設置場所マップ", html)
        self.assertIn("フタマスと検索されることもありますが、公式名称は『ふたマス!!!!!!』です。", html)
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
        self.assertIn('<meta name="robots" content="index,follow,max-image-preview:large">', html)

    def test_work_guides_link_back_to_the_national_list_not_the_hub(self) -> None:
        html = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertNotIn('href="../"', html)
        self.assertIn('href="../../character_manholes.html#works"', html)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        crumbs = next(n for n in schema["@graph"] if n["@type"] == "BreadcrumbList")["itemListElement"]
        self.assertEqual(["ポケふた図鑑", "キャラクターマンホール全国一覧", "アイドルマスター"], [c["name"] for c in crumbs])

    def test_work_guides_load_the_same_stylesheet_version_as_the_national_list(self) -> None:
        """character-work.css は全国一覧と共有。バージョンがずれると作品ガイドに古いCSSが残る。"""
        html = generate_html(IDOLMASTER, RECORDS, EVENT, now=datetime(2026, 9, 20, tzinfo=JST))
        self.assertIn(f'assets/character-work.css?v={CHARACTER_CSS_VERSION}"', html)

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
