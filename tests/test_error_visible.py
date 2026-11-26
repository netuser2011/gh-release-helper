# -*- coding: utf-8 -*-
"""「报错不能一闪而过」的回归测试。

踩过的两个坑：
1. 主循环里流程抛异常后直接重画菜单，而 render_menu 第一件事就是清屏，
   错误信息在出现的那一瞬间被抹掉。
2. Python 版本过低 / requests 没装时走 sys.exit(消息)，双击运行的窗口和消息
   一起消失，用户只看到「闪退」。

下面的用例把「清屏」换成一条哨兵行，据此断言错误信息一定出现在清屏之后。
"""

import builtins
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import bootstrap
import favorites as fav
import main as app
import ui

ENTER_TO_CONTINUE = "回车返回主菜单"


class RenderNoticeTest(unittest.TestCase):
    def render(self, notice):
        """跑一次真实的主菜单渲染，返回 (输出内容, 清屏次数)。"""
        clears = []
        saved_clear = ui.clear
        ui.clear = lambda *a, **k: clears.append(1)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.render_menu({"version": 1, "repos": {}}, "", notice)
        finally:
            ui.clear = saved_clear
        return buf.getvalue(), len(clears)

    def test_notice_is_reprinted_after_the_screen_is_wiped(self):
        out, clears = self.render(ui.c("  ✖ 模拟：API 请求失败", ui.RED))
        self.assertEqual(clears, 1, "render_menu 依然会清屏")
        self.assertLess(out.index("✖ 模拟"), out.index("GitHub Release"),
                        "报错必须排在菜单标题之前：清屏后重新贴回去，才看得见")

    def test_empty_notice_leaves_the_menu_clean(self):
        out, _ = self.render("")
        self.assertNotIn("⚠", out)
        self.assertIn("搜索仓库", out)


class MenuLoopTest(unittest.TestCase):
    """跑真实主循环，只替换流程函数、键盘输入和收藏读写。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)

        for target, name in ((app, "flow_search"), (app, "flow_favorites"), (app, "flow_add_favorite"),
                             (ui, "ask"), (ui, "clear"), (ui, "is_tty"), (app, "fav")):
            self.addCleanup(setattr, target, name, getattr(target, name))

        # 收藏读写全部指向临时目录，测试绝不碰项目里的 favorites.json
        fav_path = root / "favorites.json"
        app.fav = types.SimpleNamespace(
            load=lambda: fav.load(fav_path),
            save=lambda store: None,
            count=fav.count,
            entries=fav.entries,
            add=fav.add,
            remove=fav.remove,
            find_key=fav.find_key,
            update_release=fav.update_release,
            FAVORITES_FILE=fav_path,
        )

        self.addCleanup(setattr, app.gh, "TOKEN_FILE", app.gh.TOKEN_FILE)
        app.gh.TOKEN_FILE = root / ".github_token"          # 不存在 → 走「无 Token」分支
        self.addCleanup(restore_token_env, hold_token_env())

        ui.is_tty = lambda: False                            # 不真清屏、不弹 Token 引导
        ui.clear = lambda *a, **k: print("<<<CLEAR>>>")

        self.addCleanup(setattr, sys, "argv", sys.argv)
        sys.argv = ["main.py"]                               # 让 argparse 只看这里

    def drive(self, inputs):
        """按脚本喂输入，返回 (退出码, 每一屏的内容, 没用完的输入)；同时记下问过的提示语。"""
        pending = list(inputs)
        self.prompts = []

        def fake_ask(prompt=""):
            self.prompts.append(prompt)
            if not pending:
                raise ui.UserQuit
            return pending.pop(0)

        ui.ask = fake_ask
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = app.main()
        return code, buf.getvalue().split("<<<CLEAR>>>"), pending

    def fail_with(self, message):
        def flow(*a, **k):
            raise app.gh.GitHubError(message)

        return flow

    def test_api_error_survives_the_menu_redraw(self):
        app.flow_search = self.fail_with("模拟：仓库不存在或无权访问")
        code, screens, leftover = self.drive(["1", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(leftover, [], "报错之后不该再额外吃掉一次回车")
        last = screens[-1]
        self.assertIn("模拟：仓库不存在", last)
        self.assertIn("搜索仓库", last, "报错和菜单要同时可见")

    def test_old_error_is_replaced_not_stacked(self):
        app.flow_search = self.fail_with("模拟：限流")
        app.flow_add_favorite = self.fail_with("模拟：网络中断")
        code, screens, leftover = self.drive(["1", "3", "0"])
        self.assertEqual(code, 0)
        last = screens[-1]
        self.assertIn("模拟：网络中断", last)
        self.assertNotIn("模拟：限流", last, "上上条报错不该在新操作之后还挂着")

    def test_notice_disappears_once_a_flow_succeeds(self):
        app.flow_search = self.fail_with("模拟：限流")

        def ok(*a, **k):
            print("  流程正常结束")

        app.flow_favorites = ok
        # 成功的流程会走「回车返回主菜单」，所以这里要多喂一次回车
        code, screens, leftover = self.drive(["1", "2", "", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(leftover, [])
        self.assertIn("模拟：限流", screens[1 + 1])
        self.assertNotIn("模拟：限流", screens[-1])

    def test_invalid_option_is_reported_without_an_extra_enter(self):
        code, screens, leftover = self.drive(["7", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(leftover, [], "无效选项只重画菜单，不该多等一次按键")
        self.assertIn("无效选项", screens[-1])

    def test_bare_enter_just_refreshes_the_menu(self):
        code, screens, _ = self.drive(["", "0"])
        self.assertEqual(code, 0)
        self.assertNotIn("无效选项", screens[-1])

    def test_ctrl_c_inside_a_flow_returns_to_the_menu(self):
        def cancel(*a, **k):
            raise ui.UserQuit

        app.flow_search = cancel
        code, screens, leftover = self.drive(["1", "0"])
        self.assertEqual(code, 0)
        self.assertIn("已取消", screens[-1])

    def test_flow_errors_do_not_trigger_the_enter_prompt(self):
        app.flow_search = self.fail_with("模拟：限流")
        code, screens, _ = self.drive(["1", "0"])
        self.assertEqual(code, 0)
        self.assertIn("模拟：限流", screens[-1])
        self.assertNotIn(ENTER_TO_CONTINUE, "".join(self.prompts),
                         "报错靠 notice 留住，不该再多按一次回车；也没让错误被下一次清屏抹掉")

    def test_menu_tells_you_the_token_shortcut(self):
        """没配 Token 时，菜单状态行要直接指向 5，而不是让人去翻文档。"""
        self.addCleanup(setattr, app, "configure_token", app.configure_token)
        app.configure_token = lambda: ""
        code, screens, _ = self.drive(["5", "", "0"])
        self.assertEqual(code, 0)
        self.assertIn("按 5 配一个", screens[1])
        self.assertIn("配置 Token", screens[1])


class TokenShortcutLoopTest(unittest.TestCase):
    """菜单 5：配好 Token 后本次运行立刻生效，提示还得活过下一次清屏。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for target, name in ((app, "configure_token"), (ui, "ask"), (ui, "clear"),
                             (ui, "is_tty"), (app, "token_source"), (app, "fav")):
            self.addCleanup(setattr, target, name, getattr(target, name))
        fav_path = root / "favorites.json"
        app.fav = types.SimpleNamespace(
            load=lambda: fav.load(fav_path),
            save=lambda store: None,
            count=fav.count,
            entries=fav.entries,
            add=fav.add,
            remove=fav.remove,
            find_key=fav.find_key,
            update_release=fav.update_release,
            FAVORITES_FILE=fav_path,
        )
        self.addCleanup(setattr, app.gh, "TOKEN_FILE", app.gh.TOKEN_FILE)
        app.gh.TOKEN_FILE = root / ".github_token"           # 不存在 → 一律按「无 Token」起屏
        self.addCleanup(restore_token_env, hold_token_env())
        self.addCleanup(setattr, sys, "argv", sys.argv)
        sys.argv = ["main.py"]
        ui.clear = lambda *a, **k: print("<<<CLEAR>>>")
        ui.is_tty = lambda: False

    def drive(self, calls, inputs):
        recorded = []

        def configure():
            recorded.append(1)
            return calls

        app.configure_token = configure
        pending = list(inputs)
        ui.ask = lambda prompt="": pending.pop(0) if pending else ""
        buf = io.StringIO()
        with redirect_stdout(buf):
            app.main()
        return buf.getvalue().split("<<<CLEAR>>>"), recorded

    def test_new_token_applies_to_this_run_and_survives_redraw(self):
        screens, recorded = self.drive("ghp_whatever", ["5", "", "0"])
        self.assertEqual(recorded, [1])
        self.assertIn("Token 已生效", screens[-1])
        self.assertIn("已配置", screens[-1], "状态行要从「未配置」翻成「已配置」")
        self.assertNotIn("按 5 配一个", screens[-1])

    def test_cancelling_keeps_anonymous_state(self):
        screens, _ = self.drive("", ["5", "", "0"])
        self.assertNotIn("Token 已生效", screens[-1])
        self.assertIn("按 5 配一个", screens[-1])


class ConfigureTokenFlowTest(unittest.TestCase):
    """configure_token 本体：打印官方页面、可选唤起浏览器、只写本地文件。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, app.gh, "TOKEN_FILE", app.gh.TOKEN_FILE)
        self.addCleanup(setattr, app.dl, "open_in_browser", app.dl.open_in_browser)
        self.addCleanup(setattr, builtins, "input", builtins.input)
        app.gh.TOKEN_FILE = Path(self.tmp.name) / ".github_token"
        self.opened = []
        app.dl.open_in_browser = lambda url: self.opened.append(url) or True

    def run_flow(self, answers):
        pending = list(answers)
        builtins.input = lambda prompt="": pending.pop(0) if pending else ""
        buf = io.StringIO()
        with redirect_stdout(buf):
            token = app.configure_token()
        return token, buf.getvalue()

    def test_prints_the_real_token_page_and_opens_it(self):
        token, out = self.run_flow(["y", ""])
        self.assertIn(app.gh.TOKEN_CREATE_URL, out)
        self.assertIn("scopes=public_repo", out)
        self.assertIn("personal-access-tokens", out, "细粒度 Token 的入口也要给出来")
        self.assertEqual(token, "")
        self.assertEqual(self.opened, [app.gh.TOKEN_CREATE_URL])
        self.assertFalse(app.gh.TOKEN_FILE.exists(), "没粘贴就不该写文件")

    def test_pasted_token_lands_in_the_local_file_only(self):
        token, out = self.run_flow(["y", "  ghp_pasted_by_user  "])
        self.assertEqual(token, "ghp_pasted_by_user")
        self.assertEqual(app.gh.TOKEN_FILE.read_text(encoding="utf-8").strip(), "ghp_pasted_by_user")
        self.assertNotIn("ghp_pasted_by_user", out, "保存成功的话只提路径，别把 Token 再打印一遍")
        self.assertIn(".gitignore", out)

    def test_declining_the_browser_still_leaves_the_paste_step(self):
        """已经有 Token 的人不需要打开网页，直接粘贴就行。"""
        token, out = self.run_flow(["n", "ghp_direct"])
        self.assertEqual(self.opened, [])
        self.assertEqual(token, "ghp_direct")
        self.assertIn(app.gh.TOKEN_CREATE_URL, out, "不打开浏览器也得看到地址，方便手动复制")


class RepoLinkTest(unittest.TestCase):
    """没资产时给网页跳转，选完仓库也能先去网页看看。"""

    def setUp(self):
        self.opened = []
        saved = app.dl.open_in_browser
        app.dl.open_in_browser = lambda url: self.opened.append(url) or True
        self.addCleanup(setattr, app.dl, "open_in_browser", saved)

    def test_targets_include_release_page_repo_home_and_website(self):
        links = app.browser_targets(
            "files-community/Files",
            release={"html_url": "https://github.com/files-community/Files/releases/tag/v3"},
            chosen={"homepage": "files.com"},
        )
        self.assertEqual(links, [
            ("Release 发布页", "https://github.com/files-community/Files/releases/tag/v3"),
            ("GitHub 仓库主页", "https://github.com/files-community/Files"),
            ("项目官网", "https://files.com"),
        ])

    def test_no_assets_offers_browser_instead_of_dead_end(self):
        saved_release, saved_choose = app.gh.get_latest_release_or_explain, ui.choose
        app.gh.get_latest_release_or_explain = lambda repo, token: {
            "tag_name": "v1", "html_url": "https://github.com/a/b/releases/tag/v1", "assets": []
        }
        ui.choose = lambda prompt, count, allow_zero=False: 1
        self.addCleanup(setattr, app.gh, "get_latest_release_or_explain", saved_release)
        self.addCleanup(setattr, ui, "choose", saved_choose)

        buf = io.StringIO()
        with redirect_stdout(buf):
            app.browse_release("a/b", "")
        out = buf.getvalue()
        self.assertIn("没有上传任何资产", out)
        self.assertIn("Release 发布页", out)
        self.assertEqual(self.opened, ["https://github.com/a/b/releases/tag/v1"])

    def test_gateway_choice_to_browser_skips_download(self):
        saved_choose, saved_browse = ui.choose, app.browse_release
        ui.choose = lambda prompt, count, allow_zero=False: 2
        calls = []
        app.browse_release = lambda *a, **kw: calls.append(1)
        self.addCleanup(setattr, ui, "choose", saved_choose)
        self.addCleanup(setattr, app, "browse_release", saved_browse)

        buf = io.StringIO()
        with redirect_stdout(buf):
            proceed = app.offer_repo_gateway("a/b", {"homepage": "https://a.example"})
        self.assertFalse(proceed)
        self.assertEqual(calls, [], "选了去网页就不该再进下载流程")
        self.assertEqual(self.opened, ["https://github.com/a/b"])

    def test_gateway_default_choice_proceeds_to_download(self):
        saved_choose = ui.choose
        ui.choose = lambda prompt, count, allow_zero=False: 1
        self.addCleanup(setattr, ui, "choose", saved_choose)
        with redirect_stdout(io.StringIO()):
            proceed = app.offer_repo_gateway("a/b", {})
        self.assertTrue(proceed)
        self.assertEqual(self.opened, [])

    def test_back_hint_is_not_duplicated_in_choose_prompt(self):
        """ui.choose 自己会追加「（0 返回）：」，调用方不能再写一遍。"""
        saved_choose = ui.choose
        prompts = []

        def spy(prompt, count, allow_zero=False):
            prompts.append(prompt)
            return 0

        ui.choose = spy
        self.addCleanup(setattr, ui, "choose", saved_choose)
        with redirect_stdout(io.StringIO()):
            app.offer_repo_gateway("a/b", {})
            app.offer_browser([("Release 发布页", "https://github.com/a/b/releases/tag/v1")])
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertNotIn("0 返回", prompt, "调用方传入的 prompt 不该自带返回提示")


def hold_token_env():
    previous = os.environ.pop("GITHUB_TOKEN", None)
    return previous


def restore_token_env(previous):
    if previous is not None:
        os.environ["GITHUB_TOKEN"] = previous


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "crash.log"
        self.addCleanup(setattr, bootstrap, "_crash_log_path", bootstrap._crash_log_path)
        bootstrap._crash_log_path = lambda: str(self.log)
        self.addCleanup(setattr, sys, "stdin", sys.stdin)

    def test_fatal_exit_prints_explains_and_exits_nonzero(self):
        sys.stdin = io.StringIO("")  # 非交互：不能卡在等按键上
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                bootstrap.fatal_exit("缺少第三方依赖 requests，请先执行：pip install -r requirements.txt")
        self.assertEqual(ctx.exception.code, 1)
        text = err.getvalue()
        self.assertIn("缺少第三方依赖 requests", text)
        self.assertIn("crash.log", text, "要告诉用户去哪里翻这条记录")
        self.assertIn("缺少第三方依赖 requests", self.log.read_text(encoding="utf-8"))

    def test_fatal_exit_includes_the_underlying_error(self):
        sys.stdin = io.StringIO("")
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit):
                bootstrap.fatal_exit("依赖检查失败", ImportError("No module named 'requests'"))
        self.assertIn("ImportError", err.getvalue())

    def test_ensure_runtime_passes_on_this_interpreter(self):
        self.assertTrue(hasattr(bootstrap.ensure_runtime(), "get"))

    def test_ensure_runtime_names_the_missing_module(self):
        """缺依赖提示要写清到底缺哪个，不能把 %s 直接甩给用户。"""
        self.addCleanup(setattr, bootstrap, "REQUIRED_MODULES", bootstrap.REQUIRED_MODULES)
        bootstrap.REQUIRED_MODULES = bootstrap.REQUIRED_MODULES + ("no_such_mod_xyz",)
        sys.stdin = io.StringIO("")  # 非交互：不能卡在等按键上
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit):
                bootstrap.ensure_runtime()
        text = err.getvalue()
        self.assertIn("缺少第三方依赖：no_such_mod_xyz", text)
        self.assertNotIn("%s", text)

    def test_wait_for_enter_only_applies_to_a_real_keyboard(self):
        asked = []
        saved_input = builtins.input
        self.addCleanup(setattr, builtins, "input", saved_input)
        builtins.input = lambda prompt="": asked.append(prompt)

        sys.stdin = io.StringIO("")
        bootstrap._wait_for_enter()
        self.assertEqual(asked, [], "管道输入时不该等按键")

        class FakeTTY(io.StringIO):
            def isatty(self):
                return True

        sys.stdin = FakeTTY("")
        bootstrap._wait_for_enter()
        self.assertEqual(asked, ["\n按回车键退出 ..."])


class ReportCrashTest(unittest.TestCase):
    def test_traceback_is_printed_and_saved(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        saved_file, saved_stdin = ui.__file__, sys.stdin
        ui.__file__ = str(Path(tmp.name) / "ui.py")   # report_crash 用它定位 crash.log
        sys.stdin = io.StringIO("")
        try:
            def raiser():
                raise RuntimeError("模拟：没兜住的崩溃")

            buf = io.StringIO()
            try:
                raiser()
            except RuntimeError as exc:
                with redirect_stderr(buf):
                    log = ui.report_crash(exc)
            self.assertIn("RuntimeError: 模拟：没兜住的崩溃", buf.getvalue())
            self.assertIn("模拟：没兜住的崩溃", Path(log).read_text(encoding="utf-8"))
        finally:
            ui.__file__, sys.stdin = saved_file, saved_stdin


if __name__ == "__main__":
    unittest.main()
