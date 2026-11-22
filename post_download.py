#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用下载后处理：第三方资产下载完后直接运行 / 自动解压 / 删包。

与 self_update.py 的区别：这里是给「用户下载的任意仓库资产」用的，
不写回 version.txt，不调用同步 ui.confirm，也不套本程序自更新的边界检测。
交互由 TUI 层负责，本模块只提供可单测的纯动作。
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

# Windows 上双击就能装的安装包类型
LAUNCHABLE = {"exe", "msi", "msix", "appx", "appinstaller"}
ARCHIVES = {"zip"}


def kind_of(path: Path) -> str:
    """按扩展名归类：可直接启动 / 可解压 / 其它。"""
    ext = path.suffix.lower().lstrip(".")
    if ext in LAUNCHABLE:
        return "launch"
    if ext in ARCHIVES:
        return "archive"
    return "other"


def launch(path: Path) -> None:
    """直接启动安装包，弹出它自己的安装向导。

    不套 /VERYSILENT：那类参数只对 Inno Setup 有效，NSIS / MSI / 自解压包各不相同，
    静默装反而会让用户看不到界面、以为什么都没发生。
    """
    subprocess.Popen([str(path)])


def extract(path: Path) -> Path:
    """把 zip 解压到同目录下以压缩包名命名的文件夹，返回目标目录。"""
    target = path.parent / path.stem
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(target)
    return target


def delete(path: Path) -> None:
    """删掉已下载的安装包/压缩包。"""
    path.unlink()
