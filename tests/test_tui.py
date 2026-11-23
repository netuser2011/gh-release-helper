# -*- coding: utf-8 -*-
"""Textual TUI 冒烟测试：验证主菜单渲染、状态行与弹窗交互。

用 Textual 的 run_test 无头驱动，不依赖真实终端；全程 stub 业务模块，不联网。
"""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

import downloader as dl
import github_api as gh
import tui
from textual.widgets import Input, ListView, ProgressBar, Static

FAKE_REPOS = [{"full_name": "octocat/Hello-World", "stargazers_count": 100,
               "description": "test", "language": "Python"}]
FAKE_RELEASE = {"tag_name": "v1.2.0", "body": "## 更新\n- 修复问题",
                "html_url": "https://github.com/octocat/Hello-World", "assets": []}


class TuiSmokeTest(unittest.TestCase):
    def test_menu_renders_with_status(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            async with app.run_test() as pilot:
                await pilot.pause()
                return (
                    app.title,
                    len(app.query_one("#main-list", ListView).children),
                    str(app.query_one("#status").renderable),
                )

        title, count, status = asyncio.run(run())
        self.assertEqual(title, "GH Release Helper")
        self.assertEqual(count, 6)
        self.assertIn("收藏", status)
        self.assertIn("未配置", status)

    def test_input_dialog_submits(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            async with app.run_test() as pilot:
                await pilot.pause()

                async def ask():
                    return await app.ask_input("测试输入：")

                task = asyncio.create_task(ask())
                await pilot.pause()
                app.screen.query_one(Input).value = "hello"
                app.screen.query_one(Input).focus()
                await pilot.press("enter")
                await pilot.pause()
                return await task

        self.assertEqual(asyncio.run(run()), "hello")

    def test_confirm_dialog_yes(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            async with app.run_test() as pilot:
                await pilot.pause()

                async def ask():
                    return await app.confirm("确认？")

                task = asyncio.create_task(ask())
                await pilot.pause()
                await pilot.press("y")
                await pilot.pause()
                return await task

        self.assertTrue(asyncio.run(run()))


class TuiFlowTest(unittest.TestCase):
    """走一遍主菜单→搜索→仓库页→返回→Token 弹窗的完整交互，stub 网络。"""

    def test_search_to_repo_and_back(self):
        async def run():
            with patch.object(gh, "search_repos", return_value=(FAKE_REPOS, 1)), \
                 patch.object(gh, "get_latest_release_or_explain", return_value=FAKE_RELEASE):
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.query_one("#main-list", ListView).focus()
                    await pilot.press("enter")          # → 搜索页
                    await pilot.pause()
                    search = type(app.screen_stack[-1]).__name__
                    app.screen.query_one("#kw", Input).value = "hello"
                    await pilot.press("enter")          # 触发搜索
                    await pilot.pause()
                    await pilot.pause()
                    count = len(app.screen.query_one("#results", ListView).children)
                    await pilot.press("enter")          # → 仓库页（已自动聚焦列表）
                    await pilot.pause()
                    await pilot.pause()
                    repo = type(app.screen_stack[-1]).__name__
                    await pilot.press("escape")         # → 回搜索页
                    await pilot.pause()
                    back = type(app.screen_stack[-1]).__name__
                    return search, count, repo, back

        search, count, repo, back = asyncio.run(run())
        self.assertEqual(search, "SearchScreen")
        self.assertEqual(count, 1)
        self.assertEqual(repo, "RepoScreen")
        self.assertEqual(back, "SearchScreen")


class TypeFilterTest(unittest.TestCase):
    """资产按类型分组筛选，下载方式用按钮，不再逐个列链接、不输 123。"""

    ASSETS = [
        {"name": "app.zip", "size": 100, "browser_download_url": "https://x/a.zip"},
        {"name": "app2.zip", "size": 200, "browser_download_url": "https://x/b.zip"},
        {"name": "app.exe", "size": 300, "browser_download_url": "https://x/a.exe"},
        {"name": "app.apk", "size": 400, "browser_download_url": "https://x/a.apk"},
    ]

    def test_type_groups(self):
        groups = tui.type_groups(self.ASSETS)
        self.assertEqual([g[0] for g in groups], ["zip", "exe", "apk"])
        self.assertEqual(len(groups[0][1]), 2)  # ZIP 下 2 个

    def test_type_then_mode_buttons(self):
        release = dict(FAKE_RELEASE, assets=self.ASSETS)

        async def run():
            with patch.object(gh, "get_latest_release_or_explain", return_value=release), \
                 patch.object(tui.dl, "open_in_browser") as browser:
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.RepoScreen(app, {"full_name": "o/r"}))
                    await pilot.pause()
                    await pilot.pause()
                    # 仓库页列出类型而非逐个资产
                    actions = app.screen.query_one("#actions", ListView)
                    labels = [str(i.label_text) for i in actions.children]
                    # 前两项是说明/网页，之后是类型
                    self.assertIn("ZIP", labels[2])
                    self.assertIn("EXE", labels[3])
                    # 选 ZIP（index 2）→ 资产页
                    actions.index = 2
                    actions.focus()
                    await pilot.pause()
                    await pilot.press("enter")
                    await pilot.pause()
                    asset_page = type(app.screen_stack[-1]).__name__
                    asset_count = len(app.screen.query_one("#assets", ListView).children)
                    # 选第一个资产 → 下载方式按钮弹窗
                    av = app.screen.query_one("#assets", ListView)
                    av.index = 0
                    av.focus()
                    await pilot.pause()
                    await pilot.press("enter")
                    for _ in range(5):
                        await pilot.pause()
                    mode_page = type(app.screen_stack[-1]).__name__
                    # 点"浏览器"按钮
                    app.screen.query_one("#browser", tui.Button).press()
                    await pilot.pause()
                    return asset_page, asset_count, mode_page, browser.called

        asset_page, count, mode_page, browser_called = asyncio.run(run())
        self.assertEqual(asset_page, "AssetScreen")
        self.assertEqual(count, 2)
        self.assertEqual(mode_page, "ModeDialog")
        self.assertTrue(browser_called)


class DownloadScreenTest(unittest.TestCase):
    """终端下载页展示测速结果与实时进度；进度走 progress_hook，不被 TUI 吞掉。"""

    LINE = {"id": "github", "label": "GitHub 官方", "url": "https://x/a.zip",
            "ok": True, "speed": 5_000_000}
    RESULTS = [
        LINE,
        {"id": "proxy", "label": "代理", "url": "https://y/a.zip", "ok": True, "speed": 2_000_000},
        {"id": "bad", "label": "镜像", "url": "https://z/a.zip", "ok": False, "error": "timeout"},
    ]

    def test_speedtest_and_progress(self):
        self.addCleanup(setattr, dl, "progress_hook", None)

        def fake_fetch(url, name, target, workers=None):
            for done, total in ((25, 100), (60, 100), (100, 100)):
                if dl.progress_hook:
                    dl.progress_hook(done, total, done * 1000)
            return __import__("pathlib").Path("/tmp/a.zip"), "4 并发分段"

        async def run():
            with patch.object(dl, "choose_line", return_value=(self.LINE, self.RESULTS)), \
                 patch.object(dl, "fetch", side_effect=fake_fetch), \
                 patch.object(tui.pd, "kind_of", return_value="other"):
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.DownloadScreen(app, "https://x/a.zip", "app.zip"))
                    for _ in range(10):
                        await pilot.pause()
                    screen = app.screen_stack[-1]
                    return (
                        type(screen).__name__,
                        len(str(screen.query_one("#lines", Static).renderable).splitlines()),
                        screen.query_one("#bar", ProgressBar).progress,
                        "B/s" in str(screen.query_one("#result", Static).renderable),
                        dl.progress_hook,
                    )

        page, line_count, progress, has_speed, hook = asyncio.run(run())
        self.assertEqual(page, "DownloadScreen")
        self.assertEqual(line_count, 3)      # 三条线路评分都展示了
        self.assertEqual(progress, 100)      # 进度条走到满
        self.assertTrue(has_speed)           # 速度文本显示
        self.assertIsNone(hook)              # hook 用完还原，不污染 CLI


class BaseScreenTest(unittest.TestCase):
    """所有功能页都有可点击返回按钮，ESC 绑定仍保留。"""

    def test_screens_inherit_base(self):
        for cls in (tui.SearchScreen, tui.RepoScreen, tui.AssetScreen, tui.DownloadScreen,
                    tui.LinkScreen, tui.FavoritesScreen, tui.AddFavoriteScreen,
                    tui.CheckUpdatesScreen, tui.NotesScreen):
            self.assertTrue(issubclass(cls, tui.BaseScreen), cls.__name__)

    def test_back_button_pops_screen(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(tui.SearchScreen(app))
                await pilot.pause()
                before = len(app.screen_stack)
                app.screen.query_one("#back", tui.Button).press()
                await pilot.pause()
                return before, len(app.screen_stack)

        before, after = asyncio.run(run())
        self.assertEqual(before, 2)
        self.assertEqual(after, 1)


class LinkScreenTest(unittest.TestCase):
    """「只打印下载链接」必须真的显示链接，且复制有反馈。"""

    def test_link_visible_and_copy_feedback(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            with patch.object(tui.GHReleaseApp, "copy_to_clipboard") as clipboard:
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.LinkScreen(app, "https://x/app.zip", "app.zip"))
                    await pilot.pause()
                    screen = app.screen_stack[-1]
                    page = type(screen).__name__
                    shown = screen.query_one("#link-url", Input).value
                    screen.query_one("#copy", tui.Button).press()
                    await pilot.pause()
                    feedback = str(screen.query_one("#feedback", Static).renderable)
                    copied = clipboard.call_args.args[0] if clipboard.called else None
                    return page, shown, feedback, copied

        page, shown, feedback, copied = asyncio.run(run())
        self.assertEqual(page, "LinkScreen")
        self.assertEqual(shown, "https://x/app.zip")
        self.assertIn("已复制", feedback)
        self.assertEqual(copied, "https://x/app.zip")

    def test_mode_link_button_opens_link_screen(self):
        async def run():
            app = tui.GHReleaseApp("", "无")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                asyncio.create_task(app.run_download("o/r", {
                    "name": "app.zip", "browser_download_url": "https://x/app.zip",
                }))
                await pilot.pause()
                mode = type(app.screen_stack[-1]).__name__
                app.screen.query_one("#link", tui.Button).press()
                for _ in range(5):
                    await pilot.pause()
                screen = app.screen_stack[-1]
                return mode, type(screen).__name__, screen.query_one("#link-url", Input).value

        mode, page, url = asyncio.run(run())
        self.assertEqual(mode, "ModeDialog")
        self.assertEqual(page, "LinkScreen")
        self.assertEqual(url, "https://x/app.zip")


class PostDownloadTest(unittest.TestCase):
    """下载完成后：安装包询问并启动；zip 解压并询问删包。"""

    LINE = {"id": "github", "label": "官方", "url": "https://x/a", "ok": True, "speed": 5_000_000}
    RESULTS = [LINE]

    def setUp(self):
        self.addCleanup(setattr, dl, "progress_hook", None)

    def test_installer_launches_after_confirm(self):
        async def run():
            with patch.object(dl, "choose_line", return_value=(self.LINE, self.RESULTS)), \
                 patch.object(dl, "fetch", return_value=(Path("C:/dl/app.exe"), "直连")), \
                 patch.object(tui.pd, "launch") as launch:
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.DownloadScreen(app, "https://x/app.exe", "app.exe"))
                    for _ in range(12):
                        await pilot.pause()
                    dialog = type(app.screen_stack[-1]).__name__
                    await pilot.press("y")
                    await pilot.pause()
                    return dialog, launch.call_args.args[0].name if launch.called else None

        dialog, launched = asyncio.run(run())
        self.assertEqual(dialog, "ConfirmDialog")
        self.assertEqual(launched, "app.exe")

    def test_archive_extracts_and_deletes(self):
        async def run():
            with patch.object(dl, "choose_line", return_value=(self.LINE, self.RESULTS)), \
                 patch.object(dl, "fetch", return_value=(Path("C:/dl/app.zip"), "直连")), \
                 patch.object(tui.pd, "extract", return_value=Path("C:/dl/app")) as extract, \
                 patch.object(tui.pd, "delete") as delete:
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.DownloadScreen(app, "https://x/app.zip", "app.zip"))
                    for _ in range(12):
                        await pilot.pause()
                    dialog = type(app.screen_stack[-1]).__name__
                    await pilot.press("y")
                    await pilot.pause()
                    return dialog, extract.call_count, delete.call_count

        dialog, extracts, deletes = asyncio.run(run())
        self.assertEqual(dialog, "ConfirmDialog")
        self.assertEqual(extracts, 1)
        self.assertEqual(deletes, 1)


class FavoritesDeleteTest(unittest.TestCase):
    """收藏可删除：二次确认后列表与计数同步更新。"""

    def test_delete_with_confirm(self):
        store = {"version": 1, "repos": {
            "o/r": {"last_tag": "v1", "added_at": "2026-01-01 00:00:00"},
        }}

        async def run():
            with patch.object(tui.fav, "load", return_value=store), \
                 patch.object(tui.fav, "save") as save:
                app = tui.GHReleaseApp("", "无")
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.FavoritesScreen(app))
                    await pilot.pause()
                    screen = app.screen_stack[-1]
                    before = len(screen.entries)
                    screen.query_one("#del-fav", tui.Button).press()
                    await pilot.pause()
                    dialog = type(app.screen_stack[-1]).__name__
                    await pilot.press("y")
                    await pilot.pause()
                    await pilot.pause()
                    return before, dialog, len(screen.entries), save.called

        before, dialog, after, saved = asyncio.run(run())
        self.assertEqual(before, 1)
        self.assertEqual(dialog, "ConfirmDialog")
        self.assertEqual(after, 0)
        self.assertTrue(saved)


class CheckUpdatesParityTest(unittest.TestCase):
    """TUI 的检查更新必须和 CLI 走同一套裁剪：该拒的直接拒、该问的弹窗问。"""

    def store(self, n):
        return {"version": 1, "repos": {
            f"o/r{i}": {"added_at": "2026-01-01 00:00:00", "last_tag": "v1.0", "assets": []}
            for i in range(1, n + 1)}}

    def run_screen(self, n, key):
        """返回 (送进循环的目标数, 页面文本)；key 是弹窗上的按键，None 表示不该有弹窗。"""
        seen = {"count": None, "text": ""}

        def fake_iter(targets, token):
            seen["count"] = len(targets)
            return iter(())

        async def go():
            app = tui.GHReleaseApp("", "无")
            app.store = self.store(n)
            with patch.object(tui.fc, "iter_favorite_repos", fake_iter), \
                 patch.object(tui.fav, "save", lambda store: None), \
                 patch.object(tui.su, "check_self_update", return_value=(False, {})):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    app.push_screen(tui.CheckUpdatesScreen(app))
                    for _ in range(4):
                        await pilot.pause()
                    top = type(app.screen_stack[-1]).__name__
                    assert (top == "ConfirmDialog") == (key is not None), top
                    if key:
                        await pilot.press(key)
                        for _ in range(6):
                            await pilot.pause()
                    screen = next(s for s in app.screen_stack if isinstance(s, tui.CheckUpdatesScreen))
                    seen["text"] = str(screen.query_one("#lines", Static).renderable)

        asyncio.run(go())
        return seen["count"], seen["text"]

    def test_over_30_declined_checks_only_first_30(self):
        count, _text = self.run_screen(35, "n")
        self.assertEqual(count, 30)

    def test_over_30_accepted_checks_all(self):
        count, _text = self.run_screen(35, "y")
        self.assertEqual(count, 35)

    def test_over_40_without_token_sends_no_request(self):
        count, text = self.run_screen(41, None)
        self.assertEqual(count, None, "拒绝路径不该进限流循环")
        self.assertIn("未配置 Token 时最多检查 40 个", text)
        self.assertIn("按 5 配置 Token", text)

    def test_small_batch_asks_nothing(self):
        count, _text = self.run_screen(3, None)
        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
