#!/usr/bin/env python3
"""Generate the travel-poster OGP image for the nationwide summary page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).parent.parent.parent
CANVAS = (1200, 630)
OUTPUT = ROOT / "apps" / "web" / "assets" / "ogp" / "pokefuta_summary_ogp.png"
NDJSON = ROOT / "docs" / "pokefuta.ndjson"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"
PHOTO_IDS = ("141", "188", "105")

INK = (39, 31, 27)
PAPER = (249, 241, 218)
SKY = (178, 225, 232)
PURPLE = (87, 64, 143)
PURPLE_DARK = (58, 40, 106)
YELLOW = (246, 201, 55)
WHITE = (255, 255, 255)

FONT_BOLD = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]
FONT_REGULAR = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def find_font(paths: list[str]) -> Optional[Path]:
    return next((Path(path) for path in paths if Path(path).exists()), None)


def font(path: Optional[Path], size: int) -> ImageFont.ImageFont:
    return ImageFont.truetype(str(path), size, index=0) if path else ImageFont.load_default()


def load_stats() -> tuple[int, int]:
    records = []
    for line in NDJSON.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    active = [record for record in records if record.get("status", "active") == "active"]
    prefectures = {record.get("prefecture") for record in active if record.get("prefecture")}
    return len(active), len(prefectures)


def paper_texture(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, PAPER)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            grain = ((x * 17 + y * 31) % 13) - 6
            pixels[x, y] = tuple(max(0, min(255, channel + grain)) for channel in PAPER)
    return image


def circle_photo(path: Path, size: int, border: int = 9) -> Image.Image:
    source = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    source = ImageOps.fit(source, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    photo = Image.new("RGBA", (size + border * 2, size + border * 2), (0, 0, 0, 0))
    ImageDraw.Draw(photo).ellipse((0, 0, photo.width - 1, photo.height - 1), fill=(54, 47, 41, 255))
    photo.paste(source, (border, border), mask)
    return photo


def draw_pin(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    radius = int(15 * scale)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)
    draw.ellipse((x - radius + 4, y - radius + 4, x + radius - 4, y + radius - 4), fill=PURPLE)
    draw.polygon(((x - radius + 4, y + 8), (x + radius - 4, y + 8), (x, y + int(34 * scale))), fill=PURPLE)
    draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=WHITE)


def compose() -> Image.Image:
    total, installed = load_stats()
    image = paper_texture(CANVAS).convert("RGBA")
    draw = ImageDraw.Draw(image)
    bold_path = find_font(FONT_BOLD)
    regular_path = find_font(FONT_REGULAR) or bold_path
    fonts = {
        "eyebrow": font(bold_path, 27),
        "title": font(bold_path, 96),
        "title2": font(bold_path, 82),
        "body": font(regular_path, 28),
        "badge_label": font(bold_path, 25),
        "badge_count": font(bold_path, 76),
        "badge_small": font(bold_path, 22),
        "ribbon": font(bold_path, 25),
        "brand": font(bold_path, 19),
    }

    # Sea panel and simple island silhouettes.
    draw.rounded_rectangle((700, -40, 1245, 665), radius=90, fill=SKY)
    islands = [
        [(1028, 44), (1093, 31), (1140, 62), (1115, 105), (1053, 112), (1018, 78)],
        [(994, 126), (1026, 153), (1008, 191), (966, 180), (958, 146)],
        [(945, 199), (975, 220), (962, 260), (921, 276), (898, 244), (915, 211)],
        [(880, 285), (923, 304), (938, 341), (899, 363), (853, 337), (844, 306)],
        [(824, 362), (857, 393), (837, 423), (795, 416), (788, 386)],
    ]
    for points in islands:
        draw.polygon(points, fill=(118, 175, 82, 205))
    draw.arc((735, 90, 1200, 525), 20, 142, fill=(255, 255, 255, 180), width=4)
    for x, y, scale in ((1060, 68, 1.0), (1000, 151, .9), (934, 232, 1.0), (879, 317, .85), (814, 393, .8)):
        draw_pin(draw, x, y, scale)

    # Heading.
    draw.text((54, 35), "全国のポケふた・ポケモンマンホール", font=fonts["eyebrow"], fill=INK)
    draw.line((56, 75, 655, 75), fill=(91, 71, 126), width=3)
    draw.text((48, 92), "ポケふた", font=fonts["title"], fill=INK, stroke_width=1, stroke_fill=INK)
    draw.text((86, 192), "データマップ", font=fonts["title2"], fill=PURPLE_DARK)
    draw.text((58, 301), "都道府県別・ポケモン別に探せる", font=fonts["body"], fill=(91, 77, 66))
    draw.text((58, 342), "全国のポケふた旅ガイド", font=fonts["body"], fill=(91, 77, 66))

    # Nationwide count badge.
    badge = (545, 83, 765, 303)
    draw.ellipse(badge, fill=PURPLE, outline=(255, 255, 255, 210), width=5)
    draw.ellipse((554, 92, 756, 294), outline=(255, 255, 255, 90), width=2)
    label = "全国"
    draw.text((655, 110), label, font=fonts["badge_label"], fill=WHITE, anchor="ma")
    draw.text((655, 143), str(total), font=fonts["badge_count"], fill=YELLOW, anchor="ma")
    draw.text((655, 225), f"枚 / {installed}都道府県", font=fonts["badge_small"], fill=WHITE, anchor="ma")

    # Actual manhole covers.
    placements = ((955, 430, 235, 8), (760, 478, 145, -8), (1111, 363, 124, 9))
    for photo_id, (cx, cy, size, angle) in zip(PHOTO_IDS, placements):
        path = IMAGE_DIR / f"{photo_id}_latest.jpeg"
        if not path.exists():
            continue
        photo = circle_photo(path, size)
        photo = photo.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        shadow = Image.new("RGBA", photo.size, (0, 0, 0, 0))
        shadow.paste((45, 32, 20, 115), (0, 10), photo.getchannel("A"))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        position = (int(cx - photo.width / 2), int(cy - photo.height / 2))
        image.alpha_composite(shadow, position)
        image.alpha_composite(photo, position)

    # Travel ribbon and brand.
    ribbon_points = [(36, 434), (604, 419), (627, 476), (53, 493)]
    draw.polygon(ribbon_points, fill=YELLOW)
    draw.text((70, 441), "旅の思い出に、ポケふた探しの冒険を！", font=fonts["ribbon"], fill=INK)
    draw.text((54, 575), "data.pokefuta.com/summary/", font=fonts["brand"], fill=(88, 73, 62))
    draw.text((1147, 580), "POKEFUTA TRACKER", font=fonts["brand"], fill=PURPLE_DARK, anchor="ra")

    return image.convert("RGB")


def main() -> None:
    output = compose()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output.save(OUTPUT, "PNG", optimize=True)
    print(f"Saved: {OUTPUT} ({output.width}x{output.height})")


if __name__ == "__main__":
    main()
