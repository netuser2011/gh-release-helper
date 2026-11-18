## 这个 PR 改了什么

一句话说明动机，再列要点。修 bug 的请附上对应 issue 编号（`Fixes #123`）。

-

## 怎么验证

写下你实际跑过的命令，别只写「测试通过」：

```bash
python -m unittest discover -s tests
python main.py
```

## 自检清单

- [ ] `python -m unittest discover -s tests` 全绿（本地是 Python 3.8 再跑一次）
- [ ] `python -m py_compile main.py cli.py github_api.py downloader.py favorites.py ui.py bootstrap.py` 无输出
- [ ] 中文 Windows 控制台（默认 GBK）里手动跑过一遍，界面不闪退、报错不会消失
- [ ] 新增的用户可见行为写进了 `CHANGELOG.md` 的 `[Unreleased]`
- [ ] 没有引入新的第三方依赖；有的话已在 README 与 CI 里说明
- [ ] 没有硬编码 Token、仓库名、作者名、文件类型
- [ ] 没有把 `favorites.json` / `config.json` / `.github_token` / `crash.log` 加进提交
- [ ] 改了下载逻辑的话：`.part` 清理、文件名净化、同名不覆盖这三条仍然成立

## 截图 / 录屏（界面有变化时）

