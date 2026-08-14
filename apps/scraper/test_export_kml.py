#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("export_kml.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("export_kml", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

NS = {"kml": MODULE.KML_NS}


def record(**overrides):
    base = {
        "id": "1",
        "title": "鹿児島県/指宿市",
        "prefecture": "鹿児島県",
        "city": "指宿",
        "address": "鹿児島県指宿市湊1丁目1-1",
        "pokemons": ["イーブイ"],
        "lat": 31.237194,
        "lng": 130.642861,
        "status": "active",
    }
    base.update(overrides)
    return base


def placemarks(tree: ET.ElementTree):
    return tree.getroot().findall(".//kml:Placemark", NS)


def text_of(placemark, tag: str) -> str:
    node = placemark.find(f"kml:{tag}", NS)
    return node.text if node is not None and node.text else ""


class LoadRecordsTest(unittest.TestCase):
    def _write(self, body: str) -> Path:
        tmp = Path(tempfile.mkdtemp()) / "in.ndjson"
        tmp.write_text(body, encoding="utf-8")
        return tmp

    def test_skips_blank_and_malformed_lines(self) -> None:
        path = self._write('{"id":"1"}\n\n  \nnot json\n{"id":"2"}\n')
        self.assertEqual([{"id": "1"}, {"id": "2"}], MODULE._load_records(path))

    def test_skips_non_dict_json(self) -> None:
        path = self._write('{"id":"1"}\n[1,2,3]\n"str"\n')
        self.assertEqual([{"id": "1"}], MODULE._load_records(path))

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            MODULE._load_records(Path(tempfile.mkdtemp()) / "nope.ndjson")


class SafeFloatTest(unittest.TestCase):
    def test_accepts_number_and_numeric_string(self) -> None:
        self.assertEqual(1.5, MODULE._safe_float(1.5))
        self.assertEqual(1.5, MODULE._safe_float("1.5"))

    def test_rejects_none_and_garbage(self) -> None:
        self.assertIsNone(MODULE._safe_float(None))
        self.assertIsNone(MODULE._safe_float(""))
        self.assertIsNone(MODULE._safe_float("北緯31度"))


class FormatNameTest(unittest.TestCase):
    def test_appends_pokemon_names(self) -> None:
        self.assertEqual(
            "鹿児島県/指宿市 (イーブイ)",
            MODULE._format_name(record()),
        )

    def test_joins_multiple_pokemons(self) -> None:
        self.assertEqual(
            "東京都/町田市 (キャタピー, ナゾノクサ, ビードル)",
            MODULE._format_name(record(title="東京都/町田市",
                                       pokemons=["キャタピー", "ナゾノクサ", "ビードル"])),
        )

    def test_falls_back_to_id_when_title_missing(self) -> None:
        self.assertEqual("Pokéfuta #7 (イーブイ)", MODULE._format_name(record(id="7", title="")))

    def test_title_only_when_no_pokemons(self) -> None:
        self.assertEqual("鹿児島県/指宿市", MODULE._format_name(record(pokemons=[])))


class FormatDescriptionTest(unittest.TestCase):
    def test_includes_address(self) -> None:
        self.assertIn("Address: 鹿児島県指宿市湊1丁目1-1", MODULE._format_description(record()))

    def test_falls_back_to_address_norm(self) -> None:
        desc = MODULE._format_description(
            record(address="", address_norm="新潟県小千谷市城内1-8-22")
        )
        self.assertIn("Address: 新潟県小千谷市城内1-8-22", desc)

    def test_omits_absent_fields(self) -> None:
        desc = MODULE._format_description({"id": "1", "prefecture": "沖縄県"})
        self.assertEqual("Prefecture: 沖縄県", desc)

    def test_renders_tag_list(self) -> None:
        desc = MODULE._format_description(record(tags=["station_front", "tourism"]))
        self.assertIn("Tags: station_front, tourism", desc)


class BuildKmlTest(unittest.TestCase):
    def _build(self, records, include_deleted=False):
        return MODULE.build_kml(records, include_deleted=include_deleted,
                                document_name="Pokéfuta")

    def test_coordinates_are_lng_lat_alt(self) -> None:
        tree = self._build([record()])
        coords = tree.getroot().find(".//kml:coordinates", NS)
        self.assertEqual("130.642861,31.237194,0", coords.text)

    def test_deleted_records_excluded_by_default(self) -> None:
        recs = [record(id="1"), record(id="2", status="deleted")]
        self.assertEqual(1, len(placemarks(self._build(recs))))

    def test_deleted_records_included_when_requested(self) -> None:
        recs = [record(id="1"), record(id="2", status="deleted")]
        self.assertEqual(2, len(placemarks(self._build(recs, include_deleted=True))))

    def test_records_without_coordinates_are_dropped(self) -> None:
        recs = [record(id="1"), record(id="2", lat=None), record(id="3", lng="")]
        self.assertEqual(1, len(placemarks(self._build(recs))))

    def test_placemarks_sorted_by_numeric_id(self) -> None:
        recs = [record(id="10", title="十"), record(id="2", title="二"), record(id="1", title="一")]
        names = [text_of(p, "name") for p in placemarks(self._build(recs))]
        self.assertEqual(["一 (イーブイ)", "二 (イーブイ)", "十 (イーブイ)"], names)

    def test_document_name_reflects_status_filter(self) -> None:
        active = self._build([record()]).getroot().find(".//kml:name", NS)
        self.assertEqual("Pokéfuta (active only)", active.text)
        every = self._build([record()], include_deleted=True).getroot().find(".//kml:name", NS)
        self.assertEqual("Pokéfuta (all statuses)", every.text)

    def test_output_is_serialisable_and_reparsable(self) -> None:
        tree = self._build([record(), record(id="2", title="東京都/町田市")])
        out = Path(tempfile.mkdtemp()) / "out.kml"
        tree.write(out, encoding="utf-8", xml_declaration=True)
        self.assertEqual(2, len(placemarks(ET.parse(out))))


if __name__ == "__main__":
    unittest.main()
