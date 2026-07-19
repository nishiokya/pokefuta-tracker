import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _manhole(**overrides) -> dict:
    base = {
        "id": "406",
        "prefecture": "愛知県",
        "city": "常滑",
        "address": "愛知県常滑市りんくう町２丁目",
        "lat": 34.876,
        "lng": 136.826,
        "pokemons": ["ピジョット"],
        "titles": [],
        "tags": [],
    }
    base.update(overrides)
    return base


def _character_spot(**overrides) -> dict:
    base = {
        "ref": "character:aichi-idolmaster-maekawa-miku",
        "kind": "character",
        "title": "前川みく×とこにゃん（ふたマス!!!!!!）",
        "work": "アイドルマスター シンデレラガールズ",
        "prefecture": "愛知県",
        "city": "常滑市",
        "lat": 34.880154,
        "lng": 136.828192,
        "studio_url": "",
        "photo_url": "",
    }
    base.update(overrides)
    return base


class LoadDesignSpotsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gundam = self.root / "gmanhole.ndjson"
        self.character = self.root / "character.ndjson"
        self.submissions = self.root / "design_manholes.ndjson"

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self) -> list[dict]:
        return pages.load_design_spots(self.gundam, self.character, self.submissions)

    def test_gundam_filters_and_defaults(self):
        _write_ndjson(self.gundam, [
            {"id": "1", "title": "豊富町観光情報センター", "prefecture": "北海道",
             "city": "豊富町", "lat": 45.10487, "lng": 141.772842, "status": "active"},
            {"id": "2", "title": "撤去済み", "lat": 45.0, "lng": 141.0, "status": "removed"},
            {"id": "3", "title": "座標なし", "status": "active"},
        ])
        _write_ndjson(self.character, [])
        _write_ndjson(self.submissions, [])
        spots = self._load()
        self.assertEqual([s["ref"] for s in spots], ["gundam:1"])
        self.assertEqual(spots[0]["work"], "ガンダムマンホール")

    def test_character_guards(self):
        _write_ndjson(self.gundam, [])
        _write_ndjson(self.character, [
            {"id": "miku", "title": "前川みく×とこにゃん", "work": "アイマス",
             "prefecture": "愛知県", "city": "常滑市",
             "lat": 34.880154, "lng": 136.828192,
             "coordinate_method": "municipal_google_map_link",
             "installation_status": "installed", "status": "active"},
            {"id": "not-installed", "title": "未設置", "lat": 35.0, "lng": 137.0,
             "coordinate_method": "official_google_map_link",
             "installation_status": "planned", "status": "active"},
            {"id": "bad-coords", "title": "座標未検証", "lat": 35.0, "lng": 137.0,
             "coordinate_method": "manual_guess",
             "installation_status": "installed", "status": "active"},
        ])
        _write_ndjson(self.submissions, [])
        spots = self._load()
        self.assertEqual([s["ref"] for s in spots], ["character:miku"])

    def test_submission_enriches_master_spot(self):
        _write_ndjson(self.gundam, [
            {"id": "1", "title": "豊富町観光情報センター", "lat": 45.10487,
             "lng": 141.772842, "status": "active"},
        ])
        _write_ndjson(self.character, [])
        _write_ndjson(self.submissions, [
            {"id": "pokefuta-design:abc", "title": "豊富町観光情報センター",
             "lat": 45.1049, "lng": 141.7729, "status": "active",
             "canonical_ref": None,
             "nearby_refs": [{"ref": "gundam:1", "distance_m": 30}],
             "source_url": "https://pokefuta.com/design-manholes/abc",
             "photo_url": "https://pokefuta.com/api/design-manholes/abc/photo?size=small"},
        ])
        spots = self._load()
        # 合流するので独立スポットにはならない
        self.assertEqual(len(spots), 1)
        self.assertEqual(spots[0]["studio_url"], "https://pokefuta.com/design-manholes/abc")
        self.assertTrue(spots[0]["photo_url"])

    def test_submission_near_pokefuta_is_skipped(self):
        _write_ndjson(self.gundam, [])
        _write_ndjson(self.character, [])
        _write_ndjson(self.submissions, [
            {"id": "pokefuta-design:dup", "title": "愛知県/豊橋市",
             "lat": 34.7, "lng": 137.4, "status": "active",
             "canonical_ref": None,
             "nearby_refs": [{"ref": "pokefuta:272", "distance_m": 46}],
             "source_url": "https://pokefuta.com/design-manholes/dup",
             "photo_url": ""},
        ])
        self.assertEqual(self._load(), [])

    def test_standalone_submission_becomes_spot(self):
        _write_ndjson(self.gundam, [])
        _write_ndjson(self.character, [])
        _write_ndjson(self.submissions, [
            {"id": "pokefuta-design:shachi", "title": "鯱",
             "lat": 35.19178, "lng": 136.90333, "status": "active",
             "canonical_ref": None, "nearby_refs": [],
             "source_url": "https://pokefuta.com/design-manholes/shachi",
             "photo_url": "https://pokefuta.com/api/design-manholes/shachi/photo?size=small"},
        ])
        spots = self._load()
        self.assertEqual(len(spots), 1)
        self.assertEqual(spots[0]["kind"], "studio")
        self.assertEqual(spots[0]["studio_url"], "https://pokefuta.com/design-manholes/shachi")

    def test_missing_files_return_empty(self):
        self.assertEqual(self._load(), [])

    def test_rows_with_empty_id_or_bad_coords_are_skipped(self):
        _write_ndjson(self.gundam, [
            {"id": "", "title": "ID空", "lat": 45.0, "lng": 141.0, "status": "active"},
            {"id": "9", "title": "座標が文字列", "lat": "北緯45度", "lng": 141.0,
             "status": "active"},
        ])
        _write_ndjson(self.character, [
            {"id": "  ", "title": "ID空白", "lat": 35.0, "lng": 137.0,
             "coordinate_method": "official_google_map_link",
             "installation_status": "installed", "status": "active"},
        ])
        _write_ndjson(self.submissions, [
            {"id": "", "title": "ID空投稿", "lat": 35.0, "lng": 137.0,
             "status": "active", "canonical_ref": None, "nearby_refs": [],
             "source_url": "https://pokefuta.com/design-manholes/x", "photo_url": ""},
        ])
        self.assertEqual(self._load(), [])

    def test_non_pokefuta_urls_are_dropped(self):
        _write_ndjson(self.gundam, [])
        _write_ndjson(self.character, [])
        _write_ndjson(self.submissions, [
            {"id": "pokefuta-design:evil", "title": "不正URL",
             "lat": 35.0, "lng": 137.0, "status": "active",
             "canonical_ref": None, "nearby_refs": [],
             "source_url": "javascript:alert(1)",
             "photo_url": "http://example.com/a.jpg"},
        ])
        spots = self._load()
        self.assertEqual(len(spots), 1)
        self.assertEqual(spots[0]["studio_url"], "")
        self.assertEqual(spots[0]["photo_url"], "")


class DesignSectionRenderTest(unittest.TestCase):
    def _html(self, manhole=None, nearby_design=None, **kwargs) -> str:
        return pages.generate_html(
            manhole or _manhole(),
            None,  # photo
            {},    # pokemon_meta
            kwargs.pop("nearby", []),
            [],    # same_pref
            9,     # pref_total
            [],    # same_pokemon
            {},    # id_to_image_url
            nearby_design=nearby_design,
            **kwargs,
        )

    def test_no_design_spots_no_section(self):
        html = self._html(nearby_design=[])
        self.assertNotIn("design-manholes", html)
        self.assertNotIn("近くのデザインマンホール", html)

    def test_section_with_studio_link_and_fallback(self):
        spots = [
            (_character_spot(), 0.765),
            (_character_spot(
                ref="gundam:1",
                kind="gundam",
                title="豊富町観光情報センター",
                work="ガンダムマンホール",
                studio_url="https://pokefuta.com/design-manholes/abc",
                photo_url="https://pokefuta.com/api/design-manholes/abc/photo?size=small",
            ), 12.3),
        ]
        html = self._html(nearby_design=spots)
        self.assertIn("id='design-manholes'", html)
        self.assertIn("近くのデザインマンホール", html)
        # 写真館投稿があるものは写真館詳細へ、写真つき
        self.assertIn("https://pokefuta.com/design-manholes/abc", html)
        self.assertIn("写真館で見る →", html)
        self.assertIn("/api/design-manholes/abc/photo", html)
        # 投稿がないものは一覧へフォールバック＋募集表示
        self.assertIn(f"href='{pages.DESIGN_STUDIO_LIST_URL}'", html)
        self.assertIn("写真募集中", html)
        # 1km未満はm表示、以上はkm表示
        self.assertIn("765 m", html)
        self.assertIn("12.3 km", html)
        # GA4イベント
        self.assertIn("click_nearby_design_manhole", html)

    def test_design_title_badge_becomes_anchor_only_with_spots(self):
        titles = [{
            "key": "near_character_manhole", "emoji": "🎨",
            "label": "キャラクターマンホールまで約1km以内",
            "hashtag": "#キャラクターマンホール近接",
        }]
        with_spots = self._html(
            manhole=_manhole(titles=titles),
            nearby_design=[(_character_spot(), 0.765)],
        )
        self.assertIn("class='hero-badge hero-badge-title hero-badge-anchor'", with_spots)
        self.assertIn("href='#design-manholes'", with_spots)

        without_spots = self._html(manhole=_manhole(titles=titles), nearby_design=[])
        self.assertNotIn("href='#design-manholes'", without_spots)

    def test_unsafe_studio_url_falls_back_to_list(self):
        spot = _character_spot(
            studio_url="javascript:alert(1)",
            photo_url="javascript:alert(2)",
        )
        html = self._html(nearby_design=[(spot, 0.5)])
        self.assertNotIn("javascript:", html)
        self.assertIn(f"href='{pages.DESIGN_STUDIO_LIST_URL}'", html)
        self.assertIn("写真募集中", html)

    def test_attribute_values_escape_quotes(self):
        spot = _character_spot(
            studio_url="https://pokefuta.com/design-manholes/a'b\"c",
        )
        html = self._html(nearby_design=[(spot, 0.5)])
        self.assertIn("a&#39;b&quot;c", html)
        self.assertNotIn("design-manholes/a'b", html)

    def test_section_order_travel_info_above_pokemon_seo(self):
        nearby = [(_manhole(id="999", city="西尾市"), 20.6)]
        html = self._html(
            nearby=nearby,
            nearby_design=[(_character_spot(), 0.765)],
        )
        i_location = html.index("設置場所")
        i_design = html.index("近くのデザインマンホール")
        i_nearby = html.index("次に寄れるポケふた")
        i_pokemon = html.index("登場ポケモン")
        self.assertLess(i_location, i_design)
        self.assertLess(i_design, i_nearby)
        self.assertLess(i_nearby, i_pokemon)


class NearbyDesignComputationTest(unittest.TestCase):
    def test_generate_all_pages_attaches_nearby_spots(self):
        spots = [
            _character_spot(),  # 常滑ポケふたから約765m
            _character_spot(ref="gundam:99", title="遠方ガンダム", lat=43.0, lng=141.3),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dist"
            img = Path(tmp) / "img"
            img.mkdir()
            pages.generate_all_pages(
                [_manhole()], {}, {}, out, img, design_spots=spots,
            )
            html = (out / "manholes" / "406" / "index.html").read_text(encoding="utf-8")
        self.assertIn("前川みく×とこにゃん", html)
        self.assertNotIn("遠方ガンダム", html)


if __name__ == "__main__":
    unittest.main()
