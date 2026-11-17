# GitHub Release 交互式下载助手

一个跑在终端里的 GitHub Release 下载工具：不知道作者是谁也能用——只输入仓库名就能搜出候选仓库，按编号选择，收藏常用项目，然后一键在浏览器和本地同时下载资产文件。

全部走 GitHub 官方 REST API，不解析网页 HTML。
仅用于授权测试，禁止非法用途

配套文档：[更新日志](CHANGELOG.md) · [参与贡献](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [发布步骤](PUBLISHING.md)

```
╭──────────────────────────────────────────╮
│ GitHub Release 交互式下载助手            │
│ 搜索 · 收藏 · 一键下载                   │
╰──────────────────────────────────────────╯
  收藏夹 3 个   Token 已配置 · 本地 .github_token   下载目录 C:\Users\me\Downloads

   1  搜索仓库  —  按名字找项目，选编号看 Release 资产并下载
   2  查看收藏  —  调出已存仓库的下载链接，支持直接下载
   3  添加收藏  —  把常用仓库存进 favorites.json
   4  退出      —  保存收藏并退出
   0  配置 Token —  打开 GitHub Token 页面，粘贴后存本地 .github_token，解除限流
```

## 功能特性

- **不知道作者也能找**：只输入仓库名关键词，按星标排序列出候选（作者/名字、星标、语言、简介），输入编号即可。
- **收藏夹持久化**：以 `作者名/仓库名` 为键写入 `favorites.json`，附带星标、简介与上次看到的资产清单，重启后仍在。
- **双重下载**：选定文件后既可唤起系统默认浏览器下载，也可用 `requests` 流式直接落到本地，带实时进度条（百分比 / 速度 / 剩余时间）。
- **按类型筛选**：先问你要 ZIP 还是 EXE（也支持 MSI、DMG、DEB 等实际存在的类型与「全部」）。
- **下载目录可选**：每次下载前可以选默认目录、仅本次换目录、换目录并永久记住，也可以一键恢复系统默认下载目录。
- **只复制链接**：也可以只打印下载链接，粘进浏览器或你惯用的任何下载工具都行。
- **一键解除限流**：菜单按 `0` 就跳到 GitHub 的 Token 创建页（链接已带 `public_repo` 权限参数），
  粘贴回来只写本地 `.github_token`；Token 不进源码、不进日志，保存后也不会再打印一遍。
- **终端友好**：自适应列宽的表格（中英文、emoji 混排不错位），ANSI 颜色，`NO_COLOR` 或管道输出时自动降级为纯文本。
- **异常明确**：网络不通、超时、SSL 被代理拦截、仓库不存在、没有 release、API 限流，分别给出可读提示而不是裸 traceback。
- **报错不会消失**：早期失败（Python 版本 / 缺依赖）写 `crash.log` 并等你按键；菜单里的错误会留在重画后的菜单顶部；未预料的崩溃打印完整 traceback 后落盘。
- **上手无门槛**：所有仓库名、作者名、文件类型、保存位置都在终端里选编号或输入，不需要记任何命令行参数。

## 环境要求

- Python 3.8 及以上（推荐 3.10+）
- 一个第三方依赖：`requests`；其余全部是标准库，不依赖 rich / colorama / tqdm，也不用任何 GUI 框架

## 安装

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
```

## 使用

### 方式一：双击 `Run.bat`

不想碰命令行的话，直接双击 `Run.bat` 即可进入菜单。它会先找到本机 Python（优先 `py -3`，其次 `python`），
发现缺 `requests` 时按 `requirements.txt` 自动装一次，之后任何报错都留在窗口里等你按键。

### 方式二：命令行

```bash
python main.py
```

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
- 下载先写 `.part` 临时文件，校验字节数一致后再改名；中途 Ctrl+C 或断流会清掉半截文件，不会留下打不开的残文件。
- 资产文件名会做净化，去掉路径分隔符与非法字符，避免恶意文件名造成的路径穿越。
- 不想要本地下载时，也可以只唤起浏览器，或只打印链接粘到别处。

## 配置 GitHub Token（可选，用于解除限流）

| 状态 | 未认证核心 API | Search API |
| --- | --- | --- |
| 无 Token | 60 次/小时 | 10 次/分钟 |
| 有 Token | 5000 次/小时 | 30 次/分钟 |

四种方式，任选其一（**不要把 Token 写进源码**）：

1. **菜单里按 `0`**（推荐）：程序会打印 Token 创建页地址并问你要不要直接用浏览器打开——
   链接已经带上 `scopes=public_repo`，进到页面点一下 Create 就行。把结果粘回终端，
   只写进本地 `.github_token`（POSIX 下权限收紧为仅当前用户可读写，Windows 由 ACL 决定；
   该文件已在 `.gitignore` 中），屏幕上不会把 Token 再打印一遍。首次启动没有 Token 时
   也会主动问这同一段话。
2. **只要地址，不想开菜单**：`python cli.py --token-url` 打印创建页链接后退出，
   不读也不写任何 Token，适合远程帮别人排障。
3. **环境变量**：`set GITHUB_TOKEN=ghp_xxx`（PowerShell 用 `$env:GITHUB_TOKEN="ghp_xxx"`）。
4. **命令行参数**：`python main.py --token ghp_xxx`。

优先级：`--token` > 环境变量 > `.github_token` 文件。

直接可点的地址（菜单里的 `0` 打开的就是第一条）：

- 经典 Token：<https://github.com/settings/tokens/new?scopes=public_repo&description=gh-release-helper>
- 细粒度 Token：<https://github.com/settings/personal-access-tokens/new>（只给 Public Repositories 的 Read-only 即可）
- 查看 / 撤销已发出的 Token：<https://github.com/settings/tokens>

公共仓库只需要 `public_repo` 这一个范围，不需要额外勾选权限；配好之后本次运行立刻生效，不用重启。

> ⚠️ Token 等同于你的 GitHub 密码。一旦不小心提交到仓库或被他人看到，请立刻在上面的页面撤销（revoke）并重新生成。

## 隐私说明

- 程序只向 `api.github.com` 和 `github.com` 发起请求，不会上传你的任何本地数据，也没有统计、埋点或自动更新。
- 收藏夹（`favorites.json`）、下载目录偏好（`config.json`）、Token（`.github_token`）都只存在你自己机器上，且已写进 `.gitignore`，正常提交不会带上它们。
- 只用公开的读取接口，不会对你的仓库做任何写操作。
- 配置 Token 时程序只打开 `https://github.com/settings/tokens/new?...` 这个官方页面，
  链接里不含你的账号信息；你粘贴回来的 Token 只写进 `.github_token`，不会在屏幕上回显，
  也不会进 `crash.log`。
- 不想在这台机器上留 Token 时，删掉 `.github_token` 即可（菜单里按 `0` 会重新问一次），
  或者到 <https://github.com/settings/tokens> 直接撤销。

## 项目结构

```
gh-release-helper/
├── main.py           # 交互菜单入口（四大流程）
├── cli.py            # 命令行模式：只打印下载链接
├── github_api.py     # GitHub REST API 封装、Token 解析、统一异常
├── downloader.py     # 流式下载、进度条、目录选择、文件名净化、浏览器唤起
├── favorites.py      # favorites.json 读写与去重
├── ui.py             # ANSI 颜色、表格、UTF-8 输出、崩溃日志（纯标准库）
├── bootstrap.py      # 启动前置检查：Python 版本、requests 依赖（纯标准库）
├── Run.bat           # 双击启动：探测 Python、缺依赖自动装、出错停窗（纯 ASCII）
├── requirements.txt
├── .gitignore        # 忽略 favorites.json / config.json / crash.log / .github_token
├── .editorconfig     # 统一 UTF-8 与缩进，避免中文注释被写坏
├── LICENSE           # MIT
├── README.md
├── CHANGELOG.md      # 更新日志（Keep a Changelog 格式）
├── CONTRIBUTING.md   # 代码约定、怎么跑测试、PR 自检清单
├── SECURITY.md       # Token 与下载安全说明、漏洞私密报告方式
├── PUBLISHING.md     # 把这个文件夹变成公开仓库的完整步骤
├── tests/            # 离线单元测试：不联网、不碰个人文件
│   ├── test_ui.py
│   ├── test_core.py
│   └── test_error_visible.py
└── .github/
    ├── workflows/ci.yml              # 3.8/3.10/3.12/3.13 跑测试 + Windows 冒烟
    ├── PULL_REQUEST_TEMPLATE.md
    └── ISSUE_TEMPLATE/               # 问题反馈 / 功能建议 两个模板
```

运行后会自动生成这几个本地文件，都不需要提交：`favorites.json`、`config.json`、`.github_token`、`crash.log`。

## 开发与测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests        # 90+ 用例，约 0.2 秒，全程离线
```

测试不会打 GitHub API（网络用假响应），也不会读写你的 `favorites.json`（落盘指向临时目录）。
改代码前建议先读 `CONTRIBUTING.md` 的代码约定；要发布则按 `PUBLISHING.md` 一步步来。

## 常见问题

**Q：报 `SSL 证书校验失败`？**
本机有代理工具（SteamTools、Charles、Fiddler、企业网关等）对 HTTPS 做中间人，它的根证书不在 certifi 的信任库里。把该根证书导出为 `.pem`，然后设置 `REQUESTS_CA_BUNDLE` 指向它即可。关掉代理工具通常也能立刻恢复。

**Q：`该 release 没有任何资产文件`？**
不是 bug。有些项目（例如 VS Code）只发布 tag，安装包放在自己官网；也有项目把资产挂在别的 release 上。可以试试 `python cli.py owner/repo --no-latest` 看历史 release。

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
程序不会留下半截文件：`.part` 临时文件会被清掉，重新下载即可。同名文件也不会覆盖，会自动加 `(1)` 后缀。

**Q：能不能不装 requests？**
不能。搜索、Release 与下载都依赖它，这也是项目唯一的第三方库，`pip install -r requirements.txt` 一句就好。

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

## License

MIT，见 `LICENSE`。你可以自由使用、修改、再分发，保留版权声明即可。
想换成 Apache-2.0 或 GPL-3.0，改 `LICENSE` 与本段，并按 `PUBLISHING.md` 第 2 步的说明替换版权持有人。
