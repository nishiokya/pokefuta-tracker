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
    manholes         [{"id": "487", "note": "ひとこと"}] 並べた順に出す
    links            任意。[{"text": ..., "href": "/..." か "https://...", "external": true}]
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
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    # Actions は UTC で動くので、日付の切り替わりは日本時間で見る
    return datetime.now(JST).date()


def feature_path(feature: dict) -> str:
    return f"{FEATURES_BASE}{feature['slug']}/"


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
        and all(isinstance(m, dict) and str(m.get("id", "")).strip() for m in entry["manholes"])
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
