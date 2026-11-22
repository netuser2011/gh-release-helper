# -*- coding: utf-8 -*-
"""自身更新测试：版本比对、安装包筛选、静默安装/自动解压、删包、失败降级。

全程离线：gh/dl/ui/subprocess/zipfile/version 都用假实现，不联网、不碰真实文件。
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import github_api as gh
import self_update as su
import version


def release(tag="v1.3.0", assets=None, body=""):
    return {
        "tag_name": tag,
        "body": body,
        "assets": assets if assets is not None else [
            {"name": "GHDownloader-Windows-V1.3.0-Setup.exe",
             "browser_download_url": "https://x/setup.exe", "size": 100},
        ],
    }


class CheckSelfUpdateTest(unittest.TestCase):
    def setUp(self):
        self.current = "V1.2.0"
        self.release = release()
        self.raise_error = None
        for target, name, value in (
            (version, "read_current", lambda: self.current),
            (su.gh, "get_latest_release", self._get_release),
        ):
            original = getattr(target, name)
            setattr(target, name, value)
            self.addCleanup(setattr, target, name, original)

    def _get_release(self, repo, token):
        if self.raise_error:
            raise self.raise_error
        return self.release

    def _check(self):
        with redirect_stdout(io.StringIO()):
            return su.check_self_update("tok")

    def test_newer_version_detected(self):
        has, rel = self._check()
        self.assertTrue(has)
        self.assertEqual(rel, self.release)

    def test_same_version_not_detected(self):
        self.current = "V1.3.0"
        has, _ = self._check()
        self.assertFalse(has)

    def test_failure_degrades_without_raising(self):
        self.raise_error = gh.GitHubError("限流", status_code=429)
        has, rel = self._check()
        self.assertFalse(has)
        self.assertEqual(rel, {})


class PickInstallerTest(unittest.TestCase):
    def test_prefers_exe_over_zip(self):
        rel = release(assets=[
            {"name": "GH.zip", "browser_download_url": "x"},
            {"name": "GH-Setup.exe", "browser_download_url": "y"},
        ])
        picked = su.pick_installer(rel)
        self.assertEqual(picked[1], "exe")
        self.assertEqual(picked[0]["name"], "GH-Setup.exe")

    def test_zip_fallback(self):
        rel = release(assets=[{"name": "GH.zip", "browser_download_url": "x"}])
        picked = su.pick_installer(rel)
        self.assertEqual(picked[1], "zip")

    def test_no_installer_returns_none(self):
        self.assertIsNone(su.pick_installer(release(assets=[])))


class OfferInstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.answers = []
        self.popen_calls = []
        self.written = []
        self.running_install_dir = False
        self.extract_fail = False

        for target, name, value in (
            (su.ui, "confirm", self._confirm),
            (su, "_running_from_install_dir", lambda: self.running_install_dir),
            (su.subprocess, "Popen", self._popen),
            (version, "write_current", lambda tag: self.written.append(tag) or self.dir / "version.txt"),
        ):
            original = getattr(target, name)
            setattr(target, name, value)
            self.addCleanup(setattr, target, name, original)

    def _confirm(self, prompt, default=True):
        return self.answers.pop(0) if self.answers else default

    def _popen(self, args):
        self.popen_calls.append(args)

    def run_offer(self, kind, latest="v1.3.0"):
        saved = self.dir / ("GH-Setup.exe" if kind == "exe" else "GH.zip")
        if kind == "zip":
            import zipfile
            with zipfile.ZipFile(saved, "w") as zf:
                zf.writestr("GH Downloader.exe", b"fake")
        else:
            saved.write_bytes(b"fake-exe")
        buf = io.StringIO()
        with redirect_stdout(buf):
            su.offer_installer(saved, kind, latest)
        return saved, buf.getvalue()

    def test_exe_silent_install_and_write_version(self):
        self.answers = [True]
        saved, out = self.run_offer("exe")
        self.assertEqual(len(self.popen_calls), 1)
        self.assertEqual(self.popen_calls[0][0], str(saved))
        self.assertIn("/VERYSILENT", self.popen_calls[0])
        self.assertEqual(self.written, ["v1.3.0"])

    def test_decline_keeps_file_no_install(self):
        self.answers = [False]
        saved, out = self.run_offer("exe")
        self.assertEqual(self.popen_calls, [])
        self.assertEqual(self.written, [])
        self.assertTrue(saved.exists())

    def test_zip_extracts_and_deletes_on_yes(self):
        self.answers = [True, True]
        saved, out = self.run_offer("zip")
        self.assertTrue((self.dir / "GH").is_dir())
        self.assertEqual(self.written, ["v1.3.0"])
        self.assertFalse(saved.exists())
        self.assertIn("压缩包已删除", out)

    def test_zip_keeps_archive_on_no(self):
        self.answers = [True, False]
        saved, out = self.run_offer("zip")
        self.assertTrue((self.dir / "GH").is_dir())
        self.assertTrue(saved.exists())

    def test_install_dir_running_prompts_restart(self):
        self.running_install_dir = True
        self.answers = [True]
        saved, out = self.run_offer("exe")
        self.assertEqual(self.popen_calls, [])
        self.assertEqual(self.written, ["v1.3.0"])
        self.assertIn("关闭本程序", out)


if __name__ == "__main__":
    unittest.main()
