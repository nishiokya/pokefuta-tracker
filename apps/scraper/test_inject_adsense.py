from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("inject_adsense.py")
SPEC = importlib.util.spec_from_file_location("inject_adsense", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class InjectAdsenseTest(unittest.TestCase):
    def test_normalizes_publisher_id(self) -> None:
        self.assertEqual(
            ("pub-1234567890123456", "ca-pub-1234567890123456"),
            MODULE.normalize_publisher_id("ca-pub-1234567890123456"),
        )
        with self.assertRaises(ValueError):
            MODULE.normalize_publisher_id("pub-123")

    def test_verification_meta_does_not_load_ads_without_slot(self) -> None:
        html = "<html><head></head><body><!-- adsense:prefecture --></body></html>"
        result = MODULE.inject_html(html, "ca-pub-1234567890123456")
        self.assertIn('name="google-adsense-account"', result)
        self.assertNotIn("pagead2.googlesyndication.com", result)
        self.assertNotIn('class="ad-slot ', result)

    def test_explicit_slot_loads_one_responsive_ad(self) -> None:
        html = "<html><head></head><body><!-- adsense:prefecture --></body></html>"
        result = MODULE.inject_html(
            html,
            "ca-pub-1234567890123456",
            prefecture_slot="1234567890",
        )
        self.assertEqual(1, result.count("pagead2.googlesyndication.com"))
        self.assertEqual(1, result.count('class="ad-slot ad-slot--prefecture"'))
        self.assertIn('data-ad-slot="1234567890"', result)
        self.assertIn('href="/assets/adsense.css"', result)
        self.assertIn('aria-label="広告"', result)
        self.assertIn("width: 320px; height: 100px", result)
        self.assertIn("width: 728px; height: 90px", result)
        self.assertNotIn("data-full-width-responsive", result)
        self.assertNotIn('data-ad-format="auto"', result)

    def test_configure_writes_ads_txt_and_keeps_top_ad_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<html><head></head><body>top</body></html>", encoding="utf-8")
            (root / "prefecture.html").write_text(
                "<html><head></head><body><!-- adsense:prefecture --></body></html>",
                encoding="utf-8",
            )
            updated, ad_pages = MODULE.configure(
                root, "pub-1234567890123456", "1234567890", "",
            )
            self.assertEqual(2, updated)
            self.assertEqual(1, ad_pages)
            self.assertNotIn("pagead2", (root / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(
                "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n",
                (root / "ads.txt").read_text(encoding="utf-8"),
            )
