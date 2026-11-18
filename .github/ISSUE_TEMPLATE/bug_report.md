---
name: 问题反馈
about: 程序报错、下载失败、界面错乱
title: "[Bug] "
labels: bug
assignees: ""
---

<!-- 先把下面这行删掉再提交：crash.log 里正常不含 Token，但贴之前自己看一眼。 -->

**发生了什么**
一句话说明白现象，比如「搜索 files 之后选编号 1，报 SSL 证书校验失败」。

**怎么复现**
1. 运行 `python main.py`（或 `Run.bat` / `python cli.py xxx/yyy`）
2. 输入 `1`，关键词 `files`
3. 选编号 `1`
4. 看到报错：……

**期望看到什么 / 实际看到什么**


**报错原文**

```
把控制台里的报错整段贴进来；如果窗口关掉了，贴 crash.log 的最后一段
```

**环境**

- 操作系统：Windows 11 / macOS / Ubuntu …（含版本号）
- Python：`python -V` 的输出
- requests：`python -m pip show requests` 的 Version
- 是否开着代理工具（SteamTools / Clash / Charles / 企业网关）：是 / 否
- 是否配置了 GitHub Token（不用说是哪个，只要回答有或没有）：

**补充**

- 同样的仓库，浏览器打开 `https://github.com/<owner>/<repo>/releases/latest` 能看到文件吗？
- 换个仓库还复现吗？（能帮你圈定是网络问题还是代码问题）
- 下载相关的问题：当时选的是哪种方式（终端 / 浏览器 / 只复制链接）、哪条线路
  （自动测速 / 直连 / 镜像），以及屏幕上有没有跑出进度条？文件多大？
- 设过 `GHR_THREADS` 或 `GHR_DOWNLOAD_DIR` 吗？分别是什么值？
