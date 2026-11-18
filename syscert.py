#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动信任系统证书存储，解决代理工具导致的 SSL 证书校验失败。

Watt Toolkit / SteamTools 等代理工具会给 HTTPS 做中间人，并把自签根证书
装进 Windows 证书存储。requests 默认只认 certifi 自带的 CA，不认这张根
证书，于是报 SSL 校验失败——关掉代理才能用，但直连 GitHub 又很慢。

本模块在启动时把「certifi + 系统证书」合并成一个 PEM bundle，写到用户
目录，并设置 REQUESTS_CA_BUNDLE 让 requests 使用它。浏览器信任的站点，
本工具也能访问，无需退出代理工具。

只用 Python 标准库（certifi 是 requests 自带的，可选）。任何一步失败都
静默跳过，不影响主流程——证书是增强项，不是运行前提。
"""

from __future__ import annotations

import os
import re
import ssl
from pathlib import Path

CA_ENV = "REQUESTS_CA_BUNDLE"
_CERT_DIR = Path.home() / ".gh-release-helper"
_CA_FILE = _CERT_DIR / "ca-bundle.pem"

_PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)

# 供菜单/排障查询的最近一次结果
_last: dict = {"enabled": False, "count": 0, "error": ""}


def _certifi_pems() -> list[str]:
    """读取 requests 自带的 certifi 证书包；拿不到就返回空列表。"""
    try:
        import certifi

        text = Path(certifi.where()).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001  certifi 缺失或读取失败都算可选
        return []
    return [block.strip() + "\n" for block in _PEM_BLOCK.findall(text)]


def _system_pems() -> list[str]:
    """从系统证书存储导出 CA（Windows 上即受信任的根证书，含代理工具装的）。"""
    ders = ssl.create_default_context().get_ca_certs(binary_form=True)
    return [ssl.DER_cert_to_PEM_cert(der).strip() + "\n" for der in ders]


def ensure_system_certs() -> bool:
    """导出系统证书并让 requests 信任；返回是否生效。

    已经手动设置过 REQUESTS_CA_BUNDLE 时不覆盖，尊重用户选择。
    """
    if os.environ.get(CA_ENV, "").strip():
        _last.update(enabled=False, count=0, error="已有 REQUESTS_CA_BUNDLE，尊重用户设置")
        return False
    try:
        # dict.fromkeys 去重；certifi 放前面，保证原本信任的 CA 不丢
        pems = list(dict.fromkeys(_certifi_pems() + _system_pems()))
        if not pems:
            _last.update(enabled=False, count=0, error="没有可导出的证书")
            return False
        _CERT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CA_FILE.with_name(_CA_FILE.name + ".tmp")
        try:
            tmp.write_text("".join(pems), encoding="ascii")
            tmp.replace(_CA_FILE)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        os.environ[CA_ENV] = str(_CA_FILE)
        _last.update(enabled=True, count=len(pems), error="")
        return True
    except Exception as exc:  # noqa: BLE001  证书是增强项，失败绝不能挡住主流程
        _last.update(enabled=False, count=0, error=f"{exc.__class__.__name__}: {exc}")
        return False


def describe() -> str:
    """给菜单/排障用的一行状态说明。"""
    if _last["enabled"]:
        return f"已信任系统证书 {_last['count']} 张"
    if _last["error"]:
        return f"系统证书未生效（{_last['error']}）"
    return "系统证书未初始化"
