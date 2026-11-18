# ghfind v1.1.0

> 终端里的 GitHub Release 下载助手 —— 搜索、收藏、一键下载。

这是 v1.0.0 之后的第一个功能更新版本，聚焦三件事：**下载更稳、断网能续、代理工具不再报 SSL 错**。旧的 v1.0.0 发行版保留不动，本版为最新推荐版本。

---

## 下载

| 文件 | 适用系统 | 说明 |
| --- | --- | --- |
| `ghfind-v1.1.0-win64.zip` | Windows 64 位 | 解压后双击 `ghfind.exe` 即可，**无需安装 Python** |

解压后目录里是 `ghfind.exe` 和 `_internal/`，二者需放在同一目录，不要单独移动 exe。

---

## 本版更新内容

### ✨ 新增

- **断点续传**：下载中途断网或按 Ctrl+C，不再删除半截文件，而是保留进度；下次重跑同一下载只补未完成的段。服务器文件发生变化（ETag / 长度不符）时自动从头下载，避免新旧内容错位。
- **无资产时的网页跳转**：Release 没上传资产时，不再只打印一句提示就结束，而是列出 **Release 发布页 / GitHub 仓库主页 / 作者官网** 供选择跳转；搜索选中仓库后也能先去网页看看再决定要不要下载。
- **自动信任系统证书**：启动时自动把系统证书（含 Watt Toolkit / SteamTools 等代理工具装的根证书）合并进 requests 的信任库。**开着代理工具也不会再报 `SSL 证书校验失败`**，无需手动导出证书或退出代理。主菜单新增「证书」状态行可查看是否生效。

### 🔧 改进

- 多线程分段下载（≥ 2 MB 且支持 Range 时，默认 4 线程，`GHR_THREADS` 可调 1–8）。
- 多线路测速择优：1 条直连 + 6 个公共镜像，并发测速挑最快的一条；全不通时逐条列出原因。
- 文档与程序现状同步：README / CHANGELOG 已更新到本版。

### 🔒 安全

- 系统证书信任只纳入本机**已受信任**的 CA（与浏览器一致），不降低安全基线；不新增第三方依赖。
- 断点续传的进度记录包含 URL / 总长 / ETag，文件更新后不复用旧进度。
- 镜像前缀强制 HTTPS、线路只认白名单，不接受临时输入的第三方地址。

---

## 从源码运行

需要 Python 3.8+ 和 `requests`：

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
python main.py
```

想直接打印下载链接：`python cli.py owner/repo`

---

完整更新日志见 [CHANGELOG.md](https://github.com/netuser2011/gh-release-helper/blob/main/CHANGELOG.md)。有问题欢迎提 Issue。
