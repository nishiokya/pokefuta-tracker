import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_summary_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_summary_pages", MODULE_PATH)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(summary)


class LatestPhotosSectionTests(unittest.TestCase):
    """summary の「最新追加写真」カードのキャプション統一（場所 · 投稿者 · 7月16日）。"""

    S = {
        "pref_key": "ja",
        "latest_photos": {"h2": "最新追加写真", "note": "テスト用の説明"},
    }
    RECORDS = {
        "220": {
            "prefecture": "北海道",
            "city": "斜里町",
            "title": "北海道/斜里町",
            "pokemons": ["パルキア", "ロコン"],
        }
    }

    def _build(self, photo: dict) -> str:
        return summary._build_latest_photos_section(
            self.S, self.RECORDS, {"photos": {"p1": photo}}
        )

    def test_meta_has_location_poster_and_locale_date(self):
        html = self._build({
            "manhole_id": "220",
            "url": "https://example.com/220.jpeg",
            "created_at": "2026-07-15T15:30:00+00:00",  # JST では 7/16
            "display_name": "テスト太郎",
            "public_user_id": "6096691c-eeda-4e73-8401-a11274868ede",
        })
        self.assertIn(
            '<span class="photo-card-meta">北海道/斜里町 · '
            '<a class="poster-link" href="https://pokefuta.com/users/'
            '6096691c-eeda-4e73-8401-a11274868ede/visits"',
            html,
        )
        self.assertIn('>テスト太郎</a> · 7月16日</span>', html)
        self.assertIn('<article class="photo-card">', html)
        self.assertIn('<a class="photo-card-main" href="/manholes/220/">', html)

    def test_meta_without_poster_keeps_location_and_date(self):
        html = self._build({
            "manhole_id": "220",
            "url": "https://example.com/220.jpeg",
            "created_at": "2026-07-16T00:00:00+00:00",
        })
        self.assertIn(
            '<span class="photo-card-meta">北海道/斜里町 · 7月16日</span>', html
        )

    def test_long_poster_name_is_truncated(self):
        html = self._build({
            "manhole_id": "220",
            "url": "https://example.com/220.jpeg",
            "created_at": "2026-07-16T00:00:00+00:00",
            "display_name": "とても長い名前の投稿者さんイーブイ推し団長",
        })
        self.assertIn("とても長い名前の投稿者さんイーブイ推し…", html)

    def test_non_ja_page_renders_nothing(self):
        html = summary._build_latest_photos_section(
            {**self.S, "pref_key": "en"}, self.RECORDS, {"photos": {}}
        )
        self.assertEqual(html, "")


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

    def test_japanese_prefecture_jump_links_to_static_pages(self):
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        html = summary._build_prefecture_jump_section(summary.SUMMARY_STRINGS["ja"], stats)
        self.assertIn('href="/prefectures/fukui/"', html)
        self.assertIn('href="/prefectures/gunma/"', html)
        self.assertIn('data-summary-event="summary_prefecture_click"', html)
        self.assertIn("<h3>北海道・東北</h3>", html)
        # 0枚の県にもページがあるので、薄いチップで残す（47県すべてにリンク）
        self.assertEqual(html.count('data-surface="summary_prefecture_jump" data-prefecture='), 47)
        self.assertEqual(html.count('class="is-empty"'), len(stats["empty"]))
        for language, strings in summary.SUMMARY_STRINGS.items():
            if language != "ja":
                self.assertEqual(summary._build_prefecture_jump_section(strings, stats), "")

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

    def test_japanese_hero_prefecture_link_goes_to_the_prefectures_index(self):
        """ja版のヒーローの「都道府県から探す」の目的地は詳細ページの入口
        （/prefectures/）であるべきで、同じページ内の集計グリッドへの
        アンカーに戻してはいけない。市区町村ランキングとポケふた旅も ja だけ出す。"""
        html = summary._build_hero_links(summary.SUMMARY_STRINGS["ja"])
        self.assertIn('href="/prefectures/"', html)
        self.assertIn('href="/municipalities/"', html)
        self.assertIn('href="/trip/"', html)
        self.assertIn('href="#travel-discovery"', html)
        self.assertNotIn('href="#prefecture-count-heading"', html)
        self.assertIn('data-surface="summary_hero"', html)

    def test_non_japanese_hero_prefecture_link_stays_on_the_localized_anchor(self):
        """/prefectures/・/municipalities/・/trip/ はja専用ページなので、他言語では飛ばさず、
        その言語でローカライズされた同一ページ内の集計セクションのままにする。"""
        for language, strings in summary.SUMMARY_STRINGS.items():
            if language == "ja":
                continue
            with self.subTest(language=language):
                html = summary._build_hero_links(strings)
                self.assertIn('href="#prefecture-count-heading"', html)
                for ja_only in ('href="/prefectures/"', 'href="/municipalities/"', 'href="/trip/"'):
                    self.assertNotIn(ja_only, html)

    def test_rendered_page_keeps_anchors_used_by_hero_links_and_map(self):
        """ヒーローのリンクと地図ページ（map.html）が飛ぶ先のアンカーが、どの言語のページにもある。
        ja は県の詳細を /prefectures/ に任せて、地方ごとの入口だけにする。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary.render_page(strings, stats, {}, {}, records_by_id, {}, {})
                self.assertIn('id="travel-discovery"', html)
                self.assertIn('id="rare-discovery"', html)
                if language == "ja":
                    self.assertNotIn('id="prefecture-count-heading"', html)
                    self.assertIn('id="prefecture-jump-heading"', html)
                    self.assertIn('href="/prefectures/hokkaido/"', html)
                else:
                    self.assertIn('id="prefecture-count-heading"', html)
                    self.assertNotIn('id="prefecture-jump-heading"', html)

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

    def test_popular_pokemon_cards_use_the_representative_photo(self):
        """ポケモンのページと同じ決め方: 公開写真のある蓋だけを候補にし、代表がその中にあれば代表、
        無ければ新しい公開写真。画像ファイルが残っていても、公開写真の一覧に無い蓋は出さない。"""
        pokemon_stats = {"by_count": [{"ja_name": "ラッキー", "slug": "chansey", "count": 3}]}
        records = {mid: {"id": mid, "pokemons": ["ラッキー"]} for mid in ("10", "20", "30")}
        photos = {"photos": {
            "10": {"manhole_id": "10", "created_at": "2026-10-01T00:00:00Z"},
            "20": {"manhole_id": "20", "created_at": "2026-09-01T00:00:00Z"},
            # 30 は写真が非公開・削除になった（画像ファイルだけ残っている）
        }}
        strings = summary.SUMMARY_STRINGS["ja"]
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            for mid in ("10", "20", "30"):
                (image_dir / f"{mid}_lid.jpeg").write_bytes(b"x")
            original = summary.IMAGE_DIR
            summary.IMAGE_DIR = image_dir
            try:
                def build(reps, photos_data=photos):
                    return summary._build_popular_pokemon_section(
                        strings, pokemon_stats, records, {}, reps, photos_data
                    )
                chosen = build({"ラッキー": "20"})
                newest = build({})
                withdrawn = build({"ラッキー": "30"})
                no_public = build({"ラッキー": "30"}, {"photos": {}})
            finally:
                summary.IMAGE_DIR = original
        self.assertIn('src="/manhole/image/20_lid.jpeg"', chosen)  # 人が選んだ代表
        self.assertIn('src="/manhole/image/10_lid.jpeg"', newest)  # 代表が無ければ新しい公開写真
        self.assertIn('src="/manhole/image/10_lid.jpeg"', withdrawn)  # 代表が非公開なら使わない
        self.assertNotIn("<img", no_public)  # 公開写真が無ければ文字だけ
        self.assertIn('href="/pokemon/"', chosen)


    def test_no_photos_section_is_japanese_only(self):
        """写真なし節の県リンクは ja 専用ページ（/prefectures/）を指すが、
        節そのものが ja でしか描画されないので他言語に漏れない。

        レビューで「他言語の summary から ja 専用ページへ飛ぶ」と
        指摘されたが、pref_key の early return が20行上にあるため
        実際には描画されない。読み違えが再発しないよう固定する。"""
        records = {
            "1": {"id": "1", "status": "active", "prefecture": "鹿児島県"},
            "2": {"id": "2", "status": "active", "prefecture": "宮城県"},
        }
        photos = {"photos": {}}
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary._build_no_photos_section(strings, records, photos)
                if language == "ja":
                    self.assertIn("/prefectures/kagoshima/", html)
                else:
                    self.assertEqual("", html)



class PageOrderTests(unittest.TestCase):
    def test_daily_fact_stays_near_the_top(self):
        """「今日の雑学」の「地図で見る」は summary_map_click の出どころ（旧ページで3番目に押されていた）。
        読まれない下の方へ回さず、最新写真の直後・都道府県の前に置く。"""
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        records_by_id = {str(r["id"]): r for r in records}
        html = summary.render_page(summary.SUMMARY_STRINGS["ja"], stats, {}, {}, records_by_id, {}, {})
        self.assertLess(html.index('class="daily-fact-card"'), html.index('id="prefecture-jump-heading"'))
        self.assertLess(html.index('id="prefecture-jump-heading"'), html.index('id="fact-list-heading"'))

    def test_broken_representatives_file_does_not_stop_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reps.json"
            for content in ('[1, 2]', '{"representatives": [1]}', "{broken"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(summary.load_pokemon_representatives(path), {})
            path.write_text('{"representatives": {"ラッキー": 91}}', encoding="utf-8")
            self.assertEqual(summary.load_pokemon_representatives(path), {"ラッキー": "91"})
            self.assertEqual(summary.load_pokemon_representatives(Path(tmp) / "missing.json"), {})


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
