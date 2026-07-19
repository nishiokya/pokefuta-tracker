"""Unit tests for export_latest_manhole_photos (network-free).

Run: python3 tools/test_export_latest_manhole_photos.py
"""

import importlib.util
import unittest
from pathlib import Path

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


class SelectGalleryPhotosTest(unittest.TestCase):
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

    def test_empty_input(self):
        self.assertEqual(export.select_gallery_photos([], 5), [])

    def test_visit_as_list_is_normalized(self):
        photo = _photo("listy", shot_at="2026-01-01T00:00:00Z")
        photo["visit"] = [photo["visit"]]
        result = export.select_gallery_photos([photo], 5)
        self.assertEqual([p["id"] for p in result], ["listy"])


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
