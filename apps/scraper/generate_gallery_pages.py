#!/usr/bin/env python3
"""みんなのマンホール写真ギャラリー（/gallery/）を静的ページで作る。

写真館（pokefuta.com）の特集「ぬいぐるみと旅するポケふた」（/photos/plush）・「雪景色のポケふた」
（/photos/snow）を図鑑へ移したもの。写真館はページを開くたびに Supabase から写真を読んでいたが、
ここでは日次ジョブ（import-manhole-photos.yml）が書く `docs/api/tagged-photos.json` から作る
（Supabase の Egress を減らすため。2026-11-23）。

- /gallery/         入口。特集2本へのカード
- /gallery/plush/   ぬいぐるみと一緒に撮られた写真（投稿の新しい順）。蓋とぬいぐるみをそれぞれ切り抜いて見せる
- /gallery/snow/    雪の写っている写真（撮影日の新しい順）。景色が主役なので写真全体を見せる

見た目と中身は写真館の src/components/features/TaggedPhotoFeature.tsx に合わせる。
画像は写真館の /api/photo/{id}?size=small を読む（写真館が配るたびに公開かを確かめるので、
非公開に戻した写真の画像は出ない。行は次の日次の生成まで残る＝最大1日。2026-11-23 に了承済み）。
写真・投稿者のリンク先は写真館、蓋の名前のリンク先は図鑑の蓋のページ。

データが無い・壊れているときもページは作る（写真館の 308 の行き先なので消さない）。写真は0枚になる。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from display_names import compose_display_name  # noqa: E402
from site_names import og_site_name  # noqa: E402

BASE_URL = "https://data.pokefuta.com"
APP_URL = "https://pokefuta.com"
OG_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"
GALLERY_PATH = "/gallery/"
GALLERY_TITLE = "みんなのマンホール写真ギャラリー"

DEFAULT_TAGGED = ROOT / "docs" / "api" / "tagged-photos.json"
DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_OUTPUT = ROOT / "dist" / "gallery"

# 写真館の photoBoxZoom の最大倍率（LID_ZOOM_MAX）。サムネイルを拡大するので、それ以上はぼやける
ZOOM_MAX = 3
# カードに出すポケモンの数（写真館の POKEMON_TAG_LIMIT）
POKEMON_TAG_LIMIT = 3
# 入口のカードに並べる写真の数
PREVIEW_COUNT = 4
# 先頭の何枚を eager にするか（写真館と同じ）
EAGER_COUNT = 6
JST = timezone(timedelta(hours=9))

AI_TAG_HELP = (
    "ぬいぐるみ・風景・人物・雪・紅葉・足元のタグは AI で、夜のタグは撮影時刻と場所から"
    "自動で判定しています。間違っていたらごめんなさい。"
)


# ---------------------------------------------------------------- データ


def load_tagged(path: Path) -> dict[str, Any]:
    """tagged-photos.json の features。読めない・success でないときは空（ページは0枚で作る）。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[gallery] WARNING: {path} を読めません（{exc}）。写真0枚で作ります", file=sys.stderr)
        return {}
    if not isinstance(payload, dict) or payload.get("success") is not True:
        print(f"[gallery] WARNING: {path} が success でありません。写真0枚で作ります", file=sys.stderr)
        return {}
    features = payload.get("features")
    return features if isinstance(features, dict) else {}


def feature_photos(features: dict[str, Any], key: str) -> list[dict[str, Any]]:
    entry = features.get(key)
    photos = entry.get("photos") if isinstance(entry, dict) else None
    if not isinstance(photos, list):
        return []
    return [p for p in photos if isinstance(p, dict) and isinstance(p.get("id"), str) and p["id"]]


def load_manholes(path: Path) -> dict[str, dict]:
    """manhole_id → pokefuta.ndjson のレコード（id ごとに後勝ちでまとめる。generate_tag_pages と同じ）。"""
    by_id: dict[str, dict] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(record.get("id", "")).strip()
        if record_id:
            by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return by_id


# ---------------------------------------------------------------- 切り抜き（写真館の photo-ai-tags.ts と同じ計算）


def _unit_box(value: Any) -> Optional[list[float]]:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 1 for v in value):
        return None
    x0, y0, x1, y1 = (float(v) for v in value)
    return [x0, y0, x1, y1] if x1 > x0 and y1 > y0 else None


def _pct(value: float) -> str:
    rounded = round(value * 1000) / 10
    text = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return f"{'0' if text == '-0' else text}%"


def box_zoom_style(ai_tags: Any, box: list[float], pad: float, max_zoom: float = ZOOM_MAX) -> Optional[str]:
    """写真の中の枠（蓋・ぬいぐるみ）だけを正方形の枠いっぱいに切り抜く img の style。写真館の photoBoxZoom。

    枠の長いほうの辺 × pad を一辺にし、枠の中心を真ん中に合わせる（写真の外が見えないよう端ではずらし、
    一辺は写真の短辺まで）。写真の縦横比は ai_tags.crop（短辺の正方形）から分かる。crop が無ければ None。
    """
    crop = _unit_box(ai_tags.get("crop")) if isinstance(ai_tags, dict) else None
    if not crop:
        return None
    aspect = (crop[3] - crop[1]) / (crop[2] - crop[0])  # W / H
    height = 1 / aspect
    short_side = min(1.0, height)
    side = min(max(max(box[2] - box[0], (box[3] - box[1]) * height) * pad, short_side / max_zoom), short_side)

    def clamp(value: float, hi: float) -> float:
        return min(max(value, 0.0), max(hi, 0.0))

    left = clamp((box[0] + box[2]) / 2 - side / 2, 1 - side)
    top = clamp(((box[1] + box[3]) / 2) * height - side / 2, height - side)
    return (
        f"position:absolute;width:{_pct(1 / side)};height:{_pct(height / side)};"
        f"left:{_pct(-left / side)};top:{_pct(-top / side)};max-width:none"
    )


def plush_clips(ai_tags: Any) -> Optional[tuple[str, str]]:
    """(蓋の style, ぬいぐるみの style)。どちらかの枠か crop が無ければ None（写真館の hasPlushClip）。"""
    if not isinstance(ai_tags, dict):
        return None
    lid = _unit_box(ai_tags.get("lid"))
    plush = _unit_box(ai_tags.get("plush_box"))
    if not lid or not plush:
        return None
    lid_style = box_zoom_style(ai_tags, lid, 1.04)
    plush_style = box_zoom_style(ai_tags, plush, 1.12)
    if not lid_style or not plush_style:
        return None
    return lid_style, plush_style


def ai_tag_labels(photo: dict[str, Any]) -> list[str]:
    """写真館の photoAiTags(…, { compact: true }) のラベル（人物・足元は出さない）。"""
    tags = photo.get("ai_tags")
    if not isinstance(tags, dict):
        return []
    labels = []
    if tags.get("plush") is True:
        labels.append("ぬいぐるみ")
    if tags.get("night") is True:
        labels.append("夜")
    if tags.get("scene") == "landscape" and photo.get("is_landscape") is not True:
        labels.append("風景")
    if tags.get("snow") is True:
        labels.append("雪")
    if tags.get("autumn") is True:
        labels.append("紅葉")
    return labels


# ---------------------------------------------------------------- 表示の部品


def _attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def photo_src(photo_id: str) -> str:
    return f"{APP_URL}/api/photo/{quote(photo_id)}?size=small"


def photo_page_url(photo_id: str) -> str:
    return f"{APP_URL}/p/{quote(photo_id)}?from=data"


def poster_url(public_id: str) -> str:
    return f"{APP_URL}/users/{quote(public_id)}/visits?from=data"


def format_date_jst(value: Any) -> tuple[str, str]:
    """(datetime 属性, 表示)。写真館の formatDateJaJst と同じく JST の年月日。読めなければ空。"""
    if not isinstance(value, str) or not value:
        return "", ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "", ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(JST)
    return local.date().isoformat(), f"{local.year}年{local.month}月{local.day}日"


def clean_pokemons(record: Optional[dict]) -> list[str]:
    return [
        name for name in (record or {}).get("pokemons", []) or []
        if isinstance(name, str) and name.strip() and "ローカルActs" not in name
    ]


def manhole_name(record: Optional[dict]) -> str:
    return (compose_display_name(record) if record else "") or "ポケふた"


def plush_media(photo: dict[str, Any], index: int) -> str:
    """蓋（丸いスタンプ、左上、大きく）とぬいぐるみ（角丸のステッカー、右下に重ねる）。写真館の /photos/plush と同じ。"""
    clips = plush_clips(photo.get("ai_tags"))
    src = _attr(photo_src(photo["id"]))
    loading = "eager" if index < EAGER_COUNT else "lazy"
    if not clips:
        return snow_media(photo, index)
    lid_style, plush_style = clips
    return (
        '<span class="gl-media gl-media--plush">'
        f'<span class="gl-lid"><img src="{src}" alt="" width="400" height="400" style="{lid_style}" '
        f'loading="{loading}" decoding="async"></span>'
        f'<span class="gl-plush"><img src="{src}" alt="" width="400" height="400" style="{plush_style}" '
        f'loading="{loading}" decoding="async"></span>'
        "</span>"
    )


def snow_media(photo: dict[str, Any], index: int) -> str:
    """雪は蓋のまわりの景色が主役なので、切り抜かずに写真全体を見せる。"""
    loading = "eager" if index < EAGER_COUNT else "lazy"
    return (
        '<span class="gl-media gl-media--whole">'
        f'<img src="{_attr(photo_src(photo["id"]))}" alt="" width="400" height="400" '
        f'loading="{loading}" decoding="async"></span>'
    )


def photo_card(
    photo: dict[str, Any],
    index: int,
    manholes: dict[str, dict],
    media: Callable[[dict[str, Any], int], str],
    feature: str,
) -> str:
    photo_id = photo["id"]
    manhole_id = str(photo.get("manhole_id") or "")
    record = manholes.get(manhole_id)
    name = manhole_name(record)
    pokemons = clean_pokemons(record)[:POKEMON_TAG_LIMIT]
    shot_iso, shot_label = format_date_jst(photo.get("shot_at") or photo.get("created_at"))
    poster = photo.get("poster_name") if isinstance(photo.get("poster_name"), str) and photo["poster_name"].strip() else "名無しのトレーナー"
    public_id = photo.get("poster_public_id") if isinstance(photo.get("poster_public_id"), str) else ""
    comment = photo.get("comment") if isinstance(photo.get("comment"), str) and photo["comment"].strip() else ""
    labels = ai_tag_labels(photo)
    badge = '<span class="gl-badge">周辺の風景</span>' if photo.get("is_landscape") is True else ""
    track = f'data-position="{index + 1}" data-content-id="{_attr(photo_id)}" data-surface="gallery_{feature}"'

    alt_parts = [*(["周辺の風景"] if badge else []), *labels, name, *pokemons]
    if shot_label:
        alt_parts.append(f"撮影 {shot_label}")
    manhole_html = (
        f'<a class="gl-place" href="/manholes/{quote(manhole_id)}/" data-track="gallery_manhole_click" '
        f'data-destination="{_attr(manhole_id)}" {track}>{escape(name)}</a>'
        if record else f'<span class="gl-place">{escape(name)}</span>'
    )
    poster_html = (
        f'<a href="{_attr(poster_url(public_id))}" data-track="gallery_poster_click" '
        f'data-destination="poster_visits" {track}>{escape(poster)}</a>'
        if public_id else escape(poster)
    )
    pokemon_html = (
        '<span class="gl-pokemon">' + "".join(f"<span>{escape(p)}</span>" for p in pokemons) + "</span>"
        if pokemons else ""
    )
    time_html = f'<time datetime="{_attr(shot_iso)}">{escape(shot_label)}</time>' if shot_label else ""
    comment_html = f'<p class="gl-comment">{escape(comment)}</p>' if comment else ""
    return (
        '<li class="gl-card">'
        f'<a class="gl-photo" href="{_attr(photo_page_url(photo_id))}" '
        f'aria-label="{_attr("、".join(alt_parts) + "の写真を写真館で見る")}" '
        f'data-track="gallery_photo_click" data-destination="photo" {track}>'
        f"{media(photo, index)}{badge}</a>"
        '<div class="gl-body">'
        f"{manhole_html}{pokemon_html}"
        f'<p class="gl-meta"><span class="gl-poster">{poster_html}</span>{time_html}</p>'
        f"{comment_html}"
        "</div></li>"
    )


# ---------------------------------------------------------------- ページ


FEATURES: dict[str, dict[str, Any]] = {
    "plush": {
        "title": "ぬいぐるみと旅するポケふた",
        "kicker": "🧸 特集",
        "lead": "ぬいぐるみと一緒に撮られたポケふたの写真です。旅のお供と並んだ一枚を、みんなの投稿から集めました。",
        "lab_note": "AI がぬいぐるみの写っている写真を見つけて、蓋とぬいぐるみが入るように切り抜いています。まちがいもあります。",
        "count_label": "ぬいぐるみと一緒に撮られたポケふたの写真",
        "sort_label": "新しく投稿された順",
        "empty": "まだ写真がありません。",
        "description": "ぬいぐるみと一緒に撮られたポケふた（ポケモンマンホール）の写真{count}枚。みんなが写真館に投稿した旅の一枚を集めました。",
        "media": plush_media,
    },
    "snow": {
        "title": "雪景色のポケふた",
        "kicker": "❄️ 特集",
        "lead": "雪と一緒に写るポケふたの写真です。みんなが投稿した冬の景色を、撮影日の新しい順に並べました。",
        # 2026-11-14 までの投稿は人が確かめた判定、それより後は AI の判定（写真館の /photos/snow と同じ）
        "lab_note": "雪の写っている写真を集めています。新しい投稿は AI が見つけているので、まちがいもあります。",
        "count_label": "雪と一緒に写るポケふたの写真",
        "sort_label": "撮影日の新しい順",
        "empty": "雪景色の写真は、まだありません。",
        "description": "雪と一緒に写るポケふた（ポケモンマンホール）の写真{count}枚。みんなが写真館に投稿した冬の景色を集めました。",
        "media": snow_media,
    },
}


def feedback_url(page_name: str, path: str) -> str:
    """感想は公式 X へ（写真館の featureFeedbackUrl と同じ宛先）。"""
    text = quote(f"@pokemonmanhole {page_name}の感想: ")
    return f"https://x.com/intent/post?text={text}&url={quote(BASE_URL + path, safe='')}"


PHOTO_MEDIA_CSS = """
    .gl-media { position: absolute; inset: 0; display: block; }
    .gl-media--plush { background: radial-gradient(circle at 30% 20%, #fff8eb 0, #f1e3c6 75%); }
    .gl-media--whole { display: flex; align-items: center; justify-content: center;
      background: radial-gradient(circle at 30% 20%, #f4f9fd 0, #dceaf4 75%); }
    .gl-media--whole img { width: 100%; height: 100%; object-fit: contain; }
    .gl-lid, .gl-plush { position: absolute; display: block; aspect-ratio: 1 / 1; overflow: hidden;
      background: #efe4cc; border: 3px solid white; }
    .gl-lid { left: 4%; top: 4%; width: 80%; border-radius: 50%; box-shadow: 0 4px 10px rgba(0,0,0,.15); }
    .gl-plush { right: 4%; bottom: 4%; width: 40%; border-radius: 16%; transform: rotate(4deg);
      box-shadow: 0 6px 14px rgba(0,0,0,.2); }
    .gl-lid img, .gl-plush img { display: block; }
"""


STYLE = """
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: #f7f0df; color: #201b16;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65; overflow-wrap: anywhere;
    }
    a { color: #176f68; }
    .page { max-width: var(--page-max-wide, 1120px); margin: 0 auto; padding: 20px 16px 56px; }
    .breadcrumb { display: flex; flex-wrap: wrap; gap: 8px; font-size: .82rem; font-weight: 800; }
    .breadcrumb a { text-decoration: none; }
    .hero {
      margin-top: 14px; padding: 24px;
      border: 1px solid rgba(93,67,35,.15); border-radius: 24px;
      background: linear-gradient(135deg, #fffaf0, #f0e9fb);
      box-shadow: 0 14px 32px rgba(77,56,30,.08);
    }
    .hero-kicker { margin: 0; color: #6b4aa2; font-size: .8rem; font-weight: 900; }
    h1 { margin: 4px 0 8px; font-size: clamp(1.5rem, 5.5vw, 2.6rem); line-height: 1.2; }
    .lead { max-width: 760px; margin: 0; color: #574b41; font-weight: 650; }
    .count { margin: 10px 0 0; color: #6a4d36; font-size: .92rem; font-weight: 800; }
    .count small { margin-left: 6px; color: #8b816f; font-size: .78rem; font-weight: 700; }
    .lab {
      margin-top: 16px; padding: 12px 14px; border: 1px dashed rgba(123,99,168,.5); border-radius: 12px;
      background: repeating-linear-gradient(135deg, #f3eefa 0, #f3eefa 12px, #eee6f8 12px, #eee6f8 24px);
      color: #4a3a66; font-size: .84rem;
    }
    .lab b {
      display: inline-block; margin-right: 6px; padding: 2px 10px; border-radius: 999px;
      background: #7b63a8; color: white; font-size: .74rem;
    }
    .lab a {
      display: inline-flex; align-items: center; min-height: 36px; margin-top: 8px; padding: 0 12px;
      border-radius: 999px; background: white; color: #5b4688; font-size: .78rem; font-weight: 900;
      text-decoration: none; box-shadow: inset 0 0 0 1px rgba(123,99,168,.4);
    }
    .gl-grid {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px;
      margin: 18px 0 0; padding: 0; list-style: none;
    }
    .gl-card {
      min-width: 0; overflow: hidden; border-radius: 12px; background: #fff8eb;
      box-shadow: 0 1px 3px rgba(77,56,30,.1); outline: 1px solid rgba(123,99,168,.15);
    }
    .gl-photo { position: relative; display: block; aspect-ratio: 1 / 1; overflow: hidden; background: #efe4cc; }
""" + PHOTO_MEDIA_CSS + """
    .gl-badge {
      position: absolute; left: 8px; top: 8px; padding: 3px 8px; border-radius: 999px;
      background: rgba(32,27,22,.72); color: white; font-size: .7rem; font-weight: 800;
    }
    .gl-body { padding: 8px 10px 10px; font-size: .8rem; }
    .gl-place { display: block; color: #4f3828; font-weight: 900; line-height: 1.4; text-decoration: none; }
    a.gl-place:hover { text-decoration: underline; }
    .gl-pokemon { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
    .gl-pokemon span { padding: 1px 7px; border-radius: 999px; background: #eee7fb; color: #57408f;
      font-size: .7rem; font-weight: 800; }
    .gl-meta { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 2px 8px;
      margin: 6px 0 0; color: #75685c; font-size: .74rem; }
    .gl-poster { min-width: 0; font-weight: 800; }
    .gl-poster a { color: #176f68; }
    .gl-comment {
      display: -webkit-box; margin: 6px 0 0; overflow: hidden; color: #574b41;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .note { margin-top: 18px; color: #75685c; font-size: .78rem; }
    .empty { margin-top: 18px; padding: 24px; border-radius: 12px; background: #fff8eb; color: #6a4d36; text-align: center; }
    section.box {
      margin-top: 22px; padding: 20px; border: 1px solid rgba(93,67,35,.14);
      border-radius: 19px; background: #fffaf0;
    }
    h2 { margin: 0 0 10px; font-size: 1.25rem; line-height: 1.35; }
    .links { display: flex; flex-wrap: wrap; gap: 8px; }
    .links a {
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px;
      border-radius: 999px; background: #eee7fb; color: #57408f;
      font-size: .86rem; font-weight: 850; text-decoration: none;
    }
    .links a.primary { background: #b5483c; color: white; }
    .features { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; margin-top: 18px; }
    .feature-card {
      display: block; min-width: 0; overflow: hidden; border-radius: 18px; background: #fffaf0;
      border: 1px solid rgba(93,67,35,.14); box-shadow: 0 8px 20px rgba(77,56,30,.06);
      color: inherit; text-decoration: none;
    }
    .feature-card:hover { box-shadow: 0 12px 26px rgba(77,56,30,.12); }
    .feature-card .gl-preview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px; padding: 4px; }
    .feature-card .gl-preview > span { position: relative; display: block; aspect-ratio: 1 / 1; overflow: hidden;
      border-radius: 10px; background: #efe4cc; }
    .feature-card .gl-preview .gl-lid { border-width: 2px; }
    .feature-card .gl-preview .gl-plush { border-width: 2px; }
    .feature-copy { padding: 10px 16px 16px; }
    .feature-copy b { display: block; font-size: 1.15rem; }
    .feature-copy span { display: block; margin-top: 4px; color: #574b41; font-size: .86rem; }
    .feature-copy small { display: inline-block; margin-top: 8px; color: #6b4aa2; font-size: .82rem; font-weight: 900; }
    @media (min-width: 700px) {
      .gl-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
      .features { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (min-width: 1024px) {
      .gl-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    @media (max-width: 699.98px) {
      .hero { padding: 20px 16px; }
    }
"""


def _head(title: str, description: str, canonical: str, jsonld: list[dict]) -> str:
    scripts = "\n".join(
        f'  <script type="application/ld+json">\n{_json_for_script(item)}\n  </script>'
        for item in jsonld
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{_attr(description)}">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <link rel="canonical" href="{_attr(canonical)}">
  <link rel="preconnect" href="{APP_URL}">

  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  {og_site_name("ja_JP")}
  <meta property="og:title" content="{_attr(title)}">
  <meta property="og:description" content="{_attr(description)}">
  <meta property="og:url" content="{_attr(canonical)}">
  <meta property="og:image" content="{_attr(OG_IMAGE)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_attr(title)}">
  <meta name="twitter:description" content="{_attr(description)}">
  <meta name="twitter:image" content="{_attr(OG_IMAGE)}">

{scripts}

  <style>{STYLE}  </style>
</head>"""


def _analytics(page_path: str, feature: str) -> str:
    # 送信は共有ローダー経由（生成スクリプトに gtag を直書きしない。AGENTS.md）
    return f"""  <script src="/assets/analytics.js?v=20261018a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': {_json_for_script(page_path)},
      site_type: 'map',
      page_type: 'gallery',
      gallery: {_json_for_script(feature)}
    }});
    window.PokefutaAnalytics.bindClickTracking({{
      event_category: 'gallery',
      surface: 'gallery_page',
      gallery: {_json_for_script(feature)}
    }}, {{ detail: true }});
  </script>"""


def _breadcrumb_ld(items: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(items, start=1)
        ],
    }


def _upload_links(surface: str) -> str:
    return (
        '<div class="links">'
        f'<a class="primary" href="{APP_URL}/upload?from=data" data-track="gallery_upload_click" '
        f'data-destination="upload" data-surface="{surface}">ポケふた写真館で写真を投稿する</a>'
        f'<a href="{GALLERY_PATH}" data-track="gallery_index_click" data-destination="gallery" '
        f'data-surface="{surface}">{GALLERY_TITLE}へ</a>'
        "</div>"
    )


def build_feature_page(key: str, photos: list[dict[str, Any]], limit: int, manholes: dict[str, dict]) -> str:
    meta = FEATURES[key]
    path = f"{GALLERY_PATH}{key}/"
    canonical = BASE_URL + path
    count = len(photos)
    title = f"{meta['title']}（写真{count}枚）| {GALLERY_TITLE} | ポケふた図鑑"
    description = meta["description"].format(count=count)
    capped = f"<small>（新しい{limit}枚まで）</small>" if limit and count >= limit else ""
    cards = "".join(photo_card(photo, i, manholes, meta["media"], key) for i, photo in enumerate(photos))
    body = (
        f'<ul class="gl-grid">{cards}</ul><p class="note">{escape(AI_TAG_HELP)}</p>'
        if photos else f'<p class="empty">{escape(meta["empty"])}</p>'
    )
    jsonld = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": meta["title"],
            "description": description,
            "url": canonical,
            "inLanguage": "ja",
            "isPartOf": {"@type": "CollectionPage", "name": GALLERY_TITLE, "url": BASE_URL + GALLERY_PATH},
        },
        _breadcrumb_ld([
            ("ポケふた図鑑", f"{BASE_URL}/"),
            (GALLERY_TITLE, BASE_URL + GALLERY_PATH),
            (meta["title"], canonical),
        ]),
    ]
    other = [k for k in FEATURES if k != key]
    other_links = "".join(
        f'<a href="{GALLERY_PATH}{k}/" data-track="gallery_feature_click" data-destination="{k}" '
        f'data-surface="gallery_related">{escape(FEATURES[k]["title"])}</a>'
        for k in other
    )
    return f"""{_head(title, description, canonical, jsonld)}
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくずリスト">
      <a href="/">ポケふた図鑑</a><span aria-hidden="true">›</span>
      <a href="{GALLERY_PATH}">{GALLERY_TITLE}</a><span aria-hidden="true">›</span>
      <span>{escape(meta["title"])}</span>
    </nav>

    <header class="hero">
      <p class="hero-kicker">{escape(meta["kicker"])}</p>
      <h1>{escape(meta["title"])}</h1>
      <p class="lead">{escape(meta["lead"])}</p>
      <p class="count">{escape(meta["count_label"])} {count}枚{capped}<small>{escape(meta["sort_label"])}</small></p>
      <div class="lab"><b>ポケふたラボ・実験中</b>{escape(meta["lab_note"])}<br>
        <a href="{_attr(feedback_url(meta["title"], path))}" target="_blank" rel="noopener noreferrer"
          data-track="gallery_feedback_click" data-destination="x" data-surface="gallery_lab">感想をおくる</a></div>
    </header>

    {body}

    <section class="box" aria-labelledby="more-heading">
      <h2 id="more-heading">ほかの特集・写真を投稿する</h2>
      <div class="links">{other_links}</div>
      <div style="margin-top:10px">{_upload_links("gallery_footer")}</div>
    </section>
  </main>
{_analytics(path, key)}
</body>
</html>
"""


def _preview(key: str, photos: list[dict[str, Any]]) -> str:
    media = FEATURES[key]["media"]
    tiles = "".join(f"<span>{media(photo, 0)}</span>" for photo in photos[:PREVIEW_COUNT])
    return f'<span class="gl-preview" aria-hidden="true">{tiles}</span>' if tiles else ""


def build_index_page(features: dict[str, list[dict[str, Any]]]) -> str:
    canonical = BASE_URL + GALLERY_PATH
    total = sum(len(photos) for photos in features.values())
    title = f"{GALLERY_TITLE}（ぬいぐるみ・雪景色）| ポケふた図鑑"
    description = (
        "みんながポケふた写真館に投稿したポケふた（ポケモンマンホール）の写真から、"
        "ぬいぐるみと一緒の写真や雪景色の写真を特集で集めました。"
    )
    cards = "".join(
        f'<a class="feature-card" href="{GALLERY_PATH}{key}/" data-track="gallery_feature_click" '
        f'data-destination="{key}" data-surface="gallery_index">'
        f"{_preview(key, features.get(key, []))}"
        f'<span class="feature-copy"><b>{escape(FEATURES[key]["kicker"])} {escape(FEATURES[key]["title"])}</b>'
        f'<span>{escape(FEATURES[key]["lead"])}</span>'
        f'<small>写真{len(features.get(key, []))}枚を見る →</small></span></a>'
        for key in FEATURES
    )
    jsonld = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": GALLERY_TITLE,
            "description": description,
            "url": canonical,
            "inLanguage": "ja",
            "hasPart": [
                {"@type": "CollectionPage", "name": FEATURES[k]["title"], "url": f"{canonical}{k}/"}
                for k in FEATURES
            ],
        },
        _breadcrumb_ld([("ポケふた図鑑", f"{BASE_URL}/"), (GALLERY_TITLE, canonical)]),
    ]
    return f"""{_head(title, description, canonical, jsonld)}
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくずリスト">
      <a href="/">ポケふた図鑑</a><span aria-hidden="true">›</span>
      <span>{GALLERY_TITLE}</span>
    </nav>

    <header class="hero">
      <p class="hero-kicker">📷 みんなの投稿から</p>
      <h1>{GALLERY_TITLE}</h1>
      <p class="lead">ポケふた写真館に届いた写真から、テーマごとに集めた特集です。旅のお供のぬいぐるみと並んだ一枚や、雪の積もった冬の景色を見てみてください。</p>
      <p class="count">特集 {len(FEATURES)}本・写真 {total}枚</p>
    </header>

    <div class="features">{cards}</div>

    <section class="box" aria-labelledby="post-heading">
      <h2 id="post-heading">写真を投稿する</h2>
      <p class="note" style="margin-top:0">写真はポケふた写真館に投稿されたものです。公開の記録の写真だけを、毎朝の更新で集めています。</p>
      {_upload_links("gallery_index_footer")}
    </section>
  </main>
{_analytics(GALLERY_PATH, "index")}
</body>
</html>
"""


def generate(tagged_path: Path, manholes_path: Path, output_dir: Path) -> dict[str, int]:
    raw = load_tagged(tagged_path)
    manholes = load_manholes(manholes_path)
    limit = 0
    try:
        limit = int(json.loads(tagged_path.read_text(encoding="utf-8")).get("limit") or 0)
    except (OSError, ValueError, AttributeError, TypeError):
        limit = 0
    features = {key: feature_photos(raw, key) for key in FEATURES}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(build_index_page(features), encoding="utf-8")
    for key, photos in features.items():
        page_dir = output_dir / key
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(build_feature_page(key, photos, limit, manholes), encoding="utf-8")
    return {key: len(photos) for key, photos in features.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tagged", type=Path, default=DEFAULT_TAGGED)
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    counts = generate(args.tagged, args.manholes, args.output)
    print(f"[gallery] wrote {args.output}: " + ", ".join(f"{k} {v}枚" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
