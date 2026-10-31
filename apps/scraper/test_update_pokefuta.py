#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class UpdatePokefutaApplyInstallStatusTest(unittest.TestCase):
    def test_scheduled_but_photographed_counts_as_installed(self) -> None:
        record = {"id": "461", "installed": False}
        note = "2026年4月11日設置予定"
        idx = {"461": {"manhole_no": "461", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx, frozenset({"461"}))
        self.assertTrue(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_photo_confirmation_survives_photo_removal(self) -> None:
        record = {"id": "461"}
        idx = {"461": {"manhole_no": "461", "installation_date": "2026年4月11日設置予定"}}
        MODULE.apply_install_status(record, idx, frozenset({"461"}))
        self.assertEqual("photo", record["installed_evidence"])
        result = MODULE.apply_install_status(record, idx, frozenset())
        self.assertFalse(result)
        self.assertTrue(record["installed"])

    def test_official_installed_note_drops_photo_evidence(self) -> None:
        record = {"id": "461", "installed": True, "installed_evidence": "photo"}
        idx = {"461": {"manhole_no": "461", "installation_date": ""}}
        MODULE.apply_install_status(record, idx, frozenset({"461"}))
        self.assertTrue(record["installed"])
        self.assertNotIn("installed_evidence", record)

    def test_scheduled_without_photo_stays_preinstall(self) -> None:
        record = {"id": "461"}
        idx = {"461": {"manhole_no": "461", "installation_date": "2026年4月11日設置予定"}}
        MODULE.apply_install_status(record, idx, frozenset({"1"}))
        self.assertFalse(record["installed"])

    def test_load_photo_ids_reads_snapshot(self) -> None:
        import json, logging, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"manholes": [{"id": 461, "photo_count": 1}, {"id": 2, "photo_count": 0}]}, f)
        self.assertEqual({"461"}, MODULE.load_photo_ids(f.name, logging.getLogger("t")))
        self.assertEqual(set(), MODULE.load_photo_ids("/nonexistent.json", logging.getLogger("t")))

    def test_scheduled_not_yet_installed(self) -> None:
        record = {"id": "481"}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)
        self.assertFalse(record["installed"])
        self.assertEqual(record["installation_note"], "2026年8月上旬までに設置予定。")

    def test_installed_empty_note(self) -> None:
        record = {"id": "484"}
        idx = {"484": {"manhole_no": "484", "installation_date": ""}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertNotIn("installation_note", record)

    def test_id_124_edge_case_not_fooled_by_yotei(self) -> None:
        record = {"id": "124"}
        note = "移設済み（ポケストップは順次移設予定）"
        idx = {"124": {"manhole_no": "124", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_viewing_caveat_still_installed(self) -> None:
        record = {"id": "1"}
        note = "公園の開園時間外には、ポケふたをご覧いただくことができません。"
        idx = {"1": {"manhole_no": "1", "installation_date": note}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)
        self.assertTrue(record["installed"])
        self.assertEqual(record["installation_note"], note)

    def test_transition_returns_true_when_already_had_field(self) -> None:
        record = {"id": "481", "installed": True}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx)
        self.assertTrue(result)
        self.assertFalse(record["installed"])

    def test_first_time_set_returns_false(self) -> None:
        record = {"id": "481"}
        idx = {"481": {"manhole_no": "481", "installation_date": "2026年8月上旬までに設置予定。"}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)

    def test_id_not_in_index_returns_false_and_untouched(self) -> None:
        record = {"id": "999", "title": "unchanged"}
        idx = {"481": {"manhole_no": "481", "installation_date": ""}}
        result = MODULE.apply_install_status(record, idx)
        self.assertFalse(result)
        self.assertEqual(record, {"id": "999", "title": "unchanged"})


class UpdatePokefutaOfficialOutageTest(unittest.TestCase):
    """公式が止まっている（503・タイムアウト・メンテ画面）ときに既存の蓋を deleted にしない。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "pokefuta.ndjson"
        rows = [
            {"id": str(i), "title": f"t{i}", "prefecture": "東京都", "city": "千代田区",
             "lat": 35.0, "lng": 139.0, "status": "active"}
            for i in range(1, 4)
        ]
        self.original = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        self.out.write_text(self.original, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, fetch_side_effect, *extra_args: str) -> None:
        argv = ["update_pokefuta.py", "--out", str(self.out), "--scan-max", "3",
                "--photo-snapshot", str(Path(self.tmp.name) / "missing.json"), *extra_args]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(MODULE, "fetch", side_effect=fetch_side_effect), \
                mock.patch.object(MODULE, "fetch_install_status", return_value={}), \
                mock.patch.object(MODULE.time, "sleep"):
            MODULE.main()

    def _statuses(self) -> dict:
        lines = self.out.read_text(encoding="utf-8").splitlines()
        return {r["id"]: r["status"] for r in map(json.loads, lines)}

    def test_site_down_aborts_without_writing(self) -> None:
        with mock.patch.object(MODULE, "MAX_CONSECUTIVE_FETCH_ERRORS", 2):
            with self.assertRaises(SystemExit) as cm:
                self._run(MODULE.FetchError("503"))
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self.out.read_text(encoding="utf-8"), self.original)

    def test_isolated_fetch_error_keeps_record_active(self) -> None:
        def fake_fetch(url, logger, headers):
            if "/desc/1/" in url:
                raise MODULE.FetchError("timeout")
            return None  # 404

        with self.assertRaises(SystemExit) as cm:
            self._run(fake_fetch)
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(self._statuses(), {"1": "active", "2": "deleted", "3": "deleted"})

    def test_mass_deletion_aborts_without_writing(self) -> None:
        # メンテ画面が 200 で返り座標が読めないと、全件が削除扱いになる
        with self.assertRaises(SystemExit) as cm:
            self._run(lambda url, logger, headers: "<html>maintenance</html>", "--max-deletions", "2")
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self.out.read_text(encoding="utf-8"), self.original)

    def test_fetch_raises_on_server_error_and_returns_none_on_404(self) -> None:
        logger = MODULE.setup_logger("CRITICAL")
        resp_503 = mock.Mock(status_code=503)
        resp_503.raise_for_status.side_effect = MODULE.requests.HTTPError("503")
        with mock.patch.object(MODULE.requests, "get", return_value=resp_503), \
                mock.patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.FetchError):
                MODULE.fetch("https://example.invalid/", logger, {})
        with mock.patch.object(MODULE.requests, "get", return_value=mock.Mock(status_code=404)):
            self.assertIsNone(MODULE.fetch("https://example.invalid/", logger, {}))


if __name__ == "__main__":
    unittest.main()
