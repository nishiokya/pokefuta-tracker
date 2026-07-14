import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("import_design_manholes.py")
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("import_design_manholes", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {MODULE_PATH}")
importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(importer)


class ImportDesignManholesTests(unittest.TestCase):
    def setUp(self):
        self.submission = importer.normalize_submission(
            {
                "id": "submission-1",
                "title": "  テスト蓋  ",
                "description": "説明",
                "submitter_name": "投稿者",
                "latitude": 35.0,
                "longitude": 135.0,
                "width": 100,
                "height": 200,
                "created_at": "2026-07-10T00:00:00Z",
                "photo_url": "/api/design-manholes/submission-1/photo?size=small",
            }
        )

    def test_normalize_submission_makes_photo_url_absolute(self):
        self.assertEqual(self.submission["title"], "テスト蓋")
        self.assertEqual(
            self.submission["photo_url"],
            "https://pokefuta.com/api/design-manholes/submission-1/photo?size=small",
        )

    def test_geocode_cache_only_resolves_new_coordinates(self):
        calls = []

        def resolver(latitude, longitude):
            calls.append((latitude, longitude))
            return {"prefecture": "大阪府", "city": "大阪市", "address": "大阪府大阪市"}

        cache = importer.geocode_submissions(
            [self.submission], {}, resolver, sleep_seconds=0
        )
        cache = importer.geocode_submissions(
            [self.submission], cache, resolver, sleep_seconds=0
        )

        self.assertEqual(calls, [(35.0, 135.0)])
        self.assertEqual(len(cache), 1)

    def test_incomplete_geocode_cache_is_retried(self):
        calls = []

        def resolver(latitude, longitude):
            calls.append((latitude, longitude))
            return {"prefecture": "北海道", "city": "当別町", "address": "北海道当別町"}

        cache = importer.geocode_submissions(
            [self.submission],
            {"35.0000000,135.0000000": {"prefecture": "", "city": "", "address": "町名"}},
            resolver,
            sleep_seconds=0,
        )

        self.assertEqual(calls, [(35.0, 135.0)])
        self.assertEqual(cache["35.0000000,135.0000000"]["prefecture"], "北海道")

    def test_nearby_candidate_does_not_auto_merge(self):
        references = {
            "gundam": [
                {"id": "5", "title": "既存蓋", "lat": 35.0001, "lng": 135.0001}
            ]
        }
        records = importer.build_public_records(
            [self.submission],
            {
                "35.0000000,135.0000000": {
                    "prefecture": "大阪府",
                    "city": "大阪市",
                    "address": "大阪府大阪市",
                }
            },
            {},
            references,
            "2026-07-14T00:00:00Z",
        )

        self.assertIsNone(records[0]["canonical_ref"])
        self.assertEqual(records[0]["review_status"], "needs_review")
        self.assertEqual(records[0]["nearby_refs"][0]["ref"], "gundam:5")
        self.assertNotIn("submitter_name", records[0])

    def test_manual_override_links_canonical_record(self):
        records = importer.build_public_records(
            [self.submission],
            {},
            {"submission-1": {"canonical_ref": "gundam:5"}},
            {},
            "2026-07-14T00:00:00Z",
        )

        self.assertEqual(records[0]["canonical_ref"], "gundam:5")
        self.assertEqual(records[0]["review_status"], "matched")

    def test_manual_review_status_can_clear_nearby_candidate(self):
        references = {
            "pokefuta": [
                {"id": "10", "title": "近くの別の蓋", "lat": 35.0001, "lng": 135.0001}
            ]
        }
        records = importer.build_public_records(
            [self.submission],
            {},
            {"submission-1": {"review_status": "reviewed_distinct"}},
            references,
            "2026-07-14T00:00:00Z",
        )

        self.assertEqual(records[0]["review_status"], "reviewed_distinct")
        self.assertEqual(records[0]["nearby_refs"][0]["ref"], "pokefuta:10")

    def test_unchanged_record_preserves_last_updated(self):
        initial = importer.build_public_records(
            [self.submission], {}, {}, {}, "2026-07-14T00:00:00Z"
        )
        repeated = importer.build_public_records(
            [self.submission],
            {},
            {},
            {},
            "2026-07-15T00:00:00Z",
            previous_records=initial,
        )

        self.assertEqual(repeated[0]["last_updated"], "2026-07-14T00:00:00Z")

    def test_snapshot_at_capacity_requires_pagination(self):
        with self.assertRaisesRegex(ValueError, "pagination is required"):
            importer.validate_snapshot_size(
                [self.submission], [], limit=1, allow_shrink=False, allow_truncated=False
            )

    def test_public_map_loads_community_dataset_and_filter(self):
        source = (ROOT / "apps/web/gmanhole_map.html").read_text(encoding="utf-8")

        self.assertIn("fetch('./design_manholes.ndjson')", source)
        self.assertIn("id=\"chk-community\"", source)
        self.assertIn("buildCommunityPopup(d)", source)
        self.assertIn("communityByCanonicalRef", source)

    def test_pages_deploy_copies_public_dataset(self):
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")

        self.assertIn("cp docs/design_manholes.ndjson dist/design_manholes.ndjson", workflow)


if __name__ == "__main__":
    unittest.main()
