# -*- coding: utf-8 -*-
"""用户数据目录测试：环境变量优先级、默认位置与旧文件迁移，全程用临时目录。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paths


class AppDataDirTest(unittest.TestCase):
    def test_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "custom-data"
            with patch.dict(os.environ, {"GHR_DATA_DIR": str(target)}):
                self.assertEqual(paths.app_data_dir(), target)
            self.assertTrue(target.is_dir(), "目录要尽力建好，否则保存会直接失败")

    def test_default_dir_per_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"GHR_DATA_DIR": "", "APPDATA": str(root)}):
                result = paths.app_data_dir()
            if os.name == "nt":
                self.assertEqual(result, root / "gh-release-helper")
            else:
                self.assertTrue(str(result).endswith(".local/share/gh-release-helper"))


class MigrateLegacyFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "src"
        self.source.mkdir()
        (self.source / "main.py").write_text("", encoding="utf-8")  # 标记为源码目录
        self.data = self.root / "data"
        self.data.mkdir()
        self.addCleanup(setattr, paths, "__file__", paths.__file__)
        paths.__file__ = str(self.source / "paths.py")
        self.env = patch.dict(os.environ, {"GHR_DATA_DIR": str(self.data)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_copies_legacy_files_without_removing_them(self):
        for name in paths._LEGACY_FILES:
            (self.source / name).write_text(name, encoding="utf-8")
        paths.migrate_legacy_files()
        for name in paths._LEGACY_FILES:
            self.assertEqual((self.data / name).read_text(encoding="utf-8"), name)
            self.assertTrue((self.source / name).is_file(), "旧文件要留着，迁移失败也不丢数据")

    def test_existing_target_is_not_overwritten(self):
        (self.source / "favorites.json").write_text("old", encoding="utf-8")
        (self.data / "favorites.json").write_text("new", encoding="utf-8")
        paths.migrate_legacy_files()
        self.assertEqual((self.data / "favorites.json").read_text(encoding="utf-8"), "new")

    def test_copy_failure_does_not_raise(self):
        (self.source / "config.json").write_text("{}", encoding="utf-8")
        with patch.object(paths.shutil, "copy2", side_effect=OSError("占用")):
            paths.migrate_legacy_files()
