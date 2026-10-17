from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apps.scraper import features as FEATURES
from apps.scraper import generate_feature_pages as MODULE
from apps.scraper import generate_sitemap as SITEMAP
from apps.scraper import generate_summary_pages as SUMMARY


def _record(mid: str, city: str, **extra) -> dict:
    return {
        "id": mid, "prefecture": "沖縄県", "city": city, "address": f"沖縄県{city}村{mid}",
        "lat": 26.6, "lng": 128.1, "pokemons": ["ガーディ"], "status": "active", "installed": True,
        **extra,
    }


RECORDS = {
    "487": _record("487", "国頭", installed=False, installation_note="2026年10月下旬頃に設置予定。"),
    "488": _record("488", "大宜味"),
}


def _feature(slug: str = "okinawa-test", **extra) -> dict:
    return {
        "slug": slug, "title": "沖縄にポケふたが増えます", "published": "2026-10-17",
        "highlight_until": "2027-01-31", "prefecture": "沖縄県",
        "manholes": [{"id": "488", "note": "西海岸"}, {"id": "487", "note": "辺戸岬"}],
        **extra,
    }


def _write(directory: Path, *entries: dict) -> Path:
    for entry in entries:
        (directory / f"{entry['slug']}.json").write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return directory


class LoadFeaturesTests(unittest.TestCase):
    def test_keeps_the_written_order_and_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(Path(tmp), _feature("a"), _feature("b", published="2026-07-09"))
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
        self.assertEqual([f["slug"] for f in loaded], ["a", "b"])
        self.assertEqual([r["id"] for r in loaded[0]["records"]], ["488", "487"])

    def test_skips_future_broken_and_missing_manholes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(
                Path(tmp),
                _feature("future", published="2026-10-18"),
                _feature("missing", manholes=[{"id": "999"}]),
                _feature("Bad_Slug"),
            )
            (d / "renamed.json").write_text(json.dumps(_feature("other")), encoding="utf-8")
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
        self.assertEqual(loaded, [])

    def test_skips_wrong_types_in_optional_fields(self) -> None:
        """書き間違いでデプロイが止まらないよう、任意の項目も型が違えば特集ごと飛ばす。"""
        broken = [
            _feature("links-int", links=1),
            _feature("links-item", links=["/prefectures/okinawa/"]),
            _feature("link-href", links=[{"text": "県", "href": 1}]),
            _feature("prefecture-list", prefecture=["沖縄県"]),
            _feature("lead-number", lead=1),
            _feature("note-list", manholes=[{"id": "488", "note": ["西海岸"]}]),
            _feature("sections-str", sections="本文"),
            _feature("section-empty", sections=[{"heading": "見出し", "body": ""}]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(Path(tmp), *broken, _feature("ok"))
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
            self.assertEqual([f["slug"] for f in loaded], ["ok"])
            # 残った特集はページまで描ける
            MODULE.generate_all(list(RECORDS.values()), {}, Path(tmp) / "dist", d)

    def test_highlight_ends_after_its_day(self) -> None:
        features = [_feature()]
        self.assertEqual(len(FEATURES.highlighted(features, date(2027, 1, 31))), 1)
        self.assertEqual(FEATURES.highlighted(features, date(2027, 2, 1)), [])
        self.assertEqual(FEATURES.highlighted([_feature(highlight_until=None)], date(2026, 10, 17)), [])

    def test_unsafe_links_are_dropped(self) -> None:
        links = FEATURES.safe_links(_feature(links=[
            {"text": "県", "href": "/prefectures/okinawa/"},
            {"text": "x", "href": "javascript:alert(1)"},
            {"text": "x", "href": "//evil.example/"},
            {"text": "公式", "href": "https://example.com/"},
        ]))
        self.assertEqual([link["text"] for link in links], ["県", "公式"])


class FeaturePageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feature = {**_feature(), "records": [RECORDS["488"], RECORDS["487"]]}

    def test_page_lists_manholes_with_preinstall_note(self) -> None:
        html = MODULE.build_feature_page(self.feature, {}, [])
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/features/okinawa-test/">', html)
        self.assertIn("2026年10月下旬頃に設置予定。", html)
        self.assertLess(html.index('href="/manholes/488/"'), html.index('href="/manholes/487/"'))
        self.assertIn('id="prefecture-map"', html)
        self.assertNotIn('data-track="prefecture_', html)
        self.assertIn("PokefutaAnalytics.bindClickTracking(", html)

    def test_sections_are_split_into_paragraphs(self) -> None:
        feature = {**self.feature, "sections": [{"heading": "行き方", "body": "飛行機で1時間。\n\n船は<15時間>。"}]}
        html = MODULE.build_feature_page(feature, {}, [])
        self.assertIn('<h2 id="section-1-heading">行き方</h2>', html)
        self.assertIn("<p>飛行機で1時間。</p>", html)
        self.assertIn("<p>船は&lt;15時間&gt;。</p>", html)
        self.assertLess(html.index('id="notes-heading"'), html.index('id="section-1-heading"'))

    def test_generate_all_writes_index_and_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "src"
            d.mkdir()
            _write(d, _feature())
            out = Path(tmp) / "dist"
            written = MODULE.generate_all(list(RECORDS.values()), {}, out, d)
            self.assertEqual([f["slug"] for f in written], ["okinawa-test"])
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="/features/okinawa-test/"', index)
            self.assertTrue((out / "okinawa-test" / "index.html").exists())


class RealFeatureDataTests(unittest.TestCase):
    def test_every_feature_file_loads(self) -> None:
        """dataset/features/ の特集が書式違い・蓋の書き間違いで黙って消えないようにする。"""
        records = {str(r["id"]): r for r in SUMMARY.load_records(SUMMARY.NDJSON)}
        files = sorted(FEATURES.DEFAULT_FEATURES_DIR.glob("*.json"))
        loaded = FEATURES.load_features(records, today=date(2099, 1, 1))
        self.assertEqual(sorted(f["slug"] for f in loaded), sorted(p.stem for p in files))


class SummaryAndSitemapTests(unittest.TestCase):
    def test_summary_shows_highlighted_feature_in_japanese_only(self) -> None:
        feature = {**_feature(), "records": [RECORDS["488"], RECORDS["487"]]}
        ja = SUMMARY._build_features_section(SUMMARY.SUMMARY_STRINGS["ja"], [feature], {})
        self.assertIn('href="/features/okinawa-test/"', ja)
        self.assertIn("2026年10月下旬頃に設置予定。", ja)
        self.assertEqual(SUMMARY._build_features_section(SUMMARY.SUMMARY_STRINGS["en"], [feature], {}), "")

    def test_summary_always_links_to_the_feature_index(self) -> None:
        """highlight_until を過ぎて入口が消えても、/features/ への導線は ja の /summary/ に残す。"""
        records = SUMMARY.load_records(SUMMARY.NDJSON)
        stats = SUMMARY.build_stats(records)
        by_id = {str(r["id"]): r for r in records}
        ja = SUMMARY.render_page(SUMMARY.SUMMARY_STRINGS["ja"], stats, {}, {}, by_id, {}, {})
        self.assertIn('href="/features/"', ja)
        self.assertNotIn('class="summary-section summary-feature"', ja)
        en = SUMMARY.render_page(SUMMARY.SUMMARY_STRINGS["en"], stats, {}, {}, by_id, {}, {})
        self.assertNotIn('href="/features/"', en)

    def test_sitemap_lists_features(self) -> None:
        xml = SITEMAP.build_sitemap(["1"], feature_paths=["/features/okinawa-test/"])
        self.assertIn("<loc>https://data.pokefuta.com/features/</loc>", xml)
        self.assertIn("<loc>https://data.pokefuta.com/features/okinawa-test/</loc>", xml)
        self.assertNotIn("/features/</loc>", SITEMAP.build_sitemap(["1"]))


if __name__ == "__main__":
    unittest.main()
