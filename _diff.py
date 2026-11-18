import requests, os
t = open('.github_token', encoding='utf-8').read().splitlines()[0].strip()
h = {'Authorization': 'Bearer ' + t}
files = ['main.py', 'downloader.py', 'README.md', 'CHANGELOG.md', 'docs/index.html', 'tests/test_core.py', 'PUBLISHING.md', 'ui.py']
for f in files:
    local = os.path.getsize(f) if os.path.exists(f) else 0
    try:
        r = requests.get(f'https://api.github.com/repos/netuser2011/gh-release-helper/contents/{f}', headers=h, timeout=20)
        if r.status_code == 404:
            print(f'{f}: local={local}B remote=MISSING -> {"需要上传" if local else "-"}')
        else:
            remote = r.json()['size']
            mark = '一致' if local == remote else 'DIFFERENT -> 需同步'
            print(f'{f}: local={local}B remote={remote}B {mark}')
    except Exception as e:
        print(f'{f}: error {e}')
