# Windows onedir test distribution; no tests, keys, ledgers or local environments.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / "examples/six-layer-demo"), "examples/six-layer-demo")]
for name in ("quickstart.txt", "ai-usage.md", "export-format.md", "template-format.md", "release-notes.md"):
    datas.append((str(root / "docs" / name), "docs"))
for package in ("keyring", "PySide6_Essentials", "shiboken6", "Pillow", "pywin32-ctypes",
                "jaraco.classes", "jaraco.context", "jaraco.functools", "more-itertools"):
    datas += copy_metadata(package)

a = Analysis(
    [str(root / "packaging/entrypoint.py")], pathex=[str(root / "src")],
    binaries=[], datas=datas,
    hiddenimports=["keyring.backends.Windows", "win32ctypes.pywin32.win32cred",
                   "win32ctypes.pywin32.pywintypes", "PIL.PngImagePlugin"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["pytest", "pytestqt", "tkinter", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AnimeRpgSpriteStudio",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AnimeRpgSpriteStudio")
