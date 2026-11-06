import unittest
from datetime import datetime, timedelta, timezone

from apps.scraper.check_site_stats_freshness import validate


NOW = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)
STATS = {
    "generated_at": "2026-07-17T21:00:00+00:00",
    "manholes": 482,
    "manholes_with_photos": 250,
    "posts": 370,
    "public_posts": 338,
    "private_posts": 32,
}


class ValidateTest(unittest.TestCase):
    def test_accepts_fresh_matching_stats(self):
        self.assertEqual(
            validate(STATS, STATS, {}, now=NOW, max_age=timedelta(hours=30)), []
        )

    def test_rejects_stale_stats(self):
        site = {**STATS, "generated_at": "2026-07-15T00:00:00+00:00"}
        errors = validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30))
        self.assertTrue(any("stale" in error for error in errors))

    def test_rejects_different_counts(self):
        site = {**STATS, "posts": 280}
        errors = validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30))
        self.assertIn("posts differs: upstream=370, site=280", errors)

    def test_live_counts_may_differ_from_snapshot(self):
        site = {**STATS, "posts": 400, "public_posts": 360, "private_posts": 40, "counts_source": "live"}
        self.assertEqual(
            validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30)), []
        )

    def test_live_counts_still_need_the_latest_snapshot(self):
        site = {**STATS, "counts_source": "live", "generated_at": "2026-07-16T21:00:00+00:00"}
        errors = validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30))
        self.assertTrue(any("generated_at differs" in error for error in errors))

    def test_live_counts_must_not_be_missing(self):
        site = {**STATS, "counts_source": "live", "posts": None}
        errors = validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30))
        self.assertIn("posts is missing from live counts: site=None", errors)

    def test_snapshot_fallback_still_compares_counts(self):
        site = {**STATS, "counts_source": "snapshot", "posts": 280}
        errors = validate(STATS, site, {}, now=NOW, max_age=timedelta(hours=30))
        self.assertIn("posts differs: upstream=370, site=280", errors)

    def test_rejects_static_nextjs_cache(self):
        errors = validate(
            STATS,
            STATS,
            {"x-nextjs-cache": "HIT"},
            now=NOW,
            max_age=timedelta(hours=30),
        )
        self.assertTrue(any("statically cached" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
