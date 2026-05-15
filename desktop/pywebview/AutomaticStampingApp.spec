# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


PROJECT_ROOT = Path(SPECPATH).parents[1]


a = Analysis(
    [str(PROJECT_ROOT / "desktop" / "pywebview" / "app.py")],
    pathex=[str(PROJECT_ROOT), str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "web"), "web"),
        (str(PROJECT_ROOT / "config"), "config"),
        (str(PROJECT_ROOT / "firmware"), "firmware"),
        (str(PROJECT_ROOT / "tools"), "tools"),
    ],
    hiddenimports=[
        "uvicorn.lifespan.off",
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "cv2",
        "numpy",
        "serial",
    ],
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
    a.binaries,
    a.datas,
    [],
    name="AutomaticStampingSystem",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
