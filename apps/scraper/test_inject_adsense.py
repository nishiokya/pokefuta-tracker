from __future__ import annotations

import importlib.util
import re
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
        self.assertIn("width: 300px; height: 250px", result)
        self.assertIn("width: 728px; height: 90px", result)
        self.assertNotIn("data-full-width-responsive", result)
        self.assertNotIn('data-ad-format="auto"', result)

    def test_narrow_screens_get_a_rectangle_not_a_banner(self) -> None:
        """モバイルをバナーに固定し直さないこと。

        AdSense実測（2026-08-21〜09-19）では 320x100 が全表示回数の40%を
        占めながらインプレッション収益 ¥15 で全サイズ中の最下位だった
        （728x90 は ¥48、970x90 は ¥130）。アクセスの71%がモバイルなので、
        ここをバナーに戻すと収益の一番大きい取りこぼしが再発する。
        """
        html = "<html><head></head><body><!-- adsense:manhole --></body></html>"
        result = MODULE.inject_html(
            html, "ca-pub-1234567890123456", manhole_slot="1234567890",
        )
        for banner in ("height: 100px", "height: 60px", "height: 50px"):
            with self.subTest(banner=banner):
                self.assertNotIn(banner, result)

    def test_reserved_height_matches_the_injected_ad_height(self) -> None:
        """adsense.css の min-height が広告本体の高さと揃っていること。

        本体の寸法は inject_adsense.py が head に直書きし、枠の予約高さは
        apps/web/assets/adsense.css にある。2ファイルに分かれているので、
        片方だけ変えるとレイアウトシフトが無言で復活する
        （AGENTS.md「広告枠はレイアウトシフトを起こさないよう表示領域を予約」）。
        """
        html = "<html><head></head><body><!-- adsense:prefecture --></body></html>"
        result = MODULE.inject_html(
            html, "ca-pub-1234567890123456", prefecture_slot="1234567890",
        )
        stylesheet = (
            Path(__file__).resolve().parents[1] / "web" / "assets" / "adsense.css"
        ).read_text(encoding="utf-8")

        ad_heights = [int(v) for v in re.findall(r"height: (\d+)px", result)]
        reserved = [int(v) for v in re.findall(r"min-height: (\d+)px", stylesheet)]
        self.assertEqual(3, len(ad_heights), result)
        self.assertEqual(3, len(reserved), stylesheet)
        # ラベル用の padding 20px + 下 6px を足した値が予約高さ
        self.assertEqual([h + 26 for h in ad_heights], reserved)

    def test_configure_writes_ads_txt_and_keeps_top_ad_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                "<html><head></head><body><!-- adsense:home --></body></html>",
                encoding="utf-8",
            )
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


    def test_home_slot_is_between_gallery_and_events_on_japanese_top_only(self) -> None:
        web = MODULE_PATH.resolve().parents[1] / "web"
        index = (web / "index.html").read_text(encoding="utf-8")
        client = "ca-pub-1234567890123456"
        slot = "9876543210"
        result = MODULE.inject_html(index, client, home_slot=slot)
        self.assertEqual(1, result.count('class="ad-slot ad-slot--home"'))
        self.assertEqual(1, result.count('adsbygoogle.js?client='))
        self.assertIn(f'data-ad-slot="{slot}"', result)
        self.assertLess(result.index("<!-- home:gallery:end -->"), result.index('ad-slot--home"'))
        self.assertLess(result.index('ad-slot--home"'), result.index("<!-- home:events:start -->"))
        self.assertNotIn("<!-- adsense:home -->", result)
        self.assertEqual(result, MODULE.inject_html(result, client, home_slot=slot))

        english = (web / "index.en.html").read_text(encoding="utf-8")
        self.assertNotIn("adsbygoogle.js", MODULE.inject_html(english, client, home_slot=slot))

    def test_configure_validates_home_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "ADSENSE_HOME_SLOT"):
                MODULE.configure(Path(directory), "pub-1234567890123456", "", "", home_slot="invalid")
