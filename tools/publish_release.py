"""Publikuje wydanie (Release) na GitHubie z gotowym ImageNotes.exe i paczką ZIP."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from imagenotes import config  # noqa: E402

DIST = PROJECT_ROOT / "dist"
EXE = DIST / f"{config.APP_NAME}.exe"
ZIP = DIST / f"{config.APP_NAME}-{config.VERSION}-win64-portable.zip"

DEFAULT_NOTES = """\
ImageNotes {version}

Narzędzie na Windows do notowania na zdjęciach i mapach. Nic nie trzeba instalować, wystarczy
rozpakować i uruchomić.

ImageNotes.exe to gotowy program. ZIP zawiera to samo plus krótką instrukcję, którą można wysłać
dalej komuś, kto też nie ma Pythona.

Do notowania jest tekst z wyborem koloru, rozmiaru i kąta, strzałka, krzyżyk, checkmark i rysowanie
odręczne. Po zdjęciu pływa się prawym przyciskiem myszy, a przybliża kółkiem tam, gdzie stoi kursor.
Notatki zapisują się same i nadpisują jedną kopię roboczą, więc nie robi się sterta plików,
a oryginalne zdjęcie zostaje nietknięte. Po ponownym otwarciu edytuje się notatki, a nie sam obraz.

Skróty: Ctrl+O otwórz, Ctrl+S zapisz, Ctrl+Z cofnij, Del usuń, Ctrl+0 dopasuj, F11 pełny ekran.

Wymaga 64-bitowego Windows. Autor: Adam Warzecha.
"""


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wydanie ImageNotes na GitHubie")
    parser.add_argument("--tag", default=f"v{config.VERSION}", help="tag wydania (domyślnie v<wersja>)")
    parser.add_argument("--notes", default="", help="opis wydania (domyślnie szablon)")
    parser.add_argument("--no-build", action="store_true", help="nie buduj EXE")
    parser.add_argument(
        "--notes-only", action="store_true",
        help="tylko popraw opis istniejącego wydania (bez budowania i wgrywania plików)",
    )
    args = parser.parse_args()

    if not shutil_which("gh"):
        print("BŁĄD: brak gh CLI w PATH.")
        return 1
    status = gh("auth", "status")
    if status.returncode != 0:
        print("BŁĄD: gh nie jest zalogowany. Uruchom: gh auth login")
        return 1

    notes = args.notes or DEFAULT_NOTES.format(version=config.VERSION)

    if args.notes_only:
        edit = gh("release", "edit", args.tag, "--notes", notes,
                  "--title", f"{config.APP_NAME} {config.VERSION}")
        if edit.returncode != 0:
            print("BŁĄD: nie udało się poprawić opisu:", edit.stderr.strip())
            return 1
        print(f"Opis wydania {args.tag} zaktualizowany.")
        return 0

    if not args.no_build or not EXE.exists() or not ZIP.exists():
        print("Buduję EXE i paczkę…")
        build = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "build_exe.py")])
        if build.returncode != 0:
            print("BŁĄD: budowanie nie powiodło się.")
            return 1

    assets = [p for p in (EXE, ZIP) if p.exists()]
    if not assets:
        print("BŁĄD: brak plików do wgrania w dist/")
        return 1
    for path in assets:
        print(f"  {path.name}: {path.stat().st_size / 1024 / 1024:.1f} MB")

    exists = gh("release", "view", args.tag).returncode == 0

    if exists:
        print(f"Wydanie {args.tag} już jest — podmieniam pliki i opis.")
        upload = gh("release", "upload", args.tag, *[str(p) for p in assets], "--clobber")
        if upload.returncode != 0:
            print("BŁĄD wgrywania:", upload.stderr.strip())
            return 1
        edit = gh("release", "edit", args.tag, "--notes", notes, "--title", f"{config.APP_NAME} {config.VERSION}")
        if edit.returncode != 0:
            print("OSTRZEŻENIE: nie udało się zaktualizować opisu:", edit.stderr.strip())
    else:
        print(f"Tworzę nowe wydanie {args.tag}.")
        create = gh(
            "release", "create", args.tag,
            *[str(p) for p in assets],
            "--title", f"{config.APP_NAME} {config.VERSION}",
            "--notes", notes,
            "--target", "main",
        )
        if create.returncode != 0:
            print("BŁĄD tworzenia wydania:", create.stderr.strip())
            return 1

    view = gh("release", "view", args.tag, "--json", "url,assets",
              "--jq", '"url: \\(.url)\\npliki: " + ([.assets[] | "\\(.name) (\\(.size/1048576*100|round/100) MB)"] | join(", "))')
    print(view.stdout.strip() or "OK")
    return 0


def shutil_which(program: str) -> str:
    """Znajduje program w PATH bez importowania shutil (nazwa koliduje z lokalną zmienną)."""
    import shutil

    return shutil.which(program) or ""


if __name__ == "__main__":
    raise SystemExit(main())
