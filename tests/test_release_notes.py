# -*- coding: utf-8 -*-
"""搜索结果的更新说明入口：表格标记、dN 查看、缓存复用与返回行为。"""

import io
import unittest
from contextlib import redirect_stdout

import main as app
import github_api as gh
import ui


SEARCH_ITEMS = [
    {"full_name": "owner/alpha", "stargazers_count": 1000, "language": "Python", "description": "很长的简介"},
    {"full_name": "owner/beta", "stargazers_count": 500, "language": "Go", "description": "另一段简介"},
]
RELEASE = {
    "tag_name": "v2.0",
    "body": "## 更新\n新增功能 A\n修复问题 B",
    "assets": [{"name": "a.zip", "size": 10, "browser_download_url": "https://x/a.zip"}],
}


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self):
        self.answers = []
        self.release_calls = []
        self.shown = []

        def patch(obj, name, value):
            original = getattr(obj, name)
            setattr(obj, name, value)
            self.addCleanup(setattr, obj, name, original)

        patch(app.gh, "search_repos", lambda keyword, token="", limit=10: (SEARCH_ITEMS, 1234))
        patch(app.gh, "get_latest_release_or_explain", self._get_release)
        patch(app.pager, "show", lambda text, title="": self.shown.append((text, title)))
        patch(ui, "ask", self._ask)
        self.addCleanup(app._release_cache.clear)
        app._release_cache.clear()

    def _get_release(self, repo, token):
        self.release_calls.append(repo)
        return dict(RELEASE)

    def _ask(self, prompt=""):
        if not self.answers:
            raise ui.UserQuit
        return self.answers.pop(0)

    def run_pick(self, answers):
        self.answers = list(answers)
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = app.search_and_pick("files", "tok")
        return result, buf.getvalue()

    def test_table_shows_update_entry_not_description(self):
        _, out = self.run_pick(["0"])
        self.assertIn("更新说明", out)
        self.assertIn("[d1 更新说明]", out)
        self.assertIn("[d2 更新说明]", out)
        self.assertNotIn("很长的简介", out)

    def test_prompt_mentions_return_only_once(self):
        saved_ui_c = ui.c
        prompts = []

        def spy_c(text, *codes):
            if "d+编号" in text:
                prompts.append(text)
            return saved_ui_c(text, *codes)

        ui.c = spy_c
        self.addCleanup(setattr, ui, "c", saved_ui_c)
        self.run_pick(["0"])
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].count("0 返回"), 1)

    def test_d_number_opens_pager_then_returns_to_table(self):
        self.run_pick(["d2", "0"])
        self.assertEqual(len(self.shown), 1)
        self.assertEqual(self.shown[0][0], RELEASE["body"])
        self.assertIn("owner/beta", self.shown[0][1])
        self.assertIn("v2.0", self.shown[0][1])

    def test_invalid_d_number_does_not_open_pager(self):
        _, out = self.run_pick(["d9", "0"])
        self.assertEqual(self.shown, [])
        self.assertIn("范围 d1-d2", out)

    def test_plain_number_selects_repo(self):
        chosen, out = self.run_pick(["1"])
        self.assertEqual(chosen["full_name"], "owner/alpha")
        self.assertIn("已选择", out)

    def test_zero_returns_none(self):
        chosen, _ = self.run_pick(["0"])
        self.assertIsNone(chosen)

    def test_release_is_cached_between_view_and_download(self):
        app.get_release("owner/alpha", "tok")
        app.get_release("owner/alpha", "tok")
        self.assertEqual(self.release_calls, ["owner/alpha"])

    def test_browse_release_reuses_cached_release(self):
        app.get_release("owner/alpha", "tok")
        saved = app.do_download
        app.do_download = lambda repo, asset: None
        self.addCleanup(setattr, app, "do_download", saved)
        with redirect_stdout(io.StringIO()):
            app.browse_release("owner/alpha", "tok", repo_meta={})
        self.assertEqual(self.release_calls, ["owner/alpha"])

    def test_query_failure_keeps_search_alive(self):
        def boom(repo, token):
            self.release_calls.append(repo)
            raise gh.GitHubError("模拟：限流", status_code=403)

        saved = app.gh.get_latest_release_or_explain
        app.gh.get_latest_release_or_explain = boom
        self.addCleanup(setattr, app.gh, "get_latest_release_or_explain", saved)
        chosen, out = self.run_pick(["d1", "1"])
        self.assertIn("获取更新说明失败", out)
        self.assertEqual(chosen["full_name"], "owner/alpha")

    def test_empty_body_shows_placeholder_in_pager(self):
        saved = app.gh.get_latest_release_or_explain
        app.gh.get_latest_release_or_explain = lambda repo, token: {"tag_name": "v1", "body": ""}
        self.addCleanup(setattr, app.gh, "get_latest_release_or_explain", saved)
        self.run_pick(["d1", "0"])
        self.assertEqual(self.shown[0][0], "")


if __name__ == "__main__":
    unittest.main()
