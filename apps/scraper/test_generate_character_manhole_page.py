from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from generate_character_manhole_page import (  # noqa: E402
    FAQ_ITEMS,
    build_faq_items,
    build_prefecture_summaries,
    build_work_summaries,
    generate_html,
    GALLERY_PHOTO_LIMIT,
    HERO_PHOTO_LIMIT,
    UNLINKED_PHOTO_LABEL,
    build_photos,
    load_active_manholes,
    select_photos,
)
from character_manhole_works import CHARACTER_CSS_VERSION  # noqa: E402
from character_manhole_works import WorkPage  # noqa: E402

RESERVED_INDEX_PAGE_IDS = (
    "sec-intro", "sec-map", "sec-hero", "sec-hub", "sec-pref", "sec-events", "sec-newrelease",
)


def _write_ndjson(directory: Path, name: str, records: list[dict]) -> Path:
    path = directory / name
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    return path


CHARACTER_RECORDS = [
    {
        "id": "zls-1", "work": "ゾンビランドサガ", "character": "源さくら",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "active",
        "marker_color": "#10b981", "marker_label": "ゾ", "landmark": "唐人プラザビル",
        "lat": 33.256344, "lng": 130.299759,
    },
    {
        "id": "zls-2", "work": "ゾンビランドサガ", "character": "二階堂サキ",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "active",
        "marker_color": "#10b981", "marker_label": "ゾ",
        "lat": 33.246159, "lng": 130.3026375,
    },
    {
        "id": "yp-1", "work": "弱虫ペダル", "character": "小野田坂道",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "marker_color": "#ec4899", "marker_label": "弱",
        # lat/lng が無いレコードもある想定（ジオコーディング未済など）
    },
    {
        # status != active は除外される
        "id": "removed-1", "work": "ゾンビランドサガ", "character": "撤去済み",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "invalid",
        "marker_color": "#10b981", "marker_label": "ゾ",
        "lat": 33.0, "lng": 130.0,
    },
    {
        # installation_status が明示的に撤去済みなら除外
        "id": "removed-2", "work": "弱虫ペダル", "character": "撤去済み2",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": "removed",
        "marker_color": "#ec4899", "marker_label": "弱",
        "lat": 32.0, "lng": 129.0,
    },
    {
        # installation_status が None は許容
        "id": "yp-2", "work": "弱虫ペダル", "character": "今泉俊輔",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": None,
        "marker_color": "#ec4899", "marker_label": "弱",
        "lat": 32.744, "lng": 129.8737,
    },
]

GUNDAM_RECORDS = [
    {"id": "1", "prefecture": "北海道", "city": "豊富町", "status": "active", "franchise": "gundam", "lat": 45.10487, "lng": 141.772842},
    {"id": "2", "prefecture": "佐賀県", "city": "佐賀市", "status": "active", "franchise": "gundam", "lat": 33.25, "lng": 130.3},
    {"id": "3", "prefecture": "佐賀県", "city": "唐津市", "status": "invalid", "franchise": "gundam", "lat": 33.45, "lng": 129.97},
]


# design_manholes.ndjson の形（?size=small つきの photo_url、canonical_ref / nearby_refs）
PHOTO_RECORDS = [
    {   # canonical_ref がガンダム（掲載中）→ キャラクターマンホールの写真
        "id": "p-gundam", "title": "豊富駅ガンダムマンホール", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/p-gundam/photo?size=small",
        "canonical_ref": "gundam:1", "nearby_refs": [{"distance_m": 30, "ref": "gundam:1"}],
        "prefecture": "北海道", "city": "豊富町", "source_url": "https://pokefuta.com/design-manholes/p-gundam",
        "created_at": "2026-09-01T00:00:00+00:00",
    },
    {   # nearby_refs 側にキャラクターマンホール参照 → キャラクターマンホールの写真
        "id": "p-zls", "title": "佐賀の蓋", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/p-zls/photo?size=small",
        "canonical_ref": None, "nearby_refs": [{"distance_m": 5, "ref": "character:zls-1"}],
        "prefecture": "佐賀県", "city": "佐賀市", "source_url": "https://pokefuta.com/design-manholes/p-zls",
        "created_at": "2026-09-02T00:00:00+00:00",
    },
    *[
        {"id": f"p-plain-{i}", "title": f"投稿{i}", "status": "active",
         "photo_url": f"https://pokefuta.com/api/design-manholes/p-plain-{i}/photo?size=small",
         "canonical_ref": None, "nearby_refs": [{"distance_m": 46, "ref": "pokefuta:272"}],
         "prefecture": "愛知県", "city": "名古屋市\u3000北区",
         "source_url": f"https://pokefuta.com/design-manholes/p-plain-{i}",
         "created_at": f"2026-08-{i + 1:02d}T00:00:00+00:00"}
        for i in range(24)
    ],
    {   # 参照先が掲載データに無い（撤去済みなど）→ キャラクターマンホールとは言わない
        "id": "p-dangling", "title": "参照切れ", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/p-dangling/photo?size=small",
        "canonical_ref": "gundam:999", "prefecture": "北海道", "city": "稚内市",
        "created_at": "2026-07-01T00:00:00+00:00",
    },
    {"id": "p-inactive", "title": "非アクティブ", "status": "removed", "canonical_ref": "gundam:1",
     "photo_url": "https://pokefuta.com/api/design-manholes/p-inactive/photo?size=small"},
    # size=medium/large/未指定は 2MB 原寸へのリダイレクトになるので、キャラ紐付けがあっても使わない
    {"id": "p-medium", "title": "サイズ違反medium", "status": "active", "canonical_ref": "gundam:1",
     "photo_url": "https://pokefuta.com/api/design-manholes/p-medium/photo?size=medium"},
    {"id": "p-large", "title": "サイズ違反large", "status": "active",
     "photo_url": "https://pokefuta.com/api/design-manholes/p-large/photo?size=large"},
    {"id": "p-nosize", "title": "サイズ指定なし", "status": "active",
     "photo_url": "https://pokefuta.com/api/design-manholes/p-nosize/photo"},
]


class WorkSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)

    def test_excludes_inactive_and_removed_records(self):
        ids = {record["id"] for record in self.character_records}
        self.assertNotIn("removed-1", ids)
        self.assertNotIn("removed-2", ids)
        self.assertIn("yp-2", ids)  # installation_status=None は許容
        self.assertEqual(4, len(self.character_records))

        gundam_ids = {record["id"] for record in self.gundam_records}
        self.assertNotIn("3", gundam_ids)
        self.assertEqual(2, len(self.gundam_records))

    def test_work_summaries_sorted_by_count_descending(self):
        summaries = build_work_summaries(self.character_records, self.gundam_records)
        counts = [summary["count"] for summary in summaries]
        self.assertEqual(counts, sorted(counts, reverse=True))
        works = [summary["work"] for summary in summaries]
        # ゾンビランドサガ(2) / 弱虫ペダル(2) / ガンダム(1) が含まれる
        self.assertIn("ゾンビランドサガ", works)
        self.assertIn("弱虫ペダル", works)
        self.assertTrue(any("ガンダム" in work for work in works))

    def test_gundam_entry_uses_special_work_query(self):
        summaries = build_work_summaries(self.character_records, self.gundam_records)
        gundam = next(s for s in summaries if "ガンダム" in s["work"])
        self.assertEqual("gundam", gundam["query"])
        self.assertEqual(2, gundam["count"])

    def test_work_page_path_does_not_depend_on_display_name(self):
        renamed = WorkPage(
            "zombieland-saga", "ゾンビランドサガシリーズ", "ゾンビランドサガ",
            ("ゾンビランドサガ",), "intro", "guide", "question", "answer",
        )
        records = [record for record in self.character_records if record["work"] == "ゾンビランドサガ"]
        with patch("generate_character_manhole_page.page_for_work", return_value=renamed):
            summary = build_work_summaries(records, [])[0]
        self.assertEqual("ゾンビランドサガシリーズ", summary["work"])
        self.assertEqual("characters/zombieland-saga/", summary["path"])
        self.assertEqual("ゾンビランドサガ", summary["query"])

    def test_main_prefectures_are_ordered_by_count(self):
        summaries = build_work_summaries(self.character_records, self.gundam_records)
        gundam = next(s for s in summaries if "ガンダム" in s["work"])
        # 同数（1枚ずつ）は北から
        self.assertEqual([("北海道", 1), ("佐賀県", 1)], gundam["main_prefectures"])

    def test_prefecture_summaries_combine_character_and_gundam(self):
        summaries = build_prefecture_summaries(self.character_records, self.gundam_records)
        by_pref = {entry["prefecture"]: entry["count"] for entry in summaries}
        # 佐賀県: キャラクターマンホール2件 + ガンダム(active)1件 = 3
        self.assertEqual(3, by_pref["佐賀県"])
        # 長崎県: キャラクターマンホール2件（active）
        self.assertEqual(2, by_pref["長崎県"])
        # 北海道: ガンダムのみ1件
        self.assertEqual(1, by_pref["北海道"])
        counts = [entry["count"] for entry in summaries]
        self.assertEqual(counts, sorted(counts, reverse=True))



def _build(character_records: list[dict], gundam_records: list[dict]) -> str:
    return generate_html(character_records, gundam_records)


def _json_ld_graph(html: str) -> list[dict]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return json.loads(match.group(1))["@graph"]


def _node(graph: list[dict], type_name: str) -> dict:
    return next(node for node in graph if node.get("@type") == type_name)


def _visible_body(html: str) -> str:
    """初期表示で読める本文（<main> から、閉じた <details> の中身・script・style を除いたテキスト）。"""
    main = html[html.index("<main"):html.index("</main>")]
    main = re.sub(r"<details(?![^>]*\bopen\b)[^>]*>.*?</details>", " ", main, flags=re.S)
    main = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", main, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))


class _PageTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)
        self.total_count = len(self.character_records) + len(self.gundam_records)
        self.html = _build(self.character_records, self.gundam_records)


class GenerateHtmlTest(_PageTestCase):
    def test_includes_work_names_and_counts(self):
        self.assertIn("ゾンビランドサガ", self.html)
        self.assertIn("弱虫ペダル", self.html)
        self.assertIn('<b class="cm-num">2</b>枚', self.html)

    def test_work_cards_show_main_characters_and_prefectures_as_text(self):
        card = re.search(r'<a class="lp-work-card" href="./characters/zombieland-saga/".*?</a>', self.html, re.S).group(0)
        self.assertIn("<span>主なキャラクター</span>源さくら、二階堂サキ", card)
        self.assertIn("<span>主な都道府県</span>佐賀県 2", card)

    def test_work_cards_link_to_static_guides_and_only_fall_back_to_the_map(self):
        self.assertIn('class="lp-work-card" href="./characters/zombieland-saga/"', self.html)
        self.assertIn('class="lp-work-card" href="./characters/yowamushi-pedal/"', self.html)
        self.assertIn('class="lp-work-card" href="./characters/gundam/"', self.html)
        self.assertNotIn('class="lp-work-card" href="./gmanhole_map.html', self.html)
        # 作品ページが無い作品だけ、地図の作品クエリへ送る
        html = _build(self.character_records + [
            {"id": "x-1", "work": "未登録の作品", "character": "だれか", "prefecture": "福岡県",
             "city": "福岡市", "status": "active"},
        ], self.gundam_records)
        self.assertIn('class="lp-work-card" href="./gmanhole_map.html?work=%E6%9C%AA', html)

    def test_idolmaster_brands_are_grouped_into_one_guide(self):
        records = self.character_records + [
            {"id": "imas-1", "work": "アイドルマスター SideM", "character": "渡辺みのり",
             "prefecture": "茨城県", "city": "筑西市", "status": "active"},
            {"id": "imas-2", "work": "学園アイドルマスター", "character": "姫崎莉波",
             "prefecture": "熊本県", "city": "熊本市", "status": "active"},
        ]
        html = _build(records, self.gundam_records)
        self.assertEqual(1, html.count('class="lp-work-card" href="./characters/idolmaster/"'))
        self.assertIn('アイドルマスター</strong><span class="lp-work-count"><b class="cm-num">2</b>枚', html)

    def test_location_directory_contains_all_active_records_without_javascript(self):
        lists = re.findall(r'<ul class="lp-location-list">(.*?)</ul>', self.html, re.S)
        self.assertEqual(3, len(lists))
        directory = "".join(lists)
        self.assertEqual(self.total_count, directory.count("<li "))
        self.assertIn("唐人プラザビル", directory)
        self.assertIn("豊富町", directory)
        self.assertIn("小野田坂道", directory)  # 座標なしでも一覧には載る
        self.assertNotIn("撤去済み", directory)

    def test_prefecture_list_is_text_with_count_and_main_works(self):
        rows = dict(re.findall(
            r'<li data-pref="([^"]+)"><a href="#pref-[a-z]+">[^<]+</a><b><span class="cm-num">\d+</span>枚</b>'
            r'<span class="lp-pref-works">([^<]+)</span></li>',
            self.html,
        ))
        self.assertEqual({"北海道", "佐賀県", "長崎県"}, set(rows))
        self.assertEqual("ゾンビランドサガ 2・機動戦士ガンダム 1", rows["佐賀県"])
        self.assertNotIn("lp-pref-bar", self.html)
        # 県名は設置場所一覧の該当県へ飛ぶ
        self.assertIn('<a href="#pref-saga">佐賀県</a>', self.html)
        self.assertIn('id="pref-saga"', self.html)

    def test_prefecture_rows_add_up_to_the_total(self):
        counts = [int(n) for n in re.findall(r'</a><b><span class="cm-num">(\d+)</span>枚</b>', self.html)]
        self.assertEqual(self.total_count, sum(counts))

    def test_location_sources_are_safe_and_escaped(self):
        records = [dict(self.character_records[0], title='<script>alert(1)</script>', landmark="",
                        source_url='https://example.com/?a=1&b=2'),
                   dict(self.character_records[1], source_url='javascript:alert(2)')]
        html = _build(records, self.gundam_records)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_escapes_quotes_in_data_attributes(self):
        records = [dict(self.character_records[0], prefecture='佐賀県" onmouseover="alert(1)')]
        html = _build(records, [])
        # JSON-LD の中は JSON のエスケープ（\"）で守られるので、HTML 側だけを見る
        markup = re.sub(r'<script type="application/ld\+json">.*?</script>', "", html, flags=re.S)
        self.assertFalse('" onmouseover=' in markup, "attribute breakout in HTML markup")
        self.assertIn("&quot;", markup)

    def test_gundam_official_source_and_missing_location_fallback(self):
        records = [dict(self.gundam_records[0], official_url='https://example.com/official',
                        detail_url='https://example.com/detail')]
        html = _build([], records)
        self.assertIn('href="https://example.com/official"', html)
        self.assertNotIn('href="https://example.com/detail"', html)
        self.assertIn('詳細な住所は未記録', html)

    def test_place_label_does_not_repeat_a_character_already_in_the_title(self):
        records = [{"id": "imas-a", "work": "アイドルマスター SideM", "title": "渡辺みのり（ふたマス!!!!!!）",
                    "character": "渡辺みのり", "prefecture": "茨城県", "city": "筑西市", "status": "active"}]
        html = _build(records, [])
        self.assertIn("渡辺みのり（ふたマス!!!!!!）（アイドルマスター）", html)
        self.assertNotIn("（渡辺みのり／", html)

    def test_place_label_does_not_repeat_the_work_as_the_character(self):
        records = [{"id": "cm-1", "work": "ちびまる子ちゃん", "character": "ちびまる子ちゃん",
                    "landmark": "エスパルスドリームプラザ", "prefecture": "静岡県", "city": "静岡市清水区",
                    "status": "active"}]
        html = _build(records, [])
        self.assertIn("エスパルスドリームプラザ（ちびまる子ちゃん）", html)
        self.assertNotIn("ちびまる子ちゃん／ちびまる子ちゃん", html)

    def test_does_not_hardcode_totals_and_reacts_to_data_changes(self):
        self.assertIn(f"{self.total_count}枚", self.html)
        fewer_records = self.character_records[:-1]
        html_after = _build(fewer_records, self.gundam_records)
        total_after = len(fewer_records) + len(self.gundam_records)
        self.assertNotEqual(self.total_count, total_after)
        self.assertIn(f"地図で{total_after}件を見る", html_after)
        self.assertNotIn(f"地図で{self.total_count}件を見る", html_after)


class SeoStructureTest(_PageTestCase):
    """検索意図（作品・都道府県・市町村・キャラクター＋マンホール）に本文で答える構成。"""

    def test_title_description_and_canonical(self):
        self.assertIn(f"<title>アニメ・キャラクターマンホール全国一覧｜{self.total_count}枚の設置場所・地図</title>", self.html)
        self.assertIn('name="description" content="全国3都道府県・3作品、6枚', self.html)
        self.assertIn('<link rel="canonical" href="https://data.pokefuta.com/character_manholes.html">', self.html)
        self.assertIn('<meta name="robots" content="index,follow">', self.html)

    def test_has_exactly_one_h1_answering_the_directory_intent(self):
        headings = re.findall(r"<h1[^>]*>(.*?)</h1>", self.html, re.S)
        self.assertEqual(1, len(headings))
        self.assertIn("アニメ・キャラクターマンホール", headings[0])
        self.assertIn("全国一覧・設置場所", headings[0])

    def test_first_view_says_it_is_a_directory_of_all_listed_places(self):
        hero = self.html[self.html.index('id="lp-intro"'):self.html.index('class="lp-hub"')]
        self.assertIn(f"全国{self.total_count}枚の設置場所を、作品・キャラクター・都道府県・市町村から探せる図鑑です。", hero)

    def test_required_h2_in_order(self):
        h2s = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", self.html, re.S)]
        self.assertEqual([
            "アニメ・キャラクターマンホールを作品から探す",
            "都道府県から設置場所を探す",
            "全国の主な設置場所",
            "投稿されたマンホール写真",
            "キャラクターマンホールとは",
            "よくある質問",
        ], h2s)

    def test_search_hub_offers_the_four_ways_to_search(self):
        hub = self.html[self.html.index('<nav class="lp-hub"'):]
        hub = hub[:hub.index("</nav>")]
        for label in ("作品から探す", "都道府県から探す", "設置場所名・市町村から探す", "地図で探す"):
            with self.subTest(label=label):
                self.assertIn(f"<b>{label}</b>", hub)
        self.assertIn('href="#works"', hub)
        self.assertIn('href="#prefectures"', hub)
        self.assertIn('<input id="place-q"', hub)
        self.assertIn(f'href="./gmanhole_map.html"', hub)
        self.assertIn(f"地図で{self.total_count}件を見る", hub)

    def test_intro_explains_the_topic_scope_and_caveats_in_300_to_500_chars(self):
        intro = self.html[self.html.index('<section class="lp-intro"'):]
        intro = intro[:intro.index("</section>")]
        for label in ("キャラクターマンホールとは", "このページで分かること", "掲載範囲と注意"):
            self.assertIn(f"<strong>{label}</strong>", intro)
        text = re.sub(r"\s+", "", re.sub(r"<strong>.*?</strong>|<[^>]+>", "", intro))
        self.assertGreaterEqual(len(text), 300)
        self.assertLessEqual(len(text), 500)

    def test_proper_nouns_are_in_the_initially_visible_body(self):
        """閉じた details の奥だけでなく、初期表示の本文に作品・キャラ・県・市町村・設置場所名が出る。"""
        body = _visible_body(self.html)
        for word in ("ゾンビランドサガ", "弱虫ペダル", "機動戦士ガンダム",   # 作品
                     "源さくら", "小野田坂道",                             # キャラクター
                     "佐賀県", "長崎県", "北海道",                         # 都道府県
                     "佐賀市", "長崎市", "豊富町",                         # 市町村
                     "唐人プラザビル"):                                   # 設置場所
            with self.subTest(word=word):
                self.assertIn(word, body)

    def test_no_map_library_or_tiles_on_first_view(self):
        self.assertNotIn("leaflet", self.html.lower())
        self.assertNotIn("tile.openstreetmap.org", self.html)
        self.assertNotIn("map-gateway", self.html)

    def test_submission_cta_follows_the_photo_gallery(self):
        photos_start = self.html.index('id="lp-photos-heading"')
        section = self.html[photos_start:self.html.index("</section>", photos_start)]
        self.assertIn("その1枚、まだカメラロールにありますか？", section)
        self.assertIn('href="./design_manhole.html"', section)
        self.assertIn('href="https://pokefuta.com/design-manholes?from=data"', section)

    def test_json_ld_collection_page_points_at_the_work_item_list(self):
        graph = _json_ld_graph(self.html)
        page = _node(graph, "CollectionPage")
        item_list = _node(graph, "ItemList")
        self.assertEqual("https://data.pokefuta.com/character_manholes.html", page["url"])
        self.assertEqual(page["mainEntity"]["@id"], item_list["@id"])
        self.assertEqual(3, item_list["numberOfItems"])
        self.assertEqual(3, len(item_list["itemListElement"]))
        urls = {item["url"] for item in item_list["itemListElement"]}
        self.assertIn("https://data.pokefuta.com/characters/zombieland-saga/", urls)
        self.assertIn("https://data.pokefuta.com/characters/gundam/", urls)
        # 画面の作品カードと同じ並び・同じリンク先
        card_hrefs = re.findall(r'<a class="lp-work-card" href="\./([^"]+)"', self.html)
        self.assertEqual([u.replace("https://data.pokefuta.com/", "") for u in
                          (i["url"] for i in item_list["itemListElement"])], card_hrefs)

    def test_breadcrumb_json_ld_matches_the_visible_breadcrumb(self):
        crumbs = _node(_json_ld_graph(self.html), "BreadcrumbList")["itemListElement"]
        self.assertEqual(["ポケふた図鑑", "キャラクターマンホール全国一覧"], [c["name"] for c in crumbs])
        nav = re.search(r'<nav class="cw-breadcrumb"[^>]*>(.*?)</nav>', self.html, re.S).group(1)
        for crumb in crumbs:
            self.assertIn(crumb["name"], nav)

    def test_faq_json_ld_matches_the_visible_questions_and_answers(self):
        faq_block = self.html[self.html.index('class="cm-faq"'):]
        visible = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", faq_block)
        ld = [(q["name"], q["acceptedAnswer"]["text"]) for q in _node(_json_ld_graph(self.html), "FAQPage")["mainEntity"]]
        self.assertEqual([(escape(q), escape(a)) for q, a in ld], visible)
        expected = build_faq_items(
            build_work_summaries(self.character_records, self.gundam_records),
            build_prefecture_summaries(self.character_records, self.gundam_records),
        )
        self.assertEqual(expected, ld)

    def test_faq_does_not_name_a_single_leader_when_prefectures_tie(self):
        tied = [{"prefecture": "佐賀県", "count": 3}, {"prefecture": "長崎県", "count": 3},
                {"prefecture": "北海道", "count": 1}]
        answer = dict(build_faq_items([], tied))["キャラクターマンホールが多い都道府県はどこですか？"]
        self.assertIn("最も多いのは佐賀県と長崎県（各3枚）", answer)
        self.assertNotIn("最も多いのは佐賀県（", answer)
        self.assertIn("北海道（1枚）が続きます", answer)

    def test_faq_counts_come_from_the_same_aggregation_as_the_body(self):
        questions = dict(build_faq_items(
            build_work_summaries(self.character_records, self.gundam_records),
            build_prefecture_summaries(self.character_records, self.gundam_records),
        ))
        self.assertIn("最も多いのは佐賀県（3枚）", questions["キャラクターマンホールが多い都道府県はどこですか？"])
        self.assertIn("2都道府県に2枚", questions["ガンダムマンホールはどこにありますか？"])
        self.assertTrue(set(FAQ_ITEMS).issubset(questions.items()))

    def test_stats_and_their_caveat_are_adjacent(self):
        self.assertRegex(
            self.html,
            r'(?s)<ul class="cm-stats"[^>]*>(?:(?!</ul>).)*</ul>\s*<p class="cm-hero-note">'
            rf'掲載データ：{self.total_count}枚・3作品・3都道府県。全国すべてを網羅するものではありません',
        )

    def test_about_section_keeps_its_closing_caveat(self):
        about_start = self.html.index('id="lp-about-heading"')
        tail = self.html[self.html.index("</ul>", about_start):self.html.index("</section>", about_start)]
        self.assertIn(f"「全国{self.total_count}枚」は", tail)
        self.assertIn("手作業で出典を確認しながら追加", tail)

    def test_uses_mai_counter_unit_only(self):
        self.assertNotIn("基", self.html)
        self.assertNotIn(f"{self.total_count}件見つかりました", self.html)

    def test_analytics_login_rule_and_reserved_ids_are_kept(self):
        self.assertIn('<script src="/assets/analytics.js?v=20260805a"></script>', self.html)
        self.assertIn("page_type: 'lp_character_manholes'", self.html)
        self.assertIn('href="https://pokefuta.com/login?from=data"', self.html)
        self.assertNotIn("utm_", self.html)
        for reserved_id in RESERVED_INDEX_PAGE_IDS:
            with self.subTest(reserved_id=reserved_id):
                self.assertNotIn(f'id="{reserved_id}"', self.html)

    def test_only_the_shared_character_stylesheet_carries_page_styles(self):
        self.assertNotIn("<style", self.html)
        # 作品ガイドと同じキャッシュバスター（片方だけ古いCSSが残らないように）
        self.assertIn(f'href="./assets/character-work.css?v={CHARACTER_CSS_VERSION}"', self.html)

    def test_search_covers_the_landmark_names_shown_in_the_body(self):
        """本文はランドマーク名で出すので、絞り込み対象（一覧の li）にも同じ名前がある。"""
        records = [dict(self.character_records[0], title="ゆめまるマンホール（中岡崎駅）",
                        landmark="中岡崎駅ロータリー", address="愛知県岡崎市")]
        html = _build(records, [])
        item = re.search(r'<ul class="lp-location-list">(.*?)</ul>', html, re.S).group(1)
        self.assertIn("中岡崎駅ロータリー", item)
        self.assertIn("源さくら", item)


class PhotoTest(unittest.TestCase):
    """投稿写真: キャラクターマンホールの写真を優先し、それ以外は「投稿されたデザインマンホール」と明記する。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        self.character_records = load_active_manholes(_write_ndjson(directory, "c.ndjson", CHARACTER_RECORDS))
        self.gundam_records = load_active_manholes(_write_ndjson(directory, "g.ndjson", GUNDAM_RECORDS))
        self.photo_path = _write_ndjson(directory, "design_manholes.ndjson", PHOTO_RECORDS)
        self.photos = build_photos(self.photo_path, self.character_records, self.gundam_records)
        self.html = generate_html(self.character_records, self.gundam_records, self.photo_path,
                                  seed_date=date(2026, 9, 26))

    def test_uses_only_active_small_photos(self):
        ids = {p["id"] for p in self.photos}
        self.assertEqual(27, len(self.photos))
        for excluded in ("p-inactive", "p-medium", "p-large", "p-nosize"):
            self.assertNotIn(excluded, ids)
        for url in re.findall(r'<img src="([^"]+)"', self.html):
            with self.subTest(url=url):
                self.assertTrue(url.endswith("?size=small"), url)

    def test_linked_photos_carry_work_and_place_and_link_to_the_guide_spot(self):
        by_id = {p["id"]: p for p in self.photos}
        gundam = by_id["p-gundam"]
        self.assertTrue(gundam["linked"])
        self.assertEqual("機動戦士ガンダム", gundam["label"])
        self.assertEqual("./characters/gundam/#spot-1", gundam["href"])
        zls = by_id["p-zls"]
        self.assertEqual("ゾンビランドサガ", zls["label"])
        self.assertEqual("唐人プラザビル", zls["place"])
        self.assertEqual("./characters/zombieland-saga/#spot-zls-1", zls["href"])

    def test_unlinked_photos_are_labelled_as_submitted_design_manholes(self):
        by_id = {p["id"]: p for p in self.photos}
        for photo_id in ("p-plain-0", "p-dangling"):
            photo = by_id[photo_id]
            self.assertFalse(photo["linked"])
            self.assertEqual(UNLINKED_PHOTO_LABEL, photo["label"])
            self.assertIn(UNLINKED_PHOTO_LABEL, photo["alt"])
        self.assertEqual("https://pokefuta.com/design-manholes/p-plain-0?from=data", by_id["p-plain-0"]["href"])
        self.assertEqual("名古屋市北区", by_id["p-plain-0"]["city"])  # 全角スペースを詰める

    def test_hero_and_gallery_split_without_duplicates(self):
        hero, gallery = select_photos(self.photos, seed_date=date(2026, 9, 26))
        self.assertEqual(HERO_PHOTO_LIMIT, len(hero))
        self.assertEqual(GALLERY_PHOTO_LIMIT, len(gallery))
        self.assertFalse({p["id"] for p in hero} & {p["id"] for p in gallery})
        self.assertEqual({"p-gundam", "p-zls"}, {p["id"] for p in hero[:2]})  # キャラクターマンホールが先頭
        # 同じ日なら同じ並び（日替わり）
        again, _ = select_photos(self.photos, seed_date=date(2026, 9, 26))
        self.assertEqual([p["id"] for p in hero], [p["id"] for p in again])

    def test_every_image_has_alt_width_and_height(self):
        imgs = re.findall(r"<img [^>]*>", self.html)
        self.assertGreaterEqual(len(imgs), HERO_PHOTO_LIMIT + GALLERY_PHOTO_LIMIT)
        for tag in imgs:
            with self.subTest(tag=tag[:80]):
                self.assertRegex(tag, r'alt="[^"]+"')
                self.assertRegex(tag, r'width="\d+"')
                self.assertRegex(tag, r'height="\d+"')
                self.assertIn('decoding="async"', tag)

    def test_only_images_outside_the_first_view_are_lazy(self):
        hero = self.html[self.html.index('<ul class="lp-hero-mosaic">'):self.html.index("</figure>")]
        rest = self.html[self.html.index("</figure>"):]
        self.assertEqual(HERO_PHOTO_LIMIT, hero.count("<img "))
        self.assertNotIn('loading="lazy"', hero)
        self.assertEqual(1, hero.count('fetchpriority="high"'))
        rest_imgs = re.findall(r"<img [^>]*>", rest)
        self.assertTrue(rest_imgs)
        for tag in rest_imgs:
            self.assertIn('loading="lazy"', tag)

    def test_captions_and_labels_do_not_pass_design_manholes_off_as_character_manholes(self):
        caption = re.search(r'<figcaption class="lp-hero-mosaic-caption">(.*?)</figcaption>', self.html).group(1)
        self.assertIn(f"ほかは{UNLINKED_PHOTO_LABEL}です", caption)
        gallery = self.html[self.html.index('<ul class="lp-gallery">'):]
        gallery = gallery[:gallery.index("</ul>")]
        for item in re.findall(r'<li class="lp-gallery-item[^"]*">.*?</li>', gallery, re.S):
            kind = re.search(r'<span class="lp-gallery-kind">([^<]+)</span>', item).group(1)
            if "is-linked" in item:
                self.assertNotEqual(UNLINKED_PHOTO_LABEL, kind)
            else:
                self.assertEqual(UNLINKED_PHOTO_LABEL, kind)

    def test_work_card_gets_a_thumbnail_only_when_a_linked_photo_exists(self):
        gundam = re.search(r'<a class="lp-work-card" href="./characters/gundam/".*?</a>', self.html, re.S).group(0)
        self.assertIn('<span class="lp-work-thumb"><img ', gundam)
        self.assertIn('<span>写真</span>', gundam)
        yowapeda = re.search(r'<a class="lp-work-card" href="./characters/yowamushi-pedal/".*?</a>', self.html, re.S).group(0)
        self.assertNotIn("<img", yowapeda)
        self.assertIn('class="cm-lid"', yowapeda)

    def test_photos_do_not_push_the_seo_body_out(self):
        body = _visible_body(self.html)
        for word in ("ゾンビランドサガ", "源さくら", "佐賀県", "佐賀市", "唐人プラザビル"):
            self.assertIn(word, body)
        # 写真の後ろに見出しを隠さない: H1 と件数はヒーローの写真より前
        self.assertLess(self.html.index("<h1"), self.html.index('<ul class="lp-hero-mosaic">'))
        self.assertLess(self.html.index('class="cm-hero-note"'), self.html.index('<ul class="lp-hero-mosaic">'))

    def test_page_renders_without_the_photo_dataset(self):
        html = generate_html(self.character_records, self.gundam_records, Path(self.tmpdir.name) / "missing.ndjson")
        self.assertIn('<h1 id="lp-h1">', html)
        self.assertNotIn("<img", html)


class MobileLayoutCssTest(unittest.TestCase):
    """375px で写真と本文が崩れないための CSS（実測はスクリーンショットで確認）。"""

    @classmethod
    def setUpClass(cls):
        css = (Path(__file__).resolve().parents[2] / "apps/web/assets/character-work.css").read_text(encoding="utf-8")
        cls.mobile = css[css.index("@media (max-width: 700px)"):]
        cls.css = css

    def test_photo_frames_are_reserved_and_cropped(self):
        self.assertRegex(self.css, r"\.lp-hero-mosaic-item \{[^}]*aspect-ratio: 1")
        self.assertRegex(self.css, r"\.lp-gallery a \{[^}]*aspect-ratio: 1")
        self.assertIn("object-fit: cover", self.css)

    def test_phone_layout_uses_two_column_gallery_and_four_column_mosaic(self):
        self.assertIn(".lp-gallery { grid-template-columns: repeat(2, minmax(0, 1fr));", self.mobile)
        self.assertIn(".lp-hero-mosaic { grid-template-columns: repeat(4, minmax(0, 1fr));", self.mobile)
        # 並びは 見出し → 写真 → 探し方（写真の後ろに見出しを隠さない）
        self.assertIn('grid-template-areas: "copy" "photos" "hub";', self.css)



class RealDatasetTest(unittest.TestCase):
    """実データで、主要な固有名詞が初期表示の本文に出ることを確かめる。"""

    @classmethod
    def setUpClass(cls):
        docs = Path(__file__).resolve().parents[2] / "docs"
        cls.characters = load_active_manholes(docs / "character_manholes.ndjson")
        cls.gundam = load_active_manholes(docs / "gmanhole.ndjson")
        cls.html = generate_html(cls.characters, cls.gundam, docs / "design_manholes.ndjson")
        cls.body = _visible_body(cls.html)

    def test_every_work_prefecture_and_top_city_is_visible(self):
        for summary in build_work_summaries(self.characters, self.gundam):
            with self.subTest(work=summary["work"]):
                self.assertIn(summary["work"], self.body)
        for entry in build_prefecture_summaries(self.characters, self.gundam):
            with self.subTest(prefecture=entry["prefecture"]):
                self.assertIn(entry["prefecture"], self.body)
        cities = Counter(r.get("city") for r in self.characters + self.gundam if r.get("city"))
        for city, _ in cities.most_common(10):
            with self.subTest(city=city):
                self.assertIn(city, self.body)

    def test_large_prefectures_show_cities_and_featured_places(self):
        block = re.search(r'<section class="lp-place-pref" id="pref-saga".*?</section>', self.html, re.S).group(0)
        self.assertIn("<span>市町村</span>", block)
        self.assertIn("<span>主な設置場所</span>", block)
        self.assertIn('class="lp-place-pref lp-place-pref--mini" id="pref-aomori"', self.html)

    def test_real_data_shows_many_manhole_photos_all_small(self):
        imgs = re.findall(r'<img src="([^"]+)"', self.html)
        self.assertGreaterEqual(len(imgs), 12)
        self.assertTrue(all(url.endswith("?size=small") for url in imgs))
        self.assertIn('<ul class="lp-hero-mosaic">', self.html)
        self.assertIn('<ul class="lp-gallery">', self.html)

    def test_featured_place_names_are_searchable(self):
        """本文に出した「主な設置場所」の名前は、同じ県の絞り込み対象（li）にも入っている。"""
        for block in re.findall(r'<section class="lp-place-pref" .*?</section>', self.html, re.S):
            featured = re.search(r"<span>主な設置場所</span>(.*?)</p>", block).group(1)
            items = "".join(re.findall(r'<ul class="lp-location-list">(.*?)</ul>', block, re.S))
            for label in featured.split("、"):
                place = label.split("（")[0]
                with self.subTest(place=place):
                    self.assertIn(place, items)

    def test_links_to_every_generated_work_guide(self):
        for summary in build_work_summaries(self.characters, self.gundam):
            if summary.get("path"):
                with self.subTest(path=summary["path"]):
                    self.assertIn(f'href="./{summary["path"]}"', self.html)


if __name__ == "__main__":
    unittest.main()
