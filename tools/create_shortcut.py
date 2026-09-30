"""Tworzy skrót na pulpicie, który odpala ImageNotes bez okna konsoli."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / "ImageNotes.pyw"
ICON = PROJECT_ROOT / "assets" / "imagenotes.ico"
EXE = PROJECT_ROOT / "dist" / "ImageNotes.exe"

PYTHONW = Path(
    os.environ.get("IMAGENOTES_PYTHONW")
    or r"C:\Users\adamo\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\pythonw.exe"
)


def desktop_dir() -> Path:
    candidates = [Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"]
    for shell_folder in (r"Desktop",):
        candidates.append(Path(os.environ.get("USERPROFILE", str(Path.home()))) / shell_folder)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path.home() / "Desktop"


def create_shortcut(name: str, exe: Path | None = None) -> Path:
    target = desktop_dir() / f"{name}.lnk"
    if exe is not None:
        program, arguments = str(exe), ""
        workdir, icon = str(exe.parent), f"{exe},0"
    else:
        program, arguments = str(PYTHONW), f'"{LAUNCHER}"'
        workdir, icon = str(PROJECT_ROOT), str(ICON)
    script = f"""
$W = New-Object -ComObject WScript.Shell
$S = $W.CreateShortcut("{target}")
$S.TargetPath = "{program}"
$S.Arguments = '{arguments}'
$S.WorkingDirectory = "{workdir}"
$S.IconLocation = "{icon}"
$S.Description = "ImageNotes - szybkie notatki na zdjeciacach"
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
    parser = argparse.ArgumentParser(description="Skrót ImageNotes na pulpicie")
    parser.add_argument("--name", default="ImageNotes", help="nazwa skrótu (bez .lnk)")
    parser.add_argument("--exe", action="store_true", help="skrót do dist/ImageNotes.exe (wersja samodzielna)")
    args = parser.parse_args()

    if args.exe:
        if not EXE.exists():
            print(f"BŁĄD: brak {EXE}")
            print("Najpierw zbuduj paczkę: python tools/build_exe.py")
            return 1
        target = create_shortcut(args.name, EXE)
        print(f"OK: skrót utworzony -> {target}")
        print(f"    cel: {EXE}")
        return 0

    if not LAUNCHER.exists():
        print(f"BŁĄD: brak launchera {LAUNCHER}")
        return 1
    if not PYTHONW.exists():
        print(f"BŁĄD: brak interpretera {PYTHONW}")
        print("Ustaw zmienną IMAGENOTES_PYTHONW albo popraw ścieżkę w tym skrypcie.")
        return 1

    target = create_shortcut(args.name)
    if target.exists():
        print(f"OK: skrót utworzony -> {target}")
        print(f"    cel: {PYTHONW}")
        print(f"    argument: {LAUNCHER}")
        return 0
    print("BŁĄD: skrót nie powstał")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
