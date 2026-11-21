# -*- coding: utf-8 -*-
"""菜单 5「检查更新」的流程测试：限流保护、确认裁剪、表格输出与回写。

全程不联网、不写真实配置：Release/配额/延时/确认都换成假实现，
收藏落到临时目录。沿用其它测试文件的 addCleanup(setattr, ...) 风格。
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import main as app
import github_api as gh


def make_store(n: int, tag: str = "v1.0") -> dict:
    """造 n 条收藏，added_at 保持一致以便 entries() 保持插入顺序。"""
    repos = {}
    for i in range(1, n + 1):
        repos[f"owner/repo{i}"] = {
            "added_at": "2026-01-01 00:00:00",
            "last_tag": tag,
            "assets": [],
        }
    return {"version": 1, "repos": repos}


class CheckUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fav_path = Path(self.tmp.name) / "favorites.json"

        self.releases = {}          # repo -> release dict 或 要抛出的异常
        self.quota = {"limit": 60, "remaining": 60, "authenticated": False}
        self.checked = []
        self.sleeps = []
        self.quota_calls = 0
        self.confirm_answer = True
        self.confirm_prompts = []

        def patch(obj, name, value):
            original = getattr(obj, name)
            setattr(obj, name, value)
            self.addCleanup(setattr, obj, name, original)

        patch(app.gh, "get_latest_release_or_explain", self._get_release)
        patch(app.gh, "rate_limit_status", self._rate_limit_status)
        patch(app.time, "sleep", self._sleep)
        patch(app.ui, "confirm", self._confirm)

        real_save = app.fav.save
        patch(app.fav, "save", lambda store: real_save(store, self.fav_path))

    def _get_release(self, repo, token):
        self.checked.append(repo)
        result = self.releases.get(repo)
        if isinstance(result, Exception):
            raise result
        if result is None:
            result = {"tag_name": "v2.0", "body": "", "assets": []}
        return result

    def _rate_limit_status(self, token=""):
        self.quota_calls += 1
        return dict(self.quota)

    def _sleep(self, seconds):
        self.sleeps.append(seconds)

    def _confirm(self, prompt, default=True):
        self.confirm_prompts.append(prompt)
        return self.confirm_answer

    def run_flow(self, store, token="tok"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            app.flow_check_updates(store, token)
        return buf.getvalue()

    def test_menu_item_and_dispatch(self):
        self.assertIn(("5", "检查更新", "批量检查收藏仓库的最新 Release"), app.MENU_ITEMS)
        calls = []
        original = app.flow_check_updates

        def stub(store, token):
            calls.append((store, token))

        app.flow_check_updates = stub
        self.addCleanup(setattr, app, "flow_check_updates", original)
        store = make_store(1)
        self.assertEqual(app.dispatch("5", store, "tok"), "pause")
        self.assertEqual(calls, [(store, "tok")])

    def test_no_token_over_40_refuses_before_any_request(self):
        out = self.run_flow(make_store(41), token="")
        self.assertIn("未配置 Token 时最多检查 40 个，按 0 配置 Token 后重试", out)
        self.assertEqual(self.checked, [])
        self.assertEqual(self.quota_calls, 0)

    def test_no_token_with_40_still_asks_and_can_run(self):
        self.confirm_answer = False
        out = self.run_flow(make_store(40), token="")
        self.assertIn("共 40 个仓库，全部检查？", self.confirm_prompts[0])
        self.assertEqual(len(self.checked), 30)

    def test_over_30_declining_checks_only_first_30(self):
        self.confirm_answer = False
        out = self.run_flow(make_store(35))
        self.assertIn("共 35 个仓库，全部检查？", self.confirm_prompts[0])
        self.assertEqual(len(self.checked), 30)
        self.assertIn("已只取前 30 个检查", out)

    def test_over_30_accepting_checks_all(self):
        self.confirm_answer = True
        self.run_flow(make_store(35))
        self.assertEqual(len(self.checked), 35)

    def test_normal_table_status_summary_and_writeback(self):
        store = make_store(2)
        self.releases["owner/repo1"] = {
            "tag_name": "v9.9",
            "body": "x" * 60 + "\n第二行",
            "assets": [
                {"name": "a.zip", "size": 12, "browser_download_url": "https://x/a.zip"},
                "不是字典",
            ],
        }
        self.releases["owner/repo2"] = {"tag_name": "v1.0", "body": "", "assets": []}

        out = self.run_flow(store)

        for header in ("#", "仓库", "上次 tag", "最新 tag", "状态", "更新摘要"):
            self.assertIn(header, out)
        self.assertIn("↑ 新版本", out)
        self.assertIn("— 无变化", out)
        self.assertIn("x" * 50, out)           # 正文去掉换行后只取前 50 字符
        self.assertNotIn("x" * 51, out)
        self.assertIn("已回写 2 条收藏记录", out)

        first = store["repos"]["owner/repo1"]
        self.assertEqual(first["last_tag"], "v9.9")
        self.assertEqual(first["assets"], [
            {"name": "a.zip", "size": 12, "url": "https://x/a.zip"},
        ])
        self.assertTrue(first["updated_at"])

        self.assertEqual(len(self.sleeps), 1)   # 两次请求之间只睡一次
        self.assertEqual(self.sleeps[0], 0.5)
        self.assertEqual(self.quota_calls, 2)   # 每个请求前查一次配额

    def test_429_stops_batch_and_reports_remaining(self):
        store = make_store(5)
        self.releases["owner/repo2"] = gh.RateLimitedError("too many", status_code=429)
        out = self.run_flow(store)

        self.assertIn("已触发限流，剩余 3 个未检查。配置 Token 或稍后再试。", out)
        self.assertEqual(self.checked, ["owner/repo1", "owner/repo2"])
        self.assertEqual(store["repos"]["owner/repo1"]["last_tag"], "v2.0")
        self.assertEqual(store["repos"]["owner/repo3"]["last_tag"], "v1.0")  # 未检查的不动
        self.assertIn("已回写 1 条收藏记录", out)

    def test_403_stops_batch(self):
        store = make_store(4)
        self.releases["owner/repo1"] = gh.GitHubError("鉴权失败", status_code=403)
        out = self.run_flow(store)
        self.assertIn("已触发限流，剩余 3 个未检查", out)
        self.assertEqual(len(self.checked), 1)

    def test_low_quota_stops_before_requests(self):
        self.quota = {"limit": 60, "remaining": 2, "authenticated": False}
        out = self.run_flow(make_store(4))
        self.assertIn("剩余配额不足 3 次", out)
        self.assertIn("已提前停止", out)
        self.assertEqual(self.checked, [])

    def test_missing_headers_do_not_trigger_false_stop(self):
        self.quota = {"limit": 0, "remaining": 0, "authenticated": False}
        self.run_flow(make_store(2))
        self.assertEqual(len(self.checked), 2)

    def test_quota_probe_failure_does_not_block_checks(self):
        def boom(token=""):
            raise gh.GitHubError("配额查询失败")

        app.gh.rate_limit_status = boom
        self.addCleanup(setattr, app.gh, "rate_limit_status", self._rate_limit_status)
        self.run_flow(make_store(2))
        self.assertEqual(len(self.checked), 2)

    def test_single_repo_failure_does_not_stop_batch(self):
        store = make_store(3)
        self.releases["owner/repo1"] = gh.NotFoundError("没有 release", status_code=404)
        out = self.run_flow(store)
        self.assertIn("查询失败", out)
        self.assertEqual(len(self.checked), 3)
        self.assertIn("已回写 2 条收藏记录", out)
        self.assertEqual(store["repos"]["owner/repo2"]["last_tag"], "v2.0")

    def test_empty_favorites_returns_without_requests(self):
        out = self.run_flow({"version": 1, "repos": {}})
        self.assertIn("收藏夹还是空的", out)
        self.assertEqual(self.checked, [])
        self.assertEqual(self.quota_calls, 0)


if __name__ == "__main__":
    unittest.main()
