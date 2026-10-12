import importlib.util
import json
import re
import unittest
from datetime import date, timedelta
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_summary_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_summary_pages", MODULE_PATH)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(summary)


class DiscoveryHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [
            record
            for record in summary.load_records(summary.NDJSON)
            if record.get("status", "active") == "active"
        ]
        cls.records_by_id = {str(record["id"]): record for record in cls.records}
        cls.metadata = summary.load_pokemon_metadata_with_slugs(summary.POKEMON_METADATA_JSON)

    def test_summary_hubs_exist_in_every_language(self):
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary._build_discovery_hub_sections(
                    strings, self.records_by_id, self.metadata
                )
                self.assertIn('id="travel-discovery"', html)
                self.assertIn('id="rare-discovery"', html)
                self.assertGreaterEqual(html.count("discovery-hub-card"), 9)
                self.assertIn('data-destination-hub="manhole_detail"', html)

    def test_travel_counts_match_title_data(self):
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], self.records_by_id, self.metadata
        )
        for key in (
            "remote_island",
            "roadside",
            "station_front",
            "world_heritage",
            "near_gundam_manhole",
            "gundam_manhole_city",
        ):
            # 枚数は titles ではなく tags を数える（SA・PAは roadside タグだが称号は service_area）
            count = sum(key in (record.get("tags") or []) for record in self.records)
            self.assertIn(f">{count}枚</strong>", html)

    def test_gundam_hubs_use_tag_data(self):
        """旅のテーマカードの枚数は `tags` を数える。

        以前は `titles` を見ていて、同じテーマでも地図・トップ・/tags/ と
        件数が食い違っていた（離島 28 と 30）。ソースを揃えた。
        """
        records = {
            "66": {
                "id": "66",
                "prefecture": "北海道",
                "city": "天塩町",
                "pokemons": ["ロコン"],
                "tags": ["near_gundam_manhole", "gundam_manhole_city"],
            },
            "67": {
                "id": "67",
                "prefecture": "北海道",
                "city": "稚内市",
                "pokemons": ["アローラロコン"],
                "tags": ["gundam_manhole_city"],
            },
        }
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], records, self.metadata
        )
        self.assertIn("ガンダムマンホールまで約500m以内", html)
        self.assertIn("ガンダムマンホールのあるまち", html)
        self.assertIn('data-content-id="near_gundam_manhole"', html)
        self.assertIn('data-content-id="gundam_manhole_city"', html)
        self.assertIn(">1枚</strong>", html)
        self.assertIn(">2枚</strong>", html)

    def test_gundam_crossover_prioritizes_experience_over_distance(self):
        spots = [
            {
                "rank": 1,
                "pokefuta_id": "66",
                "headline": "ロコンとドムを同時回収できる町",
                "story": "2つの公式マンホールコンテンツを一度に巡れます。",
                "proximity_label": "同じ道の駅・入口の反対側・徒歩10秒",
                "onsite_tip": "入口の反対側も確認。見落とし注意です。",
                "experience_tags": ["同じ道の駅", "入口の反対側", "徒歩10秒"],
            }
        ]
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], self.records_by_id, self.metadata, spots
        )
        self.assertIn("一緒に巡れるスポット 第1位", html)
        self.assertIn("ロコンとドムを同時回収できる町", html)
        self.assertIn("入口の反対側・徒歩10秒", html)
        self.assertIn("現地メモ:", html)
        self.assertNotIn("ガンダムマンホールまで約500m以内", html)

    def test_gundam_official_url_is_attribute_escaped(self):
        spots = [
            {
                "rank": 1,
                "pokefuta_id": "66",
                "headline": "テスト",
                "gundam_official_url": 'https://example.com/" onclick="alert(1)',
            }
        ]
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], self.records_by_id, self.metadata, spots
        )
        self.assertIn(
            'href="https://example.com/&quot; onclick=&quot;alert(1)"',
            html,
        )
        self.assertNotIn('href="https://example.com/" onclick="alert(1)"', html)

    def test_non_https_gundam_official_url_is_omitted(self):
        spots = [
            {
                "rank": 1,
                "pokefuta_id": "66",
                "headline": "テスト",
                "gundam_official_url": "javascript:alert(1)",
            }
        ]
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], self.records_by_id, self.metadata, spots
        )
        self.assertNotIn("javascript:", html)
        self.assertNotIn("ガンダムマンホール公式を見る", html)

    def test_hero_uses_popup_and_summary_hubs(self):
        # ヒーローとポップアップも 96653ca で map 側に移った。手編集の
        # map.html と、多言語のもとになる map.template.html の両方を見て、
        # 片方だけ直して食い違う事故を防ぐ。
        for filename in ("map.html", "map.template.html"):
            with self.subTest(filename=filename):
                self._assert_hero_wiring(
                    (summary.ROOT / "apps/web" / filename).read_text(encoding="utf-8")
                )

    def _assert_hero_wiring(self, source: str) -> None:
        self.assertIn("click_hero_new_photo", source)
        self.assertIn("openManholePopup(recommendation.manhole.id)", source)
        self.assertIn("'travel-discovery'", source)
        self.assertIn("'rare-discovery'", source)
        self.assertIn("destination_hub: recommendation.destinationHub", source)
        self.assertIn("getDailyRotationIndex", source)
        self.assertIn("getHeroThemeCount(themeKey)", source)
        self.assertIn("getUniqueHeroPokemon(manhole)", source)
        self.assertIn("window.I18N?.intlLocale || 'ja-JP'", source)
        self.assertIn("const pokemonMetadataPromise = loadPokemonMetadata();", source)
        self.assertIn("marker.setPopupContent(buildPokefutaPopup(marker.pokefutaData))", source)
        self.assertNotIn("await loadPokemonMetadata();", source)
        self.assertNotIn("countTemplate.replace('{count}', candidates.length)", source)
        self.assertNotIn("pokemon: reason", source)

    def test_map_theme_directory_features_nearby_gundam_manholes(self):
        # テーマ絞り込みは 96653ca でトップから map.html に分離された。
        # 定義は dataset/tag_meta.json に集約したので、顔ぶれとラベルはそちらで見る
        # （地図・トップ・/tags/・/summary/ が別々の手書きリストを持っていた名残）。
        meta = json.loads(
            (summary.ROOT / "dataset/tag_meta.json").read_text(encoding="utf-8")
        )
        by_slug = {tag["slug"]: tag for tag in meta["tags"]}
        gundam = by_slug["near_gundam_manhole"]
        self.assertEqual("ガンダムマンホール徒歩圏", gundam["label"])
        self.assertEqual(
            "ガンダムマンホールまで約500m以内のポケふた", gundam["description"]
        )
        self.assertEqual(
            {
                "roadside", "remote_island", "world_heritage",
                "near_gundam_manhole", "seaside", "tourism", "park",
            },
            {tag["slug"] for tag in meta["tags"] if tag.get("featured")},
        )
        for filename in ("map.html", "map.template.html"):
            with self.subTest(filename=filename):
                source = (summary.ROOT / "apps/web" / filename).read_text(
                    encoding="utf-8"
                )
                self.assertIn(
                    'aria-label="${description} ${count}枚" '
                    'title="${description}"',
                    source,
                )

    def test_generated_template_keeps_popup_copy_localized(self):
        # ポップアップも同じく map 側にある。多言語版のもとになるのは
        # map.template.html（map.html は日本語の手編集版）。
        template = (summary.ROOT / "apps/web/map.template.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("const UI_TEXT = window.I18N.UI;", template)
        self.assertIn("${I.photoWanted}", template)
        self.assertIn("${I.photoMissing}", template)
        self.assertIn("${I.firstPhotoUploadCta}", template)
        self.assertIn("${I.googleMapsCta}", template)
        self.assertIn("anchor.textContent = UI_TEXT.detailPageCta;", template)
        self.assertIn("getHeroPokemonDisplayName(pokemon)", template)
        self.assertNotIn("getPokemonDisplayName(pokemon)", template)
        self.assertNotIn("const UI_TEXT = {", template)

    def test_i18n_hero_strings_have_all_destinations(self):
        i18n_dir = summary.ROOT / "apps/web/i18n"
        for language in ("ja", "en", "zh-CN", "zh-TW", "ko"):
            with self.subTest(language=language):
                data = json.loads(
                    (i18n_dir / f"strings.{language}.json").read_text(encoding="utf-8")
                )
                hero = data["I18N_OBJECT"]["heroDiscovery"]
                self.assertEqual(set(hero["ctas"]), {"fresh", "travel", "rare"})
                self.assertEqual(
                    set(hero["travelThemes"]),
                    {"remote_island", "roadside", "station_front", "world_heritage"},
                )

    def test_japanese_ranking_uses_landing_page_cta(self):
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        html = summary.render_page(
            summary.SUMMARY_STRINGS["ja"],
            stats,
            {},
            {},
            {},
            {},
            {},
        )
        self.assertIn('href="/prefectures/', html)
        self.assertIn(">詳しく見る</a>", html)

    def test_hero_features_todays_trivia_with_one_map_button(self):
        """ヒーローはリンク集にせず、今日の雑学を主役にして押す所は地図の1つにする。
        Xで共有は押されていなかったので、ヒーローにも雑学の一覧にも置かない。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary.render_page(strings, stats, {}, {}, records_by_id, {}, {})
                hero = html[html.index('<header class="summary-hero">'):html.index("</header>")]
                self.assertIn('class="summary-hero-fact"', hero)
                self.assertEqual(hero.count('data-summary-event="summary_map_click"'), 1)
                self.assertNotIn("summary-hero-link", hero)
                self.assertNotIn("twitter.com/intent", html)
                self.assertNotIn("summary_share_x_click", html)

    def test_pages_missing_from_the_header_are_linked_in_japanese_only(self):
        """市区町村ランキングとポケふた旅はヘッダーに無い ja 専用ページなので、ランキングの下から文字リンクで送る。
        ポケふたがない県は ja では雑学の FAQ に入れ、県のページ（0枚でもある）へリンクする。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        faq_items = summary.summary_faq.build_faq(records, [], {}, {})
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary.render_page(strings, stats, {}, {}, records_by_id, {}, {}, faq_items=faq_items)
                if language == "ja":
                    self.assertIn('href="/municipalities/"', html)
                    self.assertIn('href="/trip/"', html)
                    self.assertNotIn('id="empty-prefecture-heading"', html)
                    empty = html[html.index('id="faq-empty-prefectures"'):]
                    empty = empty[:empty.index("</details>")]
                    for item in stats["empty"]:
                        slug = summary.PREFECTURE_SLUGS[item["pref"]]
                        self.assertIn(f'href="/prefectures/{slug}/"', empty)
                    self.assertIn('data-surface="summary_empty_prefectures"', empty)
                else:
                    empty = html[html.index('id="empty-prefecture-heading"'):]
                    empty = empty[:empty.index("</section>")]
                    self.assertNotIn('href="/municipalities/"', html)
                    self.assertNotIn('href="/trip/"', html)
                    self.assertNotIn('href="/prefectures/', empty)

    def test_rendered_page_keeps_anchors_used_by_hero_links_and_map(self):
        """ヒーローのリンクと地図ページ（map.html）が飛ぶ先のアンカーが、どの言語のページにもある。
        ja は県・ポケモン・写真を探すのをヒーローのボタンから各ページへ任せ、ここには出さない。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary.render_page(strings, stats, {}, {}, records_by_id, {}, {})
                self.assertIn('id="travel-discovery"', html)
                self.assertIn('id="rare-discovery"', html)
                for removed in ("latest-photos-heading", "popular-pokemon-heading", "no-photos-heading"):
                    self.assertNotIn(f'id="{removed}"', html)
                if language == "ja":
                    self.assertNotIn('id="prefecture-count-heading"', html)
                else:
                    self.assertIn('id="prefecture-count-heading"', html)

    def test_events_beyond_the_first_three_are_folded(self):
        events = [
            {"title": f"イベント{i}", "url": f"https://example.com/{i}", "prefecture": "岩手県",
             "start_date": "2026-01-01", "end_date": "2099-12-31"}
            for i in range(5)
        ]
        html = summary._build_events_section(summary.SUMMARY_STRINGS["ja"], events, lambda v: v)
        visible = html[:html.index("<details")]
        self.assertEqual(visible.count("<li>"), summary.EVENTS_VISIBLE)
        self.assertIn("ほか2件のイベントを見る", html)
        self.assertEqual(html.count('data-summary-event="summary_event_click"'), 5)  # 折りたたんでも全部ページに残る
        three = summary._build_events_section(summary.SUMMARY_STRINGS["ja"], events[:3], lambda v: v)
        self.assertNotIn("<details", three)

class PageOrderTests(unittest.TestCase):
    def test_trivia_comes_first(self):
        """雑学を優先する: 今日の雑学はヒーローの中、雑学の一覧はヒーローの直後に置き、一覧は折りたたまない。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        events = [{"title": "イベント", "url": "https://example.com/", "prefecture": "岩手県",
                   "start_date": "2026-01-01", "end_date": "2099-12-31"}]
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary.render_page(
                    strings, stats, {}, {}, records_by_id, {}, {}, prefecture_events=events
                )
                order = [html.index(marker) for marker in (
                    'class="summary-hero-fact"', "</header>", 'id="fact-list-heading"',
                    'id="events-heading"', 'id="travel-discovery"', 'id="ranking-heading"',
                )]
                self.assertEqual(order, sorted(order))
                facts = html[html.index('id="fact-list-heading"'):]
                facts = facts[:facts.index("</section>")]
                self.assertNotIn("<details", facts)


class TriviaFaqTests(unittest.TestCase):
    """ja の「ポケふた雑学」はデータから組み立てたカテゴリつき FAQ。"""

    @classmethod
    def setUpClass(cls):
        cls.records = summary.load_records(summary.NDJSON)
        cls.trivia = summary.summary_faq.load_trivia(summary.PREFECTURE_TRIVIA_JSON)
        cls.items = summary.summary_faq.build_faq(cls.records, cls.trivia, {}, summary.TAG_META_PAGE_HREFS)

    def test_trivia_answers_come_only_from_official_sources(self):
        trivia = [{"prefecture": "香川県", "trivia": [
            {"id": "kagawa-slowpoke-wordplay", "type": "wordplay", "text": "公式の文。", "source_type": "official",
             "source_label": "ポケモンローカルActs", "source_url": "https://local.pokemon.jp/municipality/kagawa/"},
            {"id": "niigata-ojiya-koi", "type": "local_connection", "text": "出典なし", "source_type": "dataset"},
        ]}]
        items = summary.summary_faq.build_faq([], trivia, {}, {})
        self.assertEqual([i.id for i in items], ["kagawa-slowpoke-wordplay"])
        self.assertEqual(items[0].answer_text, "公式の文。")  # 句点が二重にならない
        self.assertIn("https://local.pokemon.jp/municipality/kagawa/", items[0].answer_html)
        self.assertIn('href="/prefectures/kagawa/"', items[0].answer_html)

    def test_categories_are_in_order_and_every_answer_has_text(self):
        order = summary.summary_faq.CATEGORY_ORDER
        positions = [order.index(i.category) for i in self.items]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(set(positions), set(range(len(order))))  # 4カテゴリとも出る
        for item in self.items:
            with self.subTest(item=item.id):
                self.assertTrue(item.question.endswith("？"))
                self.assertTrue(item.answer_text and item.lead)

    def test_empty_prefectures_are_a_place_question(self):
        item = next(i for i in self.items if i.id == "empty-prefectures")
        stats = summary.build_stats(self.records)
        self.assertEqual(item.category, "場所")
        self.assertIn(f"{len(stats['empty'])}県", item.lead)
        self.assertEqual(item.answer_html.count("<li>"), len(stats["empty"]))
        all_installed = [{"prefecture": p} for p in summary.PREFECTURE_ORDER]
        self.assertEqual([], summary.summary_faq._empty_prefecture_item(all_installed))

    def test_shared_end_manhole_is_listed_once(self):
        ends = next(i for i in self.items if i.id == "ends")
        self.assertIn("いちばん南・いちばん西", ends.answer_text)
        self.assertNotIn("/", ends.answer_text.replace("いちばん南・いちばん西", ""))  # 「沖縄県/石垣市」を出さない

    def test_todays_item_rotates_through_trivia_and_records_only(self):
        start = date(2026, 10, 1)
        picked = {
            summary.summary_faq.todays_item(self.items, start + timedelta(days=n)).category for n in range(60)
        }
        self.assertEqual(picked, summary.summary_faq.HERO_CATEGORIES)
        self.assertIsNone(summary.summary_faq.todays_item([], date(2026, 10, 1)))

    def test_japanese_page_uses_the_faq_with_structured_data(self):
        stats = summary.build_stats(self.records)
        records_by_id = {str(r["id"]): r for r in self.records}
        ja = summary.render_page(summary.SUMMARY_STRINGS["ja"], stats, {}, {}, records_by_id, {}, {}, faq_items=self.items)
        self.assertEqual(ja.count('class="faq-item"'), len(self.items))
        self.assertNotIn('class="summary-fact-card"', ja)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', ja).group(1))
        self.assertEqual(ld["@type"], "FAQPage")
        self.assertEqual(len(ld["mainEntity"]), len(self.items))
        hero = ja[ja.index('<header class="summary-hero">'):ja.index("</header>")]
        self.assertIn('data-summary-event="summary_faq_click"', hero)
        en = summary.render_page(summary.SUMMARY_STRINGS["en"], stats, {}, {}, records_by_id, {}, {}, faq_items=self.items)
        self.assertNotIn('class="faq-item"', en)  # 元データが日本語しか無い
        self.assertNotIn("application/ld+json", en)
        self.assertIn('class="summary-fact-card"', en)


class StylesheetTests(unittest.TestCase):
    def test_every_selector_list_is_followed_by_its_declarations(self):
        """まとめたセレクタの途中で、宣言ブロックが抜けていない。

        使わない CSS を消したときに、まとめたセレクタの最後の1つを中身ごと消して、
        残りが次の .summary-section のルールにくっついたことがある（見出しが紫でなくなった）。"""
        lines = summary._CSS.split("\n")
        for i, line in enumerate(lines[:-1]):
            if line.rstrip().endswith(","):
                with self.subTest(line=line.strip()):
                    self.assertNotEqual(lines[i + 1].strip(), "")
        self.assertEqual(summary._CSS.count("{"), summary._CSS.count("}"))

    def test_section_headings_keep_the_brand_color(self):
        self.assertRegex(
            summary._CSS,
            r"\.summary-section h2,\s*\.summary-fact-number,\s*\.discovery-card strong \{\s*color: #57408f;",
        )


if __name__ == "__main__":
    unittest.main()
