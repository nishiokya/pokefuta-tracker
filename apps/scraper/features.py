"""特集（/features/）のデータ読み込み。

特集は dataset/features/<slug>.json に1本1ファイルで手書きする。新しい特集はファイルを足すだけで、
/features/<slug>/ のページ・/features/ の一覧・sitemap に載る。
highlight_until までの間は /summary/ の上の方にも出す（新作の告知など、期間のある話題向け）。

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
    manholes         [{"id": "487", "note": "ひとこと"}] 並べた順に出す
    links            任意。[{"text": ..., "href": "/..." か "https://...", "external": true}]
    sections         任意。[{"heading": "見出し", "body": "本文（空行で段落を分ける）"}] 見どころの下に出す
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
        and isinstance(entry.get("manholes"), list) and bool(entry["manholes"])
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
        features.append({**entry, "records": [records_by_id[mid] for mid in ids]})
    features.sort(key=lambda f: (f["published"], f["slug"]), reverse=True)
    return features


def highlighted(features: list[dict], today: date | None = None) -> list[dict]:
    """/summary/ に出す特集（highlight_until が今日以降）。"""
    today_iso = (today or _today_jst()).isoformat()
    return [f for f in features if f.get("highlight_until") and f["highlight_until"] >= today_iso]
