import http.client
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from apps.scraper import provisional_manholes as pm
from apps.scraper.page_html import upload_url
from apps.scraper.prefecture_completion import is_countable, verify_known_empty


UUID = "202ff606-b1b7-4b9b-bba2-de3092a16a6d"
OTHER_UUID = "a0326912-b668-41ee-9a63-c82fedb54136"


def ledger_entry(uuid=UUID, **overrides):
    entry = {
        "design_manhole_id": uuid,
        "prefecture": "群馬県",
        "city": "渋川",
        "building": "伊香保ロープウェイ不如帰駅前",
        "pokemons": ["サンダー"],
        "source_url": "https://www.pref.gunma.jp/site/houdou/779585.html",
        "official_id": None,
    }
    entry.update(overrides)
    return entry


def design_record(uuid=UUID, **overrides):
    record = {
        "source": "pokefuta.com",
        "source_id": uuid,
        "status": "active",
        "lat": 36.497125,
        "lng": 138.919297,
        "address": "群馬県渋川市伊香保町伊香保",
        "created_at": "2026-11-06T14:43:23+00:00",
        "canonical_ref": "pokefuta:9001",
    }
    record.update(overrides)
    return record


OVERRIDES = {UUID: {"canonical_ref": "pokefuta:9001"}}


def _jpeg_with_gps() -> bytes:
    exif = Image.Exif()
    exif[0x0110] = "test-camera"
    exif.get_ifd(0x8825)[2] = (36.0, 29.0, 49.65)
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "yellow").save(out, "JPEG", exif=exif)
    with Image.open(io.BytesIO(out.getvalue())) as check:
        assert len(check.getexif()) > 0
    return out.getvalue()


class ValidateLedgerTests(unittest.TestCase):
    def test_accepts_a_valid_ledger(self):
        pm.validate_ledger({"9001": ledger_entry()}, {"1", "490"}, OVERRIDES)

    def test_rejects_ids_below_the_provisional_range(self):
        with self.assertRaisesRegex(pm.LedgerError, "9001 以上"):
            pm.validate_ledger({"491": ledger_entry()}, {"1"}, {UUID: {"canonical_ref": "pokefuta:491"}})

    def test_rejects_a_collision_with_an_official_id(self):
        with self.assertRaisesRegex(pm.LedgerError, "公式の番号とぶつかっている"):
            pm.validate_ledger({"9001": ledger_entry()}, {"9001"}, OVERRIDES)

    def test_rejects_the_same_post_under_two_ids(self):
        ledger = {"9001": ledger_entry(), "9002": ledger_entry()}
        with self.assertRaisesRegex(pm.LedgerError, "9001 でも使っている"):
            pm.validate_ledger(ledger, set(), OVERRIDES)

    def test_requires_the_override_that_hides_the_post_from_design_manholes(self):
        with self.assertRaisesRegex(pm.LedgerError, "canonical_ref"):
            pm.validate_ledger({"9001": ledger_entry()}, set(), {})

    def test_requires_pokemons(self):
        with self.assertRaisesRegex(pm.LedgerError, "pokemons"):
            pm.validate_ledger({"9001": ledger_entry(pokemons=[])}, set(), OVERRIDES)

    def test_official_id_must_exist(self):
        with self.assertRaisesRegex(pm.LedgerError, "official_id"):
            pm.validate_ledger({"9001": ledger_entry(official_id=491)}, {"1"}, OVERRIDES)


class BuildRecordsTests(unittest.TestCase):
    def test_takes_location_from_the_post(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        self.assertEqual(record["id"], "9001")
        self.assertEqual((record["lat"], record["lng"]), (36.497125, 138.919297))
        self.assertEqual(record["address"], "群馬県渋川市伊香保町伊香保")
        self.assertEqual(record["title"], "群馬県/渋川市")
        self.assertEqual(record["place_label"], "渋川市 伊香保ロープウェイ不如帰駅前")
        self.assertTrue(record["provisional"])
        self.assertEqual(record["detail_url"], "")
        self.assertEqual(record["provisional_post_url"], f"https://pokefuta.com/design-manholes/{UUID}")
        self.assertEqual(record["added_at"], "2026-11-06T14:43:23+00:00")

    def test_skips_posts_that_are_missing_or_not_active(self):
        ledger = {"9001": ledger_entry(), "9002": ledger_entry(uuid=OTHER_UUID)}
        records = pm.build_records(ledger, [design_record(uuid=OTHER_UUID, status="hidden")])
        self.assertEqual(records, [])

    def test_skips_ids_that_moved_to_an_official_id(self):
        self.assertEqual(pm.build_records({"9001": ledger_entry(official_id=491)}, [design_record()]), [])


class PhotoTests(unittest.TestCase):
    def test_attach_photos_drops_unpublished_posts(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            (image_dir / "9001_latest.jpeg").write_bytes(b"old")

            def gone(uuid):
                raise pm.PhotoGone(uuid)

            self.assertEqual(pm.attach_photos([record], image_dir, fetch=gone), ([], []))
            self.assertFalse((image_dir / "9001_latest.jpeg").exists())
            kept, with_photo = pm.attach_photos([record], image_dir, fetch=lambda uuid: _jpeg_with_gps())
            self.assertEqual([r["id"] for r in kept], ["9001"])
            self.assertEqual([r["id"] for r in with_photo], ["9001"])
            with Image.open(image_dir / "9001_latest.jpeg") as saved:
                self.assertEqual(saved.format, "JPEG")
                self.assertEqual(len(saved.getexif()), 0)

    def test_attach_photos_keeps_the_lid_when_the_photo_is_temporarily_unavailable(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            for fetch in (lambda uuid: None, lambda uuid: b"not a jpeg"):
                (image_dir / "9001_latest.jpeg").write_bytes(b"stale")
                kept, with_photo = pm.attach_photos([record], image_dir, fetch=fetch)
                self.assertEqual([r["id"] for r in kept], ["9001"])
                self.assertEqual(with_photo, [])
                self.assertFalse((image_dir / "9001_latest.jpeg").exists())

    def test_fetch_photo_raises_photo_gone_for_unpublished_posts(self):
        def not_found(request, timeout):
            raise pm.urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        with mock.patch.object(pm.urllib.request, "urlopen", not_found):
            with self.assertRaises(pm.PhotoGone):
                pm.fetch_photo(UUID)

    def test_fetch_photo_returns_none_when_the_body_is_cut(self):
        def broken(request, timeout):
            raise http.client.IncompleteRead(b"partial")
        with mock.patch.object(pm.urllib.request, "urlopen", broken):
            self.assertIsNone(pm.fetch_photo(UUID))

    def test_merge_photos_adds_a_row_per_provisional_id(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        merged = pm.merge_photos({"photos": {"1": {"manhole_id": 1}}, "count": 1}, [record])
        self.assertEqual(set(merged["photos"]), {"1", "9001"})
        self.assertIsNone(merged["photos"]["9001"]["display_name"])
        self.assertEqual(merged["count"], 2)


class RedirectTests(unittest.TestCase):
    def test_moved_ids_get_forwarding_pages_in_every_language(self):
        ledger = {"9001": ledger_entry(official_id=491), "9002": ledger_entry(uuid=OTHER_UUID)}
        with tempfile.TemporaryDirectory() as tmp:
            written = pm.write_redirects(ledger, Path(tmp))
            self.assertEqual(
                sorted(str(p.relative_to(tmp)) for p in written),
                ["en/manholes/9001/index.html", "manholes/9001/index.html", "zh-TW/manholes/9001/index.html"],
            )
            html = (Path(tmp) / "en/manholes/9001/index.html").read_text(encoding="utf-8")
            self.assertIn('url=https://data.pokefuta.com/en/manholes/491/', html)
            self.assertIn('rel="canonical" href="https://data.pokefuta.com/en/manholes/491/"', html)
            self.assertIn("noindex", html)


class MainTests(unittest.TestCase):
    def test_writes_official_lines_unchanged_then_provisional_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official_line = json.dumps({"id": "1", "prefecture": "鹿児島県"}, ensure_ascii=False)
            (root / "official.ndjson").write_text(official_line + "\n", encoding="utf-8")
            (root / "design.ndjson").write_text(json.dumps(design_record()) + "\n", encoding="utf-8")
            (root / "ledger.json").write_text(json.dumps({"manholes": {"9001": ledger_entry()}}), encoding="utf-8")
            (root / "overrides.json").write_text(json.dumps(OVERRIDES), encoding="utf-8")
            pm.main([
                "--ledger", str(root / "ledger.json"),
                "--official", str(root / "official.ndjson"),
                "--design", str(root / "design.ndjson"),
                "--overrides", str(root / "overrides.json"),
                "--out", str(root / "out.ndjson"),
            ])
            lines = (root / "out.ndjson").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], official_line)
            self.assertEqual(json.loads(lines[1])["id"], "9001")


class ConsumerTests(unittest.TestCase):
    def test_upload_link_goes_to_the_new_pokefuta_submission(self):
        self.assertTrue(upload_url("9001", "gunma", provisional=True).startswith(pm.PROVISIONAL_UPLOAD_URL + "&"))
        # 番号では決めない（テストのデータには 9001 番台の普通の蓋もある）
        self.assertTrue(upload_url("9001", "gunma").startswith("https://pokefuta.com/upload?manhole_id=9001&"))

    def test_completion_ignores_provisional_lids(self):
        record = {"id": "9001", "provisional": True}
        self.assertFalse(is_countable(record))
        # 未設置県に仮の1枚だけがあっても、公式の取りこぼし判定は通る
        verify_known_empty({"群馬県": [record]}, ["群馬県"], known_empty={"群馬県"})

    def test_national_totals_count_official_lids_only(self):
        from apps.scraper import generate_prefecture_pages as ja
        from apps.scraper import generate_prefecture_pages_i18n as i18n

        official = {"id": "1", "prefecture": "高知県", "city": "高知", "lat": 33.5, "lng": 133.5,
                    "pokemons": ["ヌオー"], "address": "高知県高知市"}
        provisional = {**official, "id": "9002", "provisional": True}
        gunma = {**official, "id": "9001", "prefecture": "群馬県", "provisional": True}
        from apps.scraper.prefectures import PREFECTURE_ORDER

        records_by_pref = {name: [] for name in PREFECTURE_ORDER}
        records_by_pref.update({"高知県": [official, provisional], "群馬県": [gunma]})
        html = ja.build_index_page(records_by_pref)
        self.assertIn("計1枚", html)
        self.assertNotIn("計3枚", html)
        en = i18n.build_index_page(i18n.Page("en", {}), records_by_pref)
        self.assertIn("1 Poké Lids are installed in 1 of Japan", en)

    def test_shared_map_falls_back_to_the_photo_studio_upload(self):
        from apps.scraper import generate_prefecture_pages as ja

        # 市区町村・trip・特集の地図は upload_url を渡さない
        script = ja._map_script([{"id": "1", "lat": 33.5, "lng": 133.5}], "from=data")
        self.assertIn("point.upload_url || ('https://pokefuta.com/upload?manhole_id='", script)

    def test_repository_ledger_is_valid(self):
        official_ids = {
            str(json.loads(line)["id"])
            for line in pm.DEFAULT_OFFICIAL.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        overrides = json.loads(pm.DEFAULT_OVERRIDES.read_text(encoding="utf-8"))
        pm.validate_ledger(pm.load_ledger(pm.DEFAULT_LEDGER), official_ids, overrides)


if __name__ == "__main__":
    unittest.main()


class WantedTests(unittest.TestCase):
    WANTED = {
        "群馬県": {
            "source_url": "https://www.pref.gunma.jp/site/houdou/779585.html",
            "feature": "gunma-2026-autumn",
            "places": [
                {"city": "渋川市", "place": "伊香保ロープウェイ不如帰駅前"},
                {"city": "沼田市", "place": "吹割の滝遊歩道入口"},
            ],
        },
        "高知県": {"places": [{"city": "芸西村", "place": "琴ヶ浜かっぱ市"}]},
    }

    def test_places_with_a_lid_in_the_zukan_drop_out(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        geisei = {**record, "id": "9002", "prefecture": "高知県", "city": "芸西", "address": "高知県芸西村和食"}
        out = pm.wanted_places(self.WANTED, [record, geisei])
        self.assertEqual([p["city"] for p in out["群馬県"]["places"]], ["沼田市"])
        self.assertNotIn("高知県", out)

    def test_prefecture_page_card_asks_for_a_design_manhole_post(self):
        from apps.scraper import generate_prefecture_pages as ja

        self.assertEqual("", ja._wanted_html("群馬県", "gunma", None))
        html = ja._wanted_html("群馬県", "gunma", pm.wanted_places(self.WANTED, [])["群馬県"])
        self.assertIn('id="wanted"', html)
        self.assertIn("緯度経度を調べています", html)
        self.assertIn("沼田市", html)
        self.assertIn("design-manholes/new?kind=pokefuta&amp;from=data&amp;pref=gunma", html)
        self.assertIn("/features/gunma-2026-autumn/", html)

    def test_top_page_lists_provisional_lids_as_new_and_links_to_the_wanted_cards(self):
        from datetime import date

        from apps.scraper import generate_top_page as top

        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        data = top.TopData(
            records=[], photos=[], events=[], stats={}, today=date(2026, 11, 7),
            provisional=[record], wanted=pm.wanted_places(self.WANTED, [record]),
        )
        html = top.render_newrelease(data)
        self.assertIn('href="manholes/9001/"', html)
        self.assertIn("公式サイト未掲載", html)
        self.assertIn('href="prefectures/gunma/#wanted"', html)
        self.assertIn("群馬県 1か所", html)
        self.assertIn("高知県 1か所", html)
        # 全国の枚数には入れない
        self.assertEqual(data.total, 0)
