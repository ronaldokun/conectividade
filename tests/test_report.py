import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
from pathlib import Path

from url_availability_checker import Result, check_url, get_origin_location, read_urls, render_report


class TestHelpers(unittest.TestCase):
    def test_read_urls_ignores_comments_and_blanks_and_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "urls.txt"
            source.write_text("# comment\n\nhttps://example.com\nwww.example.org\n", encoding="utf-8")
            self.assertEqual(read_urls(source), ["https://example.com", "https://www.example.org"])
            source.write_text("ftp://example.com\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_urls(source)

    def test_snapshot_filenames_include_run_timestamp(self):
        class Tab:
            url = "https://example.com"
            title = "Example"
            html = "<html></html>"

            def get(self, url, timeout):
                return True

            def run_js(self, script):
                return 200

            def get_screenshot(self, path, name, full_page):
                (Path(path) / name).write_bytes(b"png")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            snapshots = output / "snapshots"
            snapshots.mkdir()
            result = check_url(Tab(), "https://example.com", 1, output, 30, 0, "20260102_030405", "lista-sites")
            self.assertEqual(result.screenshot, "snapshots/lista-sites_20260102_030405_0001.png")
            self.assertEqual(result.snapshot, "snapshots/lista-sites_20260102_030405_0001.html")

    @patch("url_availability_checker.urlopen")
    def test_origin_location_uses_public_ip_lookup_and_handles_unavailable_service(self, urlopen):
        urlopen.return_value = BytesIO(b'{"city":"Sao Paulo","region":"SP","country_name":"Brazil"}')
        self.assertEqual(get_origin_location(), "Sao Paulo, SP, Brazil")
        urlopen.side_effect = OSError("offline")
        self.assertIsNone(get_origin_location())

    def test_report_escapes_values_and_marks_non_2xx_as_failure(self):
        report = render_report([
            Result(url="https://example.com/?a=1&b=2", status_code=200, title="<safe>"),
            Result(url="https://example.org", status_code=503),
        ], report_name="lista & sites", origin_location="São Paulo, SP, Brasil")
        self.assertIn("APROVADO", report)
        self.assertIn("REPROVADO", report)
        self.assertNotIn("<th>Status</th>", report)
        self.assertIn("&lt;safe&gt;", report)
        self.assertIn("lista &amp; sites — Relatório", report)
        self.assertIn("São Paulo, SP, Brasil", report)
        self.assertIn("1 de 2 URLs aprovadas", report)


if __name__ == "__main__":
    unittest.main()
