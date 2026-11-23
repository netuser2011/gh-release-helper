# -*- mode: python ; coding: utf-8 -*-
# 打包产物：dist/GH Downloader/GH Downloader.exe + _internal/（含 version.txt）
# 便携版 zip 与 setup.iss 的安装版都从这个目录出，路径一律相对 spec 所在目录。

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('version.txt', '.')],
    hiddenimports=['truststore._api', 'truststore._windows', 'truststore._openssl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GH Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GH Downloader',
)
