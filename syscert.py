#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动信任系统证书存储，解决代理工具导致的 SSL 证书校验失败。

Watt Toolkit / SteamTools 等代理工具会给 HTTPS 做中间人，并把自签根证书
装进 Windows 证书存储。requests 默认只认 certifi 自带的 CA，不认这张根
证书，于是报 SSL 校验失败——关掉代理才能用，但直连 GitHub 又很慢。

本模块在启动时调用 truststore.inject_into_ssl()，让 requests / urllib3
直接使用操作系统（Windows / macOS / Linux）的信任存储：浏览器信任的站点，
本工具也能访问，无需自己导出、合并 PEM，也无需退出代理工具。

失败一律静默降级——证书是增强项，不是运行前提。
"""

from __future__ import annotations

import os

# 保留这个常量：用户手动设置过 REQUESTS_CA_BUNDLE 时不覆盖，尊重其选择
CA_ENV = "REQUESTS_CA_BUNDLE"

# 供菜单/排障查询的最近一次结果
_last: dict = {"enabled": False, "count": 0, "error": ""}


def _system_cert_count() -> int:
    """尽量读出系统证书数量，仅用于菜单状态展示；失败时返回 0。"""
    try:
        import ssl

        return len(ssl.create_default_context().get_ca_certs(binary_form=True))
    except Exception:  # noqa: BLE001  仅展示用，拿不到就算了
        return 0


def ensure_system_certs() -> bool:
    """把系统信任存储注入 ssl/urllib3/requests；返回是否生效。

    重复调用是安全的：truststore.inject_into_ssl() 只是替换类引用。
    """
    if os.environ.get(CA_ENV, "").strip():
        _last.update(enabled=False, count=0, error="已有 REQUESTS_CA_BUNDLE，尊重用户设置")
        return False
    try:
        # 在注入前读取，避免注入后的上下文行为差异影响计数
        count = _system_cert_count()
        import truststore

        truststore.inject_into_ssl()
        _last.update(enabled=True, count=count, error="")
        return True
    except Exception as exc:  # noqa: BLE001  证书是增强项，失败绝不能挡住主流程
        _last.update(enabled=False, count=0, error=f"{exc.__class__.__name__}: {exc}")
        return False


def describe() -> str:
    """给菜单/排障用的一行状态说明。"""
    if _last["enabled"]:
        if _last["count"]:
            return f"已信任系统证书 {_last['count']} 张（truststore）"
        return "已信任系统证书（truststore）"
    if _last["error"]:
        return f"系统证书未生效（{_last['error']}）"
    return "系统证书未初始化"
