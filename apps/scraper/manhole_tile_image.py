"""一覧の小さい正方形のタイルに出す蓋の画像を選ぶ（内部ライブラリ）。

import_latest_manhole_photos.py は蓋ごとに2つの画像を作る:
  {id}_latest.jpeg … 720px。代表写真を短辺の正方形で切ったもの（蓋の位置に寄せてある）。詳細・OGP・大きいカード向け
  {id}_lid.jpeg    … 360px。蓋の枠に合わせて拡大し、正方形を蓋でいっぱいにしたもの。小さいタイル向け
小さいタイルでは _lid を使い、無ければ（蓋の枠が無い写真・取り込み前）_latest に落とす。
"""

import re
from html import escape
from pathlib import Path
from urllib.parse import quote


def tile_image_url(manhole_id: str, image_dir: Path) -> str:
    """"/manhole/image/{id}_lid.jpeg"、無ければ "_latest.jpeg"、どちらも無ければ ""。"""
    mid = str(manhole_id).strip()
    if not mid:
        return ""
    for suffix in ("lid", "latest"):
        if (image_dir / f"{mid}_{suffix}.jpeg").exists():
            return f"/manhole/image/{quote(mid, safe='')}_{suffix}.jpeg"
    return ""


# ── 小さい版（WebP） ─────────────────────────────────────────────────────
# デプロイ時に build_small_images.py が {id}_lid.jpeg / {id}_latest.jpeg から
# {id}_lid_180.webp のような小さい版を作る。ページは srcset と sizes で表示の大きさに合う版を選ばせる。
# 720px の写真を 100px で出していたため、スマホのトップは約3MB・LCP 9秒だった（2026-10-25）。
# og:image など外へ出す画像は元の JPEG のまま。

ORIGINAL_WIDTHS = {"lid": 360, "latest": 720}
SMALL_WIDTHS = {"lid": (180, 360), "latest": (180, 360, 480)}
_IMAGE_RE = re.compile(r"_(lid|latest)\.jpeg$")


def small_image_url(url: str, width: int) -> str:
    """".../1_lid.jpeg" → ".../1_lid_180.webp"。蓋の画像でなければそのまま返す。"""
    match = _IMAGE_RE.search(url)
    if not match or width not in SMALL_WIDTHS[match.group(1)]:
        return url
    return f"{url[:match.start()]}_{match.group(1)}_{width}.webp"


def srcset(url: str, max_width: int | None = None) -> str:
    """WebP の小さい版と、それより大きい元の JPEG を並べた srcset。蓋の画像でなければ ""。

    max_width を渡すと、それより大きい候補を外す。画面の倍率が3倍の iPhone は、
    240px の表示でも 720px の元の JPEG を選ぶので、最初の画面の写真には上限を付ける。
    """
    match = _IMAGE_RE.search(url)
    if not match:
        return ""
    kind = match.group(1)
    candidates = [(small_image_url(url, w), w) for w in SMALL_WIDTHS[kind]]
    if ORIGINAL_WIDTHS[kind] > SMALL_WIDTHS[kind][-1]:
        candidates.append((url, ORIGINAL_WIDTHS[kind]))
    return ", ".join(f"{u} {w}w" for u, w in candidates if max_width is None or w <= max_width)


def responsive_attrs(url: str, sizes: str, max_width: int | None = None) -> str:
    """<img> に入れる src・srcset・sizes（属性値はエスケープ済み）。sizes は表示幅（例 "(min-width: 960px) 170px, 115px"）。"""
    attrs = f'src="{escape(url, quote=True)}"'
    candidates = srcset(url, max_width)
    if candidates:
        attrs += f' srcset="{escape(candidates, quote=True)}" sizes="{escape(sizes, quote=True)}"'
    return attrs


def map_tile_url(point: dict, image_dir: Path) -> str:
    """地図の丸い写真アイコンに出す 180px の WebP。写真なし・設置予定・切り抜き未生成なら ""。

    県・市区町村・旅・特集・多言語の地図と凡例はすべてこれで決める。
    切り抜きが無いときに投稿写真（720px の JPEG）へ落とすと 44px のアイコンに重いので、ピンのままにする。
    """
    if not point.get("photo_url") or point.get("is_preinstall"):
        return ""
    url = tile_image_url(str(point.get("id", "")), image_dir)
    return small_image_url(url, 180) if url else ""
