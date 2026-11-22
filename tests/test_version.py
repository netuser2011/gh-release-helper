# -*- coding: utf-8 -*-
"""版本模块测试：V 前缀规范化、数字比对、缺失回退、原子写回。全程离线、用临时目录。"""

import tempfile
import unittest
from pathlib import Path

import version


class NormalizeParseTest(unittest.TestCase):
    def test_normalize_keeps_v_prefix(self):
        for raw in ("v1.2.0", "1.2.0", "V1.2.0", " v1.2 ", "v1.2.0b"):
            with self.subTest(raw=raw):
                self.assertEqual(version.normalize(raw), "V1.2.0")

    def test_parse_is_numeric_tuple(self):
        self.assertEqual(version.parse("v1.2.0"), (1, 2, 0))
        self.assertEqual(version.parse("V2.10.3"), (2, 10, 3))
        self.assertEqual(version.parse("1.2"), (1, 2, 0))

    def test_is_newer_uses_numeric_order(self):
        self.assertTrue(version.is_newer("v1.10.0", "V1.2.0"))
        self.assertTrue(version.is_newer("v1.3.0", "V1.2.0"))
        self.assertFalse(version.is_newer("v1.2.0", "V1.2.0"))
        self.assertFalse(version.is_newer("v1.1.0", "V1.2.0"))


class VersionFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "version.txt"
        original = version.VERSION_FILE
        version.VERSION_FILE = self.path
        self.addCleanup(setattr, version, "VERSION_FILE", original)

    def test_read_missing_falls_back_to_v0(self):
        self.assertEqual(version.read_current(), "V0.0.0")

    def test_read_garbage_falls_back_to_v0(self):
        self.path.write_text("不是版本号", encoding="utf-8")
        self.assertEqual(version.read_current(), "V0.0.0")

    def test_write_then_read_roundtrip(self):
        saved = version.write_current("v1.3.0")
        self.assertEqual(saved, self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8").strip(), "V1.3.0")
        self.assertEqual(version.read_current(), "V1.3.0")
        self.assertFalse(list(Path(self.tmp.name).glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
