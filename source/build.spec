# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

SITE = os.path.join(os.path.dirname(os.__file__), "site-packages")
CONSOLE = os.environ.get("DSC_CONSOLE") == "1"

datas = []
binaries = []
hiddenimports = ["cffi", "_cffi_backend"]

# Bundle the app's resources (default config + starter profiles).
res_root = os.path.join(SPECPATH, "dualsense_companion", "resources")
for root, _dirs, files in os.walk(res_root):
    for fn in files:
        full = os.path.join(root, fn)
        rel = os.path.relpath(os.path.dirname(full), res_root)
        dest = "resources" if rel == "." else os.path.join("resources", rel)
        datas.append((full, dest))

# hidapi.dll must sit at the bundle root so the preloader can find it.
binaries.append((os.path.join(SITE, "pydualsense", "hidapi.dll"), "."))

# customtkinter ships theme/asset files that must travel with the app.
for pkg in ("customtkinter",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("pyaudiowpatch")

_icon = os.path.join(res_root, "app.ico")
app_icon = _icon if os.path.exists(_icon) else None

a = Analysis(
    ["run.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DualSenseCompanion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    icon=app_icon,
)
