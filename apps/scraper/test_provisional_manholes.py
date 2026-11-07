import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(pm.attach_photos([record], image_dir, fetch=lambda uuid: None), [])
            self.assertFalse((image_dir / "9001_latest.jpeg").exists())
            kept = pm.attach_photos([record], image_dir, fetch=lambda uuid: b"jpeg")
            self.assertEqual([r["id"] for r in kept], ["9001"])
            self.assertEqual((image_dir / "9001_latest.jpeg").read_bytes(), b"jpeg")

    def test_merge_photos_adds_a_row_per_provisional_id(self):
        [record] = pm.build_records({"9001": ledger_entry()}, [design_record()])
        merged = pm.merge_photos({"photos": {"1": {"manhole_id": 1}}, "count": 1}, [record])
        self.assertEqual(set(merged["photos"]), {"1", "9001"})
        self.assertIsNone(merged["photos"]["9001"]["display_name"])
        self.assertEqual(merged["count"], 2)


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
