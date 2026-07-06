from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("export_app_snapshot.py")
SPEC = importlib.util.spec_from_file_location("export_app_snapshot", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def ewkb_point_hex(lng: float, lat: float, little: bool = True, srid: int | None = 4326) -> str:
    """テスト用に PostGIS 互換の (E)WKB POINT hex を組み立てる。"""
    endian = "<" if little else ">"
    geom_type = 1 | (0x20000000 if srid is not None else 0)
    raw = struct.pack(f"{endian}B", 1 if little else 0)
    raw += struct.pack(f"{endian}I", geom_type)
    if srid is not None:
        raw += struct.pack(f"{endian}I", srid)
    raw += struct.pack(f"{endian}dd", lng, lat)
    return raw.hex().upper()


class ParseWkbPointTest(unittest.TestCase):
    def test_little_endian_ewkb_with_srid(self) -> None:
        wkb = ewkb_point_hex(130.643147, 31.251983)
        self.assertEqual((31.251983, 130.643147), MODULE.parse_wkb_point(wkb))

    def test_real_world_sample(self) -> None:
        # 実データ形式: 01 (LE) 01000020 (POINT+SRID) E6100000 (SRID 4326) + lng + lat
        wkb = ewkb_point_hex(129.910858, 33.141048)
        self.assertTrue(wkb.startswith("0101000020E6100000"))
        result = MODULE.parse_wkb_point(wkb)
        assert result is not None
        self.assertAlmostEqual(33.141048, result[0])
        self.assertAlmostEqual(129.910858, result[1])

    def test_big_endian(self) -> None:
        wkb = ewkb_point_hex(139.7671, 35.6812, little=False)
        result = MODULE.parse_wkb_point(wkb)
        assert result is not None
        self.assertAlmostEqual(35.6812, result[0])
        self.assertAlmostEqual(139.7671, result[1])

    def test_plain_wkb_without_srid(self) -> None:
        wkb = ewkb_point_hex(135.0, 34.5, srid=None)
        self.assertEqual((34.5, 135.0), MODULE.parse_wkb_point(wkb))

    def test_rejects_non_point_geometry(self) -> None:
        # geometry type 2 = LINESTRING
        raw = struct.pack("<BI", 1, 2) + struct.pack("<dd", 135.0, 34.5)
        self.assertIsNone(MODULE.parse_wkb_point(raw.hex()))

    def test_rejects_out_of_range_coordinates(self) -> None:
        wkb = ewkb_point_hex(200.0, 95.0)
        self.assertIsNone(MODULE.parse_wkb_point(wkb))

    def test_rejects_invalid_hex_and_empty(self) -> None:
        self.assertIsNone(MODULE.parse_wkb_point(""))
        self.assertIsNone(MODULE.parse_wkb_point("zz"))
        self.assertIsNone(MODULE.parse_wkb_point("0101"))


class WriteManholesJsonTest(unittest.TestCase):
    def test_payload_not_mutated_and_output_valid_json(self) -> None:
        payload = {
            "success": True,
            "total": 2,
            "with_photos": 1,
            "skipped_without_location": 0,
            "generated_at": "2026-07-06T00:00:00+00:00",
            "manholes": [
                {"id": 2, "name": "ポケふた", "photo_count": 1},
                {"id": 1, "name": "テスト", "photo_count": 0},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "manholes.json"
            MODULE.write_manholes_json(payload, out)
            # 非破壊であること
            self.assertIn("manholes", payload)
            self.assertEqual(2, len(payload["manholes"]))
            # 出力が正しい JSON で、内容が一致すること
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload, loaded)
            # 1マンホール1行のフォーマットであること
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, sum(1 for l in lines if l.lstrip().startswith('{"id"')))


if __name__ == "__main__":
    unittest.main()
