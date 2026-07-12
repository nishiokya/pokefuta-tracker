import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


def _manhole(**overrides) -> dict:
    base = {
        "id": "1",
        "prefecture": "長野県",
        "city": "岡谷",
        "address": "長野県岡谷市",
        "lat": 36.0,
        "lng": 138.0,
        "pokemons": ["ピカチュウ"],
        "titles": [],
        "tags": [],
    }
    base.update(overrides)
    return base


def _generate(manhole: dict) -> str:
    return pages.generate_html(
        manhole=manhole,
        photo=None,
        pokemon_meta={},
        nearby=[],
        same_pref=[],
        pref_total=0,
        same_pokemon=[],
        id_to_image_url={},
    )


BADGE_MARKUP = "<span class='hero-badge hero-badge-pre'>🚧 設置前</span>"


class PreinstallRenderingTests(unittest.TestCase):
    def test_preinstall_shows_badge_and_notice_without_upload_link(self):
        manhole = _manhole(
            installed=False,
            installation_note="2026年8月上旬までに設置予定。",
        )
        html = _generate(manhole)
        self.assertIn(BADGE_MARKUP, html)
        self.assertIn("設置前のポケふたです", html)
        self.assertIn("2026年8月上旬までに設置予定。", html)
        # No upload CTA (placeholder link nor the secondary hero-actions button)
        # must be rendered anywhere on the page when 設置前.
        self.assertNotIn("pokefuta.com/upload", html)
        self.assertNotIn('<div class="hero-actions">', html)

    def test_preinstall_without_note_uses_default_text(self):
        manhole = _manhole(installed=False)
        html = _generate(manhole)
        self.assertIn(BADGE_MARKUP, html)
        self.assertIn(
            "<span class='placeholder-sub'>設置予定</span>",
            html,
        )

    def test_normal_installed_absent_has_no_preinstall_markers(self):
        # Absent 'installed' field must be treated as installed=True (default rule).
        manhole = _manhole()
        html = _generate(manhole)
        self.assertNotIn(BADGE_MARKUP, html)
        self.assertNotIn("設置前のポケふたです", html)
        self.assertIn("pokefuta.com/upload", html)
        self.assertIn("hero-actions", html)

    def test_normal_installed_true_has_no_preinstall_markers(self):
        manhole = _manhole(installed=True)
        html = _generate(manhole)
        self.assertNotIn(BADGE_MARKUP, html)
        self.assertNotIn("設置前のポケふたです", html)
        self.assertIn("pokefuta.com/upload", html)
        self.assertIn("hero-actions", html)


if __name__ == "__main__":
    unittest.main()
