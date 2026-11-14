"""投稿者名の前のアイコンと、後ろの称号（詳細ページのクレジット用）。

- アイコン: 写真館の /profile で本人が選んだ公開写真。export_app_snapshot.py が日次で
  docs/api/avatars.json（公開ID → 写真ID）に書き出す。画像は写真館の
  /api/photo/<id>?size=small&strict=1（CDN に1日置かれる）を使う。未設定の人は人のマーク
- 称号: docs/api/regulars.json の users（公開ID → 段階）。名前とアイコンは写真館の
  src/lib/regular-badges.ts（REGULAR_BADGE_LABEL / REGULAR_BADGE_ICON）と同じにする

どちらもページを作るときに焼き込み、見る人のブラウザからは Supabase を読まない。
ファイルが無い・壊れているときは、アイコンは人のマーク、称号は無しで出す（ページは止めない）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[2]
AVATARS_PATH = REPO_ROOT / "docs" / "api" / "avatars.json"
REGULARS_PATH = REPO_ROOT / "docs" / "api" / "regulars.json"

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

TIER_LABEL = {
    "legend": "🏆 LEGEND",
    "crown": "👑 MASTER",
    "ranger": "⭐ RANGER",
    "regular": "🧭 EXPLORER",
    "rookie": "🌱 ROOKIE",
}
TIER_ICON = {tier: label.split(" ", 1)[0] for tier, label in TIER_LABEL.items()}
TIER_NAME = {tier: label.split(" ", 1)[1] for tier, label in TIER_LABEL.items()}

_avatars: dict[str, str] | None = None
_tiers: dict[str, str] | None = None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def set_sources(avatars: dict[str, str] | None = None, tiers: dict[str, str] | None = None) -> None:
    """テスト用。None を渡すと次に使うときファイルから読み直す。"""
    global _avatars, _tiers
    _avatars = avatars
    _tiers = tiers


def _avatar_map() -> dict[str, str]:
    global _avatars
    if _avatars is None:
        raw = _read_json(AVATARS_PATH).get("avatars")
        _avatars = {
            str(k).lower(): str(v).lower()
            for k, v in (raw.items() if isinstance(raw, dict) else [])
            if UUID_RE.fullmatch(str(k)) and UUID_RE.fullmatch(str(v))
        }
    return _avatars


def _tier_map() -> dict[str, str]:
    global _tiers
    if _tiers is None:
        raw = _read_json(REGULARS_PATH).get("users")
        _tiers = {
            str(k).lower(): str(v)
            for k, v in (raw.items() if isinstance(raw, dict) else [])
            # 配列・オブジェクトの値は辞書の in で TypeError になるので、文字列だけを見る
            if isinstance(v, str) and v in TIER_LABEL
        }
    return _tiers


def _pid(public_user_id: object) -> str:
    pid = str(public_user_id or "").strip().lower()
    return pid if UUID_RE.fullmatch(pid) else ""


def avatar_url(photo_id: str) -> str:
    return f"https://pokefuta.com/api/photo/{quote(photo_id)}?size=small&strict=1"


def avatar_html(public_user_id: object) -> str:
    """名前の前に置く丸いアイコン。未設定（と読めなかったとき）は人のマーク。"""
    photo_id = _avatar_map().get(_pid(public_user_id))
    if photo_id:
        # strict=1 は縮小版が無い写真で 404 を返す。そのときは画像を外して人のマークに戻す
        return (
            "<span class='poster-avatar' aria-hidden='true'>"
            f"<img src=\"{escape(avatar_url(photo_id))}\" alt=\"\" width=\"16\" height=\"16\""
            " loading=\"lazy\" decoding=\"async\" onerror=\"this.remove()\">"
            "</span>"
        )
    return "<span class='poster-avatar' aria-hidden='true'></span>"


def tier_of(public_user_id: object) -> str | None:
    return _tier_map().get(_pid(public_user_id))


def tier_badge_html(public_user_id: object, *, icon_only: bool = False) -> str:
    """名前の後ろに置く称号。称号の無い人は空文字。"""
    tier = tier_of(public_user_id)
    if not tier:
        return ""
    if icon_only:
        return (
            f"<span class='poster-tier poster-tier--icon poster-tier--{tier}'"
            f" title=\"{TIER_NAME[tier]}\" aria-label=\"{TIER_NAME[tier]}\">{TIER_ICON[tier]}</span>"
        )
    return f"<span class='poster-tier poster-tier--{tier}'>{TIER_LABEL[tier]}</span>"


POSTER_IDENTITY_CSS = """
    .poster-avatar {
      display: inline-block;
      flex-shrink: 0;
      width: 16px;
      height: 16px;
      margin-right: 4px;
      vertical-align: -3px;
      border-radius: 50%;
      overflow: hidden;
      background: rgba(255, 255, 255, .85) no-repeat center / 12px
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238C6A4A' stroke-width='2.4' stroke-linecap='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M4 21a8 8 0 0 1 16 0'/%3E%3C/svg%3E");
    }
    .poster-avatar img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .poster-tier {
      flex-shrink: 0;
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 800;
      line-height: 1.4;
      white-space: nowrap;
    }
    .poster-tier--icon { padding: 0 2px; background: none !important; font-size: 11px; }
    .poster-tier--legend { background: linear-gradient(90deg, #f0abfc, #fde68a, #7dd3fc); color: #4c1d95; }
    .poster-tier--crown { background: linear-gradient(#fde68a, #facc15); color: #78350f; }
    .poster-tier--ranger { background: linear-gradient(#e0f2fe, #7dd3fc); color: #0c4a6e; }
    .poster-tier--regular { background: linear-gradient(#f1f5f9, #cbd5e1); color: #334155; }
    .poster-tier--rookie { background: linear-gradient(#ecfccb, #6ee7b7); color: #065f46; }
"""
