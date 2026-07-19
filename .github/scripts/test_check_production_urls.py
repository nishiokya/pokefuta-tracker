import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_production_urls.py")
SPEC = importlib.util.spec_from_file_location("check_production_urls", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)


class CheckProductionUrlsTest(unittest.TestCase):
    def test_finds_loopback_urls_with_line_numbers(self):
        forbidden_url = "http://local" + "host:3000/profile"
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "index.html"
            page.write_text(f"safe\n<a href='{forbidden_url}'>profile</a>\n")

            self.assertEqual(checker.find_loopback_urls([page]), [(page, 2, forbidden_url)])

    def test_ignores_non_url_mentions_and_binary_assets(self):
        loopback_host = "127.0." + "0.1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.js").write_text(f"// development host: {loopback_host}\n")
            (root / "photo.jpg").write_bytes(b"http://local" + b"host/image")

            self.assertEqual(checker.find_loopback_urls([root]), [])

    def test_excludes_only_matching_paths(self):
        forbidden_url = "http://0.0." + "0.0:8000/"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "app.test.js"
            production = root / "app.js"
            fixture.write_text(forbidden_url)
            production.write_text(forbidden_url)

            self.assertEqual(
                checker.find_loopback_urls([root], ["*.test.js"]),
                [(production, 1, forbidden_url)],
            )


if __name__ == "__main__":
    unittest.main()
