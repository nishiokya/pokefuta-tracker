"""図鑑トップ（index.html）の生成ブロックの検査。

件数・都道府県一覧・写真・構造化データが生成時データから静的HTMLへ入ること、
写真はローカルミラーだけを使い、ファーストビュー外は遅延読み込みになることを見る。
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
import unittest.mock
from datetime import date
from pathlib import Path

from apps.scraper import generate_top_page as module

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "apps" / "web" / "index.html"
TODAY = date(2026, 9, 26)

SHELL = """<html><head>
  <!-- home:head:start -->
  <!-- home:head:end -->
</head><body><main>
    <!-- home:hero:start -->
    <!-- home:hero:end -->
    <!-- home:ways:start -->
    <!-- home:ways:end -->
    <!-- home:newrelease:start -->
    <!-- home:newrelease:end -->
    <!-- home:photos:start -->
    <!-- home:photos:end -->
    <!-- home:events:start -->
    <!-- home:events:end -->
    <!-- home:pref:start -->
    <!-- home:pref:end -->
    <!-- home:pokemon:start -->
    <!-- home:pokemon:end -->
          <!-- tag-chips:start -->
          <a class="hub-chip" href="/tags/roadside/">keep</a>
          <!-- tag-chips:end -->
</main></body></html>
"""

# 7地方にまたがる10県・各2枚
PREFS = ["北海道", "宮城県", "東京都", "新潟県", "京都府", "鳥取県", "香川県", "福岡県", "沖縄県", "大阪府"]


def _records() -> list[dict]:
    records = []
    for i, pref in enumerate(PREFS):
        for j in range(2):
            mid = str(i * 2 + j + 1)
            records.append({
                "id": mid, "prefecture": pref, "city": "テスト", "status": "active",
                "pokemons": ["ピカチュウ"] if j == 0 else ["ラプラス", "ローカルActs"],
                "added_at": "2025-01-01T00:00:00Z", "address": f"{pref}テスト市1-1",
            })
    return records


class Fixture:
    def __init__(self, tmp: Path, *, photos: bool = True, events: list[dict] | None = None,
                 records: list[dict] | None = None) -> None:
        self.records = records or _records()
        self.manholes = tmp / "pokefuta.ndjson"
        self.manholes.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in self.records), encoding="utf-8")
        self.image_dir = tmp / "image"
        self.image_dir.mkdir(exist_ok=True)
        photo_map = {}
        if photos:
            for n, record in enumerate(self.records):
                (self.image_dir / f"{record['id']}_latest.jpeg").write_bytes(b"x")
                photo_map[record["id"]] = {
                    "manhole_id": int(record["id"]),
                    "created_at": f"2026-09-{(n % 25) + 1:02d}T01:00:00+00:00",
                }
        self.photos = tmp / "photos.json"
        self.photos.write_text(json.dumps({"photos": photo_map}), encoding="utf-8")
        self.stats = tmp / "stats.json"
        self.stats.write_text(json.dumps({"posts": 1234, "manholes_with_photos": 15}), encoding="utf-8")
        self.events = tmp / "events.json"
        self.events.write_text(json.dumps(events or [], ensure_ascii=False), encoding="utf-8")
        self.metadata = tmp / "meta.json"
        self.metadata.write_text(json.dumps([
            {"slug": "pikachu", "form": None, "names": {"ja": "ピカチュウ"}},
            {"slug": "lapras", "form": None, "names": {"ja": "ラプラス"}},
        ], ensure_ascii=False), encoding="utf-8")

    def data(self, today: date = TODAY) -> module.TopData:
        return module.load_data(
            self.manholes, self.photos, self.stats, self.events, self.image_dir,
            today=today, pokemon_metadata=self.metadata,
        )

    def html(self, today: date = TODAY) -> str:
        return module.apply_blocks(SHELL, self.data(today))


def _block(html: str, name: str) -> str:
    match = re.search(rf"<!-- home:{name}:start -->(.*?)<!-- home:{name}:end -->", html, re.DOTALL)
    return match.group(1) if match else ""


def _json_ld(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL).group(1))


def _event(pref: str, title: str, start: str, end: str) -> dict:
    return {"prefecture": pref, "title": title, "start_date": start, "end_date": end, "url": "https://example.com/"}


class GeneratedHtmlTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_description_uses_real_prefecture_and_manhole_counts(self) -> None:
        html = Fixture(self.tmp).html()
        head = _block(html, "head")
        self.assertIn("全国10都道府県・20枚のポケふた", head)
        self.assertNotIn("47都道府県", head)
        self.assertIn('property="og:description"', head)
        self.assertIn('name="twitter:description"', head)
        self.assertIn("全国20枚の<wbr>ポケふたを探す</h1>", html)

    def test_json_ld_describes_site_page_prefecture_list_and_breadcrumb(self) -> None:
        graph = {node["@type"]: node for node in _json_ld(Fixture(self.tmp).html())["@graph"]}
        self.assertEqual({"WebSite", "CollectionPage", "ItemList", "BreadcrumbList"}, set(graph))
        self.assertEqual({"@id": "https://data.pokefuta.com/#prefectures"}, graph["CollectionPage"]["mainEntity"])
        items = graph["ItemList"]["itemListElement"]
        self.assertEqual(10, graph["ItemList"]["numberOfItems"])
        self.assertEqual(10, len(items))
        self.assertEqual("https://data.pokefuta.com/prefectures/hokkaido/", items[0]["url"])
        self.assertEqual([1, 2], [items[0]["position"], items[1]["position"]])
        self.assertEqual(graph["CollectionPage"]["description"], module.description(Fixture(self.tmp).data()))

    def test_json_ld_cannot_close_the_script_element(self) -> None:
        records = _records()
        records[0]["prefecture"] = "北海道"
        html = Fixture(self.tmp, records=records).html()
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL).group(1)
        self.assertNotIn("</", ld)

    def test_hero_shows_six_eager_photos_from_distinct_prefectures(self) -> None:
        hero = _block(Fixture(self.tmp).html(), "hero")
        imgs = re.findall(r"<img [^>]+>", hero)
        self.assertEqual(module.HERO_PHOTO_LIMIT, len(imgs))
        self.assertTrue(all('loading="eager"' in img for img in imgs))
        self.assertEqual(1, hero.count('fetchpriority="high"'))
        self.assertIn('fetchpriority="high"', imgs[0])
        prefs = re.findall(r'<span class="home-mosaic__cap"><b>[^<]*</b>(\S+) ', hero)
        self.assertEqual(len(prefs), len(set(prefs)))
        for label in ("現在地・地図から探す", "都道府県から探す", "ポケモンから探す"):
            self.assertIn(label, hero)

    def test_hero_without_photos_falls_back_to_one_column(self) -> None:
        hero = _block(Fixture(self.tmp, photos=False).html(), "hero")
        self.assertIn("home-hero--no-photos", hero)
        self.assertNotIn("<img", hero)
        self.assertNotIn("home-mosaic", hero)

    def test_gallery_is_lazy_and_spread_across_regions(self) -> None:
        html = Fixture(self.tmp).html()
        gallery = _block(html, "photos")
        imgs = re.findall(r"<img [^>]+>", gallery)
        self.assertEqual(module.GALLERY_PHOTO_LIMIT, len(imgs))
        self.assertTrue(all('loading="lazy"' in img and 'decoding="async"' in img for img in imgs))
        hero_ids = set(re.findall(r'href="manholes/(\d+)/"', _block(html, "hero")))
        gallery_ids = re.findall(r'href="manholes/(\d+)/"', gallery)
        self.assertFalse(hero_ids & set(gallery_ids))
        self.assertEqual(len(gallery_ids), len(set(gallery_ids)))
        prefs = re.findall(r'<span class="home-gallery__cap"><b>[^<]*</b><span>(\S+) ', gallery)
        regions = {module.REGION_OF[p] for p in prefs}
        self.assertGreaterEqual(len(regions), 6)
        self.assertIn("https://pokefuta.com/upload?from=data", gallery)

    def test_every_image_is_a_local_mirror_with_size_and_alt(self) -> None:
        html = Fixture(self.tmp).html()
        imgs = re.findall(r"<img [^>]+>", html)
        icons = [img for img in imgs if "home-way__icon" in img]
        photos = [img for img in imgs if img not in icons]
        self.assertEqual(4, len(icons))
        self.assertTrue(all(re.search(r'src="assets/[a-z-]+\.svg" alt=""', img) for img in icons))
        self.assertTrue(photos)
        for img in photos:
            with self.subTest(img=img):
                self.assertRegex(img, r'src="manhole/image/\d+_latest\.jpeg"')
                self.assertIn('width="720"', img)
                self.assertIn('height="720"', img)
                self.assertRegex(img, r'alt="[^"]+"')

    def test_photos_without_local_mirror_are_skipped(self) -> None:
        fixture = Fixture(self.tmp)
        for path in fixture.image_dir.glob("*.jpeg"):
            if path.name != "1_latest.jpeg":
                path.unlink()
        photos = fixture.data().photos
        self.assertEqual(["1"], [p.manhole_id for p in photos])

    def test_events_show_three_then_fold_the_rest_and_drop_finished_ones(self) -> None:
        events = [
            _event("北海道", "終わったイベント", "2026-01-01", "2026-09-25"),
            _event("宮城県", "A", "2026-08-01", "2026-12-31"),
            _event("東京都", "B", "2026-08-01", "2026-10-31"),
            _event("京都府", "C", "2026-10-10", "2027-01-31"),
            _event("福岡県", "D", "2026-07-01", "2027-03-31"),
            _event("不明県", "E", "2026-07-01", "2027-03-31"),
        ]
        block = _block(Fixture(self.tmp, events=events).html(), "events")
        self.assertNotIn("終わったイベント", block)
        self.assertNotIn(">E<", block)
        visible, _, folded = block.partition("<details")
        # 開催中を終了が近い順に、まもなく開催は後ろ
        self.assertEqual(["B", "A", "D"], re.findall(r'home-event__copy"><b>([^<]+)</b>', visible))
        self.assertEqual(["C"], re.findall(r'home-event__copy"><b>([^<]+)</b>', folded))
        self.assertIn("すべて見る（全4件）", block)
        self.assertIn("is-upcoming", folded)
        self.assertIn('data-end="2026-10-31"', visible)
        self.assertIn('href="prefectures/tokyo/"', visible)

    def test_no_events_means_no_section(self) -> None:
        html = Fixture(self.tmp).html()
        self.assertNotIn("home-events", html)
        self.assertEqual("\n    ", _block(html, "events"))

    def test_event_titles_are_escaped(self) -> None:
        events = [_event("東京都", "<script>alert(1)</script>", "2026-08-01", "2026-12-31")]
        block = _block(Fixture(self.tmp, events=events).html(), "events")
        self.assertNotIn("<script>", block)
        self.assertIn("&lt;script&gt;", block)

    def test_prefecture_list_separates_installed_and_empty_prefectures(self) -> None:
        block = _block(Fixture(self.tmp).html(), "pref")
        installed = re.findall(r'<span class="home-pref__name">([^<]+)</span>', block)
        self.assertEqual(10, len(installed))
        self.assertIn("47都道府県のうち10都道府県", block)
        note = re.search(r'<p class="home-pref-note">(.*?)</p>', block).group(1)
        self.assertIn("37県", note)
        self.assertIn('href="prefectures/gunma/"', note)
        self.assertNotIn("北海道", note)
        self.assertIn("2026年9月時点", note)
        self.assertIn("北海道・東北", block)
        self.assertIn('href="prefectures/"', block)

    def test_new_releases_only_appear_when_recent(self) -> None:
        self.assertNotIn("home-newrelease", Fixture(self.tmp).html())
        records = _records()
        records[0]["added_at"] = "2026-09-20T00:00:00Z"
        block = _block(Fixture(self.tmp, records=records).html(), "newrelease")
        self.assertIn("新作ポケふた", block)
        self.assertIn('href="manholes/1/"', block)

    def test_popular_pokemon_follow_the_pokemon_page_index(self) -> None:
        block = _block(Fixture(self.tmp).html(), "pokemon")
        self.assertIn('href="pokemon/pikachu/"', block)
        self.assertIn('href="pokemon/lapras/"', block)
        self.assertIn(">10枚</span>", block)
        self.assertNotIn("ローカルActs", block)
        self.assertIn('href="pokemon/"', block)

    def test_apply_is_idempotent_and_leaves_tag_chips_alone(self) -> None:
        data = Fixture(self.tmp).data()
        once = module.apply_blocks(SHELL, data)
        self.assertEqual(once, module.apply_blocks(once, data))
        self.assertIn('<a class="hub-chip" href="/tags/roadside/">keep</a>', once)

    def test_uninstalled_manholes_are_not_counted(self) -> None:
        """installed: false（設置前）は都道府県ページと同じく件数に入れない。"""
        records = _records()
        records[0]["installed"] = False
        data = Fixture(self.tmp, records=records).data()
        self.assertEqual(19, data.total)
        self.assertNotIn("1", {p.manhole_id for p in data.photos})
        self.assertIn("全国10都道府県・19枚", module.description(data))

    def test_place_does_not_repeat_the_prefecture(self) -> None:
        """表示名が「宮崎県/五ヶ瀬町」形式でも「宮崎県 宮崎県/五ヶ瀬町」にしない。"""
        record = {"id": "9", "prefecture": "宮崎県", "city": "五ヶ瀬", "place_label": "宮崎県/五ヶ瀬町"}
        with unittest.mock.patch.object(module, "compose_display_name", return_value="宮崎県/五ヶ瀬町"):
            self.assertEqual("五ヶ瀬町", module.place_label(record))
        with unittest.mock.patch.object(module, "compose_display_name", return_value="指宿市 指宿駅前"):
            self.assertEqual("指宿市", module.place_label(record))

    def test_photo_datetime_matches_the_jst_date_shown(self) -> None:
        """UTC 15時以降の投稿は JST で翌日。表示と datetime 属性を揃える。"""
        fixture = Fixture(self.tmp)
        photos = json.loads(fixture.photos.read_text(encoding="utf-8"))
        for item in photos["photos"].values():
            item["created_at"] = "2026-09-25T16:00:00+00:00"
        fixture.photos.write_text(json.dumps(photos), encoding="utf-8")
        gallery = _block(fixture.html(), "photos")
        self.assertIn('<time datetime="2026-09-26">9月26日</time>', gallery)
        self.assertNotIn('datetime="2026-09-25"', gallery)

    def test_pokemon_cards_use_different_photos(self) -> None:
        records = _records()
        for record in records:
            record["pokemons"] = ["ピカチュウ", "ラプラス"]
        block = _block(Fixture(self.tmp, records=records).html(), "pokemon")
        srcs = re.findall(r'src="([^"]+)"', block)
        self.assertEqual(2, len(srcs))
        self.assertEqual(2, len(set(srcs)))

    def test_tracking_uses_surface(self) -> None:
        html = Fixture(self.tmp).html()
        self.assertNotRegex(html, r"trackEvent\([^)]*\bsource:")
        self.assertIn("click_hero_photo", html)
        self.assertIn("click_search_way", html)


class CommittedIndexTest(unittest.TestCase):
    """コミット済みの apps/web/index.html（本番は dist 側で生成し直す）。"""

    def setUp(self) -> None:
        self.html = INDEX.read_text(encoding="utf-8")

    def test_every_marker_is_present(self) -> None:
        for name in ["head", *module.RENDERERS]:
            with self.subTest(name=name):
                self.assertIn(f"<!-- home:{name}:start -->", self.html)
                self.assertIn(f"<!-- home:{name}:end -->", self.html)

    def test_no_map_tiles_or_leaflet_on_first_load(self) -> None:
        self.assertNotIn("leaflet", self.html.lower())
        self.assertNotIn("tile.openstreetmap.org", self.html)

    def test_single_h1_and_description(self) -> None:
        self.assertEqual(1, self.html.count("<h1"))
        self.assertEqual(1, self.html.count('<meta name="description"'))
        self.assertIn("top-home.css?v=", self.html)

    def test_regenerating_with_repo_data_keeps_counts_consistent(self) -> None:
        dataset = ROOT / "docs" / "pokefuta.ndjson"
        if not dataset.exists():
            self.skipTest("dataset not available")
        data = module.load_data(today=TODAY)
        html = module.apply_blocks(self.html, data)
        installed = len(data.installed_prefectures)
        self.assertIn(f"全国{installed}都道府県・{data.total}枚", _block(html, "head"))
        self.assertEqual(installed, len(re.findall(r'class="home-pref__name"', html)))
        self.assertEqual(47 - installed, len(re.findall(r'<a href="prefectures/[a-z]+/">', _block(html, "pref"))))


if __name__ == "__main__":
    unittest.main()
