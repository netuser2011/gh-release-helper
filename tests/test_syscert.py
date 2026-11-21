# -*- coding: utf-8 -*-
"""syscert：truststore 注入、尊重用户设置与失败降级，全程不打真实网络。"""

import os
import unittest

import syscert


class SystemCertTest(unittest.TestCase):
    def setUp(self):
        self.saved_env = os.environ.get(syscert.CA_ENV)
        os.environ.pop(syscert.CA_ENV, None)
        self.addCleanup(self._restore_env)

        self.saved_last = dict(syscert._last)
        self.saved_count = syscert._system_cert_count
        self.addCleanup(self._restore_state)

        self.calls = []
        self.failure = None

        def fake_inject():
            self.calls.append(1)
            if self.failure is not None:
                raise self.failure

        self.saved_truststore = None
        import sys as _sys
        if "truststore" in _sys.modules:
            self.saved_truststore = _sys.modules["truststore"]
        _sys.modules["truststore"] = type("M", (), {"inject_into_ssl": staticmethod(fake_inject)})
        self.addCleanup(self._restore_truststore)

    def _restore_env(self):
        if self.saved_env is None:
            os.environ.pop(syscert.CA_ENV, None)
        else:
            os.environ[syscert.CA_ENV] = self.saved_env

    def _restore_state(self):
        syscert._system_cert_count = self.saved_count
        syscert._last.clear()
        syscert._last.update(self.saved_last)

    def _restore_truststore(self):
        import sys as _sys
        if self.saved_truststore is None:
            del _sys.modules["truststore"]
        else:
            _sys.modules["truststore"] = self.saved_truststore

    def test_injects_and_reports_enabled(self):
        syscert._system_cert_count = lambda: 189
        self.assertTrue(syscert.ensure_system_certs())
        self.assertEqual(self.calls, [1])
        self.assertIn("已信任系统证书 189 张", syscert.describe())
        self.assertIn("truststore", syscert.describe())

    def test_no_cert_count_still_reports_enabled(self):
        syscert._system_cert_count = lambda: 0
        self.assertTrue(syscert.ensure_system_certs())
        self.assertIn("已信任系统证书", syscert.describe())

    def test_respects_existing_env(self):
        os.environ[syscert.CA_ENV] = "/tmp/my.pem"
        self.assertFalse(syscert.ensure_system_certs())
        self.assertEqual(self.calls, [], "用户已设置就不该注入")
        self.assertEqual(os.environ[syscert.CA_ENV], "/tmp/my.pem")
        self.assertIn("尊重用户设置", syscert.describe())

    def test_injection_failure_degrades_silently(self):
        self.failure = RuntimeError("模拟注入失败")
        self.assertFalse(syscert.ensure_system_certs())
        self.assertIn("未生效", syscert.describe())
        self.assertNotIn(syscert.CA_ENV, os.environ)

    def test_repeated_calls_are_safe(self):
        syscert._system_cert_count = lambda: 10
        self.assertTrue(syscert.ensure_system_certs())
        self.assertTrue(syscert.ensure_system_certs())
        self.assertEqual(len(self.calls), 2, "truststore 的注入本身是幂等的")

    def test_real_truststore_is_importable(self):
        import truststore

        self.assertTrue(hasattr(truststore, "inject_into_ssl"))


if __name__ == "__main__":
    unittest.main()
