"""Shared presentation for index cards; page-specific content stays with its generator.

Keep surface and thumbnail rules here, not in per-page overrides. Layout (a
ranking row, gallery, or carousel) belongs to the page. Photos of a lid are
square so its circular design is not cropped to a landscape banner.
"""

from html import escape

try:
    from apps.scraper.manhole_tile_image import responsive_attrs
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from manhole_tile_image import responsive_attrs


CARD_CSS = """
    [data-zukan-card] {
      --zukan-card-space: 12px;
      --zukan-card-title-size: 1rem;
      min-width: 0;
      overflow: hidden;
      border: 1px solid #ded3bd;
      border-radius: 14px;
      background: #fffaf0;
      box-shadow: 0 4px 12px rgba(80,54,20,.06);
      color: #332f2a;
      text-decoration: none;
    }
    a[data-zukan-card]:hover, a[data-zukan-card]:focus-visible {
      border-color: #6f55a3;
      box-shadow: 0 2px 8px rgba(111,85,163,.12);
    }
    [data-zukan-image] {
      display: block;
      width: 100%;
      height: auto;
      aspect-ratio: 1;
      object-fit: cover;
      border-radius: 10px;
      background: #ece4d7;
    }
"""


def card_open(class_name: str, *, href: str = "", attrs: dict[str, str] | None = None) -> str:
    """Open a link or article. Attribute values are escaped; content is rendered by callers."""
    tag = "a" if href else "article"
    attributes = {"class": class_name, "data-zukan-card": ""}
    if href:
        attributes["href"] = href
    attributes.update(attrs or {})
    return f'<{tag}' + ''.join(
        f' {key}="{escape(str(value), quote=True)}"' for key, value in attributes.items()
    ) + '>'


def card_image(src: str, *, alt: str = "", size: int = 320, sizes: str = "") -> str:
    """A square lid photo with a reserved aspect ratio and consistent loading behavior.

    sizes is the displayed width; with it the browser picks a small WebP (manhole_tile_image.srcset).
    """
    source = responsive_attrs(src, sizes) if sizes else f'src="{escape(src, quote=True)}"'
    return (
        f'<img {source} alt="{escape(alt, quote=True)}" '
        f'width="{size}" height="{size}" loading="lazy" decoding="async" data-zukan-image="">'
    )
