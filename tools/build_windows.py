"""Build a fresh onedir test release without deleting existing build/release files."""
from datetime import datetime, timezone
from importlib.metadata import distribution, version
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    work = root / "build" / tag
    dist = root / "dist" / tag
    work.mkdir(parents=True)
    dist.mkdir(parents=True)
    command = [sys.executable, "-m", "PyInstaller", str(root / "packaging/AnimeRpgSpriteStudio.spec"),
               "--distpath", str(dist), "--workpath", str(work / "work"), "--noconfirm"]
    environment = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    # Avoid unrelated tool runtimes shadowing Windows system DLL names (e.g.
    # Poppler's ICU78 alias is ABI-incompatible with Qt's unversioned Windows ICU).
    environment["PATH"] = os.pathsep.join(str(p) for p in (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        windows / "System32", windows))
    with (work / "pyinstaller.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
    if process.returncode:
        print(json.dumps({"success": False, "log": str(work / "pyinstaller.log")}))
        return process.returncode
    app = dist / "AnimeRpgSpriteStudio"
    shutil.copy2(root / "docs/quickstart.txt", app / "START_HERE.txt")
    shutil.copy2(root / "docs/release-notes.md", app / "RELEASE_NOTES.md")
    licenses = app / "licenses"
    licenses.mkdir()
    packages = ("PySide6_Essentials", "shiboken6", "Pillow", "keyring", "pywin32-ctypes",
                "jaraco.classes", "jaraco.context", "jaraco.functools", "more-itertools")
    inventory = {}
    for name in packages:
        package = distribution(name)
        copied = []
        for file in package.files or []:
            if any(word in str(file).lower() for word in ("license", "copying", "notice", "copyright")):
                source = package.locate_file(file)
                if source.is_file():
                    target = licenses / name / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied.append(str(target.relative_to(app)))
        inventory[name] = {"version": version(name), "supplied_notice_files": copied}
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    notes = (
        "# Third-party notices — internal Windows test build\n\n"
        "Supplied installed-package license/notice files are copied under licenses/.\n"
        "Qt/PySide6/Shiboken metadata in this environment supplies commercial-license\n"
        "text only. Public redistribution rights are not established by this build.\n"
        "Verify the wheel source and applicable license before external distribution.\n"
        "No license purchase, public publication or compliance certification is implied.\n\n"
        "Runtime sources and license information:\n"
        "- Python: https://www.python.org/downloads/source/\n"
        "- Qt/PySide6: https://doc.qt.io/qtforpython-6/ and https://code.qt.io/\n"
        "- Qt licensing: https://doc.qt.io/qt-6/licensing.html\n"
        "- Pillow: https://github.com/python-pillow/Pillow\n"
        "- keyring: https://github.com/jaraco/keyring\n"
        "- pywin32-ctypes: https://github.com/enthought/pywin32-ctypes\n"
        "- OpenSSL: https://openssl-library.org/source/\n\n"
        "PyInstaller is a build tool with a bootloader exception; see\n"
        "https://pyinstaller.org/en/stable/license.html\n"
        "See build-info.json for installed-package notice inventory.\n")
    (app / "THIRD_PARTY_NOTICES.md").write_text(notes, encoding="utf-8")
    info = {"app_version": "0.6.0", "kind": "unsigned-internal-test-onedir", "python": sys.version.split()[0],
            "pyinstaller": version("pyinstaller"), "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "packages": inventory}
    (app / "build-info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    archive = Path(shutil.make_archive(str(dist / "AnimeRpgSpriteStudio-0.6.0-windows-test"), "zip", dist, app.name))
    digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
    (dist / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    output = {"success": True, "exe": str(app / "AnimeRpgSpriteStudio.exe"), "archive": str(archive),
              "sha256": digest, "log": str(work / "pyinstaller.log")}
    (root / "build/latest-release.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
