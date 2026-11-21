# 参与贡献

感谢你来改这个小工具。先说清楚规则，可以省掉一轮往返修改。

## 环境准备

```bash
git clone <你的仓库地址>
cd gh-release-helper
python -m pip install -r requirements.txt
python main.py                              # 进入交互菜单
```

- Python 3.10+（`.github/workflows/ci.yml` 会在 3.10 / 3.11 / 3.12 / 3.13 上各跑一遍，
  本地请用 3.10 验一次语法兼容性）。
- 共四个第三方依赖：`requests`（GitHub REST API 读接口）、`httpx`（下载 / 测速，
  asyncio 并发）、`rich`（表格 / 横幅 / 进度条 / Markdown 翻页）、`truststore`
  （把系统已受信任的 CA 注入 ssl，等效浏览器证书基线）。
- 无需任何 GUI 框架。界面统一走 `rich`，不要另外引入 `colorama` / `tqdm` /
  `urwid` 之类的渲染或进度条依赖。

## 跑测试

```bash
python -m unittest discover -s tests          # 全量，约 2.3 秒，214 个用例
python -m unittest tests.test_ui -v           # 只跑一个文件
python -m unittest tests.test_core.DownloadTest.test_bytes_land_in_one_file
```

测试全部离线：网络用假响应（`patch_get` / `patch_stream`），落盘用临时目录。
写新测试时请保持这个约束——CI 里没有 GitHub Token，任何打真实 API 的用例都会因为限流
随机变红。

## 代码约定

- **注释和面向用户的文字一律中文**；注释解释「为什么」，不解释「这行在干什么」。
- 优先用成熟库减少代码：现有的 `requests` / `httpx` / `rich` / `truststore` 都是这个原则的结果。
  新增依赖前先在 issue 里说清价值，总数控制在 5 个以内，并同步 `requirements.txt`、
  README 的「环境要求」和 CI。
- 最低支持 Python 3.10，可以直接用 `Path | None` 这类语法，不必再加
  `from __future__ import annotations`。
- `bootstrap.py` 是个例外：它只用标准库，且不写 `from __future__ import annotations`，
  因为它是「Python 版本太老 / 缺依赖」这条报错的出口，自己必须最先能跑起来。
- 所有可预期的失败都转成带中文说明的异常：`gh.GitHubError` / `dl.DownloadError`。
  界面层负责显示，不要 `print` 一句就 `return None`，也不要裸 `except:` 吞掉错误。
- 写到用户磁盘的东西必须原子化：先 `.tmp` 再 `replace()`，失败时删掉临时文件后重新抛出。
  `favorites.json`、`config.json` 都遵循这一套。
- 不要在源码里放 Token、仓库名、作者名、文件类型。这些都只能来自命令行参数、环境变量、
  本地文件或终端输入。
- 表格与截断走 `ui.pad` / `ui.truncate`，它们按显示宽度算，中英文混排才不会错位。
- **`Run.bat` 只用 ASCII、行尾 CRLF、判断错误码写 `if errorlevel N`**。两条都是踩出来的：
  `chcp 65001` 之后 cmd.exe 按字节偏移重读批处理，一行里只要出现中文，就可能从中间断开，
  后半截被当命令执行；`%errorlevel%` 写在 `(...)` 块里会在解析阶段就展开成旧值，
  运行时判断等于没做。中文提示一律由 Python 打印，`.editorconfig` 已经把这个文件的
  行尾钉成 CRLF。

## 加功能时

- **新菜单项**：改 `main.py` 的 `MENU_ITEMS` 与 `dispatch()`，别忘了 `dispatch` 的返回值
  只有 `exit` / `pause` / `again` 三种语义。主菜单会清屏重画，所以任何需要用户读完的信息
  都要走 `notice`，不能只 `print`。
- **1-4 是四大业务流程，别往里塞别的**：辅助功能放在 `SUPPORT_ITEMS`（现在只有 `0`
  配置 Token），在主循环里单独分支处理，不进 `dispatch()`。这样 README 里承诺的
  「四大菜单项」和实际界面一直对得上。
- **新的下载方式**：改 `do_download()` 里的选项表，具体落盘逻辑放 `downloader.py`，
  界面层不碰 HTTP。
- **新的 API 能力**：接口封装只进 `github_api.py`，统一走 `request_json()`，
  这样限流、SSL、代理这些错误分支不用重复写。

## 提 PR 之前

```bash
python -m py_compile main.py cli.py github_api.py downloader.py favorites.py ui.py bootstrap.py
python -m unittest discover -s tests
```

在中文 Windows 控制台（默认 GBK）里手动跑一遍 `Run.bat`，确认：

1. 界面不闪退，emoji 正常；
2. 故意输错仓库名，报错停在屏幕上而不是被下一次清屏刷掉；
3. 下载目录选项四个分支都能走通。

改动的用户可见行为请写进 `CHANGELOG.md` 的 `[Unreleased]` 段落。

## 提 Issue

用 `.github/ISSUE_TEMPLATE/` 里的模板。Bug 报告请带上：Python 版本、操作系统、
完整命令、`crash.log` 内容（记得先把 Token 相关的行删掉——正常不会包含，但看一眼更安心）。
