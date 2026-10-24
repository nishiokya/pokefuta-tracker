"""蓋の画像の小さい版（WebP）を作る。pages-deploy.yml が dist へ画像を写したあとに実行する。

{id}_lid.jpeg（360px）と {id}_latest.jpeg（720px）から、manhole_tile_image.SMALL_WIDTHS の
幅ごとに {id}_lid_180.webp のような正方形の WebP を書く。ページは manhole_tile_image.srcset で
これを指すので、1枚でも作れなければ失敗で終わらせ、壊れた画像のままデプロイしない。

    python3 apps/scraper/build_small_images.py dist/manhole/image
"""

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from manhole_tile_image import SMALL_WIDTHS, small_image_url  # noqa: E402

QUALITY = 78  # 360px で 1 枚 20KB 前後。蓋の細い線が崩れない程度


def build_one(source: Path) -> int:
    """1枚の元画像から小さい版を全部書き、書いた数を返す。既にあって元より新しければ作り直さない。"""
    kind = "lid" if source.name.endswith("_lid.jpeg") else "latest"
    written = 0
    with Image.open(source) as image:
        image = image.convert("RGB")
        for width in SMALL_WIDTHS[kind]:
            target = source.with_name(Path(small_image_url(source.name, width)).name)
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                continue
            resized = image if image.width == width else image.resize((width, width), Image.Resampling.LANCZOS)
            resized.save(target, "WEBP", quality=QUALITY, method=4)
            written += 1
    return written


def sources(image_dir: Path) -> list[Path]:
    return sorted([*image_dir.glob("*_lid.jpeg"), *image_dir.glob("*_latest.jpeg")])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image_dir", type=Path)
    args = parser.parse_args()
    files = sources(args.image_dir)
    if not files:
        print(f"[small-images] {args.image_dir} に蓋の画像がありません", file=sys.stderr)
        return 1
    with ProcessPoolExecutor() as pool:
        written = sum(pool.map(build_one, files, chunksize=16))
    print(f"[small-images] {len(files)} 枚から {written} 枚の WebP を作成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
