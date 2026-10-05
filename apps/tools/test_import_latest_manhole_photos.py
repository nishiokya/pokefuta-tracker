"""import_latest_manhole_photos.crop_to_square / crop_box のテスト（蓋の位置に寄せた正方形）。"""

import importlib.util
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
