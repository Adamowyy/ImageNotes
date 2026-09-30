"""Buduje samodzielny ImageNotes.exe (PyInstaller) — do wysłania komuś bez Pythona."""

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

# Transportowe moduły Qt, których aplikacja nie używa — bez nich paczka jest znacznie mniejsza
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

INSTRUCTIONS = """ImageNotes — jak uruchomić
===========================

Autor: Adam Warzecha.   Copyright (c) 2026 Adam Warzecha — wszelkie prawa
zastrzeżone. Program przekazany do użytku prywatnego; nie wolno podawać się
za jego autora ani rozpowszechniać go pod własnym nazwiskiem.

1. Wypakuj ten folder gdziekolwiek (np. na Pulpit albo do D:\\ ).
2. Uruchom ImageNotes.exe — dwuklik. Nic nie trzeba instalować.

Przy pierwszym uruchomieniu Windows może pokazać niebieskie okno
"System Windows ochronił Twój komputer" (SmartScreen) — to normalne przy
programach bez płatnego podpisu. Kliknij:
    "Więcej informacji"  ->  "Uruchom mimo to"

JAK ROBIĆ NOTATKI NA ZDJĘCIU
----------------------------
* Otwieranie zdjęcia: przeciągnij plik (JPG/PNG) NA ImageNotes.exe
  albo uruchom program i wciśnij Ctrl+O.
* Przesuwanie po zdjęciu: przytrzymaj PRAWY przycisk myszy.
* Przybliżanie: kółko myszy (przybliża tam, gdzie jest kursor).
* Notatki: panel w prawym górnym rogu — tekst (T), strzałka (A),
  krzyżyk (X), checkmark (C), rysowanie odręczne (B).
* Kolor, grubość, rozmiar i kąt: suwaki/próbki w tym samym panelu.
* Przesuwanie gotowej notatki: klawisz V, potem przeciągnij ją myszką
  (dwuklik na tekście = edycja, Del = usuń, Ctrl+Z = cofnij).
* Ostatnio edytowane zdjęcia: okrągły bąbelek w lewym górnym rogu.
* Dopasowanie zdjęcia do okna: Ctrl+0. Pełny ekran: F11.

GDZIE ZAPISUJĄ SIĘ NOTATKI
--------------------------
Program nie zmienia Twojego oryginalnego zdjęcia. Obok ImageNotes.exe
tworzy folder "workspace" i po każdej edycji nadpisuje tam jeden plik
z wypalonymi notatkami (+ plik .json z listą notatek, dzięki któremu
po ponownym otwarciu zdjęcia możesz je dalej edytować).

WSKAZÓWKA
---------
Możesz zrobić skrót na pulpicie: kliknij ImageNotes.exe prawym ->
"Pokaż więcej opcji" -> "Wyślij do" -> "Pulpit (utwórz skrót)".
Wtedy wystarczy przeciągnąć zdjęcie na ten skrót.

PODPIS AUTORA
-------------
* w programie: dolna linia panelu narzędzi (klik = okno "O programie")
  oraz tytuł okna,
* w każdym zapisanym zdjęciu, w metadanych pliku: Author / Artist / Copyright,
* we właściwościach pliku ImageNotes.exe (prawy klik -> Właściwości ->
  zakładka "Szczegóły": Firma, Opis, Prawa autorskie).
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
         StringStruct('FileDescription', 'ImageNotes - notatki na zdjeciach i mapach (autor: Adam Warzecha)'),
         StringStruct('FileVersion', '1.0.0'),
         StringStruct('InternalName', 'ImageNotes'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 Adam Warzecha. All rights reserved.'),
         StringStruct('LegalTrademarks', 'Adam Warzecha'),
         StringStruct('OriginalFilename', 'ImageNotes.exe'),
         StringStruct('ProductName', 'ImageNotes by Adam Warzecha'),
         StringStruct('ProductVersion', '1.0.0'),
         StringStruct('Comments', 'Autor: Adam Warzecha. Program prywatny - nie wolno przypisywac sobie autorstwa.')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def check_pyinstaller() -> str:
    try:
        import PyInstaller  # noqa: F401 - tylko sprawdzenie obecności
        return "PyInstaller"
    except ImportError:
        print("BŁĄD: brak PyInstallera. Zainstaluj w tym samym interpreterze:")
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

    print("Buduję:", " ".join(command[:8]), "...")
    subprocess.run(command, check=True, cwd=str(PROJECT_ROOT))

    exe = DIST / f"{config.APP_NAME}.exe"
    if not exe.exists():
        raise SystemExit("BŁĄD: nie znalazłem zbudowanego pliku EXE")
    return exe


def package(exe: Path, onefile: bool) -> Path:
    """Tworzy ZIP do wysłania: EXE (lub cały folder) + instrukcja."""
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
        archive.writestr("JAK-URUCHOMIC.txt", INSTRUCTIONS)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Buduje ImageNotes.exe")
    parser.add_argument("--onedir", action="store_true", help="folder z EXE zamiast jednego pliku")
    parser.add_argument("--no-zip", action="store_true", help="nie twórz paczki ZIP")
    args = parser.parse_args()

    shutil.rmtree(BUILD, ignore_errors=True)
    onefile = not args.onedir
    exe = build(onefile)
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"\nOK: {exe}  ({size_mb:.1f} MB)")

    if not args.no_zip:
        zip_path = package(exe, onefile)
        print(f"Paczka do wysłania: {zip_path}  ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("\nTest: uruchom EXE i przeciągnij na niego zdjęcie (JPG/PNG).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
