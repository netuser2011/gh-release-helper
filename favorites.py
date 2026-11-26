#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收藏持久化：以「作者名/仓库名」为键，把仓库信息与最近一次看到的 Release 资产存进 favorites.json。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import paths

FAVORITES_FILE = paths.app_data_dir() / "favorites.json"
SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(path: Path = FAVORITES_FILE) -> dict:
    """读取收藏。文件不存在时给出空结构；文件损坏时改名备份后重建，绝不让程序崩在这里。"""
    if not path.is_file():
        return {"version": SCHEMA_VERSION, "repos": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            path.replace(path.with_name(path.name + ".bak"))
        except OSError:
            pass
        return {"version": SCHEMA_VERSION, "repos": {}, "_recovered": True}

    if not isinstance(raw, dict) or not isinstance(raw.get("repos"), dict):
        return {"version": SCHEMA_VERSION, "repos": {}}
    raw.setdefault("version", SCHEMA_VERSION)
    raw["repos"] = {k: v for k, v in raw["repos"].items() if isinstance(v, dict)}
    return raw


def save(store: dict, path: Path = FAVORITES_FILE) -> None:
    """原子写入：先落临时文件再替换，避免写到一半损坏；失败时不留垃圾文件。"""
    payload = {"version": store.get("version", SCHEMA_VERSION), "repos": store.get("repos", {})}
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def find_key(store: dict, key: str) -> str | None:
    """大小写不敏感地找已存在的键（GitHub 的 owner/repo 本身不区分大小写）。"""
    lowered = key.lower()
    for existing in store.get("repos", {}):
        if existing.lower() == lowered:
            return existing
    return None


def add(store: dict, full_name: str, *, stars: int = 0, description: str = "", language: str = "",
        tag: str = "", assets: list[dict] | None = None) -> tuple[str, str]:
    """新增或覆盖一条收藏，返回 (键, 「新增」或「更新」)。"""
    repos = store.setdefault("repos", {})
    existing = find_key(store, full_name)
    key = existing or full_name
    record = repos.get(key, {})
    record.update(
        {
            "added_at": record.get("added_at") or _now(),
            "updated_at": _now(),
            "stars": stars or record.get("stars", 0),
            "description": description or record.get("description", ""),
            "language": language or record.get("language", ""),
            "last_tag": tag or record.get("last_tag", ""),
            "assets": assets if assets is not None else record.get("assets", []),
        }
    )
    repos[key] = record
    return key, ("更新" if existing else "新增")


def update_release(store: dict, key: str, tag: str, assets: list[dict]) -> None:
    """把某条收藏最近一次看到的 tag 与资产缓存写回去。"""
    existing = find_key(store, key)
    if not existing:
        return
    repos = store.setdefault("repos", {})
    repos[existing]["last_tag"] = tag
    repos[existing]["assets"] = assets
    repos[existing]["updated_at"] = _now()


def remove(store: dict, key: str) -> str | None:
    """删除一条收藏，返回真正被删掉的键。"""
    existing = find_key(store, key)
    if existing:
        store.get("repos", {}).pop(existing, None)
    return existing


def entries(store: dict) -> list[tuple[str, dict]]:
    """按加入时间从新到旧排列，方便界面上编 1、2、3 号。"""
    items = list(store.get("repos", {}).items())
    items.sort(key=lambda kv: kv[1].get("added_at", ""), reverse=True)
    return items


def count(store: dict) -> int:
    return len(store.get("repos", {}))
