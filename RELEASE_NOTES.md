# GH Downloader v1.3.1

> 终端里的 GitHub Release 下载助手 —— 全屏交互、按类型筛选、多线路择优、一键下载。

本版为 **稳定性与一致性版本**：修掉了开着代理工具时下载全线失败的问题，把两套界面的菜单编号统一成同一套，让全屏界面和文本菜单的「检查更新」走同一套限流规则，并让发布产物可以在任何机器上复现打包。

---

## 下载

| 文件 | 说明 |
| --- | --- |
| `GHDownloader-Windows-V1.3.1-Setup.exe` | **推荐。** 安装版，双击运行，自动配置快捷方式与卸载项 |
| `GHDownloader-Windows-V1.3.1.zip` | 便携版，解压后直接运行 `GH Downloader.exe`，无需安装 |

两种文件均无需安装 Python，功能完全一致。

### 命令行下载（wget / curl）

```bash
# 安装版（Windows）
wget "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1-Setup.exe"

# 便携版
wget -O ghdownloader.zip "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.1/GHDownloader-Windows-V1.3.1.zip"
```

已经是 v1.3.0 的话不用手动下载：打开程序 → 菜单 `4`「检查更新」，确认后会自动下载安装包并升级。

---

## 本版变更

### 修复

- **开着代理工具时下载全线失败。** 代理工具常把 `[::1]`、`::1` 这类 IPv6 字面量写进 `NO_PROXY`，httpx 0.28 会把每一项当 URL 解析并抛 `InvalidURL: Invalid port`，导致线路测速和终端下载一个都跑不起来。现在构造 httpx 客户端期间临时清洗 `NO_PROXY`，构造完立刻还原环境变量，你不需要改任何系统设置；`requests` 那条路径不受影响。
- **全屏界面「检查更新」会静默裁剪收藏。** 未配 Token 时超过 40 个原本一声不响只查前 40、超过 30 个不问就砍到 30，和文本菜单「直接拒绝 / 先问一句」的行为不一致。现在两条界面共用同一份判定逻辑，拒绝条件、确认弹窗、提示文案完全一致。
- **全屏界面的「检查更新」没有限流保护。** 无 Token 的 40 个上限、有 Token 的 30 个确认、0.5 秒间隔、低配额提前停止、403/429 停批，现在和文本菜单走同一条路径。
- **资产文件名撞上 Windows 保留设备名（`CON`、`NUL`、`COM1` 等）时直接下载失败。** 净化后的名字命中保留名时自动加下划线。
- **并发测速在超时或异常路径上会甩出裸异常**，把整个下载流程带崩；现在转成该线路的「测速异常」明细，未完成任务的取消也会等收尾，不再留「Task was destroyed」告警。
- **全屏界面的自更新只认 Setup.exe**，仓库只发便携 zip 时更新不了；现在和文本菜单共用安装包选型，没有 exe 时 zip 兜底。

### 变更

- **两套界面菜单编号统一。** `GHR_NO_TUI` / 管道 / CI 下的文本菜单此前是「4 退出、5 检查更新、0 配 Token」，和全屏界面的「4 检查更新、5 配 Token、0 退出」互相打架——同一个数字在两个界面干不同的事。现在同一个数字在两个界面做同一件事：`1-4` 业务流程、`5` 配置 Token、`0` 退出。
- 资产类型优先展示表去掉 `mas` / `kmassix` 两个实际不存在的后缀；没列到的后缀仍按数量排在常见类型之后，筛选行为不变。

### 改进

- **启动依赖检查对齐 `requirements.txt`。** 现在一次检查 requests / httpx / textual / truststore 四个依赖，缺哪个报哪个，不再进了菜单才发现缺库。
- **批量检查配额的预检只查一次。** 进循环前查一次 `/rate_limit`、循环内本地递减，不再每个仓库各打一次（行为不变，少一半网络往返）。

### 打包

- **发布产物可复现。** 打包配置此前是单文件模式、既不带 `version.txt` 也和实际发布的目录布局不一致（照它打包会得到 `_internal` 缺版本文件、程序自认 `V0.0.0`、永远提示有更新的包）。现在仓库里只保留一份与线上产物一致的 onedir 配置，并删掉遗留的旧 spec。
- **受版本控制的文件里不再写死本机路径**（打包配置的图标、安装脚本的打包源目录），一律相对仓库根目录，换台机器不用改任何文件。

---

## 安装说明

**安装版（推荐）：**

1. 双击 `GHDownloader-Windows-V1.3.1-Setup.exe`
2. 按向导选择安装路径（默认装到当前用户的程序目录）
3. 完成后桌面与开始菜单各有一个快捷方式
4. 卸载：设置 → 应用 → 已安装的应用 → 搜索 "GH Downloader" → 卸载

**便携版：**

1. 解压 ZIP 到任意目录
2. 双击 `GH Downloader.exe` 即可运行
3. 删除该目录即为卸载，无残留

> 注意：`GH Downloader.exe` 与 `_internal/` 文件夹需保持在同一目录，不要单独移动 exe。
> `_internal\version.txt` 是版本号的唯一真相源，删掉它程序会认为自己是 `V0.0.0` 并一直提示更新。

---

## 从源码运行

需要 Python 3.10+ 和 `requests` / `httpx` / `textual` / `truststore`：

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
python main.py
```

---

完整更新日志见 [CHANGELOG.md](https://github.com/netuser2011/gh-release-helper/blob/main/CHANGELOG.md)。有问题欢迎提 Issue。
