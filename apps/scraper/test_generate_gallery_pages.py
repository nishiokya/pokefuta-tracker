"""generate_gallery_pages（/gallery/）のテスト。ネットワークを使わない。

Run: python3 -m unittest apps.scraper.test_generate_gallery_pages
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

try:
    from apps.scraper import generate_gallery_pages as gallery
except ModuleNotFoundError:  # apps/scraper から直接実行したとき
    import generate_gallery_pages as gallery

PLUSH_TAGS = {
    "plush": True,
    "plush_score": 0.99,
    "plush_box": [0.5, 0.5, 0.9, 0.9],
    "lid": [0.1, 0.1, 0.5, 0.5],
    "crop": [0.0, 0.0, 0.75, 1.0],
}


def _photo(photo_id, tags=None, **extra):
    return {
        "id": photo_id,
        "manhole_id": 23,
        "is_landscape": False,
        "plush_score": 0.99,
        "created_at": "2026-11-01T15:30:00Z",
        "shot_at": "2026-10-31T16:00:00Z",
        "comment": None,
        "poster_name": "なまえ",
        "poster_public_id": "pub-1",
        "ai_tags": dict(tags or PLUSH_TAGS),
        **extra,
    }


MANHOLES = {"23": {"id": 23, "title": "神奈川県/横浜市", "prefecture": "神奈川県", "city": "横浜", "pokemons": ["ピカチュウ", "イーブイ", "ラプラス", "カビゴン"]}}


class BoxZoomTest(unittest.TestCase):
    """写真館の photoBoxZoom（src/lib/photo-ai-tags.ts）と同じ値になること。"""

    def test_matches_the_photo_site(self):
        # 写真館の photoBoxZoom に同じ入力を渡した結果（2026-11-23 に tsx で実行して写した）
        cases = [
            (PLUSH_TAGS, PLUSH_TAGS["lid"], 1.04, ("240.4%", "180.3%", "-22.1%", "-4.1%")),
            (PLUSH_TAGS, PLUSH_TAGS["plush_box"], 1.12, ("223.2%", "167.4%", "-106.2%", "-67.2%")),
            ({"crop": [0.125, 0.0, 0.875, 1.0]}, [0.9, 0.8, 1.0, 1.0], 1.12, ("400%", "300%", "-300%", "-200%")),
        ]
        for tags, box, pad, (width, height, left, top) in cases:
            with self.subTest(box=box):
                self.assertEqual(
                    gallery.box_zoom_style(tags, box, pad),
                    f"position:absolute;width:{width};height:{height};left:{left};top:{top};max-width:none",
                )

    def test_box_is_clamped_inside_the_photo(self):
        tags = {**PLUSH_TAGS, "crop": [0.125, 0.0, 0.875, 1.0]}  # 横長 4:3
        style = gallery.box_zoom_style(tags, [0.9, 0.8, 1.0, 1.0], 1.12)
        left = float(re.search(r"left:(-?[\d.]+)%", style).group(1))
        width = float(re.search(r"width:([\d.]+)%", style).group(1))
        # 写真の右端を越えない（left + width >= 100%）
        self.assertGreaterEqual(left + width, 100 - 0.1)

    def test_needs_crop_and_both_boxes(self):
        self.assertIsNone(gallery.box_zoom_style({}, [0.1, 0.1, 0.2, 0.2], 1.1))
        self.assertIsNone(gallery.plush_clips({k: v for k, v in PLUSH_TAGS.items() if k != "plush_box"}))
        self.assertIsNone(gallery.plush_clips({**PLUSH_TAGS, "lid": [0.5, 0.5, 0.4, 0.6]}))
        self.assertIsNotNone(gallery.plush_clips(PLUSH_TAGS))


class CardTest(unittest.TestCase):
    def _card(self, photo, media=gallery.plush_media):
        return gallery.photo_card(photo, 0, MANHOLES, media, "plush")

    def test_links_photo_and_poster_to_the_photo_site_and_manhole_to_the_dex(self):
        html = self._card(_photo("p1"))
        self.assertIn('href="https://pokefuta.com/p/p1?from=data"', html)
        self.assertIn('href="https://pokefuta.com/users/pub-1/visits?from=data"', html)
        self.assertIn('href="/manholes/23/"', html)
        self.assertIn('src="https://pokefuta.com/api/photo/p1?size=small"', html)

    def test_shows_three_pokemon_and_the_jst_shot_date(self):
        html = self._card(_photo("p1"))
        self.assertIn("<span>ラプラス</span>", html)
        self.assertNotIn("カビゴン", html)
        # 2026-10-31T16:00Z は JST で 11月1日
        self.assertIn('<time datetime="2026-11-01">2026年11月1日</time>', html)

    def test_anonymous_poster_is_not_linked(self):
        html = self._card(_photo("p1", poster_name=None, poster_public_id=None))
        self.assertIn("名無しのトレーナー", html)
        self.assertNotIn("/users/", html)

    def test_escapes_user_text(self):
        html = self._card(_photo("p1", comment='<script>alert("x")</script>', poster_name="<b>"))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<b>", html.replace("<b>ポケふたラボ", ""))

    def test_landscape_badge_and_unknown_manhole(self):
        html = gallery.photo_card(_photo("p1", manhole_id=999, is_landscape=True), 0, MANHOLES, gallery.snow_media, "snow")
        self.assertIn("周辺の風景", html)
        self.assertNotIn("/manholes/999/", html)

    def test_plush_without_boxes_falls_back_to_the_whole_photo(self):
        html = self._card(_photo("p1", tags={"plush": True}))
        self.assertIn("gl-media--whole", html)

    def test_lazy_after_the_first_rows(self):
        self.assertIn('loading="eager"', gallery.snow_media(_photo("p1"), 0))
        self.assertIn('loading="lazy"', gallery.snow_media(_photo("p1"), gallery.EAGER_COUNT))


class GenerateTest(unittest.TestCase):
    def _generate(self, payload):
        tmp = Path(tempfile.mkdtemp())
        tagged = tmp / "tagged.json"
        tagged.write_text(json.dumps(payload) if isinstance(payload, dict) else payload, encoding="utf-8")
        manholes = tmp / "pokefuta.ndjson"
        manholes.write_text(json.dumps(MANHOLES["23"], ensure_ascii=False) + "\n", encoding="utf-8")
        counts = gallery.generate(tagged, manholes, tmp / "gallery")
        pages = {
            key: (tmp / "gallery" / key / "index.html").read_text(encoding="utf-8")
            for key in ("", "plush", "snow")
        }
        return counts, pages

    def test_writes_index_and_both_features(self):
        payload = {
            "success": True,
            "generated_at": "2026-11-23T00:00:00Z",
            "limit": 2,
            "features": {
                "plush": {"total": 5, "photos": [_photo("p1"), _photo("p2")]},
                "snow": {"total": 1, "photos": [_photo("s1", tags={"snow": True})]},
            },
        }
        counts, pages = self._generate(payload)
        self.assertEqual(counts, {"plush": 2, "snow": 1})
        self.assertIn('href="/gallery/plush/"', pages[""])
        self.assertIn('href="/gallery/snow/"', pages[""])
        self.assertIn("写真2枚を見る", pages[""])
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/gallery/plush/">', pages["plush"])
        self.assertIn('content="index,follow', pages["plush"])
        self.assertIn("（新しい2枚まで）", pages["plush"])
        self.assertNotIn("まで）", pages["snow"])
        self.assertEqual(pages["plush"].count('class="gl-card"'), 2)
        self.assertIn("gl-media--whole", pages["snow"])
        for page in pages.values():
            for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
                json.loads(block)

    def test_missing_or_failed_data_still_writes_empty_pages(self):
        for payload in ("{broken", {"success": False, "features": {"plush": {"photos": [_photo("p1")]}}}):
            with self.subTest(payload=str(payload)[:20]):
                counts, pages = self._generate(payload)
                self.assertEqual(counts, {"plush": 0, "snow": 0})
                self.assertIn("まだ写真がありません", pages["plush"])
                self.assertNotIn('class="gl-card"', pages["plush"])


if __name__ == "__main__":
    unittest.main()
