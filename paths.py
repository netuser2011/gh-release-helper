#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户数据目录：Token / 收藏 / 配置放到可写位置，避免装在 Program Files 后写不进去。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_APP_DIR_NAME = "gh-release-helper"
_LEGACY_FILES = (".github_token", "favorites.json", "config.json")


def app_data_dir() -> Path:
    """按 GHR_DATA_DIR > %APPDATA% > ~/.local/share 的顺序确定数据目录，并尽力建好。"""
    override = os.environ.get("GHR_DATA_DIR", "").strip()
    if override:
        target = Path(override).expanduser()
    elif os.name == "nt":
        # Windows 上程序目录常装在 Program Files，只有 %APPDATA% 是每个用户可写的
        target = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / _APP_DIR_NAME
    else:
        target = Path.home() / ".local" / "share" / _APP_DIR_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # 建目录失败也不能挡住启动，真正写入时再报具体错误
    return target


def migrate_legacy_files() -> None:
    """源码目录首次运行时复制旧数据；旧文件保留，失败不阻断启动。"""
    source = Path(__file__).resolve().parent
    # 打包后 __file__ 指向 _internal，那里没有 main.py；只有源码目录才需要迁移
    if getattr(sys, "frozen", False) or not (source / "main.py").is_file():
        return
    target = app_data_dir()
    for name in _LEGACY_FILES:
        old, new = source / name, target / name
        if not old.is_file() or new.exists():
            continue
        try:
            shutil.copy2(old, new)
        except OSError:
            pass  # 占用或权限问题留到下次启动再试，不能盖过真正要处理的启动流程
