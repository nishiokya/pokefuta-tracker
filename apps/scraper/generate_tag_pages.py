#!/usr/bin/env python3
"""Generate static theme (tag) landing pages under /tags/<slug>/.

地図（map.html?tag=...）はテーマ絞り込みを持っているが、1URLしかないので
検索の着地面になれない。ここで作るのは「検索から直接着地できる静的ページ」で、
探索の出口は従来どおり地図に渡す（各ページの主CTAが /map.html?tag=<slug>）。

どのタグがページを持つかは `dataset/tag_meta.json` の `page: true`（現在3本）。
`/pokemon` は166ページ作って 505 sessions/4週（1ページ3.0）だったので、
テーマも「全タグを機械的に量産」はしない。増やすのは Search Console で
検索需要を確認できたテーマだけにすること。

判定は `tags`（地図のフィルタと同じソース）。`titles` にも同名のキーがあるが
付与ルールが別で件数が一致しない（remote_island は tags 30 / titles 28）。
地図へ渡す導線の一貫性を優先して `tags` に揃えている。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
    from apps.scraper.tag_meta import TagMeta, count_tags, load_tag_meta
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
    from tag_meta import TagMeta, count_tags, load_tag_meta

BASE_URL = "https://data.pokefuta.com"
OG_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"

DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_PHOTOS = ROOT / "docs" / "latest-manhole-photos.json"
DEFAULT_OUTPUT = ROOT / "dist" / "tags"
DEFAULT_ASSET_OUTPUT = ROOT / "dist" / "assets" / "tag-meta.js"

# 本文は「データから言えること」だけを書く。設置理由や自治体の意図など、
# 出典を示せない断定はここに書かないこと（都道府県ページの trivia と同じ方針）。
# 絵文字とラベルは持たない（dataset/tag_meta.json が正）。ここはページ固有の文章だけ。
TAG_PAGE_COPY: dict[str, dict[str, str]] = {
    "roadside": {
        "h1": "道の駅のポケふた",
        "lead": (
            "道の駅の敷地内、または道の駅からおよそ50m以内に設置されているポケふたです。"
            "駐車場とトイレが揃っているため、車での移動途中に立ち寄りやすいのが特徴です。"
        ),
        "description": (
            "道の駅にあるポケふた{count}枚を都道府県別にまとめました。"
            "設置場所・写真・地図へのリンクから、ドライブの立ち寄り先を選べます。"
        ),
    },
    "remote_island": {
        "h1": "離島のポケふた",
        "lead": (
            "離島に設置されているポケふたです。フェリーや航空便でしか行けない島が多く、"
            "訪問には運航スケジュールの確認が要ります。旅程を組んで訪れる一枚です。"
        ),
        "description": (
            "離島にあるポケふた{count}枚を都道府県別にまとめました。"
            "島ごとの設置場所と地図へのリンクから、渡航の計画を立てられます。"
        ),
    },
    "world_heritage": {
        "h1": "世界遺産のポケふた",
        "lead": (
            "世界遺産の構成資産やその周辺に設置されているポケふたです。"
            "観光の行き先としてもともと目的地になりやすく、ポケふた巡りと観光を1回の旅程にまとめられます。"
        ),
        "description": (
            "世界遺産の周辺にあるポケふた{count}枚を都道府県別にまとめました。"
            "設置場所・写真・地図へのリンクから、観光と合わせた巡り方を選べます。"
        ),
    },
}


def load_records(path: Path) -> list[dict]:
    """status=active のレコードを id 単位でマージして返す。

    生成スクリプト間で挙動を揃えるため generate_prefecture_pages.load_records と
    同じ規則（後勝ちマージ・active のみ）にしている。
    """
    by_id: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(record.get("id", "")).strip()
        if not record_id:
            continue
        by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return [
        record for record in by_id.values()
        if record.get("status", "active") == "active"
    ]


def load_photos(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw_photos = payload.get("photos", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_photos, dict):
        return {}
    return {
        str(manhole_id): photo
        for manhole_id, photo in raw_photos.items()
        if isinstance(photo, dict)
    }


def records_for_tag(records: list[dict], tag: str) -> list[dict]:
    selected = [
        record for record in records
        if tag in (record.get("tags") or [])
        and record.get("prefecture") in PREFECTURE_SLUGS
    ]
    order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    return sorted(
        selected,
        key=lambda record: (
            order.get(record.get("prefecture", ""), len(order)),
            record.get("city", ""),
            str(record.get("id", "")).zfill(8),
        ),
    )


def _escape_attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _clean_pokemons(record: dict) -> list[str]:
    return [
        name for name in record.get("pokemons", [])
        if isinstance(name, str) and name.strip() and "ローカルActs" not in name
    ]


def _campaign_params(pref_slug: str, tag: str) -> str:
    """写真館（pokefuta.com）へのリンクに付ける流入元パラメータ。

    県ページと同じ `from=data` + `pref` に、どのテーマページから来たかを示す
    `tag` を足す。utm_* は使わない（GA4 がセッションの流入元を上書きし、
    同一プロパティ内の図鑑→写真館が別セッション扱いになるため）。
    """
    params = "from=data"
    if pref_slug:
        params += f"&pref={quote(pref_slug)}"
    if tag:
        params += f"&tag={quote(tag)}"
    return params


def _upload_url(manhole_id: str, pref_slug: str, tag: str) -> str:
    return (
        "https://pokefuta.com/upload?"
        f"manhole_id={quote(manhole_id)}&{_campaign_params(pref_slug, tag)}"
    )


def _google_maps_url(record: dict) -> str:
    lat = record.get("lat")
    lng = record.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return ""
    return f"https://www.google.com/maps?q={lat},{lng}"


def _photo_asset_url(record: dict, photo: dict) -> str:
    mid = str(record.get("id", "")).strip()
    if not mid:
        return ""
    local = ROOT / "dataset" / "manhole" / "image" / f"{mid}_latest.jpeg"
    if local.exists():
        return f"/manhole/image/{quote(mid)}_latest.jpeg"
    url = photo.get("url") or photo.get("image_url") or ""
    return url if isinstance(url, str) and url.startswith("https://") else ""


def _prefecture_breakdown(records: list[dict], tag: str) -> str:
    counts: dict[str, int] = {}
    for record in records:
        prefecture = record.get("prefecture", "")
        counts[prefecture] = counts.get(prefecture, 0) + 1
    links = []
    for prefecture in PREFECTURE_ORDER:
        count = counts.get(prefecture)
        if not count:
            continue
        slug = PREFECTURE_SLUGS[prefecture]
        links.append(
            f'<a href="/prefectures/{quote(slug)}/" '
            f'data-track="tag_prefecture_click" data-destination="{_escape_attr(slug)}" '
            f'data-surface="tag_prefecture_breakdown">{escape(prefecture)}'
            f'<b>{count}枚</b></a>'
        )
    if not links:
        return '<p class="empty-state">該当する都道府県がありません。</p>'
    return f'<div class="pref-breakdown">{"".join(links)}</div>'


def _manhole_cards(records: list[dict], photos: dict[str, dict], tag: str) -> str:
    cards = []
    for position, record in enumerate(records, start=1):
        mid = str(record.get("id", "")).strip()
        prefecture = record.get("prefecture", "")
        pref_slug = PREFECTURE_SLUGS.get(prefecture, "")
        city = record.get("city", "") or "所在地不明"
        place = f"{prefecture} {city}" if prefecture else city
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        image_path = ROOT / "dataset" / "manhole" / "image" / f"{mid}_latest.jpeg"
        image_html = (
            f'<img src="/manhole/image/{quote(mid)}_latest.jpeg" '
            f'alt="{_escape_attr(place)}のポケふた" loading="lazy" width="72" height="72">'
            if image_path.exists()
            else '<span class="manhole-placeholder" aria-hidden="true">●</span>'
        )
        is_preinstall = record.get("installed") is False
        has_photo = (
            not is_preinstall
            and mid in photos
            and bool(_photo_asset_url(record, photos[mid]))
        )
        photo_label = (
            "設置後に投稿可能"
            if is_preinstall
            else ("投稿写真あり" if has_photo else "写真募集中")
        )
        photo_class = (
            " photo-pending"
            if is_preinstall
            else (" photo-ready" if has_photo else " photo-needed")
        )
        preinstall_badge_html = (
            '<span class="manhole-preinstall-badge">🚧 設置前</span>'
            if is_preinstall else ""
        )
        maps_url = _google_maps_url(record)
        maps_html = (
            f'<a href="{_escape_attr(maps_url)}" target="_blank" rel="noopener noreferrer" '
            f'data-track="tag_google_maps_click" data-position="{position}" '
            f'data-destination="google_maps" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions">地図で開く</a>'
            if maps_url else ""
        )
        upload_html = (
            f'<a class="upload" href="{_escape_attr(_upload_url(mid, pref_slug, tag))}" '
            f'data-track="tag_photo_upload_start" data-position="{position}" '
            f'data-destination="upload" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions" '
            f'data-photo-state="{"has_photo" if has_photo else "missing"}">'
            f'{"写真を追加" if has_photo else "写真を投稿"}</a>'
            if not is_preinstall else ""
        )
        actions_class = "manhole-actions preinstall-actions" if is_preinstall else "manhole-actions"
        cards.append(
            f'<article class="manhole-card" data-manhole-id="{_escape_attr(mid)}">'
            f'<a class="manhole-detail" href="/manholes/{quote(mid)}/" '
            f'data-track="tag_manhole_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_card">'
            f'{image_html}<span class="manhole-copy"><strong>{escape(place)}</strong>'
            f'<small>{escape(pokemons)}</small>{preinstall_badge_html}'
            f'<b class="photo-status{photo_class}">{photo_label}</b></span></a>'
            f'<div class="{actions_class}"><a href="/manholes/{quote(mid)}/" '
            f'data-track="tag_manhole_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions">詳細</a>'
            f'{maps_html}{upload_html}</div></article>'
        )
    return "".join(cards)


def _related_tags(tag: str, available: list[str], meta: TagMeta) -> str:
    links = [
        f'<a href="{_escape_attr(meta.href(other))}" data-track="tag_related_click" '
        f'data-destination="{_escape_attr(other)}" data-surface="tag_related">'
        f'{escape(meta.chip_label(other))}</a>'
        for other in available if other != tag
    ]
    links.append(
        '<a href="/map.html?view=theme" data-track="tag_map_click" '
        'data-destination="map_theme_directory" data-surface="tag_related">'
        '🗺 地図でテーマ一覧を見る</a>'
    )
    return f'<div class="related-links">{"".join(links)}</div>'


def build_page(
    tag: str,
    records: list[dict],
    photos: dict[str, dict],
    available_tags: list[str],
    tag_meta: TagMeta | None = None,
) -> str:
    tag_meta = tag_meta or load_tag_meta()
    copy = TAG_PAGE_COPY[tag]
    # 見出しの文章はページ固有、絵文字とラベルは全面共通（dataset/tag_meta.json）。
    meta = {
        "emoji": tag_meta.emoji(tag),
        "label": tag_meta.label(tag),
        "h1": copy["h1"],
        "lead": copy["lead"],
        "description": copy["description"],
    }
    count = len(records)
    prefecture_count = len({record.get("prefecture", "") for record in records})
    canonical_url = f"{BASE_URL}/tags/{quote(tag)}/"
    title = f"{meta['h1']}一覧（全国{count}枚）| ポケふた図鑑"
    description = meta["description"].format(count=count)
    map_url = f"/map.html?tag={quote(tag)}"

    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": meta["h1"],
        "description": description,
        "url": canonical_url,
        "inLanguage": "ja",
    }, ensure_ascii=False, indent=2)
    jsonld_breadcrumb = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ポケふた図鑑", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "全国のポケふた一覧", "item": f"{BASE_URL}/summary/"},
            {"@type": "ListItem", "position": 3, "name": meta["h1"], "item": canonical_url},
        ],
    }, ensure_ascii=False, indent=2)

    # AdSense の枠はあえて入れていない。広告は都道府県ページと詳細ページに
    # 各1枠という現行方針で、新設面にいきなり増やさない（CLAUDE.md の AdSense 方針）。
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{_escape_attr(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{_escape_attr(canonical_url)}">

  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{_escape_attr(title)}">
  <meta property="og:description" content="{_escape_attr(description)}">
  <meta property="og:url" content="{_escape_attr(canonical_url)}">
  <meta property="og:image" content="{_escape_attr(OG_IMAGE)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape_attr(title)}">
  <meta name="twitter:description" content="{_escape_attr(description)}">
  <meta name="twitter:image" content="{_escape_attr(OG_IMAGE)}">

  <script type="application/ld+json">
{jsonld}
  </script>
  <script type="application/ld+json">
{jsonld_breadcrumb}
  </script>

  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: #f7f0df; color: #201b16;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    a {{ color: #176f68; }}
    .page {{ max-width: 1040px; margin: 0 auto; padding: 20px 16px 56px; }}
    .breadcrumb {{ display: flex; flex-wrap: wrap; gap: 8px; font-size: .82rem; font-weight: 800; }}
    .breadcrumb a {{ text-decoration: none; }}
    .hero {{
      position: relative; overflow: hidden; margin-top: 14px; padding: 28px;
      border: 1px solid rgba(93,67,35,.15); border-radius: 24px;
      background: linear-gradient(135deg, #fffaf0, #f0e9fb);
      box-shadow: 0 14px 32px rgba(77,56,30,.08);
    }}
    .hero-kicker {{ margin: 0; color: #6b4aa2; font-size: .8rem; font-weight: 900; }}
    h1 {{ margin: 4px 0 8px; font-size: clamp(1.9rem, 6vw, 3.1rem); line-height: 1.15; }}
    .hero p.lead {{ max-width: 720px; margin: 0; color: #574b41; font-weight: 650; }}
    .stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 18px; max-width: 420px; }}
    .stat {{ padding: 14px; border-radius: 15px; background: rgba(255,255,255,.72); }}
    .stat span {{ display: block; color: #75685c; font-size: .76rem; font-weight: 850; }}
    .stat strong {{ display: block; color: #57408f; font-size: 1.55rem; line-height: 1.3; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .button {{
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px;
      border-radius: 999px; background: #176f68; color: white; font-weight: 900;
      text-decoration: none;
    }}
    .button.secondary {{ background: #6b4aa2; }}
    .button.tertiary {{ background: white; color: #176f68; box-shadow: inset 0 0 0 1px #9fc7c2; }}
    section {{
      margin-top: 22px; padding: 20px; border: 1px solid rgba(93,67,35,.14);
      border-radius: 19px; background: #fffaf0;
      box-shadow: 0 8px 20px rgba(77,56,30,.05);
    }}
    h2 {{ margin: 0 0 12px; font-size: 1.35rem; line-height: 1.35; }}
    .section-note {{ margin: 0 0 12px; color: #75685c; font-size: .86rem; }}
    .pref-breakdown {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .pref-breakdown a {{
      display: inline-flex; align-items: center; gap: 6px; min-height: 44px;
      padding: 0 12px; border-radius: 999px; background: #eee7fb;
      color: #57408f; font-size: .86rem; font-weight: 850; text-decoration: none;
    }}
    .pref-breakdown b {{ color: #6b4aa2; font-size: .78rem; }}
    .manhole-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .manhole-card {{
      overflow: hidden; border: 1px solid rgba(93,67,35,.13);
      border-radius: 14px; background: white;
    }}
    .manhole-detail {{
      display: grid; grid-template-columns: 72px minmax(0,1fr); align-items: center;
      gap: 12px; min-height: 88px; padding: 8px; color: inherit; text-decoration: none;
    }}
    .manhole-card img, .manhole-placeholder {{
      width: 72px; height: 72px; border-radius: 50%; object-fit: cover;
    }}
    .manhole-placeholder {{
      display: grid; place-items: center; background: #eee7fb; color: #7654aa; font-size: 2rem;
    }}
    .manhole-copy {{ min-width: 0; }}
    .manhole-copy strong, .manhole-copy small {{ display: block; }}
    .manhole-copy small {{ overflow: hidden; color: #75685c; text-overflow: ellipsis; white-space: nowrap; }}
    .photo-status {{
      display: inline-flex; width: fit-content; margin-top: 4px; padding: 2px 7px;
      border-radius: 999px; font-size: .68rem;
    }}
    .photo-ready {{ background: #e4f2ee; color: #176f68; }}
    .photo-needed {{ background: #fff0e5; color: #9b4b20; }}
    .photo-pending {{ background: #f0ede7; color: #6f6254; }}
    .manhole-preinstall-badge {{
      display: inline-block; margin-top: 4px; padding: 2px 8px;
      border-radius: 999px; background: #f1ede4; color: #6b5d44;
      font-size: .74rem; font-weight: 700; white-space: nowrap;
    }}
    .manhole-actions {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid #ece4d7; }}
    .manhole-actions.preinstall-actions {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .manhole-actions a {{
      display: grid; place-items: center; min-height: 44px; padding: 5px;
      color: #57408f; font-size: .76rem; font-weight: 900; text-align: center;
      text-decoration: none;
    }}
    .manhole-actions a + a {{ border-left: 1px solid #ece4d7; }}
    .manhole-actions a.upload {{ background: #b5483c; color: white; }}
    .related-links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .related-links a {{
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 12px;
      border-radius: 999px; background: #eee7fb; color: #57408f;
      font-size: .86rem; font-weight: 850; text-decoration: none;
    }}
    .empty-state {{ margin: 0; color: #75685c; }}
    footer {{ margin-top: 24px; color: #75685c; font-size: .8rem; text-align: center; }}
    @media (max-width: 700px) {{
      .hero {{ padding: 22px 18px; }}
      .manhole-grid {{ grid-template-columns: minmax(0, 1fr); }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくずリスト">
      <a href="/">ポケふた図鑑</a><span aria-hidden="true">›</span>
      <a href="/summary/">全国のポケふた一覧</a><span aria-hidden="true">›</span>
      <span>{escape(meta["h1"])}</span>
    </nav>

    <header class="hero">
      <p class="hero-kicker">{meta["emoji"]} テーマから探す</p>
      <h1>{escape(meta["h1"])}</h1>
      <p class="lead">{escape(meta["lead"])}</p>
      <div class="stats" aria-label="{_escape_attr(meta['label'])}のポケふたの集計">
        <div class="stat"><span>掲載枚数</span><strong>{count}枚</strong></div>
        <div class="stat"><span>都道府県</span><strong>{prefecture_count}県</strong></div>
      </div>
      <div class="hero-actions">
        <a class="button" href="{_escape_attr(map_url)}"
          data-track="tag_map_click" data-destination="map_tag_filter"
          data-surface="hero">地図でこのテーマを見る</a>
        <a class="button secondary" href="/summary/"
          data-track="tag_summary_click" data-destination="summary"
          data-surface="hero">全国の集計を見る</a>
        <a class="button tertiary" href="/prefectures/"
          data-track="tag_prefectures_click" data-destination="prefecture_index"
          data-surface="hero">都道府県から探す</a>
      </div>
    </header>

    <section aria-labelledby="pref-heading">
      <h2 id="pref-heading">都道府県別の{escape(meta["label"])}ポケふた</h2>
      <p class="section-note">県ページには設置マップ・現地写真・その県のポケふた一覧があります。</p>
      {_prefecture_breakdown(records, tag)}
    </section>

    <section aria-labelledby="list-heading">
      <h2 id="list-heading">{escape(meta["h1"])}一覧（{count}枚）</h2>
      <p class="section-note">都道府県順に並べています。「地図で開く」は Google マップの経路検索へ、
        「詳細」はポケふたの詳細ページへ移動します。</p>
      <div class="manhole-grid">{_manhole_cards(records, photos, tag)}</div>
    </section>

    <section aria-labelledby="related-heading">
      <h2 id="related-heading">ほかのテーマから探す</h2>
      {_related_tags(tag, available_tags, tag_meta)}
    </section>

    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
  <script src="/assets/analytics.js?v=20260805a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': '/tags/' + {_json_for_script(tag)} + '/',
      site_type: 'map',
      page_type: 'tag',
      tag: {_json_for_script(tag)}
    }});
    // 送信は共有ローダー経由（本番ホスト判定と共通コンテキストの付与をそこに集約している）。
    // 生成スクリプトに gtag を直書きしないこと（AGENTS.md）。
    function trackTagEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{
        event_category: 'tag_growth',
        surface: 'tag_page',
        tag: {_json_for_script(tag)},
        tag_label: {_json_for_script(meta["label"])}
      }}, params || {{}}));
    }}
    document.addEventListener('click', function(event) {{
      const link = event.target.closest('[data-track]');
      if (!link) return;
      trackTagEvent(link.dataset.track, {{
        position: Number(link.dataset.position || 0),
        destination: link.dataset.destination || '',
        content_id: link.dataset.contentId || '',
        photo_state: link.dataset.photoState || '',
        surface: link.dataset.surface || 'tag_page'
      }});
    }});
    const sentScrollDepths = new Set();
    function reportScrollDepth() {{
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 0) return;
      const depth = Math.round(window.scrollY / scrollable * 100);
      [50, 90].forEach(function(threshold) {{
        if (depth >= threshold && !sentScrollDepths.has(threshold)) {{
          sentScrollDepths.add(threshold);
          trackTagEvent('tag_scroll_depth', {{ percent_scrolled: threshold }});
        }}
      }});
      if (sentScrollDepths.size === 2) {{
        window.removeEventListener('scroll', reportScrollDepth);
      }}
    }}
    window.addEventListener('scroll', reportScrollDepth, {{ passive: true }});
  </script>
</body>
</html>
"""


def available_tag_slugs(records: list[dict], meta: TagMeta | None = None) -> list[str]:
    """ページを持つ（`page: true`）タグのうち、レコードが1枚以上あるものを返す。

    データが消えたテーマの空ページを出さないためのガード。sitemap 側も
    同じ関数を使うので、生成物と sitemap が食い違わない。
    """
    meta = meta or load_tag_meta()
    return [
        tag for tag in meta.page_slugs()
        if tag in TAG_PAGE_COPY and records_for_tag(records, tag)
    ]


def write_client_asset(path: Path, meta: TagMeta | None = None) -> Path:
    """地図が読む `assets/tag-meta.js` を書き出す。

    地図は map.html / map.template.html の2本に同じ定数が手書きで入っていて、
    トップや /tags/ とも食い違っていた。JS からも同じ JSON を読ませるための橋渡し。
    """
    meta = meta or load_tag_meta()
    payload = json.dumps(meta.as_client_payload(), ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "// 自動生成: dataset/tag_meta.json が正。直接編集しないこと。\n"
        "// 生成は apps/scraper/generate_tag_pages.py。\n"
        f"window.POKEFUTA_TAG_META = {payload};\n",
        encoding="utf-8",
    )
    return path


def generate_all(
    records: list[dict],
    photos: dict[str, dict],
    output_dir: Path,
    meta: TagMeta | None = None,
) -> int:
    meta = meta or load_tag_meta()
    available = available_tag_slugs(records, meta)
    for tag in available:
        out_dir = output_dir / tag
        out_dir.mkdir(parents=True, exist_ok=True)
        html = build_page(tag, records_for_tag(records, tag), photos, available, meta)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
    return len(available)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--photos", type=Path, default=DEFAULT_PHOTOS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tag-meta", type=Path, default=None)
    parser.add_argument("--asset-output", type=Path, default=DEFAULT_ASSET_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    meta = load_tag_meta(args.tag_meta)
    records = load_records(args.manholes)
    photos = load_photos(args.photos)
    count = generate_all(records, photos, args.output, meta)
    available = available_tag_slugs(records, meta)
    skipped = [tag for tag in meta.page_slugs() if tag not in available]
    asset = write_client_asset(args.asset_output, meta)
    counts = count_tags(records)
    print(
        f"[generate_tag_pages] wrote {count} tag pages to "
        f"{args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}"
        + (f" (skipped empty: {', '.join(skipped)})" if skipped else "")
    )
    print(
        f"[generate_tag_pages] wrote {asset} "
        f"({len(meta.visible_slugs(counts))} themes at or above min_count {meta.min_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
