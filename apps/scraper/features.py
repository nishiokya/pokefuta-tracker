"""特集（/features/）のデータ読み込み。

特集は dataset/features/<slug>.json に1本1ファイルで手書きする。新しい特集はファイルを足すだけで、
/features/<slug>/ のページ・/features/ の一覧・sitemap に載る。
highlight_until までの間は /summary/ の上の方にも出す（新作の告知など、期間のある話題向け）。

特集を足したら `python3 apps/scraper/features.py` で、載せた蓋とグループ（県・市町村）が合っているかを確かめる
（同じ確認は test_generate_feature_pages でも毎回走る）。

書式:
    slug             URL に使う英小文字・数字・ハイフン（ファイル名と同じにする）
    title            見出し（h1）
    published        公開日 YYYY-MM-DD。これより前は出さない。一覧は新しい順
    highlight_until  任意。この日まで /summary/ に出す
    prefecture       任意。県ページへの導線と地図の計測に使う
    kicker / lead / description  任意。見出しの上の札・導入文・meta description
    date_label       任意。published の日付に添える言葉（既定「公開」）。過去の新作をあとから特集にするときは
                     published をお披露目の日にして「お披露目」とする（このときは記事の公開日として扱わない）
    date_text        任意。日まで分からないときの表示（例「2018年12月」）。published は並び順にだけ使う
    manholes         [{"id": "487", "note": "ひとこと"}] 並べた順に出す。お披露目直後で公式サイトにまだ蓋が無いときは
                     [] にして、設置場所は sections に書く（蓋の一覧・地図・見どころは出さない）。id が付いたら足す
    links            任意。[{"text": ..., "href": "/..." か "https://...", "external": true}]
    sections         任意。[{"heading": "見出し", "body": "本文（空行で段落を分ける）"}] 見どころの下に出す
                     本文は <slug>.html に HTML で書いてもよい（そのときは sections は書かない）。
                     書き方と使えるタグは dataset/features/README.md
    timeline         任意。[{"when": "2026年10月16日", "date": "2026-10-16"（任意）, "text": "お披露目式"}]
                     お披露目・設置予定などを見出しの直後に出す
    news             任意。[{"title": 記事名, "source": 媒体名, "href": "https://...", "date": "2026-10-16"（任意）}]
                     公式発表・報道。並べた順に出す（公式を先に）
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEATURES_DIR = ROOT / "dataset" / "features"
FEATURES_BASE = "/features/"
_OPTIONAL_TEXT_KEYS = ("prefecture", "kicker", "lead", "description", "date_label", "date_text")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    # Actions は UTC で動くので、日付の切り替わりは日本時間で見る
    return datetime.now(JST).date()


def feature_path(feature: dict) -> str:
    return f"{FEATURES_BASE}{feature['slug']}/"


def date_label(feature: dict) -> str:
    return feature.get("date_label") or "公開"


def article_date(feature: dict) -> str | None:
    """構造化データの datePublished に使える日付。published が記事の公開日のときだけ返す。"""
    return feature["published"] if not feature.get("date_label") else None


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_date(value: object) -> bool:
    return value is None or (isinstance(value, str) and bool(_DATE_RE.match(value)))


def _valid(entry: object, name: str) -> bool:
    if not isinstance(entry, dict):
        return False
    slug = entry.get("slug")
    return (
        isinstance(slug, str) and bool(_SLUG_RE.match(slug)) and slug == name
        and isinstance(entry.get("title"), str) and bool(entry["title"])
        and isinstance(entry.get("published"), str) and bool(_DATE_RE.match(entry["published"]))
        and (entry.get("highlight_until") is None
             or (isinstance(entry["highlight_until"], str) and bool(_DATE_RE.match(entry["highlight_until"]))))
        # body_html は <slug>.html を検査した結果だけが入る。JSON に直接書くと検査を素通りするので断る
        and "body_html" not in entry
        and isinstance(entry.get("manholes"), list)
        and all(
            isinstance(m, dict) and isinstance(m.get("id"), (str, int)) and str(m["id"]).strip()
            and isinstance(m.get("note", ""), str)
            for m in entry["manholes"]
        )
        # 任意の項目も型が違えば飛ばす（そのまま描くとデプロイが TypeError で止まる）
        and all(isinstance(entry.get(key, ""), str) for key in _OPTIONAL_TEXT_KEYS)
        and isinstance(entry.get("sections", []), list)
        and all(
            isinstance(sec, dict) and isinstance(sec.get("heading"), str) and sec["heading"]
            and isinstance(sec.get("body"), str) and sec["body"]
            for sec in entry.get("sections", [])
        )
        and isinstance(entry.get("timeline", []), list)
        and all(
            isinstance(item, dict) and _nonempty_str(item.get("when")) and _nonempty_str(item.get("text"))
            and _optional_date(item.get("date"))
            for item in entry.get("timeline", [])
        )
        and isinstance(entry.get("news", []), list)
        and all(
            isinstance(item, dict) and _nonempty_str(item.get("title")) and _nonempty_str(item.get("source"))
            and _nonempty_str(item.get("href")) and item["href"].startswith("https://")
            and _optional_date(item.get("date"))
            for item in entry.get("news", [])
        )
        and isinstance(entry.get("links", []), list)
        and all(
            isinstance(link, dict) and isinstance(link.get("text"), str)
            and isinstance(link.get("href"), str) and isinstance(link.get("external", False), bool)
            for link in entry.get("links", [])
        )
    )


def _safe_href(href: str) -> bool:
    # "/\" はブラウザが "//" と同じに読んで別のサイトへ飛ぶので、\ ごと断る
    return "\\" not in href and (
        href.startswith("https://") or (href.startswith("/") and not href.startswith("//"))
    )


# 本文の HTML で使えるタグ。ここに無いタグ・属性は通さない（同じドメインでログインを扱うので、
# <script> や onclick が入ると利用者のログインを盗めてしまう）
BODY_TAGS = {
    "section", "h2", "h3", "p", "ul", "ol", "li", "a", "strong", "em", "br",
    "table", "thead", "tbody", "tr", "th", "td",
}
_VOID_TAGS = {"br"}
# 文字を直接書けないタグ（<p> や <li> で包む）
_NO_TEXT_TAGS = {"section", "ul", "ol", "table", "thead", "tbody", "tr"}


class _BodyParser(HTMLParser):
    """本文の HTML を読み、許したタグだけで組み直す。問題は「何行目: 何がだめか」で集める。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.problems: list[str] = []
        self.stack: list[str] = []
        self.sections = 0
        self.expect_h2 = False

    def _problem(self, text: str) -> None:
        self.problems.append(f"{self.getpos()[0]}行目: {text}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in BODY_TAGS:
            self._problem(f"<{tag}> は使えない")
            return
        href = None
        for name, value in attrs:
            if tag == "a" and name == "href":
                href = value or ""
            else:
                self._problem(f"<{tag}> の {name} 属性は使えない")
        if tag == "section":
            if self.stack:
                self._problem("<section> は一番外側に並べる（中に入れない）")
            self.sections += 1
            self.expect_h2 = True
            self.out.append(f'<section class="feature-section" aria-labelledby="section-{self.sections}-heading">')
        else:
            if not self.stack:
                self._problem(f"<{tag}> が <section> の外にある")
            elif tag == "h2" and not self.expect_h2:
                self._problem("<h2> は <section> の最初に1つだけ")
            elif tag != "h2" and self.expect_h2:
                self._problem("<section> は <h2> の見出しから始める")
            self.expect_h2 = False
            if tag == "h2":
                self.out.append(f'<h2 id="section-{self.sections}-heading">')
            elif tag == "a":
                if href is None or not _safe_href(href):
                    self._problem(f'<a href="{href or ""}"> のリンク先は https:// か / で始める')
                    href = ""
                external = href.startswith("https://")
                self.out.append(
                    f'<a href="{escape(href)}"'
                    + (' target="_blank" rel="noopener noreferrer"' if external else "") + ">"
                )
            else:
                self.out.append(f"<{tag}>")
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <br/> のような書き方
        self.handle_starttag(tag, attrs)
        if tag in BODY_TAGS and tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in BODY_TAGS or tag in _VOID_TAGS:
            return
        if not self.stack or self.stack[-1] != tag:
            opened = f"（いま閉じるのは </{self.stack[-1]}>）" if self.stack else ""
            self._problem(f"</{tag}> の閉じ方が合わない{opened}")
            if tag not in self.stack:
                return
            while self.stack[-1] != tag:
                self.out.append(f"</{self.stack.pop()}>")
        self.stack.pop()
        if self.expect_h2 and tag == "section":
            self._problem("<section> に <h2> の見出しが無い")
            self.expect_h2 = False
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not data.strip():
            self.out.append(data)
            return
        if not self.stack:
            self._problem(f"文字「{data.strip()[:10]}」が <section> の外にある")
        elif self.stack[-1] in _NO_TEXT_TAGS:
            self._problem(f"文字「{data.strip()[:10]}」は <p> や <li> などの中に書く")
        self.out.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        # <!-- メモ --> は書いてよい。ページには出さない
        pass

    def handle_decl(self, decl: str) -> None:
        self._problem("<!DOCTYPE> などは書かない（本文の部分だけを書く）")

    def unknown_decl(self, data: str) -> None:
        self._problem("<![...]> は使えない")

    def handle_pi(self, data: str) -> None:
        self._problem("<?...> は使えない")


def parse_body_html(text: str) -> tuple[str, list[str]]:
    """本文の HTML を (ページに出す HTML, 問題の一覧) にする。問題があればその特集は出さない。"""
    parser = _BodyParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        # HTMLParser は "<![foo]>" のような崩れた宣言で例外を投げる（3.11 は AssertionError、3.9 は
        # NotImplementedError と版で違う）。デプロイを止めずに問題として返す
        return "", [*parser.problems, f"{parser.getpos()[0]}行目: HTML として読めない（{exc}）"]
    problems = parser.problems
    if parser.stack:
        problems.append(f"最後まで閉じていないタグがある: {' '.join(f'<{t}>' for t in parser.stack)}")
    if not parser.sections:
        problems.append("<section> が1つも無い")
    return "".join(parser.out).strip(), problems


def check_body_files(features_dir: Path = DEFAULT_FEATURES_DIR) -> list[str]:
    """dataset/features/*.html の書き方の問題を文章で返す（無ければ空）。"""
    problems: list[str] = []
    for path in sorted(features_dir.glob("*.html")) if features_dir.exists() else []:
        json_path = path.with_suffix(".json")
        if not json_path.exists():
            problems.append(f"{path.name}: 同じ名前の {json_path.name} が無い")
            continue
        try:
            entry = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entry = {}
        if isinstance(entry, dict) and entry.get("sections"):
            problems.append(f"{path.name}: {json_path.name} にも sections がある。本文はどちらか一方に書く")
        _, found = parse_body_html(path.read_text(encoding="utf-8"))
        problems.extend(f"{path.name} {p}" for p in found)
    return problems


def safe_links(feature: dict) -> list[dict]:
    return [
        link for link in feature.get("links", []) or []
        if isinstance(link, dict) and link.get("text")
        and str(link.get("href", "")).startswith(("/", "https://"))
        and not str(link.get("href", "")).startswith("//")
    ]


def load_features(
    records_by_id: dict[str, dict],
    features_dir: Path = DEFAULT_FEATURES_DIR,
    today: date | None = None,
) -> list[dict]:
    """公開日を過ぎた特集を新しい順に返す。各特集の "records" に蓋のレコードを並べた順で入れる。

    書式が崩れている・載せた蓋がデータに無い特集は、壊れたページを出さないよう丸ごと飛ばす。
    """
    today_iso = (today or _today_jst()).isoformat()
    features = []
    for path in sorted(features_dir.glob("*.json")) if features_dir.exists() else []:
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[features] WARNING: 読めないので飛ばす: {path.name} ({exc})", file=sys.stderr)
            continue
        if not _valid(entry, path.stem):
            print(f"[features] WARNING: 書式が違うので飛ばす: {path.name}", file=sys.stderr)
            continue
        if entry["published"] > today_iso:
            continue
        ids = [str(m["id"]).strip() for m in entry["manholes"]]
        missing = [mid for mid in ids if mid not in records_by_id]
        if missing:
            print(f"[features] WARNING: 蓋が見つからないので飛ばす: {path.name} {missing}", file=sys.stderr)
            continue
        body_path = path.with_suffix(".html")
        if body_path.exists():
            if entry.get("sections"):
                print(f"[features] WARNING: 本文が sections と {body_path.name} の両方にあるので飛ばす: {path.name}",
                      file=sys.stderr)
                continue
            body, problems = parse_body_html(body_path.read_text(encoding="utf-8"))
            if problems:
                print(f"[features] WARNING: {body_path.name} の書き方が違うので飛ばす: {problems}", file=sys.stderr)
                continue
            entry = {**entry, "body_html": body}
        features.append({**entry, "records": [records_by_id[mid] for mid in ids]})
    features.sort(key=lambda f: (f["published"], f["slug"]), reverse=True)
    return features


def highlighted(features: list[dict], today: date | None = None) -> list[dict]:
    """/summary/ に出す特集（highlight_until が今日以降）。"""
    today_iso = (today or _today_jst()).isoformat()
    return [f for f in features if f.get("highlight_until") and f["highlight_until"] >= today_iso]


def _fold_kana(text: str) -> str:
    """「金ヶ崎」と「金ケ崎」のような表記ゆれをそろえる。"""
    return text.replace("ヶ", "ケ").replace("ヵ", "カ").replace("ゑ", "え")


def _city_core(city: str) -> str:
    """「三重郡菰野町」「桑名市」「台東区上野」→「菰野」「桑名」「台東」。本文に出てくるかの照合用。"""
    core = _fold_kana(city).split("郡")[-1]
    for suffix in ("市", "町", "村", "区"):
        if suffix in core:
            core = core.split(suffix)[0]
            break
    return core


def check_feature_groups(features: list[dict], min_listed_ratio: float = 0.5) -> list[str]:
    """特集に載せた蓋とそのグループが合っているかの簡易チェック。問題を文章で返す（無ければ空）。

    - 特集の prefecture と蓋の県が違う
    - 同じ蓋が1つの特集に二重に入っている／別の特集にも入っている
    - 導入文などに市町村名を並べている特集で、載せた蓋の市町村が本文に出てこない
      （半分以上の蓋の市町村が本文にある特集だけを「市町村を並べている」とみなす。全35市町村のような特集は対象外）
    """
    problems: list[str] = []
    owner: dict[str, str] = {}
    for f in features:
        slug, records = f["slug"], f["records"]
        ids = [str(r.get("id")) for r in records]
        for mid in sorted({i for i in ids if ids.count(i) > 1}):
            problems.append(f"{slug}: 蓋 {mid} が二重に入っている")
        for mid in dict.fromkeys(ids):
            if mid in owner:
                problems.append(f"{slug}: 蓋 {mid} は {owner[mid]} にも入っている")
            else:
                owner[mid] = slug
        pref = f.get("prefecture")
        if pref:
            for r in records:
                if r.get("prefecture") != pref:
                    problems.append(f"{slug}: 蓋 {r.get('id')} は{r.get('prefecture')}（特集は{pref}）")
        text = _fold_kana(" ".join(
            [f.get("title", ""), f.get("lead", ""), f.get("description", "")]
            + [t.get("text", "") for t in f.get("timeline", [])]
        ))
        cores = {str(r.get("id")): _city_core(str(r.get("city", ""))) for r in records}
        listed = [mid for mid, core in cores.items() if core and core in text]
        if cores and len(listed) / len(cores) >= min_listed_ratio:
            for mid, core in cores.items():
                if mid not in listed:
                    problems.append(f"{slug}: 蓋 {mid}（{core}）の市町村が本文に無い。ID の書き間違いかもしれない")
    return problems


if __name__ == "__main__":
    # 手元での確認用: python3 apps/scraper/features.py
    import argparse
    parser = argparse.ArgumentParser(description="特集の蓋とグループの簡易チェック")
    parser.add_argument("--manholes", type=Path, default=ROOT / "docs" / "pokefuta.ndjson")
    args = parser.parse_args()
    by_id: dict[str, dict] = {}
    for line in args.manholes.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec.get("status", "active") == "active":
                by_id[str(rec.get("id", ""))] = {**by_id.get(str(rec.get("id", "")), {}), **rec}
    loaded = load_features(by_id, today=date(2099, 1, 1))
    found = check_body_files() + check_feature_groups(loaded)
    print(f"[features] {len(loaded)} 本の特集・{sum(len(f['records']) for f in loaded)} 枚を確認")
    for p in found:
        print("  NG", p)
    if not found:
        print("  OK 問題なし")
    raise SystemExit(1 if found else 0)
