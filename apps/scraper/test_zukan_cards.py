"""Cross-page rendering contracts: changing one card component reaches every hub."""

import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
import tinycss2

from apps.scraper import generate_municipality_pages as muni
from apps.scraper import generate_pokemon_index_page as pokemon
from apps.scraper import generate_prefecture_pages as pref
from apps.scraper import generate_summary_pages as summary
from apps.scraper import generate_top_page as top
from apps.scraper.zukan_cards import CARD_CSS, card_image, card_open

CARD_SURFACE = {"background", "background-color", "border", "border-radius", "box-shadow"}
IMAGE_SHAPE = {"aspect-ratio", "object-fit"}
PSEUDO_CLASS = re.compile(r"(?<!:):[a-zA-Z-]+(\((?:[^()]|\([^()]*\))*\))?")


def render_hubs(image_dir: Path) -> dict[str, str]:
    """Small synthetic dataset, also usable for browser checks without private data."""
    records = [
        {"id": str(i), "prefecture": "東京都", "city": city,
         "address": f"東京都{city}市1-1", "title": f"東京都/{city}市",
         "lat": 35.5 + i / 100, "lng": 139.4, "status": "active", "installed": True,
         "pokemons": ["ピカチュウ"], "tags": ["roadside"]}
        for i, city in enumerate(["町田", "町田", "町田", "八王子"], 1)
    ]
    photos = {str(i): {"manhole_id": i, "url": "https://example.com/photo.jpeg",
                      "created_at": "2026-01-01T00:00:00Z"} for i in range(1, 5)}
    metadata = {"names": {"ja": "ピカチュウ", "en": "Pikachu"}, "generation": 1}
    municipalities = muni.build_municipalities(records, {"東京都/町田市": "machida"})
    with patch.object(summary, "IMAGE_DIR", image_dir):
        summary_html = summary.render_page(
            summary.SUMMARY_STRINGS["ja"], summary.build_stats(records), {}, {},
            {r["id"]: r for r in records}, {"photos": photos}, {},
        )
    return {
        "pokemon": pokemon.generate_html(
            {"pikachu": (metadata, records)}, "ja", pokemon.LANG_CONFIGS["ja"],
            pokemon.LP_INDEX_STRINGS["ja"], lambda name: name, {"photos": photos}, image_dir,
        ),
        "prefectures": pref.build_index_page({"東京都": records}, photos=photos),
        "municipalities": muni.build_ranking_page(municipalities, 4, "2026-01-01", image_dir=image_dir),
        "summary": summary_html,
    }


class SharedCardsTest(unittest.TestCase):
    def test_all_hubs_render_shared_cards_and_square_images(self):
        with tempfile.TemporaryDirectory() as directory:
            image_dir = Path(directory)
            for i in range(1, 5):
                for suffix in ("lid", "latest"):
                    (image_dir / f"{i}_{suffix}.jpeg").touch()
            pages = render_hubs(image_dir)
        for name, html in pages.items():
            with self.subTest(page=name):
                soup = BeautifulSoup(html, "html.parser")
                self.assertIn(CARD_CSS, html)
                cards = soup.select("[data-zukan-card]")
                self.assertTrue(cards)
                images = soup.select("[data-zukan-card] img[data-zukan-image]")
                self.assertTrue(images)
                for image in images:
                    self.assertEqual(image["width"], image["height"])
                    self.assertEqual(image["loading"], "lazy")
                    self.assertEqual(image["decoding"], "async")
                # Gallery and theme cards have independent links, never nested anchors.
                self.assertFalse(soup.select("a a"))
                # The old bug: a page could redefine a shared surface later in
                # its stylesheet. Reject competing rules, including media rules.
                def check_rules(rules):
                    for rule in rules:
                        if rule.type == "at-rule" and rule.content:
                            check_rules(tinycss2.parse_rule_list(rule.content))
                        if rule.type != "qualified-rule":
                            continue
                        selector = tinycss2.serialize(rule.prelude).strip()
                        # Pseudo-elements style generated boxes, not the card itself.
                        if "[data-zukan-card]" in selector or "[data-zukan-image]" in selector or "::" in selector:
                            continue
                        # Match :hover / :not(...) rules against the element they can override.
                        matchable = PSEUDO_CLASS.sub("", selector)
                        if not matchable.strip(", "):
                            continue
                        matched = soup.select(matchable)
                        declarations = {
                            d.lower_name: tinycss2.serialize(d.value).strip()
                            for d in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True)
                            if d.type == "declaration"
                        }
                        if any(el.has_attr("data-zukan-card") for el in matched):
                            self.assertFalse(declarations.keys() & CARD_SURFACE, selector)
                        if any(el.has_attr("data-zukan-image") for el in matched):
                            self.assertFalse(declarations.keys() & IMAGE_SHAPE, selector)
                            # Small thumbnails may resize, but only as squares.
                            if "height" in declarations:
                                self.assertEqual(declarations["height"], declarations.get("width"), selector)
                for style in soup.select("style"):
                    check_rules(tinycss2.parse_stylesheet(style.get_text()))
        self.assertIn('data-track="pokemon_index_ranking_click"', pages["pokemon"])
        self.assertIn('data-track="prefectures_index_detail_click"', pages["prefectures"])
        self.assertIn('href="/municipalities/tokyo/machida/"', pages["municipalities"])
        self.assertIn('data-summary-event="summary_discovery_detail_click"', pages["summary"])
        self.assertIn('/manhole/image/1_lid.jpeg', pages["summary"])

    def test_shared_image_rule_keeps_lids_square(self):
        # width/height attributes only reserve space; the rendered shape comes from CSS.
        rules = [r for r in tinycss2.parse_stylesheet(CARD_CSS, skip_whitespace=True)
                 if r.type == "qualified-rule" and tinycss2.serialize(r.prelude).strip() == "[data-zukan-image]"]
        self.assertEqual(len(rules), 1)
        declarations = {
            d.lower_name: tinycss2.serialize(d.value).strip()
            for d in tinycss2.parse_declaration_list(rules[0].content, skip_whitespace=True)
            if d.type == "declaration"
        }
        self.assertEqual(declarations.get("aspect-ratio"), "1")
        self.assertEqual(declarations.get("object-fit"), "cover")
        self.assertEqual(declarations.get("height"), "auto")

    def test_card_attributes_are_escaped(self):
        html = card_open('test', href='/path/?q="<&', attrs={"data-destination": '"<&'})
        html += card_image('/image/"<&', alt='"<&') + '</a>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(soup.a["href"], '/path/?q="<&')
        self.assertEqual(soup.img["alt"], '"<&')
        self.assertEqual(len(soup.a.attrs), 4)

    def test_summary_image_fallback_and_no_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            image_dir = Path(directory)
            (image_dir / "1_latest.jpeg").touch()
            self.assertIn('/manhole/image/1_latest.jpeg', render_hubs(image_dir)["summary"])
            (image_dir / "1_latest.jpeg").unlink()
            html = render_hubs(image_dir)["summary"]
            soup = BeautifulSoup(html, "html.parser")
            self.assertFalse(soup.select(".discovery-hub-card img"))
            self.assertTrue(soup.select('.discovery-hub-card a[href="/manholes/1/"]'))


class EventClassificationTest(unittest.TestCase):
    def test_news_excluded_from_event_hubs_but_preserved_for_prefectures(self):
        base = {"prefecture": "東京都", "url": "https://example.com/event",
                "start_date": "2020-01-01", "end_date": "2099-12-31"}
        events = [
            dict(base, title="新設発表", kind="news"),
            dict(base, title="謎解き"),
            dict(base, title="ステッカーキャンペーン"),
            dict(base, title="スタンプラリー"),
            dict(base, title="終了", end_date="2020-01-02"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            path.write_text(json.dumps(events), encoding="utf-8")
            expected = {"謎解き", "ステッカーキャンペーン", "スタンプラリー"}
            self.assertEqual({e["title"] for e in top.load_events(path, date.today())}, expected)
            selected = summary._load_prefecture_events(path)
            self.assertEqual({e["title"] for e in selected}, expected)
            self.assertIn("新設発表", {e["title"] for e in pref.load_events(path)["東京都"]})
            for strings in summary.SUMMARY_STRINGS.values():
                html = summary._build_events_section(strings, selected, lambda name: name)
                self.assertNotIn("新設発表", html)
                for title in expected:
                    self.assertIn(title, html)

    def test_translated_top_filters_news_in_browser(self):
        # 多言語版トップは api/prefecture_events.json をブラウザで読むので、同じ条件を JS 側にも置く
        template = (Path(__file__).parents[1] / "web" / "index.template.html").read_text(encoding="utf-8")
        self.assertIn("e.kind !== 'news'", template)


if __name__ == "__main__":
    unittest.main()
