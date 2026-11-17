#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载能力：requests 流式写盘 + 实时进度条，并用系统默认浏览器打开下载地址。"""

from __future__ import annotations

import json
import os
import re
import time
import webbrowser
from pathlib import Path

import requests

import ui

CHUNK = 64 * 1024
DOWNLOAD_DIR_ENV = "GHR_DOWNLOAD_DIR"
# 用户自选的默认下载目录记在这里（个人偏好，已在 .gitignore 中忽略）
CONFIG_FILE = Path(__file__).resolve().with_name("config.json")
# 文件名里不允许出现的字符（Windows 保留字符 + 路径分隔符 + 控制字符）
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DownloadError(Exception):
    """下载过程中的可预期失败。"""


def load_config() -> dict:
    """读取 config.json；文件缺失或损坏时返回空配置，不影响使用。"""
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_config(config: dict) -> Path:
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    try:
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CONFIG_FILE)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return CONFIG_FILE


def set_default_download_dir(path: str | Path) -> Path:
    """把某个目录永久记住为默认下载目录。"""
    config = load_config()
    config["download_dir"] = str(Path(path).expanduser().resolve())
    save_config(config)
    return Path(config["download_dir"])


def clear_default_download_dir() -> None:
    """取消记住的目录，回到系统默认下载目录。"""
    config = load_config()
    if config.pop("download_dir", None) is not None:
        save_config(config)


def system_download_dir() -> Path:
    """系统「下载」目录，取不到时退回用户主目录。"""
    home = Path.home()
    return next((home / d for d in ("Downloads", "下载") if (home / d).is_dir()), home / "Downloads")


def resolve_download_dir() -> Path:
    """算出当前生效的默认下载目录，优先级：环境变量 > config.json > 系统下载目录。

    只做路径计算，不碰文件系统（给界面刷新用）。
    """
    env = os.environ.get(DOWNLOAD_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    saved = str(load_config().get("download_dir", "")).strip()
    if saved:
        return Path(saved).expanduser()
    return system_download_dir()


def download_dir() -> Path:
    """真正要用来自下载的目录：解析出路径并确保它存在。"""
    target = resolve_download_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"无法创建下载目录 {target}：{exc}") from exc
    return target


def safe_filename(name: str, fallback: str = "release-asset") -> str:
    """净化资产名：只取最后一段、去掉非法字符，防止 ../ 之类的路径穿越写到目录之外。"""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _ILLEGAL.sub("", base).strip().strip(".")
    if not base:
        base = fallback
    return base[:150]


def unique_path(directory: Path, filename: str) -> Path:
    """目标文件已存在时自动加 (1)(2) 后缀，不覆盖用户已有文件。"""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for i in range(1, 1000):
        candidate = directory / f"{stem}({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise DownloadError(f"同名文件过多，请手动清理：{filename}")


def open_in_browser(url: str) -> bool:
    """调用系统默认浏览器打开链接；成功与否都返回布尔值，不抛异常打断主流程。"""
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def download(url: str, filename: str = "", directory: Path | None = None) -> Path:
    """流式下载到本地，返回最终文件路径。

    先写 .part 临时文件，校验完再改名；Ctrl+C 或网络中断时把半截文件删掉，
    避免留下一个看起来完整、实际打不开的残文件。
    """
    dest_dir = directory or download_dir()
    dest = unique_path(dest_dir, safe_filename(filename or url.rsplit("/", 1)[-1]))
    part = dest.with_name(dest.name + ".part")

    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            if resp.status_code != 200:
                raise DownloadError(f"下载失败（HTTP {resp.status_code}），请确认链接是否还有效：{url}")
            try:
                total = int(resp.headers.get("Content-Length", 0) or 0)
            except ValueError:
                total = 0
            ctype = resp.headers.get("Content-Type", "")
            # 链接被重定向到 HTML 页面时（资产已删除或需要登录）提前止损
            if total == 0 and "text/html" in ctype:
                raise DownloadError(f"服务器返回的是网页而不是文件，链接可能已失效：{url}")

            written = 0
            started = time.time()
            last_draw = 0.0
            with part.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    written += len(chunk)
                    now = time.time()
                    if now - last_draw >= 0.12:  # 限制刷新频率，否则刷屏反而看不清
                        last_draw = now
                        rate = written / max(now - started, 1e-6)
                        if ui.is_tty():
                            print("\r " + ui.progress_line(written, total, rate), end="", flush=True)
        if ui.is_tty():
            print()
    except DownloadError:
        part.unlink(missing_ok=True)
        raise
    except KeyboardInterrupt:
        part.unlink(missing_ok=True)
        print()
        raise DownloadError("已取消下载，临时文件已清理。") from None
    except requests.exceptions.RequestException as exc:
        part.unlink(missing_ok=True)
        raise DownloadError(f"下载中断：{exc}") from exc
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise DownloadError(f"写入文件失败（{dest_dir}）：{exc}") from exc

    if written == 0:
        part.unlink(missing_ok=True)
        raise DownloadError("下载到的文件是空的，链接可能已失效。")
    if total and written != total:
        part.unlink(missing_ok=True)
        raise DownloadError(f"文件不完整（{written}/{total} 字节），已放弃。")

    part.replace(dest)
    return dest
