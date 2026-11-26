#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub REST API 封装：仓库搜索、Release 资产、Token 解析与统一异常处理。

全部走官方 API（api.github.com），不解析网页 HTML。
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

import paths
import requests

API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 20
USER_AGENT = "gh-release-helper"

# Token 本地文件名（已在 .gitignore 里忽略，绝不能提交到仓库）
TOKEN_FILE = paths.app_data_dir() / ".github_token"

# Token 页面：引导用户去官方页面自己生成，源码里永远不出现真实 Token。
# scopes=public_repo 对应经典 Token，公共仓库读取只需要这一项。
TOKEN_CREATE_URL = ("https://github.com/settings/tokens/new"
                    "?scopes=public_repo&description=gh-release-helper")
TOKENS_PAGE_URL = "https://github.com/settings/tokens"
FINE_GRAINED_URL = "https://github.com/settings/personal-access-tokens/new"


class GitHubError(Exception):
    """API 调用失败的通用异常，message 面向用户可读。

    status_code 记录触发异常的 HTTP 状态码（网络层错误为 None），供调用方
    区分限流（403/429）等情况，不必去解析文案。
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NotFoundError(GitHubError):
    """404：仓库不存在，或该仓库没有 release。"""


class RateLimitedError(GitHubError):
    """API 调用超出限额（HTTP 403 限流或 429）。"""


def resolve_token(cli_token: str | None = None) -> str:
    """按「命令行 > 环境变量 GITHUB_TOKEN > 本地 .github_token 文件」的顺序取 Token。

    代码里不写死任何真实 Token，避免密钥跟着源码一起泄露。
    """
    if cli_token:
        return cli_token.strip()
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_FILE.is_file():
        try:
            for line in TOKEN_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
        except OSError:
            return ""
    return ""


def save_token(token: str) -> Path:
    """把 Token 存进本地 .github_token（权限 600），供下次启动自动读取。"""
    TOKEN_FILE.write_text(token.strip() + "\n", encoding="utf-8")
    try:
        TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # 文件系统不支持 POSIX 权限（如 FAT）时忽略
    return TOKEN_FILE


def build_headers(token: str) -> dict:
    """构造请求头：声明 API 版本，并在有 Token 时携带鉴权信息。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_json(url: str, params: dict | None = None, token: str = "") -> tuple[object, Mapping[str, str]]:
    """请求 GitHub API 并返回 (JSON 数据, 响应头)；任何失败都转成带明确提示的异常。"""
    try:
        resp = requests.get(url, params=params or {}, headers=build_headers(token), timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ProxyError as exc:
        raise GitHubError(f"代理连接失败，请检查 HTTP_PROXY / HTTPS_PROXY 配置：{exc}") from exc
    except requests.exceptions.SSLError as exc:
        raise GitHubError(
            "SSL 证书校验失败：程序已通过 truststore 信任系统证书，若仍报错，请确认代理工具（Watt Toolkit /\n"
            "      Charles / 企业网关）的根证书已安装到系统；也可手动设置 REQUESTS_CA_BUNDLE 指向它的 PEM 文件。\n"
            f"      原始错误：{exc}"
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise GitHubError(f"无法连接到 api.github.com，请检查网络或代理：{exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise GitHubError(f"请求超时（>{REQUEST_TIMEOUT}s），请稍后重试：{exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise GitHubError(f"网络请求异常：{exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise GitHubError(f"接口返回的不是合法 JSON（HTTP {resp.status_code}），可能被网关或代理拦截。") from exc

    if resp.status_code == 200:
        return data, resp.headers

    msg = data.get("message", "") if isinstance(data, dict) else ""

    if resp.status_code == 404:
        raise NotFoundError(msg or "资源不存在", resp.status_code)
    # 429 与 403 限流都归到 RateLimitedError：两者都表示「别再打了」，调用方据此停批。
    if resp.status_code == 429 or (resp.status_code in (401, 403) and "rate limit" in msg.lower()):
        reset_hint = resp.headers.get("X-RateLimit-Reset", "")
        raise RateLimitedError(
            f"API 调用已达上限：{msg}。额度重置时间戳：{reset_hint or '未知'}\n"
            "      配一个 Token 可把限额从 60 次/小时提升到 5000 次/小时：\n"
            f"      {TOKEN_CREATE_URL}\n"
            "      菜单里按 5 可以直接打开这个页面并粘贴保存。",
            resp.status_code,
        )
    if resp.status_code in (401, 403):
        raise GitHubError(
            f"鉴权失败或权限不足（HTTP {resp.status_code}）：{msg or '请确认 Token 有效且能访问该仓库'}",
            resp.status_code,
        )
    if resp.status_code == 422:
        raise GitHubError(f"请求参数有误（HTTP 422）：{msg}", resp.status_code)
    raise GitHubError(f"API 请求失败（HTTP {resp.status_code}）：{msg or resp.text[:200]}", resp.status_code)


def normalize_repo(text: str) -> tuple[str, str] | tuple[None, None]:
    """把用户输入归一化成 (owner, name)，接受 owner/repo、仓库名或完整网页地址。"""
    raw = (text or "").strip().strip("/")
    # Release / tree 等深链接和查询串不是仓库名的一部分，只认前两段
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    if "github.com/" in raw:
        raw = raw.split("github.com/", 1)[1]
    parts = [p for p in raw.split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def search_repos(keyword: str, token: str = "", limit: int = 10) -> tuple[list[dict], int]:
    """按仓库名搜索，返回 (候选列表, 匹配总数)。

    in:name 把匹配限制在仓库名，否则 GitHub 会连描述和 README 一起搜，噪声极大；
    按星标倒序，最常用的仓库自然排在前面。
    """
    data, _ = request_json(
        f"{API_BASE}/search/repositories",
        {"q": f"{keyword} in:name", "sort": "stars", "order": "desc", "per_page": max(1, min(limit, 30)), "page": 1},
        token,
    )
    if not isinstance(data, dict):
        raise GitHubError("搜索接口返回格式异常，无法解析候选仓库。")
    items = data.get("items")
    if not isinstance(items, list):
        raise GitHubError("搜索接口未返回 items 字段，无法解析候选仓库。")
    total = int(data.get("total_count", len(items)) or 0)
    return items, total


def get_repo(repo: str, token: str = "") -> dict:
    """取单个仓库的元信息，用于确认仓库是否真的存在。"""
    data, _ = request_json(f"{API_BASE}/repos/{repo}", {}, token)
    if not isinstance(data, dict):
        raise GitHubError("仓库信息接口返回格式异常。")
    return data


def get_latest_release(repo: str, token: str = "") -> dict:
    """取最新 release（GitHub 的 latest 会排除草稿与预发布）。"""
    data, _ = request_json(f"{API_BASE}/repos/{repo}/releases/latest", {}, token)
    if not isinstance(data, dict):
        raise GitHubError("release 接口返回格式异常。")
    return data


def list_releases(repo: str, token: str = "", limit: int = 5) -> list[dict]:
    """取最近若干个 release。"""
    data, _ = request_json(
        f"{API_BASE}/repos/{repo}/releases",
        {"per_page": max(1, min(limit, 100)), "page": 1},
        token,
    )
    if not isinstance(data, list):
        raise GitHubError("release 列表接口返回格式异常。")
    return data


def get_latest_release_or_explain(repo: str, token: str = "") -> dict:
    """取最新 release；404 时进一步区分「仓库不存在」和「仓库没有 release」。"""
    try:
        return get_latest_release(repo, token)
    except NotFoundError:
        try:
            get_repo(repo, token)
        except NotFoundError:
            raise GitHubError(f"仓库 {repo} 不存在或无权访问，请确认作者名与仓库名。") from None
        raise GitHubError(f"{repo} 存在，但没有发布任何 release（草稿与预发布不计入 latest）。") from None


def release_assets(release: dict) -> list[dict]:
    """安全地取出 release 里的资产列表。"""
    assets = release.get("assets") if isinstance(release, dict) else None
    return [a for a in assets if isinstance(a, dict)] if isinstance(assets, list) else []


def asset_ext(name: str) -> str:
    """资产文件的小写扩展名，不含点号；没有扩展名时返回「无」。"""
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return "无"
    return base.rsplit(".", 1)[-1].lower()


def filter_by_ext(assets: list[dict], exts: list[str]) -> list[dict]:
    """按扩展名筛选资产（大小写不敏感，点号可选）。"""
    if not exts:
        return assets
    wanted = {(e[1:] if e.startswith(".") else e).lower() for e in exts}
    return [a for a in assets if asset_ext(a.get("name", "")) in wanted]


def rate_limit_status(token: str = "") -> dict:
    """查询当前 Token 的配额，用于界面上提示剩余额度。"""
    _, headers = request_json(f"{API_BASE}/rate_limit", {}, token)
    return {
        "limit": int(headers.get("X-RateLimit-Limit", 0) or 0),
        "remaining": int(headers.get("X-RateLimit-Remaining", 0) or 0),
        "authenticated": bool(token),
    }
