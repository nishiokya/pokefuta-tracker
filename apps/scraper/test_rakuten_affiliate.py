from __future__ import annotations

import unittest

from apps.scraper import generate_prefecture_pages as PREF
from apps.scraper import rakuten_affiliate as MODULE


class RakutenAffiliateTest(unittest.TestCase):
    def test_car_url_covers_every_prefecture(self) -> None:
        for slug in PREF.PREFECTURE_SLUGS.values():
            self.assertNotEqual(MODULE.CAR_TOP_URL, MODULE.car_url(slug), slug)
        self.assertEqual("https://travel.rakuten.co.jp/cars/area/okinawa/", MODULE.car_url("okinawa"))
        self.assertEqual(
            "https://cars.travel.rakuten.co.jp/cars/area/kinki/shiga/", MODULE.car_url("shiga")
        )

    def test_link_wraps_the_target_with_the_affiliate_id(self) -> None:
        self.assertEqual(
            "https://hb.afl.rakuten.co.jp/hgc/59e54b6b.42820fd9.59e54b6c.866c5f88/_RTLink159064"
            "?pc=https%3A%2F%2Ftravel.rakuten.co.jp%2Fyado%2Fshiga%2F" + MODULE.LINK_SUFFIX,
            MODULE.link(MODULE.hotel_url("shiga")),
        )

    def test_block_is_labelled_as_an_ad_and_escapes_ampersands(self) -> None:
        html = MODULE.block_html("x", event="e", surface="s", prefecture="滋賀県", pref_slug="shiga")
        self.assertIn('aria-label="広告"', html)
        self.assertIn("広告・楽天トラベル", html)
        self.assertEqual(2, html.count('rel="nofollow sponsored noopener"'))
        self.assertIn("&amp;link_type=text", html)
        self.assertNotIn("&link_type", html)
        self.assertIn("滋賀県の宿を探す", html)
        self.assertIn("滋賀県のレンタカーを探す", html)


if __name__ == "__main__":
    unittest.main()
