import importlib.util
import tempfile
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
        self.assertEqual(records[0]["status"], "pending")
        self.assertEqual(records[0]["nearby_refs"][0]["ref"], "gundam:5")
        self.assertNotIn("submitter_name", records[0])
        self.assertEqual(importer.select_public_records(records), [])
        self.assertEqual(importer.select_review_records(records), records)

    def test_official_pokefuta_candidate_is_not_published(self):
        submission = {
            **self.submission,
            "latitude": 40.5379444444444,
            "longitude": 141.558027777778,
        }
        references = {
            "pokefuta": [
                {
                    "id": "157",
                    "title": "青森県/八戸市",
                    "lat": 40.537937,
                    "lng": 141.558034,
                }
            ]
        }

        records = importer.build_public_records(
            [submission], {}, {}, references, "2026-08-08T00:00:00Z"
        )

        self.assertEqual(records[0]["nearby_refs"][0]["ref"], "pokefuta:157")
        self.assertLessEqual(records[0]["nearby_refs"][0]["distance_m"], 1)
        self.assertEqual(records[0]["review_status"], "needs_review")
        self.assertEqual(records[0]["status"], "pending")
        with tempfile.TemporaryDirectory() as directory:
            public_path = Path(directory) / "public.ndjson"
            review_path = Path(directory) / "review.ndjson"
            importer.write_ndjson(public_path, importer.select_public_records(records))
            importer.write_ndjson(review_path, importer.select_review_records(records))

            self.assertEqual(importer.load_ndjson(public_path), [])
            review_queue = importer.load_ndjson(review_path)
            self.assertEqual(len(review_queue), 1)
            self.assertEqual(review_queue[0]["source_id"], "submission-1")
            self.assertEqual(review_queue[0]["nearby_refs"][0]["ref"], "pokefuta:157")
            self.assertLessEqual(review_queue[0]["nearby_refs"][0]["distance_m"], 1)
            self.assertEqual(
                review_queue[0]["source_url"],
                "https://pokefuta.com/design-manholes/submission-1",
            )

    def test_source_url_links_to_individual_submission_page(self):
        records = importer.build_public_records(
            [self.submission],
            {},
            {},
            {},
            "2026-07-14T00:00:00Z",
        )

        self.assertEqual(
            records[0]["source_url"],
            "https://pokefuta.com/design-manholes/submission-1",
        )

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
        self.assertEqual(records[0]["status"], "active")
        self.assertEqual(importer.select_public_records(records), records)

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
        self.assertEqual(records[0]["status"], "active")
        self.assertEqual(records[0]["nearby_refs"][0]["ref"], "pokefuta:10")
        self.assertEqual(importer.select_public_records(records), records)

    def test_public_selection_is_fail_closed(self):
        base_record = {
            "source_id": "submission-1",
            "status": "active",
            "review_status": "pending",
        }
        publishable = [
            {**base_record, "source_id": "pending", "review_status": "pending"},
            {**base_record, "source_id": "matched", "review_status": "matched"},
            {
                **base_record,
                "source_id": "reviewed-distinct",
                "review_status": "reviewed_distinct",
            },
        ]
        quarantined = [
            {**base_record, "source_id": "hidden", "status": "hidden"},
            {**base_record, "source_id": "status-pending", "status": "pending"},
            {
                **base_record,
                "source_id": "unknown-review",
                "review_status": "future_state",
            },
            {
                **base_record,
                "source_id": "needs-review",
                "review_status": "needs_review",
            },
        ]

        records = publishable + quarantined

        self.assertEqual(importer.select_public_records(records), publishable)
        self.assertEqual(importer.select_review_records(records), quarantined)

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
        self.assertIn(
            "communityData.filter(d => d.status === 'active' && !d.canonical_ref).length",
            source,
        )

    def test_pages_deploy_copies_public_dataset(self):
        workflow = (ROOT / ".github/workflows/pages-deploy.yml").read_text(encoding="utf-8")

        self.assertIn("cp docs/design_manholes.ndjson dist/design_manholes.ndjson", workflow)

    def test_update_workflow_runs_create_pr_even_when_diff_disappears(self):
        workflow = (ROOT / ".github/workflows/update-design-manholes.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("if: steps.diff.outputs.changed == 'true'", workflow)
        self.assertIn("# Family B:", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("timeout-minutes:", workflow)
        self.assertIn("dataset/design_manhole_review_queue.ndjson", workflow)


if __name__ == "__main__":
    unittest.main()
