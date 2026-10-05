"""Build a standalone ImageNotes.exe (PyInstaller) for someone who has no Python."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from imagenotes import config  # noqa: E402

DIST = PROJECT_ROOT / "dist"
BUILD = PROJECT_ROOT / "build"

# Qt modules the app does not use; excluding them shrinks the package a lot
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtStateMachine",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtRemoteObjects",
    "tkinter", "unittest", "pydoc_data", "matplotlib", "numpy", "PIL", "setuptools", "pip",
]

INSTRUCTIONS = """ImageNotes - how to run
=======================

1. Unpack this folder anywhere (Desktop, D:\\ , ...).
2. Double-click ImageNotes.exe. There is nothing to install.

The interface is in Polish.

The first time, Windows may show a blue "Windows protected your PC" box
(SmartScreen). That is normal for a program without a paid code signature:
    More info  ->  Run anyway

MAKING NOTES ON AN IMAGE
------------------------
* Open an image: drag a file (JPG/PNG) ONTO ImageNotes.exe, or start the
  program and press Ctrl+O.
* Pan: hold the RIGHT mouse button.
* Zoom: mouse wheel (zooms where the cursor is).
* Tools: the panel in the top-right corner - text (T), arrow (A), cross (X),
  checkmark (C), freehand (B), select/move (V).
* Colour, line width, text size and angle: the swatches and sliders in the
  same panel.
* Move a note you already made: press V, then drag it. Double-click text to
  edit it, Del deletes, Ctrl+Z undoes.
* Recently edited images: the round bubble in the top-left corner.
* Fit the image to the window: Ctrl+0. Full screen: F11.

WHERE THE NOTES ARE SAVED
-------------------------
The program never touches your original image. Next to ImageNotes.exe it
creates a "workspace" folder and rewrites one file there with the notes baked
in, plus a matching .json file that lists the notes - that is what lets you
edit them again after reopening the image.

TIP
---
For a desktop shortcut: right-click ImageNotes.exe -> "Show more options" ->
"Send to" -> "Desktop (create shortcut)". Then simply drag an image onto it.

Author: Adam Warzecha. MIT licence - see the repository for details.
"""

VERSION_INFO = """\\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Adam Warzecha'),
         StringStruct('FileDescription', 'ImageNotes - annotate images and large maps'),
         StringStruct('FileVersion', '1.0.0'),
         StringStruct('InternalName', 'ImageNotes'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 Adam Warzecha'),
         StringStruct('LegalTrademarks', 'ImageNotes'),
         StringStruct('OriginalFilename', 'ImageNotes.exe'),
         StringStruct('ProductName', 'ImageNotes'),
         StringStruct('ProductVersion', '1.0.0'),
         StringStruct('Comments', 'MIT licensed. Author: Adam Warzecha.')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def check_pyinstaller() -> str:
    try:
        import PyInstaller  # noqa: F401 - presence check only
        return "PyInstaller"
    except ImportError:
        print("error: PyInstaller is missing. Install it into the same interpreter:")
        print(f'  uv pip install --python "{sys.executable}" --break-system-packages pyinstaller')
        raise SystemExit(1)


def build(onefile: bool) -> Path:
    check_pyinstaller()
    config.ensure_dirs()
    icon = config.ASSETS_DIR / "imagenotes.ico"
    if not icon.exists():
        subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "make_icon.py")], check=True)

    entry = BUILD / "_entry.py"
    BUILD.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "import sys, os\n"
        f"sys.path.insert(0, r'{PROJECT_ROOT}')\n"
        "from imagenotes.app import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_INFO, encoding="utf-8")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", config.APP_NAME,
        "--version-file", str(version_file),
        "--icon", str(icon),
        "--add-data", f"{config.ASSETS_DIR}{os.pathsep}assets",
        "--paths", str(PROJECT_ROOT),
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
    ]
    command.append("--onefile" if onefile else "--onedir")
    for module in EXCLUDES:
        command += ["--exclude-module", module]
    command.append(str(entry))

    print("Building:", " ".join(command[:8]), "...")
    subprocess.run(command, check=True, cwd=str(PROJECT_ROOT))

    exe = DIST / f"{config.APP_NAME}.exe"
    if not exe.exists():
        raise SystemExit("error: the built exe was not found")
    return exe


def package(exe: Path, onefile: bool) -> Path:
    """Build the ZIP to hand over: the exe (or the whole folder) plus a readme."""
    zip_path = DIST / f"{config.APP_NAME}-{config.VERSION}-win64-portable.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        if onefile:
            archive.write(exe, exe.name)
        else:
            for path in sorted((DIST / config.APP_NAME).rglob("*")):
                if path.is_file():
                    archive.write(path, str(path.relative_to(DIST)))
        archive.writestr("README.txt", INSTRUCTIONS)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ImageNotes.exe")
    parser.add_argument("--onedir", action="store_true", help="a folder with the exe instead of a single file")
    parser.add_argument("--no-zip", action="store_true", help="do not create the ZIP")
    args = parser.parse_args()

    shutil.rmtree(BUILD, ignore_errors=True)
    onefile = not args.onedir
    exe = build(onefile)
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"\nOK: {exe}  ({size_mb:.1f} MB)")

    if not args.no_zip:
        zip_path = package(exe, onefile)
        print(f"ZIP to hand over: {zip_path}  ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("\nTest: run the exe and drop a JPG/PNG onto it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
