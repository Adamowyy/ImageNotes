"""Create a desktop shortcut that starts ImageNotes without a console window."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / "ImageNotes.pyw"
ICON = PROJECT_ROOT / "assets" / "imagenotes.ico"
EXE = PROJECT_ROOT / "dist" / "ImageNotes.exe"


def find_pythonw() -> Optional[Path]:
    """Locate a GUI-subsystem pythonw.exe (see the note in the module docstring)."""
    override = os.environ.get("IMAGENOTES_PYTHONW")
    if override:
        return Path(override)
    beside = Path(sys.executable).with_name("pythonw.exe")
    if beside.exists():
        return beside
    found = shutil.which("pythonw")
    return Path(found) if found else None


def desktop_dir() -> Path:
    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    for candidate in (profile / "Desktop", Path.home() / "Desktop"):
        if candidate.exists():
            return candidate
    return profile / "Desktop"


def create_shortcut(name: str, exe: Optional[Path] = None, pythonw: Optional[Path] = None) -> Path:
    target = desktop_dir() / f"{name}.lnk"
    if exe is not None:
        program, arguments = str(exe), ""
        workdir, icon = str(exe.parent), f"{exe},0"
    else:
        program, arguments = str(pythonw), f'"{LAUNCHER}"'
        workdir, icon = str(PROJECT_ROOT), str(ICON)
    script = f"""
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("{target}")
$S.TargetPath = "{program}"
$S.Arguments = '{arguments}'
$S.WorkingDirectory = "{workdir}"
$S.IconLocation = "{icon}"
$S.Description = "ImageNotes - annotate images and maps"
$S.WindowStyle = 1
$S.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="ImageNotes desktop shortcut")
    parser.add_argument("--name", default="ImageNotes", help="shortcut name (without .lnk)")
    parser.add_argument("--exe", action="store_true", help="point at dist/ImageNotes.exe instead of the source")
    parser.add_argument("--pythonw", default="", help="path to a real GUI pythonw.exe")
    args = parser.parse_args()

    if args.pythonw:
        os.environ["IMAGENOTES_PYTHONW"] = args.pythonw

    if args.exe:
        if not EXE.exists():
            print(f"error: {EXE} does not exist")
            print("build it first: python tools/build_exe.py")
            return 1
        target = create_shortcut(args.name, exe=EXE)
        print(f"OK: shortcut created -> {target}")
        print(f"    target: {EXE}")
        return 0

    if not LAUNCHER.exists():
        print(f"error: launcher not found: {LAUNCHER}")
        return 1
    pythonw = find_pythonw()
    if pythonw is None:
        print("error: no pythonw.exe found")
        print("pass --pythonw <path> or set IMAGENOTES_PYTHONW")
        return 1

    target = create_shortcut(args.name, pythonw=pythonw)
    if target.exists():
        print(f"OK: shortcut created -> {target}")
        print(f"    target: {pythonw}")
        print(f"    argument: {LAUNCHER}")
        return 0
    print("error: the shortcut was not created")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
