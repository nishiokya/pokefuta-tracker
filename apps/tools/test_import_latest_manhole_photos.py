"""import_latest_manhole_photos.crop_to_square / crop_box のテスト（蓋の位置に寄せた正方形）。"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

MODULE_PATH = Path(__file__).with_name("import_latest_manhole_photos.py")
SPEC = importlib.util.spec_from_file_location("import_latest_manhole_photos", MODULE_PATH)
imp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(imp)


def _striped(width: int, height: int) -> Image.Image:
    """左半分が赤、右半分が青の横長画像。"""
    image = Image.new("RGB", (width, height), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, width // 2, height))
    return image


class CropToSquareTest(unittest.TestCase):
    def test_without_crop_uses_the_middle(self):
        out = imp.crop_to_square(_striped(400, 300), 30)
        self.assertEqual(out.size, (30, 30))
        self.assertGreater(out.getpixel((2, 15))[0], 200)    # 左端は赤
        self.assertGreater(out.getpixel((27, 15))[2], 200)   # 右端は青

    def test_crop_moves_the_square_to_the_lid(self):
        # 400x300、x<200 が赤。正方形は一辺 300（30px に縮めるので 1px = 10px）
        middle = imp.crop_to_square(_striped(400, 300), 30)                     # x 50..350
        left = imp.crop_to_square(_striped(400, 300), 30, [0, 0, 0.75, 1])     # x 0..300
        right = imp.crop_to_square(_striped(400, 300), 30, [0.25, 0, 1, 1])    # x 100..400
        self.assertGreater(middle.getpixel((18, 15))[2], 200)   # x=230 は青
        self.assertGreater(left.getpixel((18, 15))[0], 200)     # x=180 は赤
        self.assertGreater(middle.getpixel((12, 15))[0], 200)   # x=170 は赤
        self.assertGreater(right.getpixel((12, 15))[2], 200)    # x=220 は青

    def test_crop_never_leaves_the_image(self):
        out = imp.crop_to_square(_striped(400, 300), 30, [0.9, 0, 1.0, 1])
        self.assertEqual(out.size, (30, 30))

    def test_crop_box_rejects_malformed(self):
        self.assertEqual(imp.crop_box({"crop": [0.1, 0, 0.85, 1]}), [0.1, 0.0, 0.85, 1.0])
        for bad in (None, [0, 0, 1], [0.5, 0, 0.5, 1], [0, 0, 1.5, 1], ["0", 0, 1, 1], True):
            self.assertIsNone(imp.crop_box({"crop": bad}), bad)


class LidTileTest(unittest.TestCase):
    def test_fills_the_square_with_the_lid(self):
        # 400x300 の真ん中に 100x100 の白い蓋。蓋の枠 × 1.04 で切るので、ほぼ白一色になる
        image = Image.new("RGB", (400, 300), (0, 0, 0))
        image.paste((255, 255, 255), (150, 100, 250, 200))
        tile = imp.lid_tile(image, [150 / 400, 100 / 300, 250 / 400, 200 / 300], 40)
        self.assertEqual(tile.size, (40, 40))
        self.assertGreater(tile.getpixel((20, 20))[0], 240)
        self.assertGreater(tile.getpixel((5, 5))[0], 200)       # 角も蓋（1.04 倍なので縁は少しだけ）

    def test_pads_with_background_when_the_lid_is_at_the_edge(self):
        image = Image.new("RGB", (400, 300), (0, 0, 0))
        tile = imp.lid_tile(image, [0.0, 0.0, 0.5, 0.5], 40)   # 左上の端の蓋 → 外は地の色
        self.assertEqual(tile.getpixel((0, 0)), imp.LID_TILE_BACKGROUND)

    def test_does_not_zoom_tiny_lids_beyond_the_limit(self):
        image = Image.new("RGB", (300, 300), (0, 0, 0))
        image.paste((255, 255, 255), (148, 148, 152, 152))      # 4px の小さい蓋
        tile = imp.lid_tile(image, [148 / 300, 148 / 300, 152 / 300, 152 / 300], 30)
        self.assertEqual(tile.getpixel((2, 2)), (0, 0, 0))       # 最大 3 倍までなので周りも写る

    def test_crop_box_reads_lid(self):
        self.assertEqual(imp.crop_box({"lid": [0.2, 0.2, 0.8, 0.8]}, "lid"), [0.2, 0.2, 0.8, 0.8])
        self.assertIsNone(imp.crop_box({"lid": [0.8, 0.2, 0.2, 0.8]}, "lid"))



class DownloadRetryTest(unittest.TestCase):
    def test_session_retries_timeouts_and_server_errors(self):
        retry = imp.download_session().get_adapter("https://example.com").max_retries
        self.assertEqual((retry.total, retry.read, retry.connect), (3, 3, 3))
        self.assertIn(503, retry.status_forcelist)
        self.assertGreater(retry.backoff_factor, 0)


class GalleryNeedsFetchTest(unittest.TestCase):
    def test_new_file_is_fetched(self):
        self.assertTrue(imp.gallery_needs_fetch(False, False, None, "a"))

    def test_same_key_is_kept(self):
        self.assertFalse(imp.gallery_needs_fetch(True, False, "a", "a"))

    def test_changed_key_is_fetched_again(self):
        self.assertTrue(imp.gallery_needs_fetch(True, False, "a", "b"))

    def test_unknown_old_file_is_kept(self):
        self.assertFalse(imp.gallery_needs_fetch(True, False, None, "b"))

    def test_refresh_fetches_everything(self):
        self.assertTrue(imp.gallery_needs_fetch(True, True, "a", "a"))

    def test_fingerprint_is_short_and_stable(self):
        self.assertEqual(imp.key_fingerprint("photos/original/x.jpg"), imp.key_fingerprint("photos/original/x.jpg"))
        self.assertEqual(len(imp.key_fingerprint("photos/original/x.jpg")), 16)
        self.assertIsNone(imp.key_fingerprint(None))

class GalleryImportTest(unittest.TestCase):
    """ギャラリーは 360px の WebP。前の形式の JPEG は取り直さずに作り直し、掃除で消す"""

    PHOTO_ID = "abcdef12-0000-0000-0000-000000000000"
    KEY = "photos/original/a.jpg"

    def _run(self, out: Path, gallery: list[dict], download=None) -> int:
        payload = {"photos": {"1": {
            "manhole_id": 1, "photo_id": "11111111-0000", "url": "https://example.com/hero.jpg",
            "gallery": [{"photo_id": "11111111-0000"}, *gallery],
        }}}
        src = out / "in.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        argv = ["import", "--input", str(src), "--output-dir", str(out), "--env-file", str(out / "none")]
        download = download or mock.Mock(return_value=Image.new("RGB", (1200, 900), (10, 20, 30)))
        with mock.patch.object(sys, "argv", argv), mock.patch.object(imp, "download_image", download), \
                mock.patch("builtins.print"):
            return imp.main()

    def _item(self, key: str = KEY) -> dict:
        return {"photo_id": self.PHOTO_ID, "url": "https://example.com/g.jpg", "storage_key": key}

    def test_new_gallery_photo_is_a_small_webp(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(self._run(out, [self._item()]), 0)
            with Image.open(out / "1_abcdef12.webp") as image:
                self.assertEqual((image.format, image.size), ("WEBP", (360, 360)))
            self.assertFalse((out / "1_abcdef12.jpeg").exists())

    def test_legacy_jpeg_is_converted_without_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            Image.new("RGB", (720, 720), (200, 0, 0)).save(out / "1_abcdef12.jpeg", "JPEG")
            (out / imp.GALLERY_SOURCES).write_text(json.dumps({"1_abcdef12.jpeg": imp.key_fingerprint(self.KEY)}))
            stale = out / "1_99999999.jpeg"
            Image.new("RGB", (720, 720)).save(stale, "JPEG")
            download = mock.Mock(return_value=Image.new("RGB", (720, 720)))
            self.assertEqual(self._run(out, [self._item()], download), 0)
            self.assertEqual(download.call_count, 1)  # 代表だけ
            with Image.open(out / "1_abcdef12.webp") as image:
                self.assertEqual(image.size, (360, 360))
                self.assertGreater(image.convert("RGB").getpixel((180, 180))[0], 150)
            self.assertFalse((out / "1_abcdef12.jpeg").exists())
            self.assertFalse(stale.exists())
            sources = json.loads((out / imp.GALLERY_SOURCES).read_text())
            self.assertEqual(sources, {"1_abcdef12.webp": imp.key_fingerprint(self.KEY)})

    def test_legacy_jpeg_with_a_changed_key_is_fetched_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            Image.new("RGB", (720, 720), (200, 0, 0)).save(out / "1_abcdef12.jpeg", "JPEG")
            (out / imp.GALLERY_SOURCES).write_text(json.dumps({"1_abcdef12.jpeg": imp.key_fingerprint("old")}))
            download = mock.Mock(return_value=Image.new("RGB", (900, 900), (0, 0, 200)))
            self.assertEqual(self._run(out, [self._item()], download), 0)
            self.assertEqual(download.call_count, 2)
            with Image.open(out / "1_abcdef12.webp") as image:
                self.assertGreater(image.convert("RGB").getpixel((180, 180))[2], 150)
            self.assertFalse((out / "1_abcdef12.jpeg").exists())

    def test_legacy_jpeg_survives_when_it_cannot_be_fetched_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            Image.new("RGB", (720, 720)).save(out / "1_abcdef12.jpeg", "JPEG")
            (out / imp.GALLERY_SOURCES).write_text(json.dumps({"1_abcdef12.jpeg": imp.key_fingerprint("old")}))
            hero = Image.new("RGB", (720, 720))
            download = mock.Mock(side_effect=[hero, OSError("unreachable")])
            self.assertEqual(self._run(out, [self._item()], download), 1)
            self.assertTrue((out / "1_abcdef12.jpeg").exists())
            self.assertFalse((out / "1_abcdef12.webp").exists())


if __name__ == "__main__":
    unittest.main()
