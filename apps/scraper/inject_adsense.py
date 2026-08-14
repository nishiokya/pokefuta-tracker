#!/usr/bin/env python3
"""Inject AdSense verification and explicit in-content ad units into built HTML.

No publisher ID means a deliberate no-op: review prerequisites can be deployed
without loading ad code or showing empty placeholders. GitHub Actions provides
the values through repository secrets after the owner creates the account.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


PUBLISHER_RE = re.compile(r"^(?:ca-)?pub-(\d{16})$")
SLOT_RE = re.compile(r"^\d{6,20}$")
MARKERS = {
    "prefecture": "<!-- adsense:prefecture -->",
    "manhole": "<!-- adsense:manhole -->",
}


def normalize_publisher_id(value: str) -> tuple[str, str]:
    """Return (pub-ID for ads.txt, ca-pub-ID for HTML)."""
    match = PUBLISHER_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("ADSENSE_PUBLISHER_ID must be pub- followed by 16 digits")
    digits = match.group(1)
    return f"pub-{digits}", f"ca-pub-{digits}"


def validate_slot(value: str, name: str) -> str:
    value = value.strip()
    if value and not SLOT_RE.fullmatch(value):
        raise ValueError(f"{name} must contain 6 to 20 digits")
    return value


def _ad_markup(client_id: str, slot_id: str, placement: str) -> str:
    return f"""<aside class="ad-slot ad-slot--{placement}" aria-label="広告">
  <span class="ad-slot__label">広告</span>
  <ins class="adsbygoogle pokefuta_adslot_1"
    data-ad-client="{client_id}"
    data-ad-slot="{slot_id}"></ins>
</aside>
<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>"""


def inject_html(
    html: str,
    client_id: str,
    prefecture_slot: str = "",
    manhole_slot: str = "",
) -> str:
    """Inject verification everywhere and ads only at explicit markers."""
    if 'http-equiv="refresh"' in html.lower() or "</head>" not in html:
        return html

    meta = f'<meta name="google-adsense-account" content="{client_id}">'
    if "google-adsense-account" not in html:
        html = html.replace("</head>", f"  {meta}\n</head>", 1)

    slots = {"prefecture": prefecture_slot, "manhole": manhole_slot}
    active = [name for name, marker in MARKERS.items() if marker in html and slots[name]]
    if not active:
        return html

    stylesheet = '<link rel="stylesheet" href="/assets/adsense.css">'
    loader = (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={client_id}" crossorigin="anonymous"></script>'
    )
    # Google公式の「画面幅ごとに正確な広告サイズを指定する」例に合わせる。
    # 外部CSSで広告本体の寸法を指定する方法は公式サポート外なので head に直書きする。
    sizing = """<style>
    .pokefuta_adslot_1 { display: block; width: 320px; height: 100px; }
    @media (min-width: 500px) { .pokefuta_adslot_1 { width: 468px; height: 60px; } }
    @media (min-width: 800px) { .pokefuta_adslot_1 { width: 728px; height: 90px; } }
  </style>"""
    if stylesheet not in html:
        html = html.replace(
            "</head>", f"  {stylesheet}\n  {sizing}\n  {loader}\n</head>", 1
        )

    for name in active:
        html = html.replace(MARKERS[name], _ad_markup(client_id, slots[name], name), 1)
    return html


def configure(root: Path, publisher: str, prefecture_slot: str, manhole_slot: str) -> tuple[int, int]:
    publisher_id, client_id = normalize_publisher_id(publisher)
    prefecture_slot = validate_slot(prefecture_slot, "ADSENSE_PREFECTURE_SLOT")
    manhole_slot = validate_slot(manhole_slot, "ADSENSE_MANHOLE_SLOT")

    updated = 0
    ad_pages = 0
    for path in sorted(root.rglob("*.html")):
        original = path.read_text(encoding="utf-8")
        result = inject_html(original, client_id, prefecture_slot, manhole_slot)
        if result != original:
            path.write_text(result, encoding="utf-8")
            updated += 1
        if 'class="ad-slot ' in result:
            ad_pages += 1

    (root / "ads.txt").write_text(
        f"google.com, {publisher_id}, DIRECT, f08c47fec0942fa0\n",
        encoding="utf-8",
    )
    return updated, ad_pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="dist", type=Path)
    args = parser.parse_args()

    publisher = os.environ.get("ADSENSE_PUBLISHER_ID", "").strip()
    prefecture_slot = os.environ.get("ADSENSE_PREFECTURE_SLOT", "").strip()
    manhole_slot = os.environ.get("ADSENSE_MANHOLE_SLOT", "").strip()

    if not publisher:
        if prefecture_slot or manhole_slot:
            raise SystemExit("AdSense slot IDs are set but ADSENSE_PUBLISHER_ID is missing")
        print("[inject_adsense] disabled: ADSENSE_PUBLISHER_ID is not configured")
        return 0

    updated, ad_pages = configure(args.root, publisher, prefecture_slot, manhole_slot)
    print(f"[inject_adsense] verified {updated} HTML files; enabled {ad_pages} ad pages; wrote ads.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
