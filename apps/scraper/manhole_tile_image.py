"""一覧の小さい正方形のタイルに出す蓋の画像を選ぶ（内部ライブラリ）。

import_latest_manhole_photos.py は蓋ごとに2つの画像を作る:
  {id}_latest.jpeg … 720px。代表写真を短辺の正方形で切ったもの（蓋の位置に寄せてある）。詳細・OGP・大きいカード向け
  {id}_lid.jpeg    … 360px。蓋の枠に合わせて拡大し、正方形を蓋でいっぱいにしたもの。小さいタイル向け
小さいタイルでは _lid を使い、無ければ（蓋の枠が無い写真・取り込み前）_latest に落とす。
"""

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
