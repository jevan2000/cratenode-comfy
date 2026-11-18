"""Security tests (no ComfyUI needed): workflows may only read files in allowed folders,
and Copy Writer only calls this machine unless the config allows another host.

    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, copywriter  # noqa: E402


class FileReads(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.outside = Path(tempfile.mkdtemp())
        (self.data / "rows.csv").write_text("title\nHi\n", encoding="utf-8")
        (self.outside / "secret.txt").write_text("private", encoding="utf-8")
        self.cfg = config.Config(data_dir=self.data)

    def test_inside_the_data_folder(self):
        self.assertEqual(self.cfg.resolve_data_path("rows.csv"), self.data / "rows.csv")
        self.assertEqual(self.cfg.resolve_data_path(str(self.data / "rows.csv")), self.data / "rows.csv")

    def test_outside_is_refused(self):
        with self.assertRaisesRegex(PermissionError, "data_roots"):
            self.cfg.resolve_data_path(str(self.outside / "secret.txt"))
        with self.assertRaises(PermissionError):
            self.cfg.resolve_data_path(str(self.data / ".." / self.outside.name / "secret.txt"))

    def test_extra_roots_allow_more(self):
        p = str(self.outside / "secret.txt")
        self.assertEqual(self.cfg.resolve_data_path(p, [self.outside]), Path(p))
        cfg = config.Config(data_dir=self.data, data_roots=[self.outside])
        self.assertEqual(cfg.resolve_data_path(p), Path(p))

    def test_bundled_files_allowed(self):
        bundled = config.BUNDLED_TEMPLATES / "thumbnail.json"
        self.assertEqual(config.Config().resolve_data_path(str(bundled)), bundled)

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_symlink_out_is_refused(self):
        link = self.data / "link.txt"
        try:
            os.symlink(self.outside / "secret.txt", link)
        except OSError:
            self.skipTest("cannot create symlinks here")
        with self.assertRaises(PermissionError):
            self.cfg.resolve_data_path(str(link))

    def test_config_keys(self):
        cfg = config.Config.from_dict({"data_roots": ["D:/data"], "allowed_hosts": ["OllamaBox"]}, "test")
        self.assertEqual(cfg.data_roots, [Path("D:/data")])
        self.assertEqual(cfg.allowed_hosts, ["ollamabox"])


class Hosts(unittest.TestCase):
    def test_loopback_only_by_default(self):
        for ok in ("http://127.0.0.1:11434", "http://localhost:11434", "https://[::1]:11434"):
            copywriter.check_host(ok)
        with self.assertRaisesRegex(PermissionError, "allowed_hosts"):
            copywriter.check_host("http://example.com:11434")
        with self.assertRaises(PermissionError):
            copywriter.check_host("http://127.0.0.1.example.com:11434")

    def test_allowed_hosts_and_schemes(self):
        copywriter.check_host("http://ollamabox:11434", ["OllamaBox"])
        for bad in ("file:///etc/passwd", "ftp://127.0.0.1/", "127.0.0.1:11434", ""):
            with self.assertRaises(ValueError):
                copywriter.check_host(bad)

    def test_generate_checks_before_sending(self):
        with self.assertRaises(PermissionError):
            copywriter.generate("http://example.com", "m", "p")


if __name__ == "__main__":
    unittest.main()
