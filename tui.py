#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Textual 全屏 TUI：方向键/鼠标操作，不再输入编号。

业务能力仍复用 github_api / downloader / favorites / self_update / version；
本模块只负责交互层。网络请求放后台 worker，避免卡住界面。
"""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Markdown, ProgressBar, Static

import downloader as dl
import favorites as fav
import flow_common as fc
import github_api as gh
import pager
import post_download as pd
import self_update as su
import syscert
import ui
import version

MENU = [
    ("1", "搜索仓库", "按名字找项目，选一个看 Release 资产并下载"),
    ("2", "查看收藏", "调出已存仓库的下载链接"),
    ("3", "添加收藏", "把常用仓库存进收藏夹"),
    ("4", "检查更新", "检查本程序 + 批量检查收藏仓库"),
    ("5", "配置 Token", "解除限流（存本地 .github_token）"),
    ("0", "退出", "保存收藏并退出"),
]

# 常见安装包类型，按此顺序优先展示；其余按出现频次排在后面。
TYPE_ORDER = ["zip", "exe", "msi", "tar", "gz", "7z", "rar", "iso", "apk", "dmg",
              "pkg", "deb", "rpm", "bin", "AppImage"]


def type_groups(assets: list[dict]) -> list[tuple[str, list[dict]]]:
    """按扩展名把资产分组，常见类型优先，其余按数量降序；返回 (类型, 资产列表)。"""
    groups: dict[str, list[dict]] = {}
    for asset in assets:
        ext = gh.asset_ext(asset.get("name", ""))
        groups.setdefault(ext, []).append(asset)
    result: list[tuple[str, list[dict]]] = []
    seen: set[str] = set()
    for want in TYPE_ORDER:
        for key in groups:
            if key.lower() == want.lower() and key not in seen:
                result.append((key, groups[key]))
                seen.add(key)
    rest = sorted((k for k in groups if k not in seen), key=lambda k: (-len(groups[k]), k))
    result.extend((k, groups[k]) for k in rest)
    return result


class Notice(Static):
    """顶部提示条。"""


class BaseScreen(ModalScreen):
    """页面基类：统一提供可点击的「← 返回上一级」按钮，ESC 绑定保留。

    子类在 compose() 开头 ``yield from super().compose()`` 即可获得按钮，
    原有容器层级与 CSS 选择器保持不变（Vertical 仍是 Screen 的直接子节点）。
    """

    BINDINGS = [Binding("escape", "app.back", "返回")]

    def compose(self) -> ComposeResult:
        yield Button("← 返回上一级", id="back", classes="back-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.action_back()


class ConfirmDialog(ModalScreen[bool]):
    """Y/N 确认弹窗，替代终端里的 ui.confirm。"""

    DEFAULT_CSS = """
    ConfirmDialog { align: center middle; }
    ConfirmDialog > Vertical {
        width: 60; height: auto; border: round $accent; padding: 1 2;
        background: $surface;
    }
    ConfirmDialog .question { width: 100%; text-align: center; margin-bottom: 1; }
    ConfirmDialog .row { width: 100%; height: auto; }
    ConfirmDialog Button { width: 1fr; margin: 0 1; }
    """

    def __init__(self, question: str, default: bool = True) -> None:
        super().__init__()
        self.question = question
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.question, classes="question")
            with Horizontal(classes="row"):
                yield Button("是 (Y)", variant="primary", id="yes")
                yield Button("否 (N)", variant="default", id="no")

    def on_mount(self) -> None:
        (self.query_one("#yes", Button) if self.default else self.query_one("#no", Button)).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def on_key(self, event) -> None:
        if event.key.lower() == "y":
            self.dismiss(True)
        elif event.key.lower() in ("n", "escape"):
            self.dismiss(False)


class ModeDialog(ModalScreen[str | None]):
    """下载方式三按钮，替代终端里输 1/2/3。"""

    DEFAULT_CSS = """
    ModeDialog { align: center middle; }
    ModeDialog > Vertical {
        width: 56; height: auto; border: round $accent; padding: 1 2;
        background: $surface;
    }
    ModeDialog .question { width: 100%; text-align: center; margin-bottom: 1; }
    ModeDialog Button { width: 100%; margin: 1 0; }
    """

    def __init__(self, name: str) -> None:
        super().__init__()
        self.asset_name = name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"下载 {self.asset_name}\n选择下载方式：", classes="question")
            yield Button("在终端下载到本地", variant="primary", id="terminal")
            yield Button("用系统浏览器下载", variant="default", id="browser")
            yield Button("只打印下载链接", variant="default", id="link")

    def on_mount(self) -> None:
        self.query_one("#terminal", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss({"terminal": "1", "browser": "2", "link": "3"}.get(event.button.id or ""))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class InputDialog(ModalScreen[str | None]):
    """单行输入弹窗，替代终端里的 ui.ask；回车提交，Esc 取消。"""

    DEFAULT_CSS = """
    InputDialog { align: center middle; }
    InputDialog > Vertical {
        width: 70; height: auto; border: round $accent; padding: 1 2;
        background: $surface;
    }
    InputDialog .prompt { width: 100%; margin-bottom: 1; }
    InputDialog Input { width: 100%; }
    InputDialog .hint { color: $text-muted; margin-top: 1; }
    """

    def __init__(self, prompt: str, default: str = "") -> None:
        super().__init__()
        self.prompt_text = prompt
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.prompt_text, classes="prompt")
            yield Input(value=self.default, placeholder="输入后回车")
            yield Static("回车确认 · Esc 取消", classes="hint")

    def on_mount(self) -> None:
        inp = self.query_one(Input)
        inp.focus()
        inp.cursor_position = len(self.default)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.dismiss(text or None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ResultItem(ListItem):
    """一条可点击的结果项。"""

    def __init__(self, label: str, data: dict) -> None:
        super().__init__()
        self.data = data
        self.set_label(label)

    def set_label(self, label: str) -> None:
        self.label_text = label

    def compose(self) -> ComposeResult:
        yield Static(self.label_text)


class GHReleaseApp(App):
    """主应用：菜单 + 各功能 Screen。"""

    CSS = """
    Screen { background: $surface; }
    #status { height: 3; padding: 0 2; color: $text-muted; }
    #status .on { color: $success; }
    #notice { height: auto; max-height: 3; padding: 0 2; color: $warning; }
    ListView { height: 1fr; border: round $accent; margin: 1 2; }
    .title { padding: 1 2; color: $accent; text-style: bold; }
    #progress { height: 1; padding: 0 2; color: $accent; }
    Markdown { margin: 1 2; }
    .back-btn { height: 1; margin: 0 2; width: auto; }
    """

    BINDINGS = [
        Binding("q", "quit", "退出", show=True),
        Binding("escape", "back", "返回", show=True),
        Binding("d", "back", "返回", show=False),
    ]

    def __init__(self, token: str, token_source: str) -> None:
        super().__init__()
        self.token = token
        self.token_source = token_source
        self.store = fav.load()
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="notice")
        yield Static(id="status")
        with Vertical(id="menu"):
            yield Static("GitHub Release 交互式下载助手  ·  搜索 · 收藏 · 一键下载", classes="title")
            yield ListView(
                *[ResultItem(f"{num}.  {label}  —  {desc}", {"num": num})
                  for num, label, desc in MENU],
                id="main-list",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "GH Release Helper"
        self.sub_title = f"版本 {version.read_current()}"
        self._refresh_status()

    def _refresh_status(self) -> None:
        token_txt = f"[green]已配置 · {self.token_source}[/]" if self.token else "[yellow]未配置 · 按 5 配一个[/]"
        count = fav.count(self.store)
        try:
            self.query_one("#status", Static).update(
                f"收藏 {count} 个     Token {token_txt}     证书 {syscert.describe()}     下载目录 {dl.resolve_download_dir()}"
            )
        except Exception:  # noqa: BLE001  弹窗覆盖时主界面不在 DOM，返回菜单时 _show_menu 会再刷新
            pass

    def set_notice(self, text: str = "") -> None:
        try:
            self.query_one("#notice", Static).update(text)
        except Exception:  # noqa: BLE001  弹窗切换瞬间 widget 可能暂不可达，提示丢失无妨
            pass

    # ---------- 主菜单 ----------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if not isinstance(item, ResultItem):
            return
        num = item.data.get("num")
        actions = {
            "1": self.action_search,
            "2": self.action_favorites,
            "3": self.action_add_favorite,
            "4": self.action_check_updates,
            "5": self.action_token,
            "0": self.action_quit_app,
        }
        if num in actions:
            actions[num]()

    def action_back(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
        else:
            self._show_menu()

    def action_quit_app(self) -> None:
        fav.save(self.store)
        self.exit()

    def _show_menu(self) -> None:
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self._refresh_status()
        self.set_notice("")

    # ---------- Token ----------
    def action_token(self) -> None:
        def done(token: str | None) -> None:
            if token:
                self.token, self.token_source = token, "本地 .github_token"
                self.set_notice("Token 已保存，本次运行立即生效。")
            self._refresh_status()

        self.push_screen(InputDialog("粘贴 GitHub Token（留空取消）："), done)

    # ---------- 通用工具 ----------
    # 用 push_screen + Future 回调实现“等待弹窗结果”，不依赖 Textual worker 上下文，
    # 因此可从事件处理器、后台任务、测试驱动等任意位置调用。
    async def ask_input(self, prompt: str, default: str = "") -> str | None:
        future: asyncio.Future = asyncio.get_running_loop().create_future()

        def done(value: str | None) -> None:
            if not future.done():
                future.set_result(value)

        self.push_screen(InputDialog(prompt, default), done)
        return await future

    async def confirm(self, question: str, default: bool = True) -> bool:
        future: asyncio.Future = asyncio.get_running_loop().create_future()

        def done(value: bool) -> None:
            if not future.done():
                future.set_result(value)

        self.push_screen(ConfirmDialog(question, default), done)
        return bool(await future)

    async def choose_mode(self, name: str) -> str | None:
        future: asyncio.Future = asyncio.get_running_loop().create_future()

        def done(value: str | None) -> None:
            if not future.done():
                future.set_result(value)

        self.push_screen(ModeDialog(name), done)
        return await future

    # ---------- 搜索仓库 ----------
    def action_search(self) -> None:
        self.push_screen(SearchScreen(self))

    # ---------- 收藏 ----------
    def action_favorites(self) -> None:
        self.push_screen(FavoritesScreen(self))

    def action_add_favorite(self) -> None:
        self.push_screen(AddFavoriteScreen(self))

    # ---------- 检查更新 ----------
    def action_check_updates(self) -> None:
        self.push_screen(CheckUpdatesScreen(self))

    # ---------- 更新说明 ----------
    def show_release_notes(self, repo: str, release: dict) -> None:
        body = str(release.get("body") or "") or "（该仓库的 release 没有填写更新说明。）"
        self.push_screen(NotesScreen(body, f"{repo} · {release.get('tag_name', '')}"))

    # ---------- 下载（复用业务模块） ----------
    async def run_download(self, repo: str, asset: dict) -> None:
        url = str(asset.get("browser_download_url") or "")
        name = str(asset.get("name") or "release-asset")
        if not url:
            self.set_notice("这个资产没有可用的下载地址。")
            return
        mode = await self.choose_mode(name)
        if mode is None:
            return
        if mode == "3":
            self.push_screen(LinkScreen(self, url, name))
            return
        if mode == "2":
            dl.open_in_browser(url)
            self.set_notice("已交给浏览器下载。")
            return
        # 终端下载交给 DownloadScreen：它展示测速结果、线路选择与实时进度
        self.push_screen(DownloadScreen(self, url, name))


class SearchScreen(BaseScreen):
    """搜索仓库：输入关键词 → 列表 → 选中看资产。"""

    DEFAULT_CSS = """
    SearchScreen { background: $surface; }
    SearchScreen > Vertical { height: 100%; }
    SearchScreen .bar { height: 3; padding: 0 2; }
    SearchScreen ListView { height: 1fr; }
    """

    def __init__(self, app: GHReleaseApp) -> None:
        super().__init__()
        self.host_app = app
        self.items: list[dict] = []
        self.keyword = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static("输入关键词后回车搜索；↑/↓ 选择，回车查看 Release", classes="bar")
            yield Input(placeholder="仓库名关键词", id="kw")
            yield ListView(id="results")

    def on_mount(self) -> None:
        self.query_one("#kw", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.keyword = event.value.strip()
        if self.keyword:
            self.do_search(self.keyword)

    @work(thread=True)
    def do_search(self, keyword: str) -> None:
        try:
            items, total = gh.search_repos(keyword, self.host_app.token, limit=10)
        except gh.GitHubError as exc:
            self.app.call_from_thread(self.set_error, str(exc))
            return
        self.app.call_from_thread(self.show_results, items, total)

    def set_error(self, message: str) -> None:
        self.query_one(".bar", Static).update(f"搜索失败：{message}")

    def show_results(self, items: list[dict], total: int) -> None:
        self.items = items
        view = self.query_one("#results", ListView)
        view.clear()
        for i, item in enumerate(items, 1):
            label = f"{i}. {item.get('full_name', '?')}  ⭐{item.get('stargazers_count', 0)}  {item.get('language') or '-'}"
            view.append(ResultItem(label, {"index": i - 1}))
        self.query_one(".bar", Static).update(f'搜索 "{self.keyword}" 命中 {total} 个，显示前 {len(items)} 个')
        if items:
            view.index = 0  # 自动选中第一条
            view.focus()    # 焦点交给列表，用户可直接按方向键/回车

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem) or not self.items:
            return
        chosen = self.items[event.item.data["index"]]
        self.app.push_screen(RepoScreen(self.host_app, chosen))


class RepoScreen(BaseScreen):
    """单个仓库：看更新说明 / 看资产下载 / 去网页。"""

    def __init__(self, host_app: GHReleaseApp, repo_meta: dict) -> None:
        super().__init__()
        self.host_app = host_app
        self.repo = repo_meta.get("full_name", "")
        self.meta = repo_meta
        self.release: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static(f"{self.repo}  ·  正在获取最新 Release ...", classes="bar")
            yield ListView(id="actions")

    def on_mount(self) -> None:
        self.load_release()

    @work(thread=True)
    def load_release(self) -> None:
        try:
            release = gh.get_latest_release_or_explain(self.repo, self.host_app.token)
        except gh.GitHubError as exc:
            self.app.call_from_thread(self.set_error, str(exc))
            return
        self.app.call_from_thread(self.show_actions, release)

    def set_error(self, message: str) -> None:
        self.query_one(".bar", Static).update(f"获取失败：{message}")

    def show_actions(self, release: dict) -> None:
        self.release = release
        tag = release.get("tag_name") or "(无 tag)"
        self.query_one(".bar", Static).update(f"{self.repo}  ·  {tag}  ·  按类型筛选下载")
        view = self.query_one("#actions", ListView)
        view.clear()
        assets = gh.release_assets(release)
        view.append(ResultItem("查看更新说明", {"act": "notes"}))
        view.append(ResultItem("打开 Release 发布页", {"act": "web"}))
        groups = type_groups(assets)
        if not groups:
            view.append(ResultItem("（该 Release 没有可下载资产）", {"act": "none"}))
        else:
            for ext, items in groups:
                label = (ext.upper() if ext != "无" else "无扩展名")
                total = sum(int(a.get("size", 0) or 0) for a in items)
                view.append(ResultItem(f"{label}  ·  {len(items)} 个文件  ·  {ui.human_size(total)}",
                                       {"act": "type", "ext": ext, "items": items}))
        view.index = 0
        view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem):
            return
        data = event.item.data
        act = data.get("act")
        if act == "notes" and self.release:
            self.host_app.show_release_notes(self.repo, self.release)
        elif act == "web" and self.release:
            dl.open_in_browser(str(self.release.get("html_url") or f"https://github.com/{self.repo}"))
        elif act == "type":
            self.app.push_screen(AssetScreen(self.host_app, self.repo,
                                             data["ext"], data["items"]))


class AssetScreen(BaseScreen):
    """某类型下的资产列表：点选具体文件后进入下载方式选择。"""

    def __init__(self, host_app: GHReleaseApp, repo: str, ext: str, assets: list[dict]) -> None:
        super().__init__()
        self.host_app = host_app
        self.repo = repo
        self.ext = ext
        self.assets = assets

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            label = self.ext.upper() if self.ext != "无" else "无扩展名"
            yield Static(f"{self.repo}  ·  {label}  ·  {len(self.assets)} 个文件", classes="bar")
            yield ListView(id="assets")

    def on_mount(self) -> None:
        view = self.query_one("#assets", ListView)
        for asset in self.assets:
            size = ui.human_size(int(asset.get("size", 0) or 0))
            view.append(ResultItem(f"{asset.get('name', '?')}  ·  {size}", {"asset": asset}))
        if self.assets:
            view.index = 0
            view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem):
            return
        asyncio.create_task(self.host_app.run_download(self.repo, event.item.data["asset"]))


class DownloadScreen(BaseScreen):
    """终端下载页：并发测速 → 展示线路评分 → 实时进度条 → 完成提示。

    进度来自 downloader.progress_hook（TUI 注入），不再用会被屏幕缓冲区吞掉的 print。
    """

    DEFAULT_CSS = """
    DownloadScreen { background: $surface; }
    DownloadScreen > Vertical {
        width: 90%; height: auto; max-height: 90%; border: round $accent;
        padding: 1 2; background: $surface;
    }
    DownloadScreen .state { width: 100%; margin-bottom: 1; }
    DownloadScreen .lines { color: $text-muted; height: auto; max-height: 8; }
    DownloadScreen ProgressBar { width: 100%; margin: 1 0; }
    DownloadScreen .done { color: $success; }
    DownloadScreen .err { color: $error; }
    """

    def __init__(self, host_app: GHReleaseApp, url: str, name: str) -> None:
        super().__init__()
        self.host_app = host_app
        self.url = url
        self.asset_name = name
        self._prev_hook = None
        self._my_hook = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static(f"下载 {self.asset_name}", classes="state")
            yield Static("正在并发测速所有线路 ...", id="state", classes="state")
            yield Static("", id="lines", classes="lines")
            yield ProgressBar(total=100, id="bar", show_eta=True)
            yield Static("", id="result", classes="state")

    def on_mount(self) -> None:
        self.do_download()

    def on_unmount(self) -> None:
        # 页面被关闭时兜底还原自己注入的 hook，避免中途 Esc 后全局残留
        if getattr(dl, "progress_hook", None) is self._my_hook:
            dl.progress_hook = self._prev_hook

    def _set_state(self, text: str, cls: str = "state") -> None:
        try:
            self.query_one("#state", Static).update(text)
        except Exception:  # noqa: BLE001
            pass

    @work(thread=True)
    def do_download(self) -> None:
        # 1) 测速（这正是原 CLI 的 7 线路并发择优，没被删）
        try:
            line, results = dl.choose_line(self.url, dl.AUTO_ROUTE)
        except dl.DownloadError as exc:
            self.app.call_from_thread(self._set_state, f"线路选择失败：{exc}", "err")
            return

        def fmt(item: dict) -> str:
            mark = "✓" if item is line else " "
            speed = ui.human_size(float(item.get("speed", 0) or 0)) + "/s"
            label = item.get("label", item.get("id", "?"))
            return f"  {mark} {label}  {speed}" if item.get("ok") else f"    {label}  不通"

        lines_text = "\n".join(fmt(item) for item in results)
        self.app.call_from_thread(self.query_one("#lines", Static).update, lines_text)
        self.app.call_from_thread(self._set_state, f"已选线路：{line.get('label', line.get('id'))}  ·  测速完成，开始下载")

        # 2) 注入进度回调，下载时实时更新进度条（线程安全）
        def hook(done: int, total: int, rate: float) -> None:
            self.app.call_from_thread(self._on_progress, done, total, rate)

        self._my_hook = hook
        self._prev_hook = dl.progress_hook
        dl.progress_hook = hook
        try:
            target = dl.download_dir()
            saved, how = dl.fetch(line["url"], self.asset_name, target)
        except dl.DownloadError as exc:
            self.app.call_from_thread(self._set_state, f"下载失败：{exc}", "err")
        else:
            self.app.call_from_thread(self._after_saved, saved, how)
        finally:
            if dl.progress_hook is hook:
                dl.progress_hook = self._prev_hook

    def _after_saved(self, saved: Path, how: str) -> None:
        saved = Path(saved)
        self._set_state(f"下载完成：{saved}（{how}）", "done")
        self.host_app.set_notice(f"下载完成：{saved}")
        asyncio.create_task(self.handle_post_download(saved))

    async def handle_post_download(self, saved: Path) -> None:
        """下载成功后：安装包询问是否立即运行；zip 解压并询问是否删包。"""
        kind = pd.kind_of(saved)
        if kind == "launch":
            if await self.host_app.confirm(f"下载完成：{saved.name}\n是否立即运行安装包？", default=True):
                try:
                    pd.launch(saved)
                    self._set_state("已启动安装包，请按安装向导操作。", "done")
                except OSError as exc:
                    self._set_state(f"启动失败：{exc}", "err")
            return
        if kind == "archive":
            try:
                target = pd.extract(saved)
            except (OSError, zipfile.BadZipFile) as exc:
                self._set_state(f"解压失败：{exc}", "err")
                return
            self._set_state(f"已解压到：{target}", "done")
            if await self.host_app.confirm("是否删除已解压的压缩包？", default=False):
                try:
                    pd.delete(saved)
                    self._set_state(f"已解压到：{target} · 压缩包已删除", "done")
                except OSError as exc:
                    self._set_state(f"删除压缩包失败：{exc}", "err")

    def _on_progress(self, done: int, total: int, rate: float) -> None:
        try:
            bar = self.query_one("#bar", ProgressBar)
            if total > 0:
                bar.update(total=total, progress=done)
            self.query_one("#result", Static).update(
                f"{ui.human_size(done)} / {ui.human_size(total)}  ·  {ui.human_size(rate)}/s"
            )
        except Exception:  # noqa: BLE001  页面可能已被关闭
            pass


class LinkScreen(BaseScreen):
    """只打印下载链接：输入框可框选，按钮一键复制到剪贴板。"""

    DEFAULT_CSS = """
    LinkScreen { background: $surface; }
    LinkScreen > Vertical {
        width: 90%; height: auto; max-height: 90%; border: round $accent;
        padding: 1 2; background: $surface;
    }
    LinkScreen .bar { width: 100%; margin-bottom: 1; }
    LinkScreen Input { width: 100%; }
    LinkScreen .hint { color: $text-muted; margin-top: 1; }
    """

    def __init__(self, host_app: GHReleaseApp, url: str, name: str) -> None:
        super().__init__()
        self.host_app = host_app
        self.url = url
        self.asset_name = name

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static(f"下载链接 · {self.asset_name}", classes="bar")
            yield Input(value=self.url, id="link-url", placeholder="下载链接")
            with Horizontal():
                yield Button("复制到剪贴板", variant="primary", id="copy")
            yield Static("可框选上方链接按 Ctrl+C，或点按钮直接复制。", id="feedback", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#link-url", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "copy":
            feedback = self.query_one("#feedback", Static)
            try:
                self.app.copy_to_clipboard(self.url)
                feedback.update("已复制到剪贴板。")
            except Exception as exc:  # noqa: BLE001  剪贴板不可用时给出可手动复制的提示
                feedback.update(f"复制失败（{exc}），请框选上方链接按 Ctrl+C。")


class FavoritesScreen(BaseScreen):
    """收藏列表：回车打开 / 按钮删除。"""

    def __init__(self, host_app: GHReleaseApp) -> None:
        super().__init__()
        self.host_app = host_app
        self.entries: list[tuple[str, dict]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static("我的收藏 · 回车打开 · 下方按钮删除", classes="bar")
            yield ListView(id="favs")
            yield Button("删除选中收藏", variant="error", id="del-fav", classes="back-btn")

    def on_mount(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        self.entries = fav.entries(self.host_app.store)
        view = self.query_one("#favs", ListView)
        view.clear()
        if not self.entries:
            view.append(ResultItem("收藏夹是空的，先用菜单 3 添加。", {"act": "none"}))
            return
        for i, (key, meta) in enumerate(self.entries, 1):
            view.append(ResultItem(f"{i}. {key}  ·  {meta.get('last_tag') or '未获取'}",
                                   {"act": "open", "index": i - 1}))
        view.index = 0
        view.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        super().on_button_pressed(event)
        if event.button.id == "del-fav":
            asyncio.create_task(self.delete_selected())

    async def delete_selected(self) -> None:
        view = self.query_one("#favs", ListView)
        index = view.index
        if index is None or index >= len(self.entries):
            self.host_app.set_notice("请先选中一个收藏。")
            return
        key = self.entries[index][0]
        if not await self.host_app.confirm(f"确定删除收藏「{key}」吗？", default=False):
            return
        removed = fav.remove(self.host_app.store, key)
        fav.save(self.host_app.store)
        self.host_app._refresh_status()
        self.host_app.set_notice(f"已删除收藏：{removed}" if removed else "删除失败")
        self.refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem):
            return
        data = event.item.data
        if data.get("act") == "open":
            key = self.entries[data["index"]][0]
            self.app.push_screen(RepoScreen(self.host_app, {"full_name": key}))


class AddFavoriteScreen(BaseScreen):
    """添加收藏：搜索后选中即收藏。"""

    def __init__(self, host_app: GHReleaseApp) -> None:
        super().__init__()
        self.host_app = host_app
        self.items: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static("输入关键词搜索，选中即收藏", classes="bar")
            yield Input(placeholder="仓库名关键词", id="kw")
            yield ListView(id="results")

    def on_mount(self) -> None:
        self.query_one("#kw", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        kw = event.value.strip()
        if kw:
            self.do_search(kw)

    @work(thread=True)
    def do_search(self, keyword: str) -> None:
        try:
            items, total = gh.search_repos(keyword, self.host_app.token, limit=10)
        except gh.GitHubError as exc:
            self.app.call_from_thread(self.set_error, str(exc))
            return
        self.app.call_from_thread(self.show_results, items)

    def set_error(self, message: str) -> None:
        self.query_one(".bar", Static).update(f"搜索失败：{message}")

    def show_results(self, items: list[dict]) -> None:
        self.items = items
        view = self.query_one("#results", ListView)
        view.clear()
        for i, item in enumerate(items, 1):
            view.append(ResultItem(f"{i}. {item.get('full_name', '?')}  ⭐{item.get('stargazers_count', 0)}",
                                   {"index": i - 1}))
        if items:
            view.index = 0
            view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem) or not self.items:
            return
        chosen = self.items[event.item.data["index"]]
        key, action = fav.add(
            self.host_app.store, chosen.get("full_name", ""),
            stars=int(chosen.get("stargazers_count", 0) or 0),
            description=chosen.get("description") or "", language=chosen.get("language") or "",
        )
        fav.save(self.host_app.store)
        self.host_app.set_notice(f"已{action}收藏：{key}")
        self.host_app._refresh_status()
        self.app.pop_screen()


class CheckUpdatesScreen(BaseScreen):
    """检查更新：本程序 + 收藏仓库。"""

    def __init__(self, host_app: GHReleaseApp) -> None:
        super().__init__()
        self.host_app = host_app
        self.self_release: dict | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static("正在检查本程序与收藏仓库的更新 ...", classes="bar")
            with VerticalScroll(id="log"):
                yield Static("", id="lines")

    def on_mount(self) -> None:
        asyncio.create_task(self.start_check())

    async def start_check(self) -> None:
        """裁剪规则与 CLI 完全一致：该拒的直接拒、该问的弹窗问，不问就只查前 30 个。

        确认必须发生在主线程，所以这里先把目标算好，再把结果交给后台线程去跑请求。
        """
        entries = fav.entries(self.host_app.store)
        targets, action, notice = fc.plan_favorite_check(entries, self.host_app.token)
        if action == "confirm" and not await self.host_app.confirm(f"{notice}？", default=False):
            targets = targets[:fc.CONFIRM_ABOVE]
        self.do_check(entries, targets, action, notice)

    @work(thread=True)
    def do_check(self, entries: list, targets: list, action: str, notice: str) -> None:
        lines: list[str] = []
        # worker 只收集结果：worker 线程里改 store / 写盘会和删收藏、退出保存抢同一份文件
        updates: list[tuple[str, str, list[dict]]] = []

        # 本程序：只检查版本，弹窗下载放到主线程 show_lines 里做
        try:
            has, release = su.check_self_update(self.host_app.token)
            if has:
                self.self_release = release
                lines.append(f"[bold yellow]本程序有新版本：{version.read_current()} → "
                             f"{version.normalize(release.get('tag_name', ''))}[/]")
                lines.append("检查完成后会询问是否下载安装包。")
            else:
                lines.append("[green]本程序已是最新版本。[/]")
        except Exception as exc:  # noqa: BLE001  自身检查不能挡住收藏检查
            lines.append(f"[yellow]本程序检查失败：{exc}[/]")

        # 收藏仓库：目标由 start_check 按 flow_common 的规则算好，这里只负责跑
        if not entries:
            lines.append("收藏夹是空的，跳过收藏检查。")
        elif action == "refuse":
            lines.append(notice)
        else:
            for _index, key, meta, release, exc, stop in fc.iter_favorite_repos(targets, self.host_app.token):
                if stop == "insufficient-quota":
                    lines.append("API 剩余配额不足 3 次，已提前停止。配置 Token 或稍后再试。")
                    break
                last = str(meta.get("last_tag") or "-")
                if exc is not None:
                    if stop == "rate-limited":
                        lines.append("已触发限流，停止检查。配置 Token 或稍后再试。")
                        break
                    lines.append(f"{key}：查询失败（{' '.join(str(exc).split())[:40]}）")
                    continue
                tag = str(release.get("tag_name") or "-")
                state = "↑ 新版本" if last != "-" and last != tag else "— 无变化"
                lines.append(f"{key}：{last} → {tag}  {state}")
                updates.append((key, tag, [
                    {"name": a.get("name", ""), "size": int(a.get("size", 0) or 0),
                     "url": a.get("browser_download_url", "")}
                    for a in gh.release_assets(release)
                ]))
            # save 交给主线程：worker 里写盘会和删收藏、退出保存互相覆盖

        self.app.call_from_thread(self.show_lines, lines, updates)

    def show_lines(self, lines: list[str], updates: list[tuple[str, str, list[dict]]]) -> None:
        self.query_one(".bar", Static).update("检查结果：")
        self.query_one("#lines", Static).update("\n".join(lines))
        # 回到主线程再改 store 并整批写盘，状态行也随之刷新
        for key, tag, assets in updates:
            fav.update_release(self.host_app.store, key, tag, assets)
        fav.save(self.host_app.store)
        self.host_app._refresh_status()
        if self.self_release:
            asyncio.create_task(self.offer_self_update())

    async def offer_self_update(self) -> None:
        release = self.self_release
        self.self_release = None
        # 与 CLI 同一选型：优先 Setup.exe，没有 exe 用 zip 兜底（解压由下载后处理负责）
        picked = su.pick_installer(release)
        if not picked:
            return
        setup, _kind = picked
        if await self.host_app.confirm("发现本程序新版本，是否下载安装包？", default=True):
            self.app.set_notice("正在下载新版本安装包 ...")
            await self.host_app.run_download("self", setup)


class NotesScreen(BaseScreen):
    """全屏查看更新说明（Textual Markdown 渲染，方向键滚动）。"""

    def __init__(self, body: str, title: str) -> None:
        super().__init__()
        self.body = body
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield from super().compose()
            yield Static(self.title_text + "   （Esc 返回）", classes="bar")
            with VerticalScroll():
                yield Markdown(self.body)


def main(token: str, token_source: str) -> None:
    """启动 TUI（供 main.py 在交互终端下调用）。"""
    GHReleaseApp(token, token_source).run()


if __name__ == "__main__":
    import bootstrap
    bootstrap.ensure_runtime()
    t, src = fc.pick_token("")
    main(t, src)
