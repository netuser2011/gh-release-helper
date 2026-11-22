#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""程序自身更新：检查本仓库最新 Release，仅在更新时下载并升级。

依赖分层：version（版本真相源）/ github_api（API）/ downloader（终端下载）/
ui 与 pager（交互）。自身更新是增强项，任何失败都只提示、不抛给收藏检查。
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import downloader as dl
import github_api as gh
import pager
import ui
import version

SELF_REPO = "netuser2011/gh-release-helper"
SILENT_ARGS = ["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"]


def check_self_update(token: str) -> tuple[bool, dict]:
    """查最新 Release；返回 (是否有新版本, release)。失败返回 (False, {})。"""
    try:
        release = gh.get_latest_release(SELF_REPO, token)
    except gh.GitHubError as exc:
        print(ui.c(f"  ⚠ 检查本程序更新失败：{exc}（不影响收藏仓库检查）", ui.YELLOW))
        return False, {}
    latest = str(release.get("tag_name") or "")
    if not latest:
        print(ui.c("  ⚠ 本程序的最新 Release 没有版本号，跳过自身更新。", ui.YELLOW))
        return False, {}
    current = version.read_current()
    if not version.is_newer(latest, current):
        print(ui.c(f"  ✔ 本程序已是最新版本（{current}）。", ui.GREEN))
        return False, {}
    print(ui.c(f"  ↑ 本程序有新版本：{current} → {version.normalize(latest)}", ui.YELLOW))
    return True, release


def pick_installer(release: dict) -> tuple[dict, str] | None:
    """优先 Setup.exe，其次 zip；返回 (资产, 类型)。都没有返回 None。"""
    assets = gh.release_assets(release)
    for kind, exts in (("exe", ["exe"]), ("zip", ["zip"])):
        for asset in assets:
            ext = gh.asset_ext(asset.get("name", ""))
            if ext in exts:
                return asset, kind
    return None


def _running_from_install_dir() -> bool:
    """从安装目录运行（exe 名以 GH Downloader 开头）时，运行中 exe 无法覆盖自身。"""
    exe = Path(sys.executable).name.lower()
    return exe.startswith("gh downloader")


def _extract_zip(saved: Path) -> Path | None:
    """把 zip 解压到下载目录下同名文件夹；失败提示并返回 None。"""
    target = saved.parent / saved.stem
    try:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(saved) as archive:
            archive.extractall(target)
    except (OSError, zipfile.BadZipFile) as exc:
        print(ui.c(f"  ✖ 解压失败：{exc}", ui.RED))
        return None
    return target


def offer_installer(saved: Path, kind: str, latest: str) -> None:
    """询问是否直接运行；Y 时 exe 静默安装、zip 自动解压并问删包，随后写回版本。"""
    if not ui.confirm("  是否直接运行安装包？", default=True):
        print(ui.c(f"  已下载到：{saved}（稍后可手动运行）。", ui.DIM))
        return

    if _running_from_install_dir():
        # 安装目录里的 exe 正在运行，无法被覆盖。先写回版本，提示用户手动重启完成切换。
        version.write_current(latest)
        print(ui.c("  ⚠ 当前程序正从安装目录运行，无法在运行中覆盖自身。", ui.YELLOW))
        print(ui.c("  新版本已下载，请关闭本程序后手动运行安装包，或重新打开程序继续。", ui.YELLOW))
        print(ui.c(f"  安装包位置：{saved}", ui.DIM))
        return

    if kind == "zip":
        target = _extract_zip(saved)
        if target is None:
            return
        print(ui.c(f"  ✔ 已解压到：{target}", ui.GREEN))
        version.write_current(latest)
        if ui.confirm("  要不要删除压缩包？", default=False):
            try:
                saved.unlink()
                print(ui.c("  ✔ 压缩包已删除。", ui.GREEN))
            except OSError as exc:
                print(ui.c(f"  ⚠ 删除压缩包失败：{exc}", ui.YELLOW))
        return

    try:
        subprocess.Popen([str(saved)] + SILENT_ARGS)
    except OSError as exc:
        print(ui.c(f"  ✖ 启动安装程序失败：{exc}", ui.RED))
        print(ui.c(f"  请手动运行：{saved}", ui.DIM))
        return
    version.write_current(latest)
    print(ui.c("  ✔ 已启动静默安装，完成后可重新打开程序。", ui.GREEN))


def run(token: str) -> None:
    """编排自身更新全流程；任何可预期失败都只提示，不打断后续收藏检查。"""
    has_update, release = check_self_update(token)
    if not has_update:
        return

    body = str(release.get("body") or "")
    if body and ui.confirm("  是否查看新版本的更新说明？", default=True):
        pager.show(body, title=f"本程序更新 · {release.get('tag_name', '')}")

    picked = pick_installer(release)
    if not picked:
        print(ui.c("  ⚠ 新版本没有可下载的安装包（Setup.exe / zip），跳过自身更新。", ui.YELLOW))
        return
    asset, kind = picked
    url = str(asset.get("browser_download_url") or "")
    name = str(asset.get("name") or "")
    if not url:
        print(ui.c("  ⚠ 安装包没有下载地址，跳过。", ui.YELLOW))
        return

    if not ui.confirm(f"  是否下载并安装 {version.normalize(release.get('tag_name', ''))}？", default=True):
        return

    try:
        line, _ = dl.choose_line(url)
    except dl.DownloadError as exc:
        print(ui.c(f"  ✖ 线路选择失败：{exc}", ui.RED))
        return

    print(ui.c(f"  ⬇ 正在下载安装包到 {dl.download_dir()} ...", ui.DIM))
    try:
        saved, _ = dl.fetch(line["url"], name, dl.download_dir())
    except dl.DownloadError as exc:
        print(ui.c(f"  ✖ 下载失败：{exc}", ui.RED))
        return
    print(ui.c(f"  ✔ 下载完成：{saved}", ui.GREEN))
    offer_installer(saved, kind, str(release.get("tag_name") or ""))
