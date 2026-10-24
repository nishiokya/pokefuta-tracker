"""Unit tests for export_latest_manhole_photos (network-free).

Run: python3 tools/test_export_latest_manhole_photos.py
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("export_latest_manhole_photos.py")
SPEC = importlib.util.spec_from_file_location("export_latest_manhole_photos", MODULE_PATH)
export = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(export)


def _photo(
    photo_id: str,
    shot_at: str | None = None,
    created_at: str = "2026-01-01T00:00:00Z",
    is_public: bool = True,
    user_id: str = "user-1",
) -> dict:
    return {
        "id": photo_id,
        "manhole_id": 1,
        "storage_key": f"photos/{photo_id}.jpeg",
        "content_type": "image/jpeg",
        "created_at": created_at,
        "visit": {
            "shot_at": shot_at,
            "is_public": is_public,
            "user_id": user_id,
            "comment": None,
        },
    }


def _scored(photo_id: str, score, shot_at=None, eligible=True, scene=None, lid_fits=None, crop=None, rep=None) -> dict:
    tags = {"model": "scene_attrs/1"}
    if scene:
        tags["scene"] = scene
    if lid_fits is not None:
        tags["lid_fits"] = lid_fits
    if crop is not None:
        tags["crop"] = crop
    if rep is not None:
        tags["rep_score"] = rep
    return {**_photo(photo_id, shot_at=shot_at), "quality_score": score,
            "quality_eligible": eligible if score is not None else None, "ai_tags": tags}


class PhotoRankTest(unittest.TestCase):
    def test_score_order_beats_newer_photos(self):
        photos = [
            _scored("new-low", 0.5, shot_at="2026-09-01T00:00:00Z"),
            _scored("old-high", 0.9, shot_at="2026-01-01T00:00:00Z"),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["old-high", "new-low"])

    def test_centered_lid_that_fits_comes_first_among_scored(self):
        photos = [
            _scored("wide", 0.84, scene="wide_context", lid_fits=True),
            _scored("closeup", 0.83, scene="centered_clean", lid_fits=False),
            _scored("centered", 0.82, scene="centered_clean", lid_fits=True),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["centered", "wide", "closeup"])

    def test_rep_score_orders_when_every_scored_candidate_has_one(self):
        photos = [
            _scored("best-quality", 0.95, scene="centered_clean", lid_fits=True, rep=3),
            _scored("best-rep", 0.7, scene="wide_context", lid_fits=True, rep=9),
            _scored("high-rep-not-fitting", 0.9, scene="centered_clean", lid_fits=False, rep=20),
            _scored("unscored", None, shot_at="2026-09-01T00:00:00Z"),
            _scored("ineligible", 0.99, eligible=False, lid_fits=True, rep=50),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)],
                         ["best-rep", "best-quality", "high-rep-not-fitting", "unscored", "ineligible"])

    def test_previous_order_while_any_scored_candidate_lacks_rep_score(self):
        photos = [
            _scored("best-rep", 0.7, scene="wide_context", lid_fits=True, rep=9),
            _scored("centered", 0.6, scene="centered_clean", lid_fits=True),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["centered", "best-rep"])

    def test_rep_score_tie_falls_back_to_quality_like_the_photo_site(self):
        photos = [
            _scored("new-low", 0.2, shot_at="2026-09-01T00:00:00Z", lid_fits=True, rep=5),
            _scored("old-high", 0.95, shot_at="2026-01-01T00:00:00Z", lid_fits=True, rep=5),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["old-high", "new-low"])

    def test_nan_quality_counts_as_unscored_and_does_not_block_rep_score(self):
        photos = [
            _scored("low-rep", 0.9, lid_fits=True, rep=1),
            _scored("high-rep", 0.5, lid_fits=True, rep=8),
            _scored("nan", float("nan")),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["high-rep", "low-rep", "nan"])

    def test_tiers_scored_then_unscored_then_ineligible(self):
        photos = [
            _scored("ineligible", 0.95, eligible=False, scene="centered_clean", lid_fits=True),
            _scored("unscored", None, shot_at="2026-09-01T00:00:00Z"),
            _scored("scored", 0.3),
        ]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["scored", "unscored", "ineligible"])

    def test_unscored_photos_fall_back_to_newest_first(self):
        photos = [_photo("old", shot_at="2026-01-01T00:00:00Z"), _photo("new", shot_at="2026-03-01T00:00:00Z")]
        self.assertEqual([p["id"] for p in export.select_gallery_photos(photos, 5)], ["new", "old"])

    def test_lid_is_exported_on_the_representative(self):
        base = "https://images.example.com"
        photo = _scored("ok", 0.5, crop=[0.05, 0, 0.8, 1])
        photo["ai_tags"]["lid"] = [0.2, 0.25, 0.7, 0.75]
        self.assertEqual(export.to_photo_entry(photo, base, {})["lid"], [0.2, 0.25, 0.7, 0.75])
        photo["ai_tags"]["lid"] = [0.7, 0.25, 0.2, 0.75]
        self.assertIsNone(export.to_photo_entry(photo, base, {})["lid"])

    def test_crop_is_exported_only_when_well_formed(self):
        base = "https://images.example.com"
        ok = _scored("ok", 0.5, crop=[0.05, 0, 0.8, 1])
        self.assertEqual(export.to_gallery_entry(ok, base, {})["crop"], [0.05, 0.0, 0.8, 1.0])
        self.assertEqual(export.to_photo_entry(ok, base, {})["crop"], [0.05, 0.0, 0.8, 1.0])
        for bad in ([0, 0, 1], [0.5, 0, 0.5, 1], [0, 0, 1.2, 1], ["0", 0, 0.75, 1], {"x": 0}):
            self.assertIsNone(export.to_gallery_entry(_scored("bad", 0.5, crop=bad), base, {})["crop"], bad)


class SelectGalleryPhotosTest(unittest.TestCase):
    def test_landscape_override_cannot_replace_a_lid(self):
        scenery = {**_photo("scenery", shot_at="2026-09-29T00:00:00Z"), "is_landscape": True}
        lid = _photo("lid")
        result = export.select_gallery_photos([scenery, lid], 5, "scenery")
        self.assertEqual([p["id"] for p in result], ["lid"])
        self.assertEqual(export.select_gallery_photos([scenery], 5, "scenery"), [])

    def test_newest_first_by_shot_at(self):
        photos = [
            _photo("old", shot_at="2026-01-01T00:00:00Z"),
            _photo("new", shot_at="2026-03-01T00:00:00Z"),
            _photo("mid", shot_at="2026-02-01T00:00:00Z"),
        ]
        result = export.select_gallery_photos(photos, 5)
        self.assertEqual([p["id"] for p in result], ["new", "mid", "old"])

    def test_shot_at_takes_priority_over_created_at(self):
        photos = [
            _photo("no-shot", shot_at=None, created_at="2026-05-01T00:00:00Z"),
            _photo("shot", shot_at="2026-06-01T00:00:00Z", created_at="2026-01-01T00:00:00Z"),
        ]
        result = export.select_gallery_photos(photos, 5)
        self.assertEqual([p["id"] for p in result], ["shot", "no-shot"])

    def test_limit_is_applied(self):
        photos = [_photo(f"p{i}", shot_at=f"2026-01-0{i}T00:00:00Z") for i in range(1, 8)]
        result = export.select_gallery_photos(photos, 5)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["id"], "p7")

    def test_private_photos_are_excluded(self):
        photos = [
            _photo("public", shot_at="2026-01-01T00:00:00Z"),
            _photo("private", shot_at="2026-02-01T00:00:00Z", is_public=False),
        ]
        result = export.select_gallery_photos(photos, 5)
        self.assertEqual([p["id"] for p in result], ["public"])

    def test_representative_is_first_gallery_entry(self):
        # The newest public photo (= representative in the default run)
        # must open the gallery.
        photos = [
            _photo("rep", shot_at="2026-03-01T00:00:00Z"),
            _photo("other", shot_at="2026-01-01T00:00:00Z"),
        ]
        newest = sorted(photos, key=export.photo_sort_date, reverse=True)[0]
        result = export.select_gallery_photos(photos, 5)
        self.assertEqual(result[0]["id"], newest["id"])
        self.assertEqual(result[0]["id"], "rep")

    def test_featured_photo_is_first_even_when_older(self):
        photos = [
            _photo("new", shot_at="2026-03-01T00:00:00Z"),
            _photo("featured", shot_at="2026-01-01T00:00:00Z"),
            _photo("mid", shot_at="2026-02-01T00:00:00Z"),
        ]
        result = export.select_gallery_photos(
            photos,
            2,
            featured_photo_id="featured",
        )
        self.assertEqual([p["id"] for p in result], ["featured", "new"])

    def test_private_featured_photo_falls_back_to_latest_public(self):
        photos = [
            _photo("public", shot_at="2026-01-01T00:00:00Z"),
            _photo("private", shot_at="2026-03-01T00:00:00Z", is_public=False),
        ]
        result = export.select_gallery_photos(
            photos,
            5,
            featured_photo_id="private",
        )
        self.assertEqual([p["id"] for p in result], ["public"])

    def test_empty_input(self):
        self.assertEqual(export.select_gallery_photos([], 5), [])

    def test_visit_as_list_is_normalized(self):
        photo = _photo("listy", shot_at="2026-01-01T00:00:00Z")
        photo["visit"] = [photo["visit"]]
        result = export.select_gallery_photos([photo], 5)
        self.assertEqual([p["id"] for p in result], ["listy"])


class FeaturedPhotoOverridesTest(unittest.TestCase):
    def test_loads_string_and_numeric_manhole_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "featured.json"
            path.write_text(json.dumps({"12": "photo-a", 34: "photo-b"}))
            self.assertEqual(
                export.load_featured_photo_overrides(str(path)),
                {"12": "photo-a", "34": "photo-b"},
            )

    def test_missing_file_means_no_overrides(self):
        self.assertEqual(
            export.load_featured_photo_overrides("/missing/featured.json"),
            {},
        )

    def test_rejects_invalid_manhole_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "featured.json"
            path.write_text(json.dumps({"not-a-manhole": "photo-a"}))
            with self.assertRaises(ValueError):
                export.load_featured_photo_overrides(str(path))


class BuildPayloadFeaturedPhotoTest(unittest.TestCase):
    @mock.patch.object(export, "fetch_manhole_comments_by_display_name", return_value={})
    @mock.patch.object(export, "fetch_user_info", return_value={})
    @mock.patch.object(export, "get_effective_r2_public_base_url", return_value="https://images.example")
    def test_landscape_only_location_does_not_count_as_photographed(self, *_mocks):
        for include_private in [False, True]:
            for gallery_limit in [0, 5]:
                photos = [{**_photo("scenery"), "is_landscape": True}]
                with mock.patch.object(export, "iter_photos", return_value=iter(photos)):
                    payload = export.build_payload(
                        include_private, 100, 10, "tako", gallery_limit, {"1": "scenery"}
                    )
                self.assertEqual(payload["count"], 0)
                self.assertEqual(payload["photos"], {})

    @mock.patch.object(export, "fetch_manhole_comments_by_display_name", return_value={})
    @mock.patch.object(export, "fetch_user_info", return_value={})
    @mock.patch.object(export, "get_effective_r2_public_base_url", return_value="https://images.example")
    def test_representative_does_not_depend_on_gallery_limit(self, *_mocks):
        # 公開の候補はそろって rep_score あり、非公開の候補には無い（--include-private）
        photos = [
            _scored("public-high-quality", 0.95, lid_fits=True, rep=1),
            _scored("public-best-rep", 0.6, lid_fits=True, rep=9),
            {**_scored("private", 0.99, lid_fits=True), "visit": {**_photo("p", is_public=False)["visit"]}},
        ]
        for gallery_limit in [0, 5]:
            with mock.patch.object(export, "iter_photos", return_value=iter([dict(p) for p in photos])):
                payload = export.build_payload(True, 100, 10, "tako", gallery_limit, {})
            self.assertEqual(payload["photos"]["1"]["photo_id"], "public-best-rep", gallery_limit)

    def test_query_filters_landscapes_before_pagination(self):
        with mock.patch.object(export, "iter_supabase_rows", return_value=iter([])) as rows:
            list(export.iter_photos(False, 100, 10))
        query = rows.call_args.args[1]
        self.assertEqual(query["is_landscape"], "eq.false")
        self.assertEqual(query["visit.is_public"], "eq.true")
        self.assertIn("is_landscape", query["select"])

    @mock.patch.object(export, "fetch_manhole_comments_by_display_name", return_value={})
    @mock.patch.object(export, "fetch_user_info", return_value={})
    @mock.patch.object(export, "get_effective_r2_public_base_url", return_value="https://images.example")
    def test_curated_photo_becomes_representative_and_first_gallery_item(
        self,
        _base_url,
        _users,
        _comments,
    ):
        photos = [
            _photo("new", shot_at="2026-03-01T00:00:00Z"),
            _photo("featured", shot_at="2026-01-01T00:00:00Z"),
        ]
        with mock.patch.object(export, "iter_photos", return_value=iter(photos)):
            payload = export.build_payload(
                include_private=False,
                batch_size=100,
                timeout=10,
                manhole_comment_display_name="tako",
                gallery_limit=5,
                featured_photo_overrides={"1": "featured"},
            )

        entry = payload["photos"]["1"]
        self.assertEqual(entry["photo_id"], "featured")
        self.assertEqual(entry["representative_source"], "curated")
        self.assertEqual(entry["gallery"][0]["photo_id"], "featured")


class ToGalleryEntryTest(unittest.TestCase):
    def test_fields_and_display_name(self):
        photo = _photo("abc", shot_at="2026-01-02T03:04:05Z", user_id="uid-9")
        entry = export.to_gallery_entry(
            photo,
            "https://images.example.com",
            {"uid-9": {"display_name": "tako", "public_user_id": "pub-uid-9"}},
        )
        self.assertEqual(
            entry,
            {
                "photo_id": "abc",
                "url": "https://images.example.com/photos/abc.jpeg",
                "storage_key": "photos/abc.jpeg",
                "content_type": "image/jpeg",
                "created_at": "2026-01-01T00:00:00Z",
                "shot_at": "2026-01-02T03:04:05Z",
                "display_name": "tako",
                "public_user_id": "pub-uid-9",
                "crop": None,
            },
        )

    def test_unknown_user_gives_none_display_name_and_public_user_id(self):
        photo = _photo("abc", user_id="unknown")
        entry = export.to_gallery_entry(photo, "https://images.example.com", {})
        self.assertIsNone(entry["display_name"])
        self.assertIsNone(entry["public_user_id"])

    def test_missing_public_user_id_key_is_safe(self):
        # Older-shaped mapping entries that only carry display_name must not
        # crash lookups; public_user_id should degrade to None.
        photo = _photo("abc", user_id="uid-legacy")
        entry = export.to_gallery_entry(
            photo,
            "https://images.example.com",
            {"uid-legacy": {"display_name": "legacy"}},
        )
        self.assertEqual(entry["display_name"], "legacy")
        self.assertIsNone(entry["public_user_id"])


class ToPhotoEntryTest(unittest.TestCase):
    def test_includes_public_user_id(self):
        photo = _photo("abc", shot_at="2026-01-02T03:04:05Z", user_id="uid-9")
        entry = export.to_photo_entry(
            photo,
            "https://images.example.com",
            {"uid-9": {"display_name": "tako", "public_user_id": "pub-uid-9"}},
        )
        self.assertEqual(entry["display_name"], "tako")
        self.assertEqual(entry["public_user_id"], "pub-uid-9")

    def test_unknown_user_gives_none_public_user_id(self):
        photo = _photo("abc", user_id="unknown")
        entry = export.to_photo_entry(photo, "https://images.example.com", {})
        self.assertIsNone(entry["display_name"])
        self.assertIsNone(entry["public_user_id"])


if __name__ == "__main__":
    unittest.main()
