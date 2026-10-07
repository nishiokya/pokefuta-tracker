#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date
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


class UpdatePokefutaApplyTitleMetadataTagsTest(unittest.TestCase):
    """tags はマスタが唯一の供給元。マスタから消したタグが ndjson に残らないこと。"""

    def test_tags_replaced_by_master(self) -> None:
        record = {"id": "175", "tags": ["seaside", "world_heritage", "remote_island"]}
        self.assertTrue(MODULE.apply_title_metadata(record, {"175": {"tags": ["seaside"]}}))
        self.assertEqual(record["tags"], ["seaside"])

    def test_tags_dropped_when_master_entry_has_no_tags(self) -> None:
        record = {"id": "176", "tags": ["remote_island"], "building": "x"}
        self.assertTrue(MODULE.apply_title_metadata(record, {"176": {"building": "x"}}))
        self.assertNotIn("tags", record)

    def test_tags_dropped_when_id_removed_from_master(self) -> None:
        record = {"id": "230", "tags": ["remote_island"]}
        self.assertTrue(MODULE.apply_title_metadata(record, {"1": {"tags": ["seaside"]}}))
        self.assertNotIn("tags", record)

    def test_record_without_tags_is_untouched(self) -> None:
        record = {"id": "230"}
        self.assertFalse(MODULE.apply_title_metadata(record, {"1": {"tags": ["seaside"]}}))


BEFORE_AUGUST = date(2026, 7, 1)


class UpdatePokefutaApplyInstallStatusTest(unittest.TestCase):
    def test_past_scheduled_date_counts_as_installed(self) -> None:
        record = {"id": "461", "installed": False}
        note = "2026年4月11日設置予定"
        idx = {"461": {"manhole_no": "461", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx, today=date(2026, 10, 7))
        self.assertTrue(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_scheduled_day_itself_is_still_preinstall(self) -> None:
        record = {"id": "461"}
        idx = {"461": {"manhole_no": "461", "installation_date": "2026年4月11日設置予定"}}
        MODULE.apply_install_status(record, idx, today=date(2026, 4, 11))
        self.assertFalse(record["installed"])

    def test_deadline_reads_jun_and_month_end(self) -> None:
        f = MODULE.scheduled_install_deadline
        self.assertEqual(date(2026, 8, 10), f("2026年8月上旬までに設置予定。"))
        self.assertEqual(date(2026, 8, 20), f("2026年8月中旬設置予定"))
        self.assertEqual(date(2026, 2, 28), f("2026年2月下旬設置予定"))
        self.assertEqual(date(2026, 12, 31), f("2026年12月設置予定"))
        self.assertIsNone(f("今冬設置予定"))

    def test_unreadable_schedule_stays_preinstall(self) -> None:
        record = {"id": "490"}
        idx = {"490": {"manhole_no": "490", "installation_date": "今冬設置予定"}}
        MODULE.apply_install_status(record, idx, today=date(2030, 1, 1))
        self.assertFalse(record["installed"])

    def test_scheduled_not_yet_installed(self) -> None:
        record = {"id": "481"}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)
        self.assertFalse(record["installed"])
        self.assertEqual(record["installation_note"], "2026年8月上旬までに設置予定。")

    def test_installed_empty_note(self) -> None:
        record = {"id": "484"}
        idx = {"484": {"manhole_no": "484", "installation_date": ""}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertNotIn("installation_note", record)

    def test_id_124_edge_case_not_fooled_by_yotei(self) -> None:
        record = {"id": "124"}
        note = "移設済み（ポケストップは順次移設予定）"
        idx = {"124": {"manhole_no": "124", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_viewing_caveat_still_installed(self) -> None:
        record = {"id": "1"}
        note = "公園の開園時間外には、ポケふたをご覧いただくことができません。"
        idx = {"1": {"manhole_no": "1", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_transition_returns_true_when_already_had_field(self) -> None:
        record = {"id": "481", "installed": True}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertTrue(result)
        self.assertFalse(record["installed"])

    def test_first_time_set_returns_false(self) -> None:
        record = {"id": "481"}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)

    def test_id_not_in_index_returns_false_and_untouched(self) -> None:
        record = {"id": "999", "title": "unchanged"}
        idx = {"481": {"manhole_no": "481", "installation_date": ""}}
        result = MODULE.apply_install_status(record, idx, today=BEFORE_AUGUST)
        self.assertFalse(result)
        self.assertEqual(record, {"id": "999", "title": "unchanged"})


if __name__ == "__main__":
    unittest.main()
