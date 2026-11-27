#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端 UI 工具：颜色、分隔线、表格、进度条与输入辅助。

所有渲染用纯文本实现，不直接依赖 rich（项目改用 textual 做 TUI；textual
内部虽自带 rich，但本模块不再直接 import 它）。纯函数（宽度/折行/体积/
进度文本/ANSI 颜色）供全项目与测试复用，NO_COLOR、管道输出时降级为纯文本。
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path

# ---------- ANSI 序列 ----------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GREY = "\033[90m"

_enabled = None


class UserQuit(Exception):
    """用户在输入提示处按了 Ctrl+C / Ctrl+D，或 stdin 已耗尽。"""


def setup_streams() -> None:
    """把标准输出/错误强制成 UTF-8。

    中文 Windows 控制台默认代码页是 cp936（GBK），print 一个 emoji 就会抛
    UnicodeEncodeError 直接闪退。Windows 控制台走 WriteConsoleW，改成 UTF-8
    反而能正常显示；errors="replace" 再兜一层，保证任何字符都再也无法让程序崩溃。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # 输出流被替换成不支持 reconfigure 的对象时跳过


def hold(msg: str = "按回车键继续 ...") -> None:
    """让刚打印出来的信息停住，等用户按键——只在真的有人坐在键盘前时。

    管道、脚本喂输入、CI 里 ``sys.stdin.isatty()`` 为假，这时直接返回，
    否则自动化测试会卡在提示上不动。
    """
    if not (sys.stdin and sys.stdin.isatty()):
        return
    try:
        input(c(f"\n{msg}", GREY))
    except (EOFError, KeyboardInterrupt):
        pass


def report_crash(exc: BaseException) -> Path:
    """兜底错误处理：打印 traceback、追加到 crash.log，并等用户按回车。

    双击 .py 运行时窗口一闪而过，根本看不到报错；把错误落盘并要求按键，
    问题才变成「可查的」。
    """
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(text, file=sys.stderr, flush=True)

    log = Path(__file__).resolve().with_name("crash.log")
    try:
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Python {sys.version.split()[0]}\n{text}")
        print(f"（上面的完整错误也已写入 {log}）", file=sys.stderr, flush=True)
    except OSError:
        pass

    hold("按回车键退出 ...")
    return log


def color_enabled() -> bool:
    """判断当前终端是否支持 ANSI 颜色（结果缓存）。"""
    global _enabled
    if _enabled is None:
        no_color = os.environ.get("NO_COLOR", "")
        force_color = os.environ.get("FORCE_COLOR", "")
        if no_color and no_color != "0":
            _enabled = False
        elif force_color and force_color != "0":
            _enabled = True
        else:
            _enabled = sys.stdout.isatty()
            if _enabled and os.name == "nt":
                # 空命令会让 conhost 进入“已启用虚拟终端”状态，Win10+ 生效
                os.system("")
    return _enabled


def is_tty() -> bool:
    return bool(sys.stdout.isatty())


def c(text: str, *codes: str) -> str:
    """给文本上色；不支持颜色时原样返回。"""
    if not codes or not color_enabled():
        return text
    return "".join(codes) + text + RESET


def term_width() -> int:
    """终端宽度，取不到时按 80 列兜底。"""
    return max(40, shutil.get_terminal_size((80, 24)).columns)


def display_width(text: str) -> int:
    """字符串在终端里占几列：东亚全角与 emoji 记 2 列，勾叉和其余字符记 1 列。"""
    width = 0
    for ch in text:
        cp = ord(ch)
        if 0x2713 <= cp <= 0x2716:
            # ✓✔✕✖ 在终端里只有一列，不能按 symbol 区间算成两列
            width += 1
        elif cp > 0x2E80 or 0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF:
            width += 2
        else:
            width += 1
    return width


def pad(text: str, width: int) -> str:
    """按显示宽度右侧补空格。"""
    return text + " " * max(0, width - display_width(text))


def truncate(text: str, width: int) -> str:
    """按显示宽度截断，超长时以省略号结尾。"""
    if display_width(text) <= width:
        return text
    out = ""
    for ch in text:
        if display_width(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


def rule(char: str = "─", width: int | None = None, color: str = GREY) -> str:
    return c(char * (width or term_width()), color)


def clear() -> None:
    if is_tty():
        os.system("cls" if os.name == "nt" else "clear")


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(cell: str) -> str:
    """去掉 ANSI 颜色码，得到单元格的可见文本。"""
    return _ANSI.sub("", str(cell))


def banner(title: str, subtitle: str = "") -> None:
    """渲染顶部标题框（纯文本 Unicode 边框，自动适配内容宽度）。"""
    lines = [_plain(title)]
    if subtitle:
        lines.append(_plain(subtitle))
    inner = max(display_width(line) for line in lines) + 2
    top = "╭" + "─" * inner + "╮"
    bottom = "╰" + "─" * inner + "╯"
    print(c(top, CYAN))
    for line in lines:
        print(c("│", CYAN) + " " + line + " " * (inner - display_width(line) - 1) + c("│", CYAN))
    print(c(bottom, CYAN))


def table(rows: list[list[str]], headers: list[str]) -> None:
    """输出等宽对齐的纯文本表格：按显示宽度算列宽，中英文混排也不错位。"""
    columns = len(headers)
    cells = [[_plain(x) for x in row] + [""] * (columns - len(row)) for row in rows]
    widths = [display_width(str(headers[i])) for i in range(columns)]
    for row in cells:
        for i, cell in enumerate(row):
            # 行比表头多一格时按 0 列起算，别让 widths[i] 越界
            width = max(widths[i] if i < len(widths) else 0, display_width(str(cell)))
            if i < len(widths):
                widths[i] = width
            else:
                widths.append(width)
    widths = [min(w, max(20, term_width() - columns * 3)) for w in widths]

    def render(row: list[str]) -> str:
        parts = [" " + str(cell) + " " * ((widths[i] if i < len(widths) else 0) - display_width(str(cell))) + " "
                 for i, cell in enumerate(row)]
        return "|" + "|".join(parts) + "|"

    print(c(render(list(headers)), BOLD))
    print("+" + "+".join("-" * (w + 2) for w in widths) + "+")
    for row in cells:
        print(render(row))


def human_size(num: float) -> str:
    """字节数转成可读体积。"""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"


def human_duration(sec: float) -> str:
    """秒数转成 1m20s 这种形式。"""
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}s"
    return f"{sec // 60}m{sec % 60:02d}s"


def progress_line(done: int, total: int, rate: float, width: int = 26) -> str:
    """单行进度条：百分比、已下/总量、速度、剩余时间。"""
    ratio = (done / total) if total > 0 else 0.0
    filled = min(width, int(width * ratio))
    bar = "█" * filled + "░" * (width - filled)
    info = f"{human_size(done)}/{human_size(total)}" if total > 0 else human_size(done)
    eta = f" ETA {human_duration((total - done) / rate)}" if total > 0 and rate > 0 else ""
    speed = f" {human_size(rate)}/s" if rate > 0 else ""
    return f"[{bar}] {ratio * 100:5.1f}%  {info}{speed}{eta}"


def progress_render(done: int, total: int, rate: float, width: int = 26) -> str:
    """纯文本进度条主体 + 与 progress_line 相同的文字信息。

    用破折号风格（不含 █/░），供 downloader 的 \\r 重绘机制使用；
    这是替代 rich 进度条的轻量实现。
    """
    ratio = (done / total) if total > 0 else 0.0
    filled = min(width, int(width * ratio))
    bar = "─" * filled + "-" * (width - filled)
    tail = progress_line(done, total, rate, width=1).split("]", 1)[-1]
    return "[" + bar + "]" + tail


def ask(prompt: str = ">>> ") -> str:
    """读取一行输入；Ctrl+C / 管道结束时抛 UserQuit，而不是抛裸异常。"""
    try:
        return input(c(prompt, BOLD)).strip()
    except EOFError:
        print()
        raise UserQuit from None
    except KeyboardInterrupt:
        print()
        raise UserQuit from None


def choose(prompt: str, count: int, allow_zero: bool = False) -> int | None:
    """要求用户输入 1..count（allow_zero 时允许 0=返回）。返回 0 表示返回，None 表示取消。"""
    hint = "0 返回" if allow_zero else ""
    while True:
        label = prompt.rstrip("：") + (f"（{hint}）：" if hint else "：")
        raw = ask(label)
        if raw.lower() in ("q", "quit", "back", "返回"):
            return None
        if not raw.isdigit():
            print(c(f"  ⚠ 请输入 0-{count} 之间的数字。", YELLOW))
            continue
        num = int(raw)
        lo = 0 if allow_zero else 1
        if lo <= num <= count:
            return num
        print(c(f"  ⚠ 编号超出范围，请输入 {lo}-{count}。", YELLOW))


def confirm(prompt: str, default: bool = True) -> bool:
    """y/n 确认，直接回车取默认值。"""
    tail = "[Y/n]" if default else "[y/N]"
    raw = ask(f"{prompt} {tail} ").lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "是")
