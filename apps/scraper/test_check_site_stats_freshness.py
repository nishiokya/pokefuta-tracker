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
