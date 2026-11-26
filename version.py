#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本真相源：本地 version.txt 是唯一权威，源码不写死具体版本号。

两条更新路径都落到同一个文件：
- 从 GitHub Release 手动装新包 → 新包自带的 version.txt 覆盖旧文件；
- 菜单 4「检查更新」自动升级 → 版本以新包自带的 version.txt 为准。

文件相对本模块解析，兼容源码运行与 PyInstaller 打包后的目录布局。
缺失或损坏时返回 V0.0.0：任何真实 Release 都比它新，会稳定提示一次更新，
而不是回退到某个写死的版本掩盖真实安装状态。
"""

import os
import re
import tempfile
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().with_name("version.txt")
FALLBACK = "V0.0.0"
_SPLIT = re.compile(r"[.\-_]")


def normalize(tag: str) -> str:
    """把任意写法统一成 V 主.次.补（如 v1.2.0 / 1.2 / V1.2.0b → V1.2.0）。"""
    text = str(tag or "").strip()
    nums = _SPLIT.split(text.lstrip("vV").strip())
    parts = []
    for chunk in nums[:3]:
        m = re.match(r"\d+", chunk)
        parts.append(str(int(m.group())) if m else "0")
    while len(parts) < 3:
        parts.append("0")
    return "V" + ".".join(parts)


def parse(tag: str) -> tuple[int, ...]:
    """转数字元组用于比较：去掉 V 前缀后每段转整数，避免 1.10 被判小于 1.9。"""
    nums = _SPLIT.split(str(tag or "").strip().lstrip("vV").strip())
    out = []
    for chunk in nums[:3]:
        m = re.match(r"\d+", chunk)
        out.append(int(m.group()) if m else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def is_newer(latest: str, current: str) -> bool:
    """latest 严格高于 current 才返回 True，防止回滚或重复更新。"""
    return parse(latest) > parse(current)


def read_current() -> str:
    """读当前版本；文件缺失/为空/无数字时回退 V0.0.0。"""
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return FALLBACK
    if not re.search(r"\d", text):
        return FALLBACK
    return normalize(text)


def write_current(tag: str) -> Path:
    """原子写回版本文件：先写同目录 .tmp 再 replace，避免半截文件。"""
    content = normalize(tag) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=VERSION_FILE.name + ".", suffix=".tmp",
                               dir=str(VERSION_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, VERSION_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return VERSION_FILE
