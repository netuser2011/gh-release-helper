import requests
repos = ['chocolatey/community', 'HandBrake/HandBrake', 'krita/krita', 'obsproject/obs-studio']
h = {'Authorization': 'Bearer ' + open('.github_token', encoding='utf-8').read().splitlines()[0].strip()}
for r in repos:
    try:
        d = requests.get(f'https://api.github.com/repos/{r}/releases/latest', headers=h, timeout=20).json()
        print(f'== {r}  tag={d.get("tag_name")}  assets={len(d.get("assets", []))}')
        for a in d.get('assets', [])[:8]:
            print(f'   {a["name"][:50]:52s} {a["size"]/1e6:9.1f} MB')
    except Exception as e:
        print(f'== {r}  failed: {e}')
