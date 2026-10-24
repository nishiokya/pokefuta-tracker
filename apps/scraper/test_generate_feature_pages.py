from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apps.scraper import features as FEATURES
from apps.scraper import generate_feature_pages as MODULE
from apps.scraper import generate_sitemap as SITEMAP
from apps.scraper import generate_summary_pages as SUMMARY


def _crumbs(html: str) -> list[tuple[str, str]]:
    """ページの JSON-LD からパンくずの (名前, URL) を取り出す。"""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        nodes = data.get("@graph", [data])
        for node in nodes:
            crumb = node if node.get("@type") == "BreadcrumbList" else node.get("breadcrumb")
            if crumb:
                return [(i["name"], i["item"]) for i in crumb["itemListElement"]]
    return []


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
            _feature("timeline-no-text", timeline=[{"when": "10月16日"}]),
            _feature("timeline-bad-date", timeline=[{"when": "10月16日", "text": "式", "date": "10/16"}]),
            _feature("news-http", news=[{"title": "記事", "source": "新聞", "href": "http://example.com/"}]),
            _feature("news-no-source", news=[{"title": "記事", "href": "https://example.com/"}]),
            _feature("section-empty", sections=[{"heading": "見出し", "body": ""}]),
            # 本文の HTML は <slug>.html だけ。JSON に書くと検査を素通りしてしまう
            _feature("body-in-json", body_html="<script>alert(1)</script>"),
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


class BodyHtmlTests(unittest.TestCase):
    """本文を <slug>.html に HTML で書いたとき。許したタグだけで組み直し、ほかは特集ごと止める。"""

    def test_sections_get_heading_ids_and_external_links_open_in_a_new_tab(self) -> None:
        body, problems = FEATURES.parse_body_html(
            "<!-- メモは出さない -->\n<section>\n  <h2>行き方</h2>\n  <p>船は&lt;15時間&gt;。<br/>"
            '<a href="https://example.com/">公式</a>・<a href="/prefectures/okinawa/">県</a></p>\n</section>\n'
            "<section><h2>宿</h2><ul><li><strong>2軒</strong>だけ</li></ul></section>\n"
        )
        self.assertEqual(problems, [])
        self.assertNotIn("メモ", body)
        self.assertIn('<section class="feature-section" aria-labelledby="section-1-heading">', body)
        self.assertIn('<h2 id="section-2-heading">宿</h2>', body)
        self.assertIn("船は&lt;15時間&gt;。<br>", body)
        self.assertIn('<a href="https://example.com/" target="_blank" rel="noopener noreferrer">公式</a>', body)
        self.assertIn('<a href="/prefectures/okinawa/">県</a>', body)

    def test_dangerous_or_broken_html_is_reported_with_line_numbers(self) -> None:
        cases = {
            "<section><h2>a</h2><script>alert(1)</script></section>": "<script> は使えない",
            '<section><h2>a</h2><p onclick="x()">b</p></section>': "onclick 属性は使えない",
            '<section><h2>a</h2><p style="color:red">b</p></section>': "style 属性は使えない",
            '<section><h2>a</h2><p><a href="javascript:alert(1)">b</a></p></section>': "https:// か / で始める",
            '<section><h2>a</h2><p><a href="//evil.example/">b</a></p></section>': "https:// か / で始める",
            '<section><h2>a</h2><p><a href="/\\evil.example/">b</a></p></section>': "https:// か / で始める",
            "<section><h2>a</h2><iframe src=x></iframe></section>": "<iframe> は使えない",
            "<section><h2>a</h2><p>b</section>": "閉じ方が合わない",
            "<section><h2>a</h2><p>b</p>": "閉じていないタグ",
            "<section><p>b</p></section>": "<h2> の見出しから始める",
            "<section><h2>a</h2><h2>b</h2></section>": "<h2> は <section> の最初に1つだけ",
            "<section><h2>a</h2>じか書き</section>": "<p> や <li> などの中に書く",
            "<p>外</p>": "<section> の外にある",
            "<!DOCTYPE html><section><h2>a</h2></section>": "本文の部分だけを書く",
            "": "<section> が1つも無い",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                _, problems = FEATURES.parse_body_html(text)
                self.assertTrue(any(expected in p for p in problems), problems)
        # 崩れた宣言は版で扱いが違う（3.9・3.11 は HTMLParser が例外、3.14 はコメント扱い）。どれでも止まらず中身は出さない
        body, problems = FEATURES.parse_body_html("<section><h2>a</h2><![foo]></section>")
        self.assertTrue(problems or "foo" not in body, (body, problems))
        _, problems = FEATURES.parse_body_html("<section>\n  <h2>a</h2>\n  <p><b>太字</b></p>\n</section>")
        self.assertEqual(problems, ["3行目: <b> は使えない"])

    NEWS = (
        '<section id="news">\n  <h2>公式発表・ニュース</h2>\n  <ul>\n'
        '    <li><a href="https://example.com/a">お披露目の記事</a><small>沖縄の新聞・'
        '<time datetime="2026-10-16">2026年10月16日</time></small></li>\n'
        '    <li><a href="https://example.com/b">公式</a><small>ポケモン公式</small></li>\n'
        "  </ul>\n</section>\n"
    )

    def test_news_section_becomes_the_news_list(self) -> None:
        body, news, problems = FEATURES.parse_body("<section><h2>行き方</h2><p>船で</p></section>\n" + self.NEWS)
        self.assertEqual(problems, [])
        self.assertNotIn("お披露目の記事", body)
        self.assertEqual(news, [
            {"title": "お披露目の記事", "source": "沖縄の新聞", "href": "https://example.com/a", "date": "2026-10-16"},
            {"title": "公式", "source": "ポケモン公式", "href": "https://example.com/b"},
        ])
        # ニュースだけの .html でもよい。ニュースの節が無ければ None（JSON の news を使う）
        self.assertEqual(FEATURES.parse_body(self.NEWS)[2], [])
        self.assertIsNone(FEATURES.parse_body("<section><h2>a</h2><p>b</p></section>")[1])

    def test_broken_news_section_is_reported(self) -> None:
        ok_item = '<li><a href="https://example.com/">記事</a><small>新聞</small></li>'

        def news(items: str, heading: str = "公式発表・ニュース", attrs: str = 'id="news"') -> str:
            return f"<section {attrs}><h2>{heading}</h2><ul>{items}</ul></section>"

        cases = {
            news('<li><a href="http://example.com/">記事</a><small>新聞</small></li>'): "https:// で始める",
            news('<li><a href="/prefectures/">記事</a><small>新聞</small></li>'): "https:// で始める",
            news('<li><a href="https://example.com/">記事</a></li>'): "媒体名を書く",
            news('<li><a href="https://example.com/"></a><small>新聞</small></li>'): "見出しを書く",
            news('<li><a href="https://example.com/">記事</a><small>新聞・'
                 '<time datetime="2026-10-16">10月16日</time></small></li>'): "2026年10月16日 と書く",
            news('<li><a href="https://example.com/">記事</a><small>新聞・'
                 '<time datetime="10/16">10月16日</time></small></li>'): "2026-10-16 の形",
            news(ok_item, heading="ニュース"): "見出しは <h2>公式発表・ニュース</h2>",
            news(ok_item, attrs='id="top"'): 'id は "news" だけ',
            news(ok_item + "<li><p>本文</p></li>"): "ニュースの節では <p> は使えない",
            news(""): "記事が1つも無い",
            news(ok_item) + news(ok_item): '<section id="news"> は1つだけ',
            "<section><h2>a</h2><p><small>小さく</small></p></section>": "ニュースの節（<section id=\"news\">）の外",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                problems = FEATURES.parse_body(text)[2]
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_news_from_html_is_drawn_like_json_news_and_cannot_be_doubled(self) -> None:
        news_json = [{"title": "記事", "source": "新聞", "href": "https://example.com/"}]
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(Path(tmp), _feature("html-news"), _feature("both-news", news=news_json))
            (d / "html-news.html").write_text(self.NEWS, encoding="utf-8")
            (d / "both-news.html").write_text(self.NEWS, encoding="utf-8")
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
            problems = FEATURES.check_body_files(d)
        self.assertEqual([f["slug"] for f in loaded], ["html-news"])
        html = MODULE.build_feature_page(loaded[0], {}, [])
        self.assertIn(
            '<a href="https://example.com/a" target="_blank" rel="noopener noreferrer" '
            'data-track="feature_news_click" data-surface="news" data-destination="沖縄の新聞">お披露目の記事</a>', html)
        self.assertIn("沖縄の新聞・<time", html)
        # ニュースはページの最後（蓋の一覧・地図より後）のまま
        self.assertLess(html.index('id="manhole-list"'), html.index('id="news-heading"'))
        self.assertTrue(any(p.startswith("both-news.html:") and "news" in p for p in problems), problems)

    def test_loader_uses_the_html_body_and_skips_broken_or_doubled_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(Path(tmp), _feature("html"), _feature("broken"),
                       _feature("both", sections=[{"heading": "見出し", "body": "本文"}]))
            (d / "html.html").write_text("<section><h2>行き方</h2><p>船で</p></section>", encoding="utf-8")
            (d / "broken.html").write_text("<section><h2>行き方</h2><script></script></section>", encoding="utf-8")
            (d / "both.html").write_text("<section><h2>行き方</h2><p>船で</p></section>", encoding="utf-8")
            (d / "orphan.html").write_text("<section><h2>a</h2></section>", encoding="utf-8")
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
            problems = FEATURES.check_body_files(d)
        self.assertEqual([f["slug"] for f in loaded], ["html"])
        html = MODULE.build_feature_page(loaded[0], {}, [])
        self.assertIn('<h2 id="section-1-heading">行き方</h2><p>船で</p>', html)
        self.assertLess(html.index('id="notes-heading"'), html.index('id="section-1-heading"'))
        self.assertTrue(any(p.startswith("broken.html 1行目: <script>") for p in problems), problems)
        self.assertTrue(any(p.startswith("both.html:") for p in problems), problems)
        self.assertTrue(any(p.startswith("orphan.html:") for p in problems), problems)


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

    def test_date_label_marks_unveiling_dates_and_drops_date_published(self) -> None:
        """過去の新作をあとから特集にしたときは、日付をお披露目の日として出し、記事の公開日とは言わない。"""
        plain = MODULE.build_feature_page(self.feature, {}, [])
        self.assertIn("2026年10月17日公開</time>", plain)
        self.assertIn('"datePublished": "2026-10-17"', plain)
        unveiled = MODULE.build_feature_page({**self.feature, "date_label": "お披露目"}, {}, [])
        self.assertIn("2026年10月17日お披露目</time>", unveiled)
        self.assertNotIn("datePublished", unveiled)
        index = MODULE.build_index_page([{**self.feature, "date_label": "お披露目"}])
        self.assertIn("2026年10月17日お披露目 / 沖縄県", index)
        # 市区町村ページと共用の <head> でサイト名が二重にならず、個別ページには付かない
        self.assertIn("<title>ポケふた特集｜ポケふた図鑑</title>", index)
        self.assertNotIn("ポケふた図鑑</title>", plain)
        # パンくずは画面と同じ並びで JSON-LD にも出す。Article は @graph で残す
        self.assertEqual(
            [name for name, _ in _crumbs(plain)], ["ポケふた図鑑", "特集", self.feature["title"]]
        )
        self.assertIn('"@type": "Article"', plain)
        self.assertEqual([name for name, _ in _crumbs(index)], ["ポケふた図鑑", "特集"])
        self.assertNotIn("datePublished", index)

    def test_index_puts_highlighted_features_in_the_new_section_first(self) -> None:
        old = {**self.feature, "slug": "old-test", "title": "むかしの特集", "highlight_until": None}
        index = MODULE.build_index_page([self.feature, old], today=date(2026, 10, 23))
        self.assertIn('id="new"', index)
        self.assertLess(index.index('id="new"'), index.index('href="/features/old-test/"'))
        self.assertEqual(index.count('href="/features/okinawa-test/"'), 1)
        self.assertIn("これまでの特集", index)
        # 期間が終わったら新作欄は消え、ふつうの一覧に戻る
        later = MODULE.build_index_page([self.feature, old], today=date(2027, 2, 1))
        self.assertNotIn('id="new"', later)
        self.assertIn("特集の一覧", later)

    def test_sections_are_split_into_paragraphs(self) -> None:
        feature = {**self.feature, "sections": [{"heading": "行き方", "body": "飛行機で1時間。\n\n船は<15時間>。"}]}
        html = MODULE.build_feature_page(feature, {}, [])
        self.assertIn('<h2 id="section-1-heading">行き方</h2>', html)
        self.assertIn("<p>飛行機で1時間。</p>", html)
        self.assertIn("<p>船は&lt;15時間&gt;。</p>", html)
        self.assertLess(html.index('id="notes-heading"'), html.index('id="section-1-heading"'))

    def test_timeline_follows_the_hero_and_news_open_in_a_new_tab(self) -> None:
        feature = {
            **self.feature,
            "timeline": [{"when": "2026年10月16日", "date": "2026-10-16", "text": "お披露目式"},
                         {"when": "10月下旬頃", "text": "設置予定"}],
            "news": [{"title": "お披露目の記事", "source": "沖縄の新聞", "date": "2026-10-16",
                      "href": "https://example.com/news"}],
        }
        html = MODULE.build_feature_page(feature, {}, [])
        self.assertIn('<time datetime="2026-10-16">2026年10月16日</time><span>お披露目式</span>', html)
        self.assertIn('<span class="feature-when">10月下旬頃</span>', html)
        self.assertLess(html.index("</header>"), html.index('id="timeline-heading"'))
        self.assertLess(html.index('id="timeline-heading"'), html.index('id="notes-heading"'))
        self.assertIn('href="https://example.com/news" target="_blank" rel="noopener noreferrer"', html)
        self.assertIn("沖縄の新聞・<time", html)
        # 書いていない特集には欄ごと出さない
        plain = MODULE.build_feature_page(self.feature, {}, [])
        self.assertNotIn("timeline-heading", plain)
        self.assertNotIn("news-heading", plain)

    def test_feature_without_manholes_yet_drops_lid_sections(self) -> None:
        """お披露目直後で公式に蓋がまだ無い特集は、日程・設置場所・ニュースだけで出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            d = _write(Path(tmp), _feature("planned", manholes=[]))
            loaded = FEATURES.load_features(RECORDS, d, today=date(2026, 10, 17))
        self.assertEqual([f["slug"] for f in loaded], ["planned"])
        html = MODULE.build_feature_page(
            {**loaded[0], "sections": [{"heading": "設置場所", "body": "土佐市：土佐市役所"}]}, {}, []
        )
        self.assertIn("土佐市役所", html)
        for absent in ("notes-heading", 'id="manhole-list"', 'id="prefecture-map"', "ポケふたを見る", '"mainEntity"'):
            self.assertNotIn(absent, html)
        self.assertIn("設置場所の一覧", MODULE.build_index_page(loaded))
        self.assertNotIn("ポケふた0枚", MODULE.build_index_page(loaded))

    def test_index_thumbs_keep_lids_without_photos_and_plus_only_counts_overflow(self) -> None:
        """写真の無い蓋は灰色の丸で並べ、「+n」は6枚を超えた分だけにする（5枚で「+2」と出ないように）。"""
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            (image_dir / "1_latest.jpeg").write_bytes(b"x")
            five = [_record(str(i), "国頭") for i in range(1, 6)]
            html = MODULE._thumbs_html(five, image_dir)
            self.assertEqual(html.count("<img"), 1)
            self.assertEqual(html.count("feature-thumb-empty"), 4)
            self.assertNotIn("stop-thumb-more", html)
            nine = [_record(str(i), "国頭") for i in range(1, 10)]
            html = MODULE._thumbs_html(nine, image_dir)
            self.assertEqual(html.count("<img") + html.count("feature-thumb-empty"), 6)
            self.assertIn('title="ほか3枚">+3</span>', html)

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
        self.assertEqual(FEATURES.check_body_files(), [])


class FeatureGroupCheckTests(unittest.TestCase):
    """特集に載せた蓋とグループ（県・市町村）が合っているかの簡易チェック。"""

    def _feature(self, slug: str, records: list[dict], **extra) -> dict:
        return {"slug": slug, "prefecture": "沖縄県", "title": "", "lead": "国頭村・大宜味村に置かれました。",
                "records": records, **extra}

    def test_real_features_have_no_group_problems(self) -> None:
        records = {str(r["id"]): r for r in SUMMARY.load_records(SUMMARY.NDJSON)}
        loaded = FEATURES.load_features(records, today=date(2099, 1, 1))
        self.assertEqual(FEATURES.check_feature_groups(loaded), [])

    def test_wrong_city_id_is_reported(self) -> None:
        wrong = _record("999", "那覇")
        problems = FEATURES.check_feature_groups([
            self._feature("a", [_record("487", "国頭"), _record("488", "大宜味"), wrong])
        ])
        self.assertEqual(len(problems), 1)
        self.assertIn("蓋 999（那覇）", problems[0])

    def test_wrong_prefecture_and_duplicates_are_reported(self) -> None:
        other = {**_record("100", "国頭"), "prefecture": "長野県"}
        problems = FEATURES.check_feature_groups([
            self._feature("a", [_record("487", "国頭"), _record("487", "国頭"), other]),
            self._feature("b", [_record("488", "大宜味")], lead="大宜味村と国頭村"),
            self._feature("c", [_record("488", "大宜味")], lead="大宜味村"),
        ])
        joined = "\n".join(problems)
        self.assertIn("a: 蓋 487 が二重に入っている", joined)
        self.assertIn("a: 蓋 100 は長野県（特集は沖縄県）", joined)
        self.assertIn("c: 蓋 488 は b にも入っている", joined)

    def test_kana_variants_and_county_names_match(self) -> None:
        recs = [{**_record("466", "金ヶ崎"), "prefecture": "岩手県"},
                {**_record("386", "三重郡菰野町"), "prefecture": "岩手県"}]
        feature = self._feature("a", recs, prefecture="岩手県", lead="金ケ崎町と菰野町")
        self.assertEqual(FEATURES.check_feature_groups([feature]), [])

    def test_features_that_do_not_list_cities_are_skipped(self) -> None:
        recs = [_record(str(i), f"町{i}") for i in range(10)]
        self.assertEqual(FEATURES.check_feature_groups([self._feature("a", recs, lead="全35市町村")]), [])


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
