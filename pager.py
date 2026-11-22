#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端翻页器：在备用屏幕里查看 Release 更新说明，↑/↓ 滚动，Q 返回。

按键读取只用标准库（Windows msvcrt / POSIX termios），Markdown 正文用
轻量文本解析成可读行（标题装饰、列表符号、折行），不依赖 rich。
非交互环境降级成行输入，便于测试与管道。
"""

from __future__ import annotations

import re
import shutil
import sys

import ui

ENTER_ALT = "\033[?1049h"
EXIT_ALT = "\033[?1049l"
CURSOR_HOME = "\033[H"
CLEAR_SCREEN = "\033[2J"


def _interactive() -> bool:
    """只有stdout和stdin都连着真人终端时才启用备用屏幕与原始按键。"""
    return ui.is_tty() and bool(sys.stdin and sys.stdin.isatty())


def wrap_text(text: str, width: int) -> list[str]:
    """按显示宽度折行，保留原有换行；宽度至少为 1。"""
    width = max(1, int(width))
    out: list[str] = []
    for raw in (text or "").splitlines():
        if not raw:
            out.append("")
            continue
        current = ""
        current_width = 0
        for ch in raw:
            ch_width = ui.display_width(ch)
            if current and current_width + ch_width > width:
                out.append(current)
                current = ch
                current_width = ch_width
            else:
                current += ch
                current_width += ch_width
        out.append(current)
    return out


def render_markdown_lines(text: str, width: int) -> list[str]:
    """把 Markdown 正文轻量渲染成可滚动的文本行，不依赖第三方库。

    处理标题、无序/有序列表、分隔线，其余按显示宽度折行；链接语法去掉外壳
    保留可读文字。解析失败时退回 wrap_text，保证怪异正文不会让翻页器崩溃。
    """
    try:
        out: list[str] = []
        width = max(20, width)
        for raw in (text or "").splitlines():
            line = raw.rstrip()
            if not line.strip():
                out.append("")
                continue
            heading = re.match(r"^(#{1,6})\s+(.*)$", line)
            if heading:
                marker = "■ " if len(heading.group(1)) <= 2 else "▸ "
                out.extend(wrap_text(marker + heading.group(2), width))
                continue
            unordered = re.match(r"^\s*[-*+]\s+(.*)$", line)
            if unordered:
                out.extend(wrap_text("• " + unordered.group(1), width))
                continue
            ordered = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
            if ordered:
                out.extend(wrap_text("• " + ordered.group(1), width))
                continue
            if re.match(r"^\s*(---+|\*\*\*+)\s*$", line):
                out.append("─" * min(width, 40))
                continue
            # [text](url) → text，去掉链接外壳只留可读文字
            plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
            plain = re.sub(r"[*_`]", "", plain)
            out.extend(wrap_text(plain, width))
        return out
    except Exception:  # noqa: BLE001  排版是增强项，不能挡住查看正文
        return wrap_text(text, width)


def _windows_key() -> str:
    import msvcrt

    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        code = msvcrt.getwch()
        if code == "H":
            return "up"
        if code == "P":
            return "down"
        return ""  # 左右键：按需求忽略
    if ch in ("q", "Q"):
        return "quit"
    return ""


def _posix_key() -> str:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if not select.select([sys.stdin], [], [], 0.05)[0]:
                return ""
            if sys.stdin.read(1) != "[":
                return ""
            if not select.select([sys.stdin], [], [], 0.05)[0]:
                return ""
            code = sys.stdin.read(1)
            if code == "A":
                return "up"
            if code == "B":
                return "down"
            return ""
        if ch in ("q", "Q"):
            return "quit"
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _line_key() -> str:
    """管道/测试里的降级：读一行文本当按键，EOF 或 Ctrl+C 视为退出。"""
    try:
        raw = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "quit"
    if raw in ("q", "quit", "退出"):
        return "quit"
    if raw in ("up", "u", "w"):
        return "up"
    if raw in ("down", "d", "s"):
        return "down"
    return ""


def read_key() -> str:
    """返回 up / down / quit / ""（忽略的按键）。"""
    if not _interactive():
        return _line_key()
    if sys.platform == "win32":
        return _windows_key()
    return _posix_key()


def _page_lines() -> int:
    return max(5, shutil.get_terminal_size((80, 24)).lines - 5)


def _draw(lines: list[str], top: int, height: int, title: str, interactive: bool) -> None:
    width = max(20, ui.term_width())
    if interactive:
        # Windows 10+ 需要这一步才认得 ANSI 序列；重复调用是幂等的
        ui.color_enabled()
        sys.stdout.write(CURSOR_HOME + CLEAR_SCREEN)
    sep = "─" * width
    if title:
        print(ui.c(f" {title}", ui.BOLD, ui.CYAN))
    print(ui.c(sep, ui.GREY))
    window = lines[top:top + height]
    for line in window:
        print(line)
    if interactive:
        for _ in range(height - len(window)):
            print()
    print(ui.c(sep, ui.GREY))
    position = f"{min(top + height, len(lines))}/{len(lines)}"
    print(ui.c(f" [↑/↓ 滚动]  Q 返回   {position}", ui.DIM), flush=True)


def show(text: str, title: str = "") -> None:
    """全屏显示正文并接受滚动按键；任何异常都在 finally 里恢复终端。"""
    lines = render_markdown_lines(text, max(20, ui.term_width() - 4))
    if not lines:
        lines = ["（该仓库的 release 没有填写更新说明。）"]

    height = _page_lines()
    max_top = max(0, len(lines) - height)
    interactive = _interactive()
    top = 0

    if interactive:
        ui.color_enabled()
        sys.stdout.write(ENTER_ALT)
        sys.stdout.flush()
    try:
        while True:
            _draw(lines, top, height, title, interactive)
            action = read_key()
            if action == "quit":
                break
            if action == "up":
                top = max(0, top - 1)
            elif action == "down":
                top = min(max_top, top + 1)
    except KeyboardInterrupt:
        pass
    finally:
        if interactive:
            sys.stdout.write(EXIT_ALT)
            sys.stdout.flush()
