from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("generate_prefecture_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_prefecture_pages", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class GeneratePrefecturePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = MODULE.load_records(MODULE.DEFAULT_MANHOLES)
        cls.pokemon_slugs = MODULE.load_pokemon_slugs(MODULE.DEFAULT_POKEMON)
        cls.photos = MODULE.load_photos(MODULE.DEFAULT_PHOTOS)
        cls.trivia = MODULE.load_trivia(MODULE.DEFAULT_TRIVIA)

    def test_generates_all_47_prefectures_including_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            count = MODULE.generate_all(
                self.records, self.pokemon_slugs, self.trivia, output,
                photos=self.photos,
            )
            self.assertEqual(47, count)
            self.assertEqual(47, len(list(output.glob("*/index.html"))))
            gunma = (output / "gunma" / "index.html").read_text(encoding="utf-8")
            self.assertIn("現在未設置", gunma)
            self.assertIn("canonical", gunma)

    def test_fukui_page_has_required_sections_and_links(self) -> None:
        records = [r for r in self.records if r.get("prefecture") == "福井県"]
        html = MODULE.build_page(
            "福井県",
            "fukui",
            records,
            MODULE.build_rankings(self.records)["福井県"],
            self.pokemon_slugs,
            self.trivia["福井県"],
            photos=self.photos,
        )
        self.assertIn("福井県のポケふた17枚", html)
        self.assertIn("福井県の設置マップ", html)
        self.assertIn("福井県で会えるポケモン", html)
        self.assertIn("福井県のマンホール一覧", html)
        self.assertIn("福井県のポケふたトリビア", html)
        self.assertIn("/pokemon/dragonite/", html)
        self.assertIn("/manholes/", html)
        self.assertIn("prefecture_manhole_click", html)
        self.assertIn(
            "旅行やポケふた巡りの計画にご活用ください。",
            html,
        )
        self.assertLess(html.index('id="map-heading"'), html.index('id="trivia-heading"'))
        self.assertIn("まず知りたい", html)
        self.assertIn(
            "福井県には17枚のポケふたがあります。県内16自治体に広がっています。",
            html,
        )
        self.assertIn("https://pokefuta.com/visits?from=data", html)
        self.assertNotIn("utm_", html)
        self.assertIn("prefecture_visit_cta_click", html)
        self.assertIn("prefecture_photo_candidate_click", html)
        self.assertIn("prefecture_photo_upload_start", html)
        self.assertIn("prefecture_map_pin_click", html)
        self.assertIn("prefecture_google_maps_click", html)
        self.assertIn("prefecture_scroll_depth", html)
        self.assertIn("<!-- adsense:prefecture -->", html)
        self.assertIn("'page_path': '/prefectures/' + \"fukui\" + '/'", html)
        self.assertIn("site_type: 'map'", html)
        self.assertLess(
            html.index('id="manhole-heading"'),
            html.index('id="pokemon-heading"'),
        )
        self.assertIn("ほか13種類のポケモンを見る", html)
        self.assertEqual(25, html.count('class="pokemon-card"'))
        first_pokemon_section = html[
            html.index('<div class="pokemon-grid">'):
            html.index('<details class="pokemon-more">')
        ]
        self.assertEqual(12, first_pokemon_section.count('class="pokemon-card"'))

    def test_active_event_renders_section_with_link(self) -> None:
        events = MODULE.load_events(MODULE.DEFAULT_EVENTS)
        self.assertIn("高知県", events)
        kochi_event = events["高知県"][0]
        html = MODULE.build_page(
            "高知県",
            "kochi",
            [r for r in self.records if r.get("prefecture") == "高知県"],
            MODULE.build_rankings(self.records)["高知県"],
            self.pokemon_slugs,
            self.trivia.get("高知県"),
            events["高知県"],
        )
        self.assertIn("開催中のイベント・スタンプラリー", html)
        self.assertIn(kochi_event["url"], html)
        self.assertIn("prefecture_event_click", html)

    def test_expired_event_is_hidden(self) -> None:
        import datetime

        past = datetime.date(2020, 1, 1)
        html = MODULE._events_html(
            [
                {
                    "title": "終了イベント",
                    "url": "https://example.com/",
                    "start": past,
                    "end": past,
                }
            ]
        )
        self.assertEqual("", html)

    def test_prefecture_without_events_has_no_event_section(self) -> None:
        html = MODULE.build_page(
            "福井県",
            "fukui",
            [r for r in self.records if r.get("prefecture") == "福井県"],
            MODULE.build_rankings(self.records)["福井県"],
            self.pokemon_slugs,
            self.trivia["福井県"],
        )
        self.assertNotIn("開催中のイベント・スタンプラリー", html)

    def test_empty_prefecture_meta_description_is_complete(self) -> None:
        html = MODULE.build_page(
            "群馬県",
            "gunma",
            [],
            None,
            self.pokemon_slugs,
            self.trivia["群馬県"],
        )
        self.assertIn(
            "現在の設置枚数や全国のポケモンマンホール情報を確認できます。",
            html,
        )
        self.assertLess(html.index('id="map-heading"'), html.index('id="trivia-heading"'))
        self.assertIn(
            "群馬県では、現在ポケふたの設置を確認できていません。",
            html,
        )
        hero = html[html.index('<header class="hero">'):html.index("</header>")]
        self.assertIn('href="/summary/"', hero)
        self.assertNotIn('href="#manhole-list"', hero)
        self.assertNotIn('href="#prefecture-map"', hero)
        self.assertIn("全国のポケふたから次の行き先を探す", html)
        self.assertNotIn("STEP 1", html)

    def test_nagano_desktop_header_summary_mentions_first_month(self) -> None:
        records = [r for r in self.records if r.get("prefecture") == "長野県"]
        html = MODULE.build_page(
            "長野県",
            "nagano",
            records,
            MODULE.build_rankings(self.records)["長野県"],
            self.pokemon_slugs,
            self.trivia["長野県"],
        )
        self.assertIn('class="hero-summary"', html)
        self.assertIn("長野県は2026年7月にポケふた初登場。", html)
        self.assertIn("現在は6自治体で6枚を巡れます。", html)
        self.assertIn(".hero-summary { display: none; }", html)

    def test_prefecture_summary_omits_initial_crawl_month(self) -> None:
        records = [r for r in self.records if r.get("prefecture") == "福井県"]
        html = MODULE.build_page(
            "福井県",
            "fukui",
            records,
            MODULE.build_rankings(self.records)["福井県"],
            self.pokemon_slugs,
            self.trivia["福井県"],
        )
        self.assertIn("福井県では16自治体で17枚のポケふたを巡れます。", html)
        self.assertNotIn("福井県は2025年10月にポケふた初登場。", html)

    def test_manhole_card_shows_preinstall_badge(self) -> None:
        records = [
            {
                "id": "9001",
                "city": "岡谷",
                "pokemons": ["ピカチュウ"],
                "installed": False,
                "installation_note": "2026年8月上旬までに設置予定。",
            }
        ]
        html = MODULE._manhole_cards(records)
        self.assertIn(
            '<span class="manhole-preinstall-badge">🚧 設置前</span>', html
        )
        self.assertIn("設置後に投稿可能", html)
        self.assertNotIn("pokefuta.com/upload", html)

    def test_manhole_card_normal_has_no_preinstall_badge(self) -> None:
        # installed absent and installed True must both be treated as installed.
        records = [
            {"id": "9002", "city": "岡谷", "pokemons": ["ピカチュウ"]},
            {"id": "9003", "city": "伊那", "pokemons": ["イーブイ"], "installed": True},
        ]
        html = MODULE._manhole_cards(records)
        self.assertNotIn("manhole-preinstall-badge", html)

    def test_photo_section_adapts_to_inventory_without_changing_template(self) -> None:
        records = [
            {
                "id": "9001",
                "prefecture": "北海道",
                "city": "写真あり町",
                "pokemons": ["ロコン"],
                "lat": 43.0,
                "lng": 141.0,
            },
            {
                "id": "9002",
                "prefecture": "北海道",
                "city": "写真なし町",
                "pokemons": ["ピカチュウ"],
                "lat": 44.0,
                "lng": 142.0,
            },
        ]
        photos = {
            "9001": {
                "url": "https://images.pokefuta.com/photos/9001.jpg",
                "created_at": "2026-07-20T00:00:00Z",
                "display_name": "旅人",
                "public_user_id": "6096691c-eeda-4e73-8401-a11274868ede",
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "dataset" / "manhole" / "image" / "9001_latest.jpeg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"test image")
            with mock.patch.object(MODULE, "ROOT", root):
                html = MODULE.build_page(
                    "北海道", "hokkaido", records, 1, self.pokemon_slugs, None,
                    photos=photos,
                )
        self.assertIn("1<span> / 2地点</span>", html)
        self.assertIn('aria-valuenow="50"', html)
        self.assertIn('loading="lazy" decoding="async" width="640" height="480"', html)
        self.assertIn("旅人さんの投稿", html)
        self.assertIn(
            'href="https://pokefuta.com/users/'
            '6096691c-eeda-4e73-8401-a11274868ede/visits?from=data"',
            html,
        )
        self.assertIn('class="photo-card-poster"', html)
        self.assertIn("写真未掲載のポケふたは1地点", html)
        self.assertIn("最初の写真を投稿", html)
        self.assertIn("manhole_id=9002&amp;from=data", html)
        self.assertIn('data-photo-state="missing"', html)
        self.assertIn("const markerClass = point.is_preinstall", html)
        self.assertIn("html: '<div class=\"prefecture-marker ' + markerClass", html)
        self.assertIn("title: (point.city || '所在地不明') + 'のポケふた'", html)
        self.assertIn("? '設置予定'", html)

    def test_photo_section_zero_inventory_invites_first_contribution(self) -> None:
        records = [
            {"id": "1", "city": "A市", "pokemons": ["イーブイ"]},
            {"id": "2", "city": "B市", "pokemons": ["ロコン"]},
        ]
        html = MODULE._photo_section("宮崎県", "miyazaki", records, {})
        self.assertIn('aria-valuenow="0"', html)
        self.assertIn("最初の1枚を募集中", html)
        self.assertEqual(2, html.count('class="contribution-card"'))
        self.assertNotIn("photo-showcase-grid", html)

    def test_untrusted_photo_url_is_not_rendered(self) -> None:
        records = [{"id": "9901", "city": "A市", "pokemons": ["イーブイ"]}]
        html = MODULE._photo_section(
            "宮崎県", "miyazaki", records,
            {"9901": {"url": "javascript:alert(1)", "created_at": "2026-07-20"}},
        )
        self.assertNotIn("javascript:", html)
        self.assertIn("写真未掲載のポケふたは1地点", html)

    def test_remote_photo_url_is_not_used_without_local_asset(self) -> None:
        record = {"id": "9902", "city": "A市"}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(MODULE, "ROOT", Path(directory)):
                self.assertEqual(
                    "",
                    MODULE._photo_asset_url(
                        record,
                        {"url": "https://example.r2.cloudflarestorage.com/photo.jpg"},
                    ),
                )

    def test_preinstall_records_are_map_points_without_photo_ctas(self) -> None:
        records = [
            {
                "id": "installed",
                "city": "設置済み市",
                "pokemons": ["イーブイ"],
                "lat": 35.0,
                "lng": 139.0,
            },
            {
                "id": "preinstall",
                "city": "設置前市",
                "pokemons": ["ロコン"],
                "lat": 36.0,
                "lng": 140.0,
                "installed": False,
            },
        ]
        html = MODULE.build_page(
            "長野県", "nagano", records, 1, self.pokemon_slugs, None,
        )
        self.assertIn("0<span> / 1地点</span>", html)
        self.assertIn("写真未掲載のポケふたは1地点", html)
        self.assertNotIn("manhole_id=preinstall", html)
        points_json = html.split("const points = ", 1)[1].split(";", 1)[0]
        points = __import__("json").loads(points_json)
        self.assertEqual(
            ["installed", "preinstall"],
            [point["id"] for point in points],
        )
        preinstall = next(point for point in points if point["id"] == "preinstall")
        self.assertTrue(preinstall["is_preinstall"])
        self.assertEqual("", preinstall["photo_url"])
        self.assertIn('<i class="legend-dot preinstall"></i>設置予定', html)
        self.assertIn("const uploadHtml = point.is_preinstall", html)
        self.assertIn("point.is_preinstall ? ' preinstall-actions' : ''", html)
        self.assertIn("設置後に写真を投稿できます", html)

    def test_preinstall_only_prefecture_prioritizes_planned_map(self) -> None:
        records = [
            {
                "id": "planned",
                "city": "設置予定市",
                "pokemons": ["ロコン"],
                "lat": 36.0,
                "lng": 140.0,
                "installed": False,
            }
        ]
        html = MODULE.build_page(
            "長野県", "nagano", records, 1, self.pokemon_slugs, None,
        )
        hero = html[html.index('<header class="hero">'):html.index("</header>")]
        self.assertIn('href="#prefecture-map"', hero)
        self.assertIn("設置予定地を地図で見る", hero)
        self.assertNotIn('href="#manhole-list"', hero)
        self.assertIn("設置予定を確認して、次の行き先を探す", html)

    def test_attribute_values_are_escaped_and_click_surfaces_are_distinct(self) -> None:
        html = MODULE._manhole_cards(
            [{"id": 'bad"id', "city": '引用符"市', "pokemons": ["イーブイ"]}],
            slug="test",
        )
        self.assertIn('data-manhole-id="bad&quot;id"', html)
        self.assertIn('data-content-id="bad&quot;id"', html)
        self.assertIn('data-surface="manhole_card"', html)
        self.assertIn('data-surface="manhole_actions"', html)
        self.assertNotIn('data-manhole-id="bad"id"', html)

    def test_downloaded_photo_asset_is_preferred_over_r2_original(self) -> None:
        record = next((
            record for record in self.records
            if str(record.get("id")) in self.photos
            and (MODULE.ROOT / "dataset" / "manhole" / "image" /
                 f"{record['id']}_latest.jpeg").exists()
        ), None)
        if record is None:
            self.skipTest("downloaded photo fixture is unavailable")
        manhole_id = str(record["id"])
        asset_url = MODULE._photo_asset_url(record, self.photos[manhole_id])
        self.assertEqual(f"/manhole/image/{manhole_id}_latest.jpeg", asset_url)
        self.assertNotIn("r2.cloudflarestorage.com", asset_url)

    def test_tied_counts_share_rank(self) -> None:
        records = [
            {"id": "1", "status": "active", "prefecture": "青森県"},
            {"id": "2", "status": "active", "prefecture": "岩手県"},
            {"id": "3", "status": "active", "prefecture": "宮城県"},
            {"id": "4", "status": "active", "prefecture": "宮城県"},
        ]
        ranks = MODULE.build_rankings(records)
        self.assertEqual(1, ranks["宮城県"])
        self.assertEqual(2, ranks["青森県"])
        self.assertEqual(2, ranks["岩手県"])
        self.assertIsNone(ranks["秋田県"])


class PrefecturePageDeployContractTest(unittest.TestCase):
    """Stable deploy gate that does not depend on daily production counts."""

    def test_synthetic_prefecture_page_contract(self) -> None:
        records = [
            {
                "id": "contract-1",
                "status": "active",
                "prefecture": "北海道",
                "city": "札幌市",
                "pokemons": ["ピカチュウ"],
                "lat": 43.0,
                "lng": 141.0,
            }
        ]
        html = MODULE.build_page(
            "北海道", "hokkaido", records, 1, {"ピカチュウ": "pikachu"}, None,
        )
        for expected in (
            '<link rel="canonical" href="https://data.pokefuta.com/prefectures/hokkaido/">',
            '<h1>北海道のポケふた</h1>',
            'id="prefecture-map"',
            'id="prefecture-photos"',
            'id="manhole-list"',
            "prefecture_photo_upload_start",
            "prefecture_map_pin_click",
            "prefecture_scroll_depth",
            "prefecture_photo_cta_click",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)
        self.assertIn("window.removeEventListener('scroll', reportScrollDepth)", html)

    def test_synthetic_generation_writes_all_prefectures(self) -> None:
        records = [
            {
                "id": "contract-1",
                "status": "active",
                "prefecture": "北海道",
                "city": "札幌市",
                "pokemons": ["ピカチュウ"],
                "lat": 43.0,
                "lng": 141.0,
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            count = MODULE.generate_all(
                records,
                {"ピカチュウ": "pikachu"},
                {},
                Path(directory),
            )
            self.assertEqual(47, count)
            self.assertEqual(47, len(list(Path(directory).glob("*/index.html"))))

    def test_generate_all_also_writes_the_prefectures_index_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            MODULE.generate_all(
                [
                    {
                        "id": "contract-1",
                        "status": "active",
                        "prefecture": "北海道",
                        "city": "札幌市",
                        "pokemons": ["ピカチュウ"],
                        "lat": 43.0,
                        "lng": 141.0,
                    }
                ],
                {"ピカチュウ": "pikachu"},
                {},
                output,
            )
            index_html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/prefectures/">', index_html)
            self.assertIn('href="/prefectures/hokkaido/"', index_html)


class RecordDateTest(unittest.TestCase):
    def test_timezone_suffixed_value_round_trips(self) -> None:
        result = MODULE._record_date({"first_seen": "2026-01-01T00:00:00Z"})
        self.assertIsNotNone(result.tzinfo)

    def test_naive_value_is_coerced_to_utc_instead_of_crashing_comparisons(self) -> None:
        """first_seen/added_at/last_updated が (誤って) タイムゾーン無しで
        入ってきても、tz-aware な cutoff との比較で
        TypeError: can't compare offset-naive and offset-aware datetimes
        にならないこと。"""
        result = MODULE._record_date({"first_seen": "2026-01-01T00:00:00"})
        self.assertIsNotNone(result.tzinfo)
        cutoff = datetime.now(MODULE.JST) - MODULE.timedelta(days=30)
        self.assertFalse(result >= cutoff)  # does not raise


class BuildIndexPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.records_by_pref = {name: [] for name in MODULE.PREFECTURE_ORDER}
        self.records_by_pref["三重県"] = [{"id": "1"}, {"id": "2"}]

    def test_links_to_every_prefecture_grouped_by_region(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref)
        for name, slug in MODULE.PREFECTURES:
            with self.subTest(prefecture=name):
                self.assertIn(f'href="/prefectures/{slug}/"', html)
        for region_name, _prefectures in MODULE.REGIONS:
            with self.subTest(region=region_name):
                self.assertIn(f">{region_name}<", html)

    def test_shows_the_installed_count_and_code_per_prefecture(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref)
        self.assertIn(
            '<article class="prefecture-card" data-track="prefectures_index_click" data-destination="mie">'
            '\n      <a class="prefecture-card-main" href="/prefectures/mie/">'
            '\n        <span class="prefecture-code">24</span>'
            '\n        <span class="prefecture-card-name">三重県</span>',
            html,
        )
        self.assertIn('<span class="count-badge">2枚</span>', html)

    def test_zero_count_prefecture_gets_the_muted_badge_and_dimmed_card(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref)
        self.assertIn('<article class="prefecture-card no-pokefuta"', html)
        self.assertIn('<span class="count-badge-zero">0枚</span>', html)

    def test_shows_a_new_badge_only_for_recently_added_records(self) -> None:
        records_by_pref = {name: [] for name in MODULE.PREFECTURE_ORDER}
        records_by_pref["三重県"] = [
            {"id": "1", "first_seen": datetime.now(MODULE.JST).isoformat()}
        ]
        html = MODULE.build_index_page(records_by_pref)
        self.assertIn('<span class="prefecture-new-badge">', html)

    def test_gallery_shows_real_thumbnails_when_photos_exist(self) -> None:
        records_by_pref = {name: [] for name in MODULE.PREFECTURE_ORDER}
        records_by_pref["三重県"] = [{"id": "1", "city": "津市"}]
        photos = {"1": {"created_at": "2026-01-01T00:00:00Z"}}
        with mock.patch.object(MODULE, "_photo_asset_url", return_value="/manhole/image/1_latest.jpeg"):
            html = MODULE.build_index_page(records_by_pref, photos)
        self.assertIn('<a class="prefecture-card-thumb" href="/manholes/1/"', html)
        self.assertIn('src="/manhole/image/1_latest.jpeg"', html)

    def test_gallery_falls_back_to_placeholder_without_photos(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref)
        self.assertIn('<span class="prefecture-card-thumb is-missing"></span>', html)

    def test_preinstall_record_never_shows_as_a_real_thumbnail(self) -> None:
        """installed:false（未設置）のレコードに写真データが残っていても、
        設置済みのポケふたと見分けがつかない形で出してはいけない。
        record id 461（福島県/小野）は installed:false のまま写真が
        ダウンロード済みという実データの不整合があり、これを再現する。"""
        records_by_pref = {name: [] for name in MODULE.PREFECTURE_ORDER}
        records_by_pref["三重県"] = [
            {"id": "1", "city": "津市", "installed": False}
        ]
        photos = {"1": {"created_at": "2026-01-01T00:00:00Z"}}
        with mock.patch.object(MODULE, "_photo_asset_url", return_value="/manhole/image/1_latest.jpeg"):
            html = MODULE.build_index_page(records_by_pref, photos)
        self.assertNotIn('href="/manholes/1/"', html)
        self.assertIn('<span class="prefecture-card-thumb is-missing"></span>', html)

    def test_preinstall_only_recent_record_does_not_trigger_the_new_badge(self) -> None:
        records_by_pref = {name: [] for name in MODULE.PREFECTURE_ORDER}
        records_by_pref["三重県"] = [
            {
                "id": "1",
                "installed": False,
                "first_seen": datetime.now(MODULE.JST).isoformat(),
            }
        ]
        html = MODULE.build_index_page(records_by_pref)
        self.assertNotIn('<span class="prefecture-new-badge">', html)

    def test_canonical_and_seo_meta(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref)
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/prefectures/">', html)
        self.assertIn('<meta name="robots" content="index,follow">', html)
        self.assertIn("<title>都道府県から探す｜全国のポケふた一覧</title>", html)

    def test_carries_the_same_prefecture_trivia_summary_shows(self) -> None:
        """/summary/ の都道府県トリビアと同じデータ・同じ文言を出すこと。
        dataset/prefecture_trivia.json の北海道エントリそのものを使う
        （coverage_percent 100% の vulpix-family = 「ロコン系」がラベルになる）。"""
        trivia = {
            "北海道": {
                "trivia": [
                    {
                        "id": "hokkaido-support-vulpix",
                        "text": "北海道の推しポケモンは、雪景色にもなじむアローラロコンとロコンです",
                    },
                    {
                        "id": "北海道-vulpix-family-100",
                        "text": "県内50枚すべてにロコン系が登場します",
                    },
                ],
                "pokemon_coverage": [
                    {"label": "ロコン系", "pokemon": ["ロコン", "アローラロコン"], "cover_count": 50, "coverage_percent": 100.0},
                    {"label": "アローラロコン", "pokemon": ["アローラロコン"], "cover_count": 37, "coverage_percent": 74.0},
                ],
            }
        }
        html = MODULE.build_index_page(self.records_by_pref, trivia=trivia)
        self.assertIn(
            '<span class="prefecture-card-trivia-label">都道府県トリビア</span>ロコン系',
            html,
        )
        self.assertIn(
            "<li>北海道の推しポケモンは、雪景色にもなじむアローラロコンとロコンです</li>",
            html,
        )
        self.assertIn("<li>県内50枚すべてにロコン系が登場します</li>", html)

    def test_omits_the_trivia_block_when_no_trivia_data_exists(self) -> None:
        html = MODULE.build_index_page(self.records_by_pref, trivia={})
        self.assertNotIn('<div class="prefecture-card-trivia">', html)

    def test_omits_the_pokemon_label_when_no_100_percent_coverage_entry_exists(self) -> None:
        trivia = {
            "三重県": {
                "trivia": [{"id": "x", "text": "テストトリビア文"}],
                "pokemon_coverage": [
                    {"label": "何か", "pokemon": ["何か"], "cover_count": 1, "coverage_percent": 50.0}
                ],
            }
        }
        html = MODULE.build_index_page(self.records_by_pref, trivia=trivia)
        self.assertIn("<li>テストトリビア文</li>", html)
        self.assertNotIn('<span class="prefecture-card-trivia-label">', html)


if __name__ == "__main__":
    unittest.main()
