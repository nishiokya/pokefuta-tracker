#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("update_pokefuta.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("update_pokefuta", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class UpdatePokefutaParseDetailTest(unittest.TestCase):
    def test_city_suffix_stripping_keeps_machi_inside_name(self) -> None:
        self.assertEqual("大町", MODULE.strip_municipality_suffix("大町市"))

    def test_city_suffix_stripping_keeps_mura_inside_name(self) -> None:
        self.assertEqual("田村", MODULE.strip_municipality_suffix("田村市"))

    def test_city_suffix_stripping_handles_plain_city(self) -> None:
        self.assertEqual("岡谷", MODULE.strip_municipality_suffix("岡谷市"))


if __name__ == "__main__":
    unittest.main()
