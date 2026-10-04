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


if __name__ == "__main__":
    unittest.main()
