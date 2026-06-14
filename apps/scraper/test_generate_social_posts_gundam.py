import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_social_posts.py")
SPEC = importlib.util.spec_from_file_location("generate_social_posts", MODULE_PATH)
social = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(social)


class GundamCrossoverCandidateTests(unittest.TestCase):
    def test_teshio_story_is_available_to_social_post_generation(self):
        spots = social.load_gundam_spots(social.GUNDAM_SPOTS_JSON)
        candidates = social.gen_gundam_crossover_candidates(spots)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        values = candidate["raw_data"]["values"]
        self.assertEqual(candidate["title"], "ロコンとドムを同時回収できる町")
        self.assertEqual(candidate["type"], "gundam_crossover")
        self.assertIn("入口を挟んで設置", values["summary"])
        self.assertEqual(
            values["proximity_label"],
            "同じ道の駅・入口の反対側・徒歩10秒",
        )
        self.assertIn("見落とし注意", values["onsite_tip"])

    def test_generated_candidates_include_teshio_story(self):
        candidates_path = social.ROOT / "docs" / "social-post-candidates.json"
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidate = next(
            item for item in candidates
            if item.get("id") == "gundam-crossover-teshio-roadside-pair"
        )
        self.assertEqual(
            candidate["raw_data"]["values"]["summary"],
            social.load_gundam_spots(social.GUNDAM_SPOTS_JSON)[0]["story"],
        )


if __name__ == "__main__":
    unittest.main()
