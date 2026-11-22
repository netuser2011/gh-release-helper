# -*- coding: utf-8 -*-
"""github_api / downloader / favorites 的纯逻辑测试。

全部不打真实网络、不往项目目录写文件：接口用假响应，落盘用临时目录。
"""

import io
import json
import os
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import httpx
import requests

import cli
import downloader as dl
import favorites as fav
import github_api as gh


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, text="", broken_json=False):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text
        self._broken_json = broken_json

    def json(self):
        if self._broken_json:
            raise ValueError("not json")
        return self._payload


def patch_get(test, resp=None, exc=None):
    """把 gh.requests.get 换成假实现，测试结束时自动还原。"""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if exc is not None:
            raise exc
        return resp

    stub = types.SimpleNamespace(get=fake_get, exceptions=requests.exceptions)
    saved = gh.requests
    gh.requests = stub
    test.addCleanup(setattr, gh, "requests", saved)
    return calls


class RepoNameTest(unittest.TestCase):
    def test_accepts_owner_slash_repo(self):
        self.assertEqual(gh.normalize_repo("files-community/Files"), ("files-community", "Files"))

    def test_accepts_web_url(self):
        self.assertEqual(gh.normalize_repo("https://github.com/cli/cli"), ("cli", "cli"))
        self.assertEqual(gh.normalize_repo("github.com/cli/cli/"), ("cli", "cli"))

    def test_bare_name_is_not_a_repo(self):
        self.assertEqual(gh.normalize_repo("files"), (None, None))
        self.assertEqual(gh.normalize_repo(""), (None, None))
        self.assertEqual(gh.normalize_repo("a/b/c"), (None, None))


class AssetTypeTest(unittest.TestCase):
    def assets(self):
        return [
            {"name": "Files.appx", "size": 10},
            {"name": "Files.zip", "size": 20},
            {"name": "Files-Setup.exe", "size": 30},
            {"name": "SHA256SUMS", "size": 1},
            {"name": "https://x/Icons.zip", "size": 5},
        ]

    def test_ext_is_lowercase_and_dots_optional(self):
        self.assertEqual(gh.asset_ext("Files.ZIP"), "zip")
        self.assertEqual(gh.asset_ext("https://x/Icons.tar.gz"), "gz")
        self.assertEqual(gh.asset_ext("SHA256SUMS"), "无")

    def test_filter_accepts_leading_dot(self):
        self.assertEqual(len(gh.filter_by_ext(self.assets(), [".zip"])), 2)
        self.assertEqual(len(gh.filter_by_ext(self.assets(), ["EXE"])), 1)

    def test_empty_exts_returns_everything(self):
        self.assertEqual(len(gh.filter_by_ext(self.assets(), [])), 5)

    def test_release_assets_skips_junk(self):
        release = {"assets": [{"name": "a.zip"}, "不是字典", None]}
        self.assertEqual(gh.release_assets(release), [{"name": "a.zip"}])
        self.assertEqual(gh.release_assets({}), [])
        self.assertEqual(gh.release_assets(None), [])


class RequestErrorTest(unittest.TestCase):
    def test_success_returns_payload_and_headers(self):
        calls = patch_get(self, resp=FakeResponse(200, {"tag_name": "v1.0"}, {"X-RateLimit-Remaining": "4999"}))
        data, headers = gh.request_json("https://api.github.com/x", {"a": 1}, "tok")
        self.assertEqual(data["tag_name"], "v1.0")
        self.assertEqual(headers["X-RateLimit-Remaining"], "4999")
        self.assertEqual(calls[0]["params"], {"a": 1})
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer tok")

    def test_anonymous_request_has_no_authorization_header(self):
        calls = patch_get(self, resp=FakeResponse(200, {}))
        gh.request_json("https://api.github.com/x")
        self.assertNotIn("Authorization", calls[0]["headers"])

    def test_404_maps_to_not_found(self):
        patch_get(self, resp=FakeResponse(404, {"message": "Not Found"}))
        with self.assertRaises(gh.NotFoundError) as ctx:
            gh.get_latest_release("no/such")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_429_maps_to_rate_limited_with_status(self):
        patch_get(self, resp=FakeResponse(429, {"message": "API rate limit exceeded"}))
        with self.assertRaises(gh.RateLimitedError) as ctx:
            gh.get_latest_release("a/b")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("配一个 Token", str(ctx.exception))

    def test_403_rate_limit_carries_status(self):
        patch_get(self, resp=FakeResponse(403, {"message": "API rate limit exceeded"}))
        with self.assertRaises(gh.RateLimitedError) as ctx:
            gh.get_latest_release("a/b")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bad_token_error_carries_status(self):
        patch_get(self, resp=FakeResponse(401, {"message": "Bad credentials"}))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release("a/b")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_network_error_has_no_status(self):
        patch_get(self, exc=requests.exceptions.ConnectionError("refused"))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release("a/b")
        self.assertIsNone(ctx.exception.status_code)

    def test_rate_limit_message_suggests_token(self):
        patch_get(
            self,
            resp=FakeResponse(
                403,
                {"message": "API rate limit exceeded for 1.2.3.4"},
                {"X-RateLimit-Reset": "1700000000"},
            ),
        )
        with self.assertRaises(gh.RateLimitedError) as ctx:
            gh.get_latest_release("a/b")
        message = str(ctx.exception)
        self.assertIn("配一个 Token", message)
        # 光说「去配 Token」不够，得把能直接点开的地址一起给出来
        self.assertIn(gh.TOKEN_CREATE_URL, message)
        self.assertIn("scopes=public_repo", message)
        self.assertIn("菜单里按 0", message)

    def test_bad_token_is_not_reported_as_rate_limit(self):
        patch_get(self, resp=FakeResponse(401, {"message": "Bad credentials"}))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release("a/b")
        self.assertIn("鉴权失败", str(ctx.exception))

    def test_html_from_a_gateway_is_explained(self):
        patch_get(self, resp=FakeResponse(200, None, text="<html>waf</html>", broken_json=True))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release("a/b")
        self.assertIn("不是合法 JSON", str(ctx.exception))

    def test_ssl_error_mentions_proxy_tool(self):
        patch_get(self, exc=requests.exceptions.SSLError("unable to get local issuer certificate"))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release("a/b")
        self.assertIn("SSL 证书校验失败", str(ctx.exception))

    def test_proxy_timeout_and_offline_each_have_their_own_hint(self):
        # ConnectTimeout 同时属于 ConnectionError 和 Timeout，先按「连不上」解释更符合现场
        cases = [
            (requests.exceptions.ProxyError("boom"), "代理"),
            (requests.exceptions.ConnectionError("refused"), "无法连接"),
            (requests.exceptions.ConnectTimeout("slow"), "无法连接"),
            (requests.exceptions.ReadTimeout("slow"), "超时"),
        ]
        for exc, needle in cases:
            patch_get(self, exc=exc)
            with self.assertRaises(gh.GitHubError) as ctx:
                gh.get_latest_release("a/b")
            self.assertIn(needle, str(ctx.exception))

    def test_missing_release_explains_repo_exists(self):
        """404 要能分清「仓库不存在」和「仓库没发过 release」。"""

        def fake(url, params=None, headers=None, timeout=None):
            if "releases" in url:
                return FakeResponse(404, {"message": "Not Found"})
            return FakeResponse(200, {"full_name": "a/b"})

        gh.requests = types.SimpleNamespace(get=fake, exceptions=requests.exceptions)
        self.addCleanup(setattr, gh, "requests", requests)
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release_or_explain("a/b")
        self.assertIn("没有发布任何 release", str(ctx.exception))

    def test_missing_repo_says_so(self):
        patch_get(self, resp=FakeResponse(404, {"message": "Not Found"}))
        with self.assertRaises(gh.GitHubError) as ctx:
            gh.get_latest_release_or_explain("no/such")
        self.assertIn("不存在或无权访问", str(ctx.exception))

    def test_search_query_limits_match_to_repo_name(self):
        calls = patch_get(self, resp=FakeResponse(200, {"items": [{"full_name": "a/b"}], "total_count": 1}))
        items, total = gh.search_repos("files", "", limit=10)
        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        self.assertIn("in:name", calls[0]["params"]["q"])
        self.assertEqual(calls[0]["params"]["sort"], "stars")

    def test_search_rejects_unexpected_payload(self):
        patch_get(self, resp=FakeResponse(200, {"items": "不是列表"}))
        with self.assertRaises(gh.GitHubError):
            gh.search_repos("files")


class TokenSourceTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("GITHUB_TOKEN",)}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        saved_file = gh.TOKEN_FILE
        gh.TOKEN_FILE = Path(self.tmp.name) / ".github_token"
        self.addCleanup(setattr, gh, "TOKEN_FILE", saved_file)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_cli_token_wins_over_env_and_file(self):
        os.environ["GITHUB_TOKEN"] = "from_env"
        gh.save_token("from_file")
        self.assertEqual(gh.resolve_token("from_cli"), "from_cli")

    def test_env_wins_over_file(self):
        os.environ["GITHUB_TOKEN"] = "from_env"
        gh.save_token("from_file")
        self.assertEqual(gh.resolve_token(), "from_env")

    def test_file_is_the_last_fallback(self):
        os.environ.pop("GITHUB_TOKEN", None)
        gh.save_token("from_file")
        self.assertEqual(gh.resolve_token(), "from_file")

    def test_no_token_anywhere_is_not_an_error(self):
        os.environ.pop("GITHUB_TOKEN", None)
        self.assertEqual(gh.resolve_token(), "")

    def test_saved_token_drops_group_and_other_bits_on_posix(self):
        path = gh.save_token("ghp_abc")
        if os.name == "nt":
            # Windows 的 chmod 只能表达「可写 / 只读」，真正的归属控制靠 ACL，
            # README 里给了 icacls 命令，这里不做无意义的断言。
            self.skipTest("Windows 权限由 ACL 决定")
        self.assertFalse(path.stat().st_mode & 0o077, "Token 文件不能给同组和其他人读")

    def test_blank_env_token_is_ignored(self):
        os.environ["GITHUB_TOKEN"] = "   "
        self.assertEqual(gh.resolve_token(), "")


class FilenameTest(unittest.TestCase):
    def test_path_traversal_is_neutralised(self):
        self.assertEqual(dl.safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(dl.safe_filename("..\\..\\Windows\\system32\\evil.exe"), "evil.exe")

    def test_url_style_names_keep_only_the_last_segment(self):
        self.assertEqual(dl.safe_filename("https://x/releases/download/v1/Files.zip"), "Files.zip")

    def test_illegal_characters_are_stripped(self):
        cleaned = dl.safe_filename('weird<>:"|?*\x00name.zip')
        self.assertEqual(cleaned, "weirdname.zip")

    def test_empty_and_dot_only_names_fall_back(self):
        self.assertEqual(dl.safe_filename(""), "release-asset")
        self.assertEqual(dl.safe_filename("..."), "release-asset")

    def test_very_long_name_is_capped(self):
        self.assertLessEqual(len(dl.safe_filename("a" * 400 + ".zip")), 150)


class DownloadDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._saved_config = dl.CONFIG_FILE
        dl.CONFIG_FILE = self.root / "config.json"
        self.addCleanup(setattr, dl, "CONFIG_FILE", self._saved_config)
        self._saved_env = os.environ.get(dl.DOWNLOAD_DIR_ENV)
        os.environ.pop(dl.DOWNLOAD_DIR_ENV, None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._saved_env is None:
            os.environ.pop(dl.DOWNLOAD_DIR_ENV, None)
        else:
            os.environ[dl.DOWNLOAD_DIR_ENV] = self._saved_env

    def test_env_beats_config_and_system(self):
        dl.set_default_download_dir(self.root / "from_config")
        env_dir = self.root / "from_env"
        os.environ[dl.DOWNLOAD_DIR_ENV] = str(env_dir)
        self.assertEqual(dl.resolve_download_dir(), env_dir)

    def test_config_beats_system_default(self):
        saved = dl.set_default_download_dir(self.root / "chosen")
        os.environ.pop(dl.DOWNLOAD_DIR_ENV, None)
        self.assertEqual(dl.resolve_download_dir(), saved)

    def test_clear_restores_system_default(self):
        dl.set_default_download_dir(self.root / "chosen")
        dl.clear_default_download_dir()
        self.assertEqual(dl.resolve_download_dir(), dl.system_download_dir())
        self.assertNotIn("download_dir", dl.load_config())

    def test_broken_config_is_ignored_not_fatal(self):
        dl.CONFIG_FILE.write_text("{ 这不是 JSON", encoding="utf-8")
        self.assertEqual(dl.resolve_download_dir(), dl.system_download_dir())

    def test_no_temp_file_left_behind(self):
        dl.set_default_download_dir(self.root / "chosen")
        leftovers = [p.name for p in self.root.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_download_dir_creates_missing_path(self):
        os.environ[dl.DOWNLOAD_DIR_ENV] = str(self.root / "新目录" / "子目录")
        self.assertTrue(dl.download_dir().is_dir())


class UniquePathTest(unittest.TestCase):
    def test_existing_names_get_numbered_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "Files.zip").write_bytes(b"x")
            self.assertEqual(dl.unique_path(d, "Files.zip").name, "Files(1).zip")
            (d / "Files(1).zip").write_bytes(b"x")
            self.assertEqual(dl.unique_path(d, "Files.zip").name, "Files(2).zip")

    def test_new_name_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(dl.unique_path(Path(tmp), "new.zip").name, "new.zip")


class DownloadTest(unittest.TestCase):
    """download() 的字节校验与清理逻辑，用假响应覆盖，不真下东西。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        # 测试终端在真终端里跑时会画出进度条，把结果刷得没法读，这里统一关掉
        saved = dl.ui.is_tty
        dl.ui.is_tty = lambda: False
        self.addCleanup(setattr, dl.ui, "is_tty", saved)

    def patch_stream(self, chunks, headers=None, status=200, exc=None):
        from contextlib import contextmanager

        class FakeResp:
            def __init__(self):
                self.status_code = status
                self.headers = headers if headers is not None else {
                    "Content-Length": str(sum(len(c) for c in chunks))}

            def iter_bytes(self, chunk_size=1):
                if exc is not None:
                    raise exc
                for c in chunks:
                    yield c

            def iter_raw(self, chunk_size=1):
                return self.iter_bytes(chunk_size)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        calls = []

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @contextmanager
            def stream(self, method, url, headers=None, **kw):
                calls.append(url)
                yield FakeResp()

        saved = dl._client
        dl._client = FakeClient
        self.addCleanup(setattr, dl, "_client", saved)
        return calls

    def test_bytes_land_in_one_file(self):
        self.patch_stream([b"aaa", b"bbb"])
        path = dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertEqual(path.read_bytes(), b"aaabbb")
        self.assertEqual(list(self.dir.iterdir()), [path])

    def test_short_stream_is_rejected_and_temp_removed(self):
        self.patch_stream([b"aaa"], headers={"Content-Length": "99"})
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertIn("不完整", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_empty_body_is_rejected(self):
        self.patch_stream([])
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertIn("空", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_html_instead_of_file_bails_out_early(self):
        self.patch_stream([b"<html>login</html>"], headers={"Content-Type": "text/html; charset=utf-8"})
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertIn("网页", str(ctx.exception))

    def test_http_error_status_is_reported(self):
        self.patch_stream([b"x"], status=404)
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_network_break_keeps_progress_for_resume(self):
        self.patch_stream([b"abc"], exc=httpx.ReadError("closed"))
        with self.assertRaises(dl.ResumableDownloadError) as ctx:
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertIn("断点", str(ctx.exception))
        # 异常在 iter_content 一开始就抛，没写出字节；但 .part 和进度文件要留下
        self.assertTrue((self.dir / "a.zip.part").is_file())
        self.assertTrue((self.dir / "a.zip.part.meta").is_file())

    def test_permanent_failure_still_cleans_up(self):
        self.patch_stream([b"x"], headers={"Content-Length": "99"})
        with self.assertRaises(dl.DownloadError):
            dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_existing_file_is_not_overwritten(self):
        (self.dir / "a.zip").write_bytes(b"OLD")
        self.patch_stream([b"new"])
        path = dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertEqual((self.dir / "a.zip").read_bytes(), b"OLD")
        self.assertEqual(path.name, "a(1).zip")

    def test_malicious_asset_name_cannot_escape_the_directory(self):
        self.patch_stream([b"data"])
        path = dl.download("https://x/a.zip", "../../../../evil.txt", self.dir)
        self.assertEqual(path.parent, self.dir)
        self.assertEqual(path.name, "evil.txt")


class FavoritesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "favorites.json"

    def test_missing_file_is_an_empty_store(self):
        self.assertEqual(fav.load(self.path), {"version": 1, "repos": {}})

    def test_round_trip(self):
        store = fav.load(self.path)
        fav.add(store, "files-community/Files", stars=100, description="Files 替代品", language="C#")
        fav.save(store, self.path)
        again = fav.load(self.path)
        self.assertEqual(fav.count(again), 1)
        meta = again["repos"]["files-community/Files"]
        self.assertEqual(meta["stars"], 100)
        self.assertEqual(meta["language"], "C#")
        self.assertTrue(meta["added_at"])

    def test_same_repo_different_case_updates_instead_of_duplicating(self):
        store = fav.load(self.path)
        key1, act1 = fav.add(store, "files-community/Files", stars=1)
        key2, act2 = fav.add(store, "Files-Community/files", stars=2)
        self.assertEqual(key1, key2)
        self.assertEqual((act1, act2), ("新增", "更新"))
        self.assertEqual(fav.count(store), 1)
        self.assertEqual(store["repos"][key2]["stars"], 2)

    def test_readd_keeps_added_at(self):
        store = fav.load(self.path)
        fav.add(store, "a/b")
        added = store["repos"]["a/b"]["added_at"]
        fav.add(store, "a/b", stars=9)
        self.assertEqual(store["repos"]["a/b"]["added_at"], added)

    def test_release_cache_round_trip(self):
        store = fav.load(self.path)
        fav.add(store, "a/b")
        fav.update_release(store, "a/b", "v9.9", [{"name": "a.zip", "size": 1, "url": "u"}])
        fav.save(store, self.path)
        meta = fav.load(self.path)["repos"]["a/b"]
        self.assertEqual(meta["last_tag"], "v9.9")
        self.assertEqual(meta["assets"][0]["name"], "a.zip")

    def test_update_release_on_unknown_key_is_silent(self):
        store = fav.load(self.path)
        fav.update_release(store, "nobody/repo", "v1", [])
        self.assertEqual(fav.count(store), 0)

    def test_corrupt_file_is_backed_up_and_rebuilt(self):
        self.path.write_text("{坏掉的 JSON", encoding="utf-8")
        store = fav.load(self.path)
        self.assertTrue(store["_recovered"])
        self.assertTrue(self.path.with_suffix(".json.bak").is_file(), "原文件要留成 .bak 供找回")

    def test_remove_returns_the_actual_key(self):
        store = fav.load(self.path)
        fav.add(store, "a/b")
        self.assertEqual(fav.remove(store, "A/B"), "a/b")
        self.assertIsNone(fav.remove(store, "a/b"))

    def test_entries_are_newest_first(self):
        store = {"version": 1, "repos": {
            "old/repo": {"added_at": "2026-01-01 00:00:00"},
            "new/repo": {"added_at": "2026-11-01 00:00:00"},
        }}
        self.assertEqual([k for k, _ in fav.entries(store)], ["new/repo", "old/repo"])

    def test_junk_records_are_dropped_on_load(self):
        self.path.write_text(json.dumps({"version": 1, "repos": {"a/b": "不是字典", "c/d": {}}}), encoding="utf-8")
        self.assertEqual(list(fav.load(self.path)["repos"]), ["c/d"])

    def test_failed_save_leaves_no_temp_file(self):
        """原子写失败（目录不存在）时，不能留一个 favorites.json.tmp 在原地。"""
        store = fav.load(self.path)
        fav.add(store, "a/b")
        unreachable = self.path.parent / "并不存在的子目录" / self.path.name
        with self.assertRaises(OSError):
            fav.save(store, unreachable)
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class CliTokenUrlTest(unittest.TestCase):
    """`cli.py --token-url`：远程帮人排障时，不用进菜单也能拿到 Token 页面地址。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, gh, "TOKEN_FILE", gh.TOKEN_FILE)
        gh.TOKEN_FILE = Path(tmp.name) / ".github_token"

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_token_url_prints_both_creation_pages(self):
        code, out = self.run_cli(["--token-url"])
        self.assertEqual(code, 0)
        self.assertIn(gh.TOKEN_CREATE_URL, out)
        self.assertIn(gh.FINE_GRAINED_URL, out)
        self.assertIn("scopes=public_repo", out, "最小权限要直接体现在链接里")

    def test_token_url_needs_no_repository_and_writes_nothing(self):
        code, _ = self.run_cli(["--token-url"])
        self.assertEqual(code, 0, "只要地址，不该因为缺仓库名报错")
        self.assertFalse(gh.TOKEN_FILE.exists(), "打印地址不等于替用户存 Token")

    def test_missing_repo_explains_the_two_ways_to_use_it(self):
        code, out = self.run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("--token-url", out)


class ResumeTest(unittest.TestCase):
    """断点续传：单流从字节偏移接着下，分段只补未完成的段。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        saved = dl.ui.is_tty
        dl.ui.is_tty = lambda: False
        self.addCleanup(setattr, dl.ui, "is_tty", saved)

    def install_get(self, handler):
        from contextlib import asynccontextmanager, contextmanager

        def make_response(url, headers):
            return self.resp(handler(url, headers))

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @contextmanager
            def stream(self, method, url, headers=None, **kw):
                yield make_response(url, headers or {})

        class FakeAsyncClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            @asynccontextmanager
            async def stream(self, method, url, headers=None, **kw):
                yield make_response(url, headers or {})

        for name, fake in (("_client", FakeClient), ("_aclient", FakeAsyncClient)):
            saved = getattr(dl, name)
            setattr(dl, name, fake)
            self.addCleanup(setattr, dl, name, saved)

    def resp(self, raw):
        status, body, headers = raw

        class R:
            def __init__(self):
                self.status_code = status
                self.headers = headers or {}
                self._body = body

            def iter_bytes(self, chunk_size=1):
                yield self._body

            async def aiter_bytes(self, chunk_size=1):
                yield self._body

            def iter_raw(self, chunk_size=1):
                yield self._body

            async def aiter_raw(self, chunk_size=1):
                yield self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False
        return R()

    def test_stream_resumes_from_saved_offset(self):
        (self.dir / "a.zip.part").write_bytes(b"abc")  # 上次下了 3 字节
        (self.dir / "a.zip.part.meta").write_text(json.dumps({
            "v": dl.PROGRESS_VERSION, "url": "https://x/a.zip", "mode": "stream",
            "total": 6, "etag": "v1", "last_modified": "",
        }), encoding="utf-8")
        seen = {}

        def handler(url, headers):
            seen["range"] = headers.get("Range")
            return (206, b"def", {"Content-Range": "bytes 3-5/6", "ETag": "v1"})

        self.install_get(handler)
        path = dl.download("https://x/a.zip", "a.zip", self.dir, etag="v1")
        self.assertEqual(seen["range"], "bytes=3-")
        self.assertEqual(path.read_bytes(), b"abcdef")
        self.assertFalse((self.dir / "a.zip.part.meta").exists(), "成功后清掉进度文件")

    def test_stream_restarts_when_etag_changed(self):
        (self.dir / "a.zip.part").write_bytes(b"OLD")
        (self.dir / "a.zip.part.meta").write_text(json.dumps({
            "v": dl.PROGRESS_VERSION, "url": "https://x/a.zip", "mode": "stream",
            "total": 6, "etag": "v1", "last_modified": "",
        }), encoding="utf-8")
        seen = {}

        def handler(url, headers):
            seen["range"] = headers.get("Range")
            return (200, b"new!!", {"Content-Length": "5"})

        self.install_get(handler)
        path = dl.download("https://x/a.zip", "a.zip", self.dir, etag="v2")
        self.assertIsNone(seen["range"], "文件变了就不能续，必须从头下")
        self.assertEqual(path.read_bytes(), b"new!!")

    def test_stream_restarts_when_server_ignores_range(self):
        (self.dir / "a.zip.part").write_bytes(b"OLD")
        (self.dir / "a.zip.part.meta").write_text(json.dumps({
            "v": dl.PROGRESS_VERSION, "url": "https://x/a.zip", "mode": "stream",
            "total": 6, "etag": "", "last_modified": "",
        }), encoding="utf-8")

        def handler(url, headers):
            return (200, b"fresh", {"Content-Length": "5"})

        self.install_get(handler)
        path = dl.download("https://x/a.zip", "a.zip", self.dir)
        self.assertEqual(path.read_bytes(), b"fresh")

    def test_parallel_only_fetches_pending_segments(self):
        total = 8
        (self.dir / "tool.zip.part").write_bytes(b"\x00" * total)
        (self.dir / "tool.zip.part.meta").write_text(json.dumps({
            "v": dl.PROGRESS_VERSION, "url": "https://x/tool.zip", "mode": "parallel",
            "total": total, "etag": "", "last_modified": "",
            "bounds": [[0, 3], [4, 7]], "done": [True, False],
        }), encoding="utf-8")
        ranges = []

        def handler(url, headers):
            ranges.append(headers.get("Range"))
            return (206, b"WXYZ", {"Content-Range": "bytes 4-7/8"})

        self.install_get(handler)
        path = dl.download_parallel("https://x/tool.zip", self.dir, "tool.zip", total, 2)
        self.assertEqual(ranges, ["bytes=4-7"], "已完成的段不该重下")
        self.assertEqual(path.read_bytes(), b"\x00\x00\x00\x00WXYZ")
        self.assertFalse((self.dir / "tool.zip.part.meta").exists())

    def test_parallel_restarts_when_file_size_changed(self):
        (self.dir / "tool.zip.part").write_bytes(b"\x00" * 3)  # 长度和 meta 对不上
        (self.dir / "tool.zip.part.meta").write_text(json.dumps({
            "v": dl.PROGRESS_VERSION, "url": "https://x/tool.zip", "mode": "parallel",
            "total": 8, "etag": "", "last_modified": "",
            "bounds": [[0, 3], [4, 7]], "done": [True, False],
        }), encoding="utf-8")
        ranges = []

        # 按 Range 起止返回对应长度，保证两段都写对；用 split 兼容 Python 3.8
        def handler(url, headers):
            rng = headers.get("Range", "")
            start, end = (int(x) for x in rng.split("=", 1)[1].split("-"))
            ranges.append(rng)
            return (206, b"A" * (end - start + 1),
                    {"Content-Range": f"bytes {start}-{end}/8"})

        self.install_get(handler)
        path = dl.download_parallel("https://x/tool.zip", self.dir, "tool.zip", 8, 2)
        self.assertEqual(ranges, ["bytes=0-3", "bytes=4-7"], "文件变了就整段重下")
        self.assertEqual(path.read_bytes(), b"A" * 8)


if __name__ == "__main__":
    unittest.main()
