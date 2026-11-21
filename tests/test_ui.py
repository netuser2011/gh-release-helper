# -*- coding: utf-8 -*-
"""ui 模块：显示宽度、对齐、可读体积、颜色开关。这些函数不联网、不碰磁盘。"""

import builtins
import io
import os
import unittest
from contextlib import redirect_stdout

import ui


class WidthTest(unittest.TestCase):
    def test_cjk_counts_two_columns(self):
        self.assertEqual(ui.display_width("下载"), 4)
        self.assertEqual(ui.display_width("Files"), 5)
        self.assertEqual(ui.display_width("下载Files"), 9)

    def test_emoji_counts_two_columns(self):
        self.assertEqual(ui.display_width("👋"), 2)
        self.assertEqual(ui.display_width("⭐ 收藏"), 6)

    def test_pad_uses_display_width(self):
        self.assertEqual(ui.display_width(ui.pad("下载", 10)), 10)
        self.assertEqual(ui.pad("abc", 2), "abc")  # 已经超宽就不补

    def test_truncate_never_exceeds_width(self):
        cut = ui.truncate("这是一个很长很长的一句仓库简介", 10)
        self.assertLessEqual(ui.display_width(cut), 10)
        self.assertTrue(cut.endswith("…"))

    def test_truncate_keeps_short_text(self):
        self.assertEqual(ui.truncate("Files", 40), "Files")


class HumanTest(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(ui.human_size(0), "0 B")
        self.assertEqual(ui.human_size(1024), "1.0 KB")
        self.assertEqual(ui.human_size(1536), "1.5 KB")
        self.assertEqual(ui.human_size(5 * 1024 ** 3), "5.0 GB")

    def test_durations(self):
        self.assertEqual(ui.human_duration(45), "45s")
        self.assertEqual(ui.human_duration(80), "1m20s")
        self.assertEqual(ui.human_duration(-5), "0s")

    def test_progress_line_fields(self):
        line = ui.progress_line(1024, 2048, 1024.0)
        self.assertIn("50.0%", line)
        self.assertIn("1.0 KB/2.0 KB", line)
        self.assertIn("1.0 KB/s", line)
        self.assertIn("ETA 1s", line)

    def test_progress_line_without_total(self):
        line = ui.progress_line(1024, 0, 0.0)
        self.assertIn("1.0 KB", line)
        self.assertNotIn("ETA", line)

    def test_progress_render_uses_rich_and_keeps_fields(self):
        rendered = ui.progress_render(1024, 2048, 1024.0)
        self.assertIn("50.0%", rendered)
        self.assertIn("1.0 KB/2.0 KB", rendered)
        self.assertIn("ETA 1s", rendered)
        # rich 的进度条是纯破折号/方块，不再是自研的 █/░ 组合
        self.assertNotIn("█", rendered)


class ColorSwitchTest(unittest.TestCase):
    def setUp(self):
        self._saved_enabled = ui._enabled
        self._saved_env = {k: os.environ.get(k) for k in ("NO_COLOR", "FORCE_COLOR")}
        ui._enabled = None
        for key in self._saved_env:
            os.environ.pop(key, None)

    def tearDown(self):
        ui._enabled = self._saved_enabled
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_no_color_disables_everything(self):
        os.environ["NO_COLOR"] = "1"
        self.assertFalse(ui.color_enabled())
        self.assertEqual(ui.c("红色", ui.RED), "红色")

    def test_no_color_zero_does_not_disable(self):
        os.environ["NO_COLOR"] = "0"
        os.environ["FORCE_COLOR"] = "1"
        self.assertTrue(ui.color_enabled())
        self.assertEqual(ui.c("x", ui.RED), ui.RED + "x" + ui.RESET)

    def test_force_color_wins_over_pipe(self):
        os.environ["FORCE_COLOR"] = "1"
        self.assertTrue(ui.color_enabled())

    def test_c_passes_through_without_codes(self):
        os.environ["FORCE_COLOR"] = "1"
        self.assertEqual(ui.c("原样"), "原样")


class TableTest(unittest.TestCase):
    def test_rows_line_up_with_mixed_scripts(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ui.table([["1", "Files 下载器", "12.3 MB"], ["2", "gemini-cli", "1.0 KB"]], ["#", "文件名", "大小"])
        lines = [line for line in buf.getvalue().splitlines() if line.startswith("|")]
        widths = {ui.display_width(line) for line in lines}
        self.assertEqual(len(widths), 1, "中英文混排时每行的显示宽度必须一致")

    def test_header_separator_matches_widths(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ui.table([["a", "b"]], ["列一", "col2"])
        out = buf.getvalue().splitlines()
        self.assertEqual(ui.display_width(out[0]), ui.display_width(out[-1]))


class HoldTest(unittest.TestCase):
    def test_hold_returns_immediately_for_non_tty(self):
        """管道、脚本喂输入、CI 里绝不能卡在「按回车」上。"""
        saved_stdin = ui.sys.stdin
        try:
            ui.sys.stdin = io.StringIO("")
            with redirect_stdout(io.StringIO()) as buf:
                ui.hold("按回车键继续 ...")
            self.assertEqual(buf.getvalue(), "")
        finally:
            ui.sys.stdin = saved_stdin

    def test_hold_waits_when_a_person_is_typing(self):
        class FakeTTY(io.StringIO):
            def isatty(self):
                return True

        saved_stdin = ui.sys.stdin
        prompts = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return ""

        saved_input, builtins.input = builtins.input, fake_input
        try:
            ui.sys.stdin = FakeTTY("")
            with redirect_stdout(io.StringIO()):
                ui.hold("按回车键退出 ...")
        finally:
            ui.sys.stdin = saved_stdin
            builtins.input = saved_input
        self.assertEqual(len(prompts), 1)
        self.assertIn("按回车键退出", prompts[0])


class UserQuitTest(unittest.TestCase):
    def test_eof_becomes_user_quit(self):
        saved_stdin, saved_input = ui.sys.stdin, builtins.input

        def raise_eof(prompt=""):
            raise EOFError

        try:
            builtins.input = raise_eof
            ui.sys.stdin = io.StringIO("")
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(ui.UserQuit):
                    ui.ask(">>> ")
        finally:
            ui.sys.stdin, builtins.input = saved_stdin, saved_input

    def test_choose_accepts_valid_number_and_rejects_range(self):
        answers = iter(["99", "2", "0"])
        saved_ask, ui.ask = ui.ask, (lambda prompt="": next(answers))
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ui.choose("请选择：", 3, allow_zero=True), 2)
        finally:
            ui.ask = saved_ask

    def test_choose_zero_means_back(self):
        saved_ask, ui.ask = ui.ask, (lambda prompt="": "0")
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ui.choose("请选择：", 3, allow_zero=True), 0)
        finally:
            ui.ask = saved_ask

    def test_choose_keyword_returns_none(self):
        saved_ask, ui.ask = ui.ask, (lambda prompt="": "返回")
        try:
            with redirect_stdout(io.StringIO()):
                self.assertIsNone(ui.choose("请选择：", 3, allow_zero=True))
        finally:
            ui.ask = saved_ask

    def test_choose_hint_is_added_once(self):
        labels = []
        answers = iter(["1"])

        def spy(prompt=""):
            labels.append(prompt)
            return next(answers)

        saved_ask, ui.ask = ui.ask, spy
        try:
            with redirect_stdout(io.StringIO()):
                ui.choose("  请输入编号选择仓库：", 5, allow_zero=True)
        finally:
            ui.ask = saved_ask
        self.assertEqual(labels, ["  请输入编号选择仓库（0 返回）："])

    def test_confirm_defaults(self):
        cases = {"": True, "y": True, "n": False, "是": True}
        for answer, expected in cases.items():
            saved_ask, ui.ask = ui.ask, (lambda prompt="", _a=answer: _a)
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertIs(ui.confirm("继续吗？", default=True), expected, answer)
            finally:
                ui.ask = saved_ask


if __name__ == "__main__":
    unittest.main()
