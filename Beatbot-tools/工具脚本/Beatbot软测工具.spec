# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/串口工具', '串口工具'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/MCU工具', 'MCU工具'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/spjz', 'spjz'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/excel转换工具', 'excel转换工具'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/主程序/icons', 'icons'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/图标', '图标'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/配置文件', '配置文件'), ('/Users/ambrose.chen/Desktop/iot/Beatbot-tools/主程序/platform_compat.py', '.')]
binaries = []
hiddenimports = ['serial', 'serial.tools.list_ports', 'openpyxl', 'pandas', 'zstandard', 'pytesseract']
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['/Users/ambrose.chen/Desktop/iot/Beatbot-tools/主程序/Beatbot.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Beatbot软测工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Beatbot软测工具',
)
app = BUNDLE(
    coll,
    name='Beatbot软测工具.app',
    icon=None,
    bundle_identifier=None,
)
