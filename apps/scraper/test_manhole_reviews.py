"""manhole_reviews.py（口コミの除外とチップ）と、書き出し側の docs/manhole-reviews.json の形。

名前・本文はすべて作り物（実在の利用者のものを使わない）。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import manhole_reviews as mr  # noqa: E402
import export_latest_manhole_photos as export  # noqa: E402

UID_A = "11111111-1111-4111-8111-111111111111"
UID_B = "22222222-2222-4222-8222-222222222222"


def _review(comment, uid=UID_A, name="テスト太郎", shot_at="2026-10-01T00:00:00+00:00", photo_ids=None):
    return {
        "comment": comment,
        "display_name": name,
        "public_user_id": uid,
        "shot_at": shot_at,
        "created_at": shot_at,
        "photo_ids": photo_ids or [],
    }


class NoiseTests(unittest.TestCase):
    def test_number_only_is_noise(self):
        for text in ["48", "１２", "#5", "No.3", "12枚目", "7 。"]:
            with self.subTest(text=text):
                self.assertTrue(mr.is_noise(text))

    def test_real_text_is_not_noise(self):
        for text in ["駅前", "駐車場あり", "3番出口すぐ"]:
            with self.subTest(text=text):
                self.assertFalse(mr.is_noise(text))


class UsableReviewsTests(unittest.TestCase):
    def test_drops_numbers_and_templates_without_travel_info(self):
        raw = {
            str(i): [_review("ニャンコ"), _review("駅から歩ける"), _review(str(i))]
            for i in range(1, 4)
        }
        usable = mr.usable_reviews(raw)
        # 同じ人が3つの蓋に書いた「ニャンコ」は落ち、旅情報を含む「駅から歩ける」は残る
        self.assertEqual([r["comment"] for r in usable["1"]], ["駅から歩ける"])

    def test_template_needs_three_manholes(self):
        raw = {"1": [_review("ニャンコ")], "2": [_review("ニャンコ")]}
        self.assertEqual(len(mr.usable_reviews(raw)), 2)

    def test_newest_first_and_whitespace_normalized(self):
        raw = {"1": [
            _review("古い\nひとこと", shot_at="2025-01-01T00:00:00+00:00"),
            _review("新しい", shot_at="2026-11-01T00:00:00+00:00"),
        ]}
        self.assertEqual([r["comment"] for r in mr.usable_reviews(raw)["1"]], ["新しい", "古い ひとこと"])

    def test_display_folds_same_text(self):
        reviews = [_review("駅から歩ける", uid=UID_A), _review("駅から歩ける", uid=UID_B), _review("入口の横")]
        shown = mr.display_reviews(reviews)
        self.assertEqual([(r["comment"], r["others"]) for r in shown], [("駅から歩ける", 1), ("入口の横", 0)])


class TipTests(unittest.TestCase):
    def _keys(self, comments):
        return [chip["key"] for chip in mr.extract_tips([_review(c) for c in comments])]

    def test_suggestion_phrases_from_the_post_form_all_match(self):
        # 写真館の投稿フォームの候補（pokefuta src/lib/visit-tip.ts VISIT_TIP_SUGGESTIONS）
        self.assertEqual(
            self._keys(["駐車場あり", "駅から歩ける", "ひさしの下にある", "建物の入り口にある", "見つけにくい", "道の駅にある"]),
            ["parking_yes", "station", "michinoeki", "entrance", "eaves", "hard_to_find"],
        )

    def test_negation_is_not_a_hit(self):
        self.assertEqual(self._keys(["高松駅前にあるわけではない", "駅から歩けない"]), [])

    def test_michinoeki_is_not_a_station(self):
        self.assertEqual(self._keys(["道の駅の入り口にある"]), ["michinoeki", "entrance"])

    def test_parking_follows_the_newest_mention(self):
        older_yes = _review("駐車場あり", shot_at="2025-01-01T00:00:00+00:00")
        newer_no = _review("駐車場は無くなっていました", shot_at="2026-11-01T00:00:00+00:00")
        chips = mr.extract_tips([newer_no, older_yes])
        self.assertEqual(chips[0]["key"], "parking_yes")  # 「無くなって」は「なし」の言い回しに当たらない
        newer_no["comment"] = "駐車場はありません"
        chips = mr.extract_tips([newer_no, older_yes])
        self.assertEqual((chips[0]["key"], chips[0]["count"], chips[0]["latest"]), ("parking_no", 1, "2026-11"))

    def test_chip_carries_count_and_latest_month(self):
        chips = mr.extract_tips([
            _review("駅前にある", shot_at="2026-11-05T00:00:00+00:00"),
            _review("駅から徒歩5分", shot_at="2026-03-01T00:00:00+00:00"),
        ])
        self.assertEqual(chips, [{"key": "station", "label": "🚉 駅から歩ける", "count": 2, "latest": "2026-11"}])

    def test_missing_prompt_names_parking_only(self):
        self.assertEqual(mr.missing_tip_prompt([]), "駐車場の情報がまだありません")
        self.assertIsNone(mr.missing_tip_prompt(mr.extract_tips([_review("駐車場あり")])))


class LoadReviewsTests(unittest.TestCase):
    def test_missing_or_broken_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            self.assertEqual(mr.load_reviews(path), {})
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(mr.load_reviews(path), {})

    def test_ids_are_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps({"reviews": {"007": [_review("駅前")]}}), encoding="utf-8")
            self.assertEqual(list(mr.load_reviews(path)), ["7"])


class ExportShapeTests(unittest.TestCase):
    def test_reviews_query_reads_public_visits_with_comment(self):
        with mock.patch.object(export, "iter_supabase_rows", return_value=iter([])) as rows:
            list(export.iter_review_visits(100, 10))
        table, query = rows.call_args.args[0], rows.call_args.args[1]
        self.assertEqual(table, "visit")
        self.assertEqual(query["is_public"], "eq.true")
        self.assertEqual(query["comment"], "not.is.null")
        self.assertIn("photo(id,is_landscape)", query["select"])

    def test_payload_has_only_public_identity_and_skips_landscape_photos(self):
        visits = [
            {"id": 1, "manhole_id": 28, "user_id": "auth-a", "comment": " 駅前 ", "shot_at": "2026-01-01T00:00:00Z",
             "created_at": "2026-01-02T00:00:00Z",
             "photo": [{"id": "p-lid", "is_landscape": False}, {"id": "p-view", "is_landscape": True}]},
            {"id": 2, "manhole_id": 28, "user_id": "auth-b", "comment": "   ", "photo": []},
            {"id": 3, "manhole_id": 5, "user_id": "auth-b", "comment": "風景だけ", "shot_at": "2026-02-01T00:00:00Z",
             "photo": [{"id": "p-view2", "is_landscape": True}]},
        ]
        users = {"auth-a": {"display_name": "テスト太郎", "public_user_id": UID_A}}
        payload = export.build_reviews_payload(visits, users, "2026-11-28T00:00:00Z")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(list(payload["reviews"]), ["5", "28"])
        entry = payload["reviews"]["28"][0]
        self.assertEqual(entry, {
            "comment": "駅前",
            "display_name": "テスト太郎",
            "public_user_id": UID_A,
            "shot_at": "2026-01-01T00:00:00Z",
            "created_at": "2026-01-02T00:00:00Z",
            "photo_ids": ["p-lid"],
        })
        # 風景だけの訪問のひとことも残る（写真は付かない）
        self.assertEqual(payload["reviews"]["5"][0]["photo_ids"], [])
        # auth の user_id は出さない
        self.assertNotIn("auth-", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
