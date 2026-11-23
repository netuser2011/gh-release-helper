# GitHub Release 交互式下载助手

一个跑在终端里的 GitHub Release 下载工具：不知道作者是谁也能用——只输入仓库名就能搜出候选仓库，选中后按后缀分组筛选资产，一键下载。全屏 TUI 交互、并发分段与断点续传、多线路测速择优、下载完自动运行安装包或解压、更新说明全屏查看、程序自身也能一键升级，也能自动信任系统证书，开着代理工具照样用。

全部走 GitHub 官方 REST API，不解析网页 HTML。

[🌐 打开官网](https://netuser2011.github.io/gh-release-helper/)

配套文档：[更新日志](CHANGELOG.md) · [参与贡献](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [发布步骤](PUBLISHING.md)

```
GitHub Release 交互式下载助手  ·  搜索 · 收藏 · 一键下载
收藏 3 个     Token 已配置 · 本地 .github_token     证书 已信任系统证书     下载目录 C:\Users\me\Downloads

  ← 返回上一级
  1.  搜索仓库  —  按名字找项目，选一个看 Release 资产并下载
  2.  查看收藏  —  调出已存仓库的下载链接
  3.  添加收藏  —  把常用仓库存进收藏夹
  4.  检查更新  —  检查本程序 + 批量检查收藏仓库
  5.  配置 Token —  解除限流（存本地 .github_token）
  0.  退出      —  保存收藏并退出
```

## 功能特性

- **不知道作者也能找**：只输入仓库名关键词，按星标排序列出候选（作者/名字、星标、语言），选中进入仓库页后点「查看更新说明」即可全屏查看最新 Release 的 Markdown 正文，方向键滚动、ESC 返回，不跳浏览器。
- **收藏夹持久化**：以 `作者名/仓库名` 为键写入 `favorites.json`，附带星标、简介与上次看到的资产清单，重启后仍在；可删除，二次确认后列表与计数同步更新。
- **批量检查更新**：菜单选「检查更新」，先看本程序自己有没有新版本，再一次遍历全部收藏仓库的最新 Release，对比上次 tag 与最新版本，展示更新摘要；内置限流保护（无 Token 最多 40 个、超过 30 个先问一句、403/429 自动停止），全屏界面与文本菜单走同一套规则。
- **程序自更新**：发现新版本后可以直接下载安装包——优先 `Setup.exe`，没有就退回便携 zip。文本菜单里确认后走 `/VERYSILENT` 静默安装并写回 `version.txt`；全屏界面走「下载后处理」，下载完问你一句再启动安装向导。每一步都要你确认，程序不会背着你替换自己。
- **三种下载方式，各做一件事**：终端下载到本地、唤起系统默认浏览器、只打印下载链接。全屏页面点按钮即可，不用输 1/2/3。
- **下载后自动处理**：exe/msi 等安装包下载完弹窗询问是否直接运行；zip 下载完自动解压到同名文件夹并询问是否删除压缩包。
- **并发分段**：文件 ≥ 512 KB 且服务器支持 `Range` 时自动切成多段，用 asyncio 并发下载（默认 8 路，`GHR_THREADS` 可调 1-16），完成后按总字节数核对；并发被镜像/代理限制时自动回退单流。
- **断点续传**：网络中断或按 Ctrl+C 会保留 `.part` 和进度记录，下次重跑只补未完成的段；文件变化（ETag / 长度不符）则自动从头下载，不会串味。
- **多线路测速择优**：内置 1 条直连 + 6 个公共镜像的 HTTPS 白名单，自动并发探测各线路吞吐（排除首字节延迟，避免误判），挑最快的一条并在下载页展示线路评分；全都不通时逐条列出原因。镜像不接受临时输入，防止文件被第三方替换。
- **按类型筛选**：Release 资产先按 ZIP / EXE / MSI / TAR / APK 等后缀分组，目录里只列类型与文件数，选一种后再列该类型下的具体文件。
- **全屏界面 + 可点击返回**：所有页面都有「← 返回上一级」按钮，ESC 也能返回；每个页面顶部有状态行，底部有键位提示。
- **两套界面同一套键位**：默认是 Textual 全屏 TUI；`GHR_NO_TUI`、管道输出或 CI 环境下自动降级成 rich 文本菜单，编号含义完全一致（`1-4` 业务流程、`5` 配置 Token、`0` 退出），看教程不会对错键。
- **没资产也有出路**：某个 Release 没上传资产时，会列出 Release 发布页、GitHub 主页与作者官网供跳转；搜索选中仓库后也能先去网页看看再决定要不要下载。
- **代理工具免折腾**：启动时通过 `truststore` 直接信任操作系统证书存储（含 Watt Toolkit / SteamTools 等代理工具装的根证书），无需手动导出 PEM 或退出代理。已设置 `REQUESTS_CA_BUNDLE` 时不覆盖，注入失败则静默降级。代理工具爱往 `NO_PROXY` 里塞 `[::1]` 这类 IPv6 字面量，httpx 会因此报 `InvalidURL` 让下载全线失败——程序在构造下载客户端时临时剔除这类条目，构造完立刻还原环境变量，你不用改系统设置。
- **下载目录可选**：每次下载前可以选默认目录、仅本次换目录、换目录并永久记住，也可以一键恢复系统默认下载目录。
- **只复制链接**：也可以只打印下载链接，粘进浏览器或你惯用的任何下载工具都行。
- **一键解除限流**：菜单按 `5` 就跳到 GitHub 的 Token 创建页（链接已带 `public_repo` 权限参数），
  粘贴回来只写本地 `.github_token`；Token 不进源码、不进日志，保存后也不会再打印一遍。
- **终端友好**：Textual 全屏 TUI（方向键/鼠标 + 按钮操作），命令行模式仍用 rich 渲染表格与进度条（中英文、emoji 混排不错位），`NO_COLOR` 或管道输出时自动降级为纯文本。
- **异常明确**：网络不通、超时、SSL 被代理拦截、仓库不存在、没有 release、API 限流，分别给出可读提示而不是裸 traceback。
- **报错不会消失**：早期失败（Python 版本 / 缺依赖）写 `crash.log` 并等你按键；菜单里的错误会留在重画后的菜单顶部；未预料的崩溃打印完整 traceback 后落盘。
- **上手无门槛**：所有仓库名、作者名、文件类型、保存位置都在终端里选编号或输入，不需要记任何命令行参数。

## 环境要求

- **安装版 / 便携版**：无需安装 Python，直接运行即可
- **从源码运行**：Python 3.10 及以上，依赖 `requests` / `httpx` / `textual` / `truststore`，不用任何 GUI 框架

## 安装

### 方式一：安装版（推荐，Windows）

无需安装 Python，下载后双击运行安装向导即可。

| 文件 | 说明 |
| --- | --- |
| [GHDownloader-Windows-V1.3.1-Setup.exe](https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1-Setup.exe) | 安装版，自动创建桌面/开始菜单快捷方式，支持从「已安装的应用」卸载 |
| [GHDownloader-Windows-V1.3.1.zip](https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1.zip) | 便携版，解压后直接运行 `GH Downloader.exe`，无需安装 |

命令行下载：

```bash
# 安装版
wget "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1-Setup.exe"

# 便携版
wget -O ghdownloader.zip "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1.zip"
```

> 便携版解压后，`GH Downloader.exe` 与 `_internal/` 文件夹需保持在同一目录，不要单独移动 exe。

### 方式二：从源码运行（开发者 / 非 Windows）

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
```

需要 Python 3.10+，依赖 `requests` / `httpx` / `textual` / `truststore`，见 `requirements.txt`。

## 使用

### 安装版 / 便携版

双击 `GH Downloader.exe`（或快捷方式）即可进入交互菜单，与源码运行体验完全一致。无需安装 Python。

### 从源码运行

不想碰命令行的话，直接双击 `Run.bat` 即可进入菜单。它会先找到本机 Python（优先 `py -3`，其次 `python`），
发现缺 `requests` 时按 `requirements.txt` 自动装一次，之后任何报错都留在窗口里等你按键。

### 进入交互界面

```bash
python main.py
```

TUI 检测到你真的在对着终端（而不是管道 / CI）时直接给全屏界面；否则是 rich 文本菜单。想看文本菜单的效果可以设 `GHR_NO_TUI=1`。

### 命令行模式：直接打印下载链接

```bash
python cli.py files-community/Files
python cli.py cli/cli --ext exe msi zip      # 按扩展名筛选
python cli.py microsoft/vscode --no-latest   # 列出最近 5 个 release
```

### 跳过菜单，一步到位

```bash
python main.py files-community/Files   # 已知仓库，直接进资产页
python main.py files                   # 只知道名字，先搜索
```

## 下载说明

选完文件后，程序会问「下载到哪里」，四种选择都够用：

| 选项 | 作用 |
| --- | --- |
| 1 当前默认目录 | 直接用现有默认位置，路径会显示在选项里 |
| 2 换一个位置（仅本次） | 这次下到别处，不改变默认设置 |
| 3 换一个位置并记住 | 下完并把新目录写进 `config.json`，以后默认就是它 |
| 4 恢复系统默认下载目录 | 只有设置过默认目录时出现，一键撤销 |

- 路径输入支持 `~`（家目录）和相对路径（相对当前工作目录解析），不存在的目录会自动创建；创建失败则回退到默认目录并说明原因，不会中断下载。
- 优先级：环境变量 `GHR_DOWNLOAD_DIR` > `config.json` 里记住的目录 > 系统「下载」目录（`~/Downloads`）。临时改一次可以用环境变量：Windows `set GHR_DOWNLOAD_DIR=D:\Downloads`，PowerShell `$env:GHR_DOWNLOAD_DIR="D:\Downloads"`，Linux/macOS `export GHR_DOWNLOAD_DIR=~/Downloads`。
- 同名文件不会覆盖，自动加 `(1)`、`(2)` 后缀。
- 下载先写 `.part` 临时文件，校验字节数一致后再改名：单流与分段都支持断点续传，中途 Ctrl+C 或断流会**保留**进度，下次重跑接着下；只有链接失效、返回网页、字节数不符这类永久性失败才清掉临时文件，不会留下打不开的残文件。
- 线路可选「自动测速」或指定某条白名单线路；选本地下载时先测速再下载，选浏览器或只打印链接则不测速。
- 资产文件名会做净化，去掉路径分隔符与非法字符，避免恶意文件名造成的路径穿越。
- 不想要本地下载时，也可以只唤起浏览器，或只打印链接粘到别处。

## 环境变量与本地文件

程序不读任何配置文件之外的东西，能改行为的开关都在这里：

| 环境变量 | 作用 |
| --- | --- |
| `GITHUB_TOKEN` | Token 来源之一，优先级低于 `--token`、高于 `.github_token` |
| `GHR_DOWNLOAD_DIR` | 覆盖默认下载目录，优先级高于 `config.json` |
| `GHR_THREADS` | 分段下载并发数，默认 8，取值夹在 1-16，写非数字则回到默认 |
| `GHR_NO_TUI` | 设了它就不进全屏 TUI，走 rich 文本菜单（管道 / CI 自动如此） |
| `NO_COLOR` / `FORCE_COLOR` | 关闭 / 强制颜色，只认非零值；`NO_COLOR=0` 不算开启 |
| `REQUESTS_CA_BUNDLE` | 你手动指定证书时程序不覆盖，truststore 注入会让位 |

| 本地文件 | 内容 | 是否提交 |
| --- | --- | --- |
| `version.txt` | 当前版本号的唯一真相源（`V1.3.1`），源码里不写死版本 | 提交 |
| `favorites.json` | 收藏的仓库、星标、简介、上次看到的 tag 与资产清单 | 忽略 |
| `config.json` | 记住的下载目录 | 忽略 |
| `.github_token` | 本地 Token | 忽略 |
| `crash.log` | 报错与 traceback（不含 Token） | 忽略 |
| `<目标文件>.part` / `.part.meta` | 断点续传的临时数据，下载成功后自动清理 | 忽略 |

`favorites.json` 损坏时程序会把它备份成 `favorites.json.bak` 再重建，不会直接丢掉你的收藏。

## 系统证书与代理工具（自动处理）

如果本机开着 Watt Toolkit / SteamTools 之类的代理工具，它们会给 HTTPS 做中间人并把自签根证书装进 Windows 系统证书存储。默认只认 certifi 的 HTTP 库会因此报 `SSL 证书校验失败`。程序在每次启动时自动处理这件事：

- 通过 `truststore.inject_into_ssl()` 让 `requests` / `httpx` 直接信任**操作系统证书存储**（Windows / macOS / Linux），浏览器信任的站点本工具也信任；
- 不再导出或合并 PEM，也不再写 `~/.gh-release-helper/ca-bundle.pem`；
- 主菜单状态行显示「证书 已信任系统证书（truststore）」，一眼能看到是否生效；
- 若你已手动设置 `REQUESTS_CA_BUNDLE`，则不覆盖你的配置；注入失败时静默跳过，不影响程序使用。

不需要你手动导出证书或退出代理。注意：它信任的是**这台电脑系统里已受信任**的证书，安全性与浏览器一致；系统证书更新后自动生效，无需刷新 bundle。

## 配置 GitHub Token（可选，用于解除限流）

| 状态 | 未认证核心 API | Search API |
| --- | --- | --- |
| 无 Token | 60 次/小时 | 10 次/分钟 |
| 有 Token | 5000 次/小时 | 30 次/分钟 |

四种方式，任选其一（**不要把 Token 写进源码**）：

1. **菜单里按 `5`**（推荐）：程序会打印 Token 创建页地址并问你要不要直接用浏览器打开——
   链接已经带上 `scopes=public_repo`，进到页面点一下 Create 就行。把结果粘回终端，
   只写进本地 `.github_token`（POSIX 下权限收紧为仅当前用户可读写，Windows 由 ACL 决定；
   该文件已在 `.gitignore` 中），屏幕上不会把 Token 再打印一遍。首次启动没有 Token 时
   也会主动问这同一段话。
2. **只要地址，不想开菜单**：`python cli.py --token-url` 打印创建页链接后退出，
   不读也不写任何 Token，适合远程帮别人排障。
3. **环境变量**：`set GITHUB_TOKEN=ghp_xxx`（PowerShell 用 `$env:GITHUB_TOKEN="ghp_xxx"`）。
4. **命令行参数**：`python main.py --token ghp_xxx`。

优先级：`--token` > 环境变量 > `.github_token` 文件。

直接可点的地址（菜单里的 `5` 打开的就是第一条）：

- 经典 Token：<https://github.com/settings/tokens/new?scopes=public_repo&description=gh-release-helper>
- 细粒度 Token：<https://github.com/settings/personal-access-tokens/new>（只给 Public Repositories 的 Read-only 即可）
- 查看 / 撤销已发出的 Token：<https://github.com/settings/tokens>

公共仓库只需要 `public_repo` 这一个范围，不需要额外勾选权限；配好之后本次运行立刻生效，不用重启。

> ⚠️ Token 等同于你的 GitHub 密码。一旦不小心提交到仓库或被他人看到，请立刻在上面的页面撤销（revoke）并重新生成。

## 隐私说明

- 程序只向 `api.github.com` 和 `github.com` 发起请求，不会上传你的任何本地数据，也没有统计或埋点。
- 不会自己联网、也不会自己升级：只有你在菜单里选「检查更新」时才会查一次本程序的最新 Release。
  查到之后每一步都要你确认——下载问一次、运行安装包再问一次；跳过就只是文件躺在下载目录里。
  你从没点过「检查更新」，程序不会有任何自更新动作。
- 收藏夹（`favorites.json`）、下载目录偏好（`config.json`）、Token（`.github_token`）都只存在你自己机器上，且已写进 `.gitignore`，正常提交不会带上它们。
- 只用公开的读取接口，不会对你的仓库做任何写操作。
- 配置 Token 时程序只打开 `https://github.com/settings/tokens/new?...` 这个官方页面，
  链接里不含你的账号信息；你粘贴回来的 Token 只写进 `.github_token`，不会在屏幕上回显，
  也不会进 `crash.log`。
- 不想在这台机器上留 Token 时，删掉 `.github_token` 即可（菜单里按 `5` 会重新问一次），
  或者到 <https://github.com/settings/tokens> 直接撤销。

## 项目结构

```
gh-release-helper/
├── main.py           # 交互入口：TTY 下把界面交给 tui.py，管道/CI/GHR_NO_TUI 走文本菜单；搜索/收藏/检查更新流程
├── tui.py            # Textual 全屏 TUI：搜索/仓库/资产/下载/收藏/更新说明等页面
├── flow_common.py    # 两种入口共用：Token 三级来源、批量检查更新的限流循环（40/30 上限、配额预检、403/429 停批）
├── self_update.py    # 本程序更新：查最新 Release、挑安装包、确认后才下载
├── post_download.py  # 下载后处理：启动安装包、解压 zip、删包
├── cli.py            # 命令行模式：只打印下载链接
├── pager.py          # 命令行下全屏翻页查看 Release 更新说明（↑/↓ 滚动、Q 返回）
├── github_api.py     # GitHub REST API 封装、Token 解析、统一异常
├── downloader.py     # httpx + asyncio 并发分段 + 断点续传、线路测速、目录选择、文件名净化、NO_PROXY 兼容
├── favorites.py      # favorites.json 读写与去重
├── syscert.py        # truststore 信任系统证书，解决代理工具导致的 SSL 错误
├── ui.py             # rich 表格/横幅/进度条、ANSI 颜色、UTF-8 输出、崩溃日志
├── version.py        # 版本号读取与比较
├── bootstrap.py      # 启动前置检查：Python ≥ 3.10、四个依赖（requests/httpx/textual/truststore）、系统证书
├── Run.bat           # 双击启动：探测 Python、缺依赖自动装、出错停窗（纯 ASCII）
├── GHDownloader.spec # PyInstaller 打包配置（onedir，产物 dist/GH Downloader/）
├── setup.iss         # Inno Setup 脚本，产出 Windows 安装版
├── icon.ico          # 应用图标（打包与安装向导共用）
├── requirements.txt
├── version.txt       # 版本号唯一真相源（V1.3.1）
├── .gitignore        # 忽略 favorites.json / config.json / crash.log / .github_token
├── .editorconfig     # 统一 UTF-8 与缩进，避免中文注释被写坏
├── LICENSE           # MIT
├── README.md
├── CHANGELOG.md      # 更新日志（Keep a Changelog 格式）
├── CONTRIBUTING.md   # 代码约定、怎么跑测试、PR 自检清单
├── SECURITY.md       # Token 与下载安全说明、漏洞私密报告方式
├── PUBLISHING.md     # 把这个文件夹变成公开仓库的完整步骤
├── RELEASE_NOTES.md  # 每个版本 Release 正文的源文本
├── docs/index.html   # 官网（GitHub Pages 直接发布这个目录）
├── tests/            # 离线单元测试：不联网、不碰个人文件
│   ├── test_ui.py
│   ├── test_core.py
│   ├── test_tui.py
│   ├── test_error_visible.py
│   ├── test_mirrors_threads.py
│   ├── test_syscert.py
│   ├── test_pager.py
│   ├── test_check_updates.py
│   ├── test_self_update.py
│   ├── test_version.py
│   ├── test_release_notes.py
│   └── __init__.py
└── .github/
    ├── workflows/ci.yml              # 3.10/3.11/3.12/3.13 跑测试 + Windows 冒烟
    ├── PULL_REQUEST_TEMPLATE.md
    └── ISSUE_TEMPLATE/               # 问题反馈 / 功能建议 两个模板
```

运行后会自动生成这几个本地文件，都不需要提交：`favorites.json`、`config.json`、`.github_token`、`crash.log`。

## 开发与测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests        # 272 个用例，全程离线
```

测试不会打 GitHub API（网络用假响应），也不会读写你的 `favorites.json`（落盘指向临时目录）。
改代码前建议先读 `CONTRIBUTING.md` 的代码约定；要发布则按 `PUBLISHING.md` 一步步来。

> 🏫 作者是一名中学生，白天上课，晚上写代码。
> 如果更新慢了，那肯定是在赶作业 😂。欢迎各路大佬提交 Issue 或 PR 一起完善这个项目！
> 觉得好用就点个 Star ⭐ 吧，你的 Star 就是我肝代码的动力！
## 常见问题

**Q：报 `SSL 证书校验失败`？**
本机有代理工具（Watt Toolkit / SteamTools、Charles、Fiddler、企业网关等）对 HTTPS 做中间人。程序启动时通过 `truststore` 让 HTTP 库**自动信任系统证书存储**，正常情况下开着代理也能用，主菜单「证书」一行会显示状态。若仍报错：确认代理工具的根证书已装进系统（而不是只装在浏览器里），或手动设置 `REQUESTS_CA_BUNDLE` 指向它的 `.pem` 文件。关掉代理工具通常也能立刻恢复。

**Q：`该 release 没有任何资产文件`？**
不是 bug。有些项目（例如 VS Code）只发布 tag，安装包放在自己官网；也有项目把资产挂在别的 release 上。程序此时会列出 Release 发布页、GitHub 主页和作者官网供你跳转。也可以试试 `python cli.py owner/repo --no-latest` 看历史 release。

**Q：为什么 `latest` 拿到的不是我想的那个版本？**
GitHub 的 `releases/latest` 会排除草稿（draft）与预发布（prerelease）。若作者只发了预发布，就会 404，此时用 `--no-latest` 查看完整列表。

**Q：搜出来的仓库不相关？**
搜索用了 `in:name` 限定，只匹配仓库名并按星标从高到低排序，因此热门项目一定排在前面。想更精准，直接输入 `owner/repo`。

**Q：终端里颜色是一串 `\033[31m`？**
Windows 7/8 的旧控制台不支持 ANSI。Windows 10 1511+ 会自动启用虚拟终端；若仍在旧环境，程序检测到后会输出纯文本。也可以显式设置 `NO_COLOR=1` 关闭颜色。

**Q：`favorites.json` 要提交吗？**
不要。它是你的个人数据，已写进 `.gitignore`。想分享清单请手动复制内容或另建 `favorites.example.json`。

**Q：能记住我选的下载目录吗？**
能。下载时选 3「换一个位置并记住」即可写进 `config.json`；想撤销就选 4「恢复系统默认下载目录」，或者直接删掉 `config.json` 里的 `download_dir` 一项。

**Q：下载一半网络断了怎么办？**
程序支持断点续传：中断时会保留 `.part` 和进度记录，下次重跑同一个下载只补未完成的段（分段下载）或从断点接着下（单流）。只有链接失效、返回网页、字节数不符这类永久性失败才会清掉临时文件。同名文件也不会覆盖，会自动加 `(1)` 后缀。

**Q：能不能不装第三方库？**
不能。项目依赖 `requests`（GitHub API）、`httpx`（下载与测速）、`textual`（全屏交互界面）、`truststore`（系统证书）四个库，`pip install -r requirements.txt` 一句装齐。

**Q：程序会偷偷自己更新吗？**
不会。自更新只挂在「检查更新」这一步后面：你不点它，程序不会去查自己的新版本。点了也会依次问你「是否下载安装包」和「是否直接运行安装包」，任意一步选否都只是把文件留在下载目录里。文本菜单路径确认后走 `/VERYSILENT` 静默安装，全屏界面则弹出正常的安装向导——两种都会写明装了哪个版本。

**Q：开着 Watt Toolkit 报 `InvalidURL: Invalid port`？**
这是 v1.3.1 修掉的坑：代理工具会把 `[::1]`、`::1` 这类 IPv6 字面量写进 `NO_PROXY`，httpx 0.28 拿它当 URL 解析就直接抛异常，导致测速和下载全线失败。现在程序构造下载客户端时会临时忽略这些无法解析的条目，构造完立刻还原环境变量。升级到 v1.3.1 即可，不需要你改系统代理设置。

**Q：程序显示自己是 `V0.0.0`，或永远提示有更新？**
版本号来自程序目录里的 `version.txt`（唯一真相源，源码里不写死）。这个文件丢了或内容没有数字，就会回退成 `V0.0.0`——任何真实 Release 都比它新，于是每次都提示更新。便携版请确认 `GH Downloader.exe` 和 `_internal/` 留在同一目录；`_internal\version.txt` 里应该是当前版本号。

**Q：更新说明怎么看？**
进入仓库页后点「查看更新说明」即可全屏查看该仓库最新 Release 的更新说明：Markdown 排版，↑/↓ 滚动，ESC 返回，不跳浏览器。菜单选「检查更新」则可批量检查所有收藏仓库的版本变化。

**Q：双击 `main.py` 就闪退，什么报错都看不到？**
先别双击 `.py`：文件关联可能被 IDE 接管（我机器上就指向了 PyCharm），而且窗口关闭时错误信息会一起消失。三种正确打开方式：

1. **双击 `Run.bat`**（推荐新手）——它会把控制台切到 UTF-8、切到脚本所在目录，自己找一个能用的 Python（`py -3` 优先，其次 `python`），`requests` 没装时按 `requirements.txt` 补装一次，再运行 `main.py`；结束时报错信息留在窗口里等你按键。
2. **在终端里运行**，输出不会消失：
   ```
   cd /d 你的路径\gh-release-helper
   python main.py
   ```
3. 崩溃时的完整 traceback 会追加进同目录的 **`crash.log`**，随时可以翻。发 issue 时请把这个文件的内容一起贴出来。

顺带说明：程序启动时会把标准输出强制成 UTF-8。中文 Windows 控制台默认是 GBK（cp936），旧版本在打印 emoji 时会抛 `UnicodeEncodeError` 直接闪退——现在既不会崩，也不会再吞掉字符。

**Q：`Run.bat` 里的提示为什么是英文？**
因为它在 `chcp 65001` 之后被执行，而 cmd.exe 是按字节偏移重读批处理的：一行里只要出现中文，行就可能从中间被切开，后半截会被当成命令执行（本机实测过：`'往' is not recognized as an internal or external command`）。所以这个文件刻意只写 ASCII，中文提示全部交给 Python 打印。改它之前先看 `CONTRIBUTING.md`。

**Q：报错信息会不会一闪而过？**
不会，三层都做了处理：

| 场景 | 现在的行为 |
| --- | --- |
| 启动就跑不起来（Python 太老、`requests` 没装） | `bootstrap.py` 打印中文说明 + 写 `crash.log` + 等按回车；`Run.bat` 还有一道 `pause` |
| 菜单里操作失败（仓库不存在、限流、SSL、下载中断） | 错误作为提示条显示在菜单顶部，**重画菜单后依然在**，直到你做下一个动作才消失；不会为它多按一次回车 |
| 没预料到的崩溃 | 完整 traceback 打印 + 追加进 `crash.log` + 等按回车才退出 |

只有在真正有人对着键盘时才会等按键；管道、脚本喂输入、CI 里会直接返回，不会卡住。

**Q：`crash.log` 里会有什么敏感内容吗？**
只有报错文本、时间戳和 Python 版本，不含 Token（Token 不经过打印路径）。贴出来之前自己扫一眼即可。

## 已知限制

- **`latest` 不等于最后一个 release**：GitHub 的 `releases/latest` 排除草稿与预发布，作者只发预发布时会 404，请用 `python cli.py owner/repo --no-latest`。
- **有些项目不在 Release 里放包**：例如 VS Code 只打 tag，安装包挂在自己官网，资产列表就是空的——程序此时给跳转链接，不会假装下载成功。
- **完整性只按字节数核对**：分段下载收尾会校验总字节数、续传会核对 ETag / Last-Modified，但不校验 SHA-256，也不做代码签名验证。对来源敏感的文件，请自己核对官方校验值。
- **走镜像 = 文件经过第三方服务器**：镜像线路的可用性由公共代理决定，理论上可被替换。默认走直连，镜像白名单固定 6 个，终端不接受临时输入的镜像地址。
- **从安装目录运行时不能自我覆盖**：`GH Downloader.exe` 正在跑，新版本安装包无法覆盖它。程序会先把新版本号写回 `version.txt`，再让你关闭后手动完成安装。
- **限流是真会撞的**：匿名 60 次/小时，一次批量检查收藏就要打好几个请求。超过 40 个收藏会直接拒绝，30 个以上会先问你一句——这不是 bug，是防止你的配额被一次操作清空。

## License

MIT，见 `LICENSE`。你可以自由使用、修改、再分发，保留版权声明即可。
想换成 Apache-2.0 或 GPL-3.0，改 `LICENSE` 与本段，并按 `PUBLISHING.md` 第 2 步的说明替换版权持有人。
