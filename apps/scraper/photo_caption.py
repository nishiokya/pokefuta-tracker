#!/usr/bin/env python3
"""投稿写真キャプション（投稿者名・日付）の共通整形。

トップページ（apps/web/index.html の formatFeedDate）が確立した
「ロケール日付表記 + 長い投稿者名の省略」をビルド時生成ページ
（マンホール詳細 / summary / ポケモン一覧）へ横展開するためのヘルパ。

- 日付は UTC の ISO8601 を Asia/Tokyo に変換してから整形する
  （サイト全体で JST 固定表示。閲覧者のタイムゾーンでは再解釈しない）。
- shot_at=撮影日 / created_at=投稿日 の意味は呼び出し側で維持すること。
- HTML エスケープは呼び出し側の責務（本モジュールはプレーン文字列を返す）。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DISPLAY_NAME_MAX_LEN = 20

# Intl 依存の locale 揺れを避け、決定的に整形するための固定月名（en 用）
_EN_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# 各ジェネレータがインライン CSS に埋め込む共通スタイル断片。
# 名前側セレクタに割り当て、隣接する日付/CTA 側には flex-shrink:0 を付ける
# （apps/web/assets/top-page.css の .hero-footer-text / .hero-footer-cta と同じ手法）。
CAPTION_ELLIPSIS_CSS = "min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"


def to_jst_date(iso_value: object) -> date | None:
    """ISO8601 文字列（'Z' / オフセット付き / 日付のみ）→ JST の date。

    naive な日時・日付のみの文字列は「既に JST」とみなしてそのまま使う。
    解釈できない値は None。
    """
    if not isinstance(iso_value, str) or not iso_value.strip():
        return None
    text = iso_value.strip()
    # 'Z' の置換は UTC サフィックスに限定する（それ以外の位置の 'Z' は不正入力
    # なので fromisoformat の ValueError に委ねる）
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone(JST).date()


def _lang_key(lang: str) -> str:
    """'zh-Hans'/'zh-Hant' 等の別名を LANG_CONFIGS 系のキーに正規化する。"""
    aliases = {"zh-hans": "zh-CN", "zh-hant": "zh-TW"}
    return aliases.get((lang or "").lower(), lang or "ja")


def format_photo_date(iso_value: object, lang: str = "ja", *, with_year: bool = False) -> str:
    """'2026-07-16T…+00:00' → '7月16日' / 'Jul 16' / '7월 16일'。

    lang は 'ja' / 'en' / 'zh-CN' / 'zh-TW' / 'ko'（'zh-Hans'/'zh-Hant' も受理）。
    with_year=True で '2026年7月16日' / 'Jul 16, 2026' 等。
    整形できない値は ''（呼び出し側で非表示にする）。
    """
    d = to_jst_date(iso_value)
    if d is None:
        return ""
    lang = _lang_key(lang)
    if lang == "en":
        base = f"{_EN_MONTHS[d.month - 1]} {d.day}"
        return f"{base}, {d.year}" if with_year else base
    if lang == "ko":
        base = f"{d.month}월 {d.day}일"
        return f"{d.year}년 {base}" if with_year else base
    # ja / zh-CN / zh-TW は同形式
    base = f"{d.month}月{d.day}日"
    return f"{d.year}年{base}" if with_year else base


def format_display_name(name: object, max_len: int = DISPLAY_NAME_MAX_LEN) -> str:
    """投稿者名を空白正規化し、超過分は '…' 付きで切り詰める。非文字列/空は ''。"""
    if not isinstance(name, str):
        return ""
    collapsed = " ".join(name.split())
    if len(collapsed) > max_len:
        return collapsed[: max_len - 1].rstrip() + "…"
    return collapsed


def caption_meta(*parts: object, sep: str = " · ") -> str:
    """'場所 · 投稿者 · 7月16日' のようなメタ行を組み立てる（None/空はスキップ）。"""
    return sep.join(str(p) for p in parts if p)
