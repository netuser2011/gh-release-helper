# -*- coding: utf-8 -*-
"""syscert：自动信任系统证书的导出与降级逻辑，全程用临时目录，不碰真实用户目录。"""

import os
import tempfile
import types
import unittest
from pathlib import Path

import syscert


class SystemCertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.saved_env = os.environ.get(syscert.CA_ENV)
        os.environ.pop(syscert.CA_ENV, None)
        self.addCleanup(self._restore_env)

        self.saved_dir, self.saved_file = syscert._CERT_DIR, syscert._CA_FILE
        self.saved_last = dict(syscert._last)
        self.saved_certifi = syscert._certifi_pems
        self.saved_system = syscert._system_pems
        syscert._CERT_DIR = self.root / "certs"
        syscert._CA_FILE = self.root / "certs" / "ca-bundle.pem"
        self.addCleanup(self._restore_paths)

    def _restore_paths(self):
        syscert._CERT_DIR, syscert._CA_FILE = self.saved_dir, self.saved_file
        syscert._certifi_pems = self.saved_certifi
        syscert._system_pems = self.saved_system
        syscert._last.clear()
        syscert._last.update(self.saved_last)

    def _restore_env(self):
        if self.saved_env is None:
            os.environ.pop(syscert.CA_ENV, None)
        else:
            os.environ[syscert.CA_ENV] = self.saved_env

    def test_exports_bundle_and_sets_env(self):
        sample = "-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----\n"
        syscert._certifi_pems = lambda: [sample]
        syscert._system_pems = lambda: [sample, sample]  # 重复要去重

        self.assertTrue(syscert.ensure_system_certs())
        self.assertEqual(os.environ[syscert.CA_ENV], str(syscert._CA_FILE))
        data = syscert._CA_FILE.read_text(encoding="ascii")
        self.assertEqual(data.count("BEGIN CERTIFICATE"), 1, "重复证书只留一份")
        self.assertIn("已信任系统证书", syscert.describe())

    def test_merges_certifi_and_system(self):
        a = "-----BEGIN CERTIFICATE-----\nQQ==\n-----END CERTIFICATE-----\n"
        b = "-----BEGIN CERTIFICATE-----\nQg==\n-----END CERTIFICATE-----\n"
        syscert._certifi_pems = lambda: [a]
        syscert._system_pems = lambda: [b]

        syscert.ensure_system_certs()
        self.assertEqual(syscert._CA_FILE.read_text(encoding="ascii").count("BEGIN CERTIFICATE"), 2)

    def test_respects_existing_env(self):
        os.environ[syscert.CA_ENV] = str(self.root / "my.pem")
        called = []
        syscert._certifi_pems = lambda: called.append(1) or []
        self.assertFalse(syscert.ensure_system_certs())
        self.assertEqual(called, [], "用户已设置就不该再导出")
        self.assertEqual(os.environ[syscert.CA_ENV], str(self.root / "my.pem"))

    def test_export_failure_degrades_silently(self):
        def boom():
            raise RuntimeError("模拟系统证书读取失败")
        syscert._certifi_pems = lambda: []
        syscert._system_pems = boom
        self.assertFalse(syscert.ensure_system_certs())
        self.assertNotIn(syscert.CA_ENV, os.environ)
        self.assertIn("未生效", syscert.describe())

    def test_no_certificates_is_not_an_error(self):
        syscert._certifi_pems = lambda: []
        syscert._system_pems = lambda: []
        self.assertFalse(syscert.ensure_system_certs())
        self.assertIn("没有可导出", syscert.describe())

    def test_real_environment_exports_something(self):
        """真实环境下原始实现至少能导出证书（Windows 上含代理工具根证书）。"""
        pems = self.saved_system()  # setUp 里保存的原始实现，不受本测试外 mock 影响
        self.assertGreater(len(pems), 0)


if __name__ == "__main__":
    unittest.main()
