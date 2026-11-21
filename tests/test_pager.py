# -*- coding: utf-8 -*-
"""pager：折行宽度、按键解析、非交互渲染与备用屏幕进入/退出。"""

import io
import unittest
from contextlib import redirect_stdout

import pager
import ui


class WrapTextTest(unittest.TestCase):
    def test_plain_ascii_wraps_at_width(self):
        self.assertEqual(pager.wrap_text("abcdefghij", 4), ["abcd", "efgh", "ij"])

    def test_cjk_counts_as_two_columns(self):
        # "下载"占 4 列，宽度 4 时后面的 ASCII 必须折到下一行
        self.assertEqual(pager.wrap_text("下载a", 4), ["下载", "a"])

    def test_original_newlines_are_kept(self):
        self.assertEqual(pager.wrap_text("第一行\n第二行", 20), ["第一行", "第二行"])

    def test_blank_line_is_kept(self):
        self.assertEqual(pager.wrap_text("a\n\nb", 10), ["a", "", "b"])

    def test_empty_text_has_no_lines(self):
        self.assertEqual(pager.wrap_text("", 10), [])

    def test_width_is_at_least_one(self):
        self.assertEqual(pager.wrap_text("ab", 0), ["a", "b"])


class LineKeyTest(unittest.TestCase):
    def call_with(self, answer):
        saved = pager._interactive
        pager._interactive = lambda: False
        self.addCleanup(setattr, pager, "_interactive", saved)
        import builtins
        saved_builtin = builtins.input
        builtins.input = lambda: answer
        self.addCleanup(setattr, builtins, "input", saved_builtin)
        return pager.read_key()

    def test_q_quits(self):
        self.assertEqual(self.call_with("q"), "quit")
        self.assertEqual(self.call_with("QUIT"), "quit")

    def test_scroll_aliases(self):
        self.assertEqual(self.call_with("up"), "up")
        self.assertEqual(self.call_with("w"), "up")
        self.assertEqual(self.call_with("down"), "down")
        self.assertEqual(self.call_with("s"), "down")

    def test_unknown_is_ignored(self):
        self.assertEqual(self.call_with("left"), "")


class ShowTest(unittest.TestCase):
    def setUp(self):
        saved_interactive, saved_key, saved_page = pager._interactive, pager.read_key, pager._page_lines
        pager._interactive = lambda: False
        pager._page_lines = lambda: 2
        self.addCleanup(setattr, pager, "_interactive", saved_interactive)
        self.addCleanup(setattr, pager, "read_key", saved_key)
        self.addCleanup(setattr, pager, "_page_lines", saved_page)

    def run_show(self, text, keys, title=""):
        actions = iter(keys)
        pager.read_key = lambda: next(actions, "quit")
        buf = io.StringIO()
        with redirect_stdout(buf):
            pager.show(text, title=title)
        return buf.getvalue()

    def test_renders_title_body_and_footer(self):
        out = self.run_show("第一行\n第二行", ["q"], title="owner/repo · v1")
        self.assertIn("owner/repo", out)
        self.assertIn("第一行", out)
        self.assertIn("第二行", out)
        self.assertIn("Q 返回", out)

    def test_empty_body_uses_placeholder(self):
        out = self.run_show("", ["q"])
        self.assertIn("没有填写更新说明", out)

    def test_scroll_down_advances_position(self):
        # rich Markdown 会在列表项之间插空行，因此用位置指示器验证滚动更稳定
        out = self.run_show("- A\n- B\n- C\n- D", ["down", "down", "down", "q"])
        self.assertIn("A", out)
        positions = [line for line in out.splitlines() if "Q 返回" in line]
        self.assertGreater(len(positions), 1)
        self.assertNotEqual(positions[0].split()[-1], positions[-1].split()[-1])

    def test_markdown_is_rendered_with_structure(self):
        lines = pager.render_markdown_lines("## 更新\n\n- 新增功能\n- 修复问题", 60)
        text = "\n".join(lines)
        self.assertIn("更新", text)
        self.assertIn("新增功能", text)
        self.assertIn("修复问题", text)
        self.assertTrue(any("•" in line for line in lines), "列表应渲染成项目符号")

    def test_enter_and_exit_alternate_screen(self):
        saved_tty = ui.is_tty
        ui.is_tty = lambda: True
        self.addCleanup(setattr, ui, "is_tty", saved_tty)
        saved_stdin_tty = pager.sys.stdin.isatty
        pager.sys.stdin.isatty = lambda: True
        self.addCleanup(setattr, pager.sys.stdin, "isatty", saved_stdin_tty)

        pager._interactive = lambda: True
        actions = iter(["quit"])
        pager.read_key = lambda: next(actions)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pager.show("内容", title="t")
        out = buf.getvalue()
        self.assertIn(pager.ENTER_ALT, out)
        self.assertIn(pager.EXIT_ALT, out)


if __name__ == "__main__":
    unittest.main()
