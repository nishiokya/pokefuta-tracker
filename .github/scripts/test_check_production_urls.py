import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check_production_urls.py")
SPEC = importlib.util.spec_from_file_location("check_production_urls", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(checker)

# このファイル自身がスキャン対象に含まれても落ちないよう、テスト内の loopback URL は
# 文字列連結で組み立てて原文には現れないようにしている（1つの文字列に戻さないこと）。


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


    def test_finds_hosts_without_port_or_path(self):
        host = "local" + "host"
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            # 行末終わり・) 終わりの両方を拾えること
            page.write_text(f"var a = http://{host}\nfoo(http://{host});\n")

            self.assertEqual(
                checker.find_loopback_urls([page]),
                [(page, 1, f"http://{host}"), (page, 2, f"http://{host}")],
            )

    def test_finds_every_url_on_a_minified_line(self):
        host = "local" + "host"
        loopback_host = "127.0." + "0.1"
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle.js"
            bundle.write_text(f'var x="http://{host}:3000/a";var y="http://{loopback_host}:8000/b";')

            self.assertEqual(
                checker.find_loopback_urls([bundle]),
                [
                    (bundle, 1, f"http://{host}:3000/a"),
                    (bundle, 1, f"http://{loopback_host}:8000/b"),
                ],
            )

    def test_finds_hosts_followed_by_query_or_fragment(self):
        host = "local" + "host"
        loopback_host = "127.0." + "0.1"
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            page.write_text(f'var a="http://{host}?api=1";\nvar b="http://{loopback_host}#debug";\n')

            self.assertEqual(
                checker.find_loopback_urls([page]),
                [
                    (page, 1, f"http://{host}?api=1"),
                    (page, 2, f"http://{loopback_host}#debug"),
                ],
            )

    def test_scans_deployed_ndjson_and_text_files(self):
        host = "local" + "host"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # pages-deploy.yml が docs/*.ndjson と robots.txt を dist へ公開する
            dataset = root / "pokefuta.ndjson"
            robots = root / "robots.txt"
            dataset.write_text(f'{{"url": "http://{host}:3000/a"}}\n')
            robots.write_text(f"Sitemap: http://{host}:8000/sitemap.xml\n")

            # ディレクトリ走査の順序は OS 依存なので順不同で比較する
            self.assertCountEqual(
                checker.find_loopback_urls([root]),
                [
                    (dataset, 1, f"http://{host}:3000/a"),
                    (robots, 1, f"http://{host}:8000/sitemap.xml"),
                ],
            )

    def test_finds_hosts_inside_template_literals(self):
        host = "local" + "host"
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            page.write_text("const url = `http://" + host + "`;\n")

            self.assertEqual(
                checker.find_loopback_urls([page]), [(page, 1, f"http://{host}")]
            )

    def test_ignores_addresses_that_merely_start_with_a_loopback_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            page.write_text('const u = "http://127.0.' + '0.15:3000/x";\n')

            self.assertEqual(checker.find_loopback_urls([page]), [])

    def test_finds_ipv6_loopback(self):
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            page.write_text('const u = "http://[' + '::1]:3000/x";\n')

            self.assertEqual(
                checker.find_loopback_urls([page]), [(page, 1, "http://[::1]:3000/x")]
            )

    def test_scans_baked_data_files(self):
        host = "local" + "host"
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "top-feed.json"
            feed.write_text(f'{{"api": "http://{host}:3000/api"}}')

            self.assertEqual(
                checker.find_loopback_urls([feed]), [(feed, 1, f"http://{host}:3000/api")]
            )

    def test_ignores_hostnames_that_merely_start_with_localhost(self):
        host = "local" + "host"
        with tempfile.TemporaryDirectory() as directory:
            page = Path(directory) / "app.js"
            page.write_text(f'const ok = "https://{host}.example.com/";\n')

            self.assertEqual(checker.find_loopback_urls([page]), [])


if __name__ == "__main__":
    unittest.main()
