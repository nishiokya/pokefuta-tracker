import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("inject_site_header.py")
SPEC = importlib.util.spec_from_file_location("inject_site_header", MODULE_PATH)
header = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(header)

HEADER = header.HEADER
STYLESHEET = header.STYLESHEET
inject = header.inject


class InjectSiteHeaderTest(unittest.TestCase):
    def test_injects_header_stylesheet_and_body_class(self):
        result = inject("<!doctype html><html><head></head><body><main></main></body></html>")
        self.assertIn(STYLESHEET, result)
        self.assertIn(HEADER, result)
        self.assertIn('<body class="has-site-header">', result)

    def test_preserves_existing_body_classes(self):
        result = inject('<html><head></head><body class="map-page"></body></html>')
        self.assertIn('<body class="has-site-header map-page">', result)

    def test_does_not_duplicate_shared_or_top_header(self):
        shared = f"<html><head></head><body>{HEADER}</body></html>"
        top = '<html><head></head><body><header class="top-app-bar"></header></body></html>'
        self.assertEqual(inject(shared), shared)
        self.assertEqual(inject(top), top)

    def test_skips_redirect_documents(self):
        redirect = '<!doctype html><meta http-equiv="refresh" content="0; url=/">'
        self.assertEqual(inject(redirect), redirect)


if __name__ == "__main__":
    unittest.main()
