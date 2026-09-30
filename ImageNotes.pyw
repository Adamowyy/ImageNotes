"""Launcher ImageNotes — uruchamiany przez pythonw.exe (bez okna konsoli).

Skrót na pulpicie wskazuje ten plik, więc przeciągnięcie zdjęcia na skrót
przekazuje jego ścieżkę jako argument i zdjęcie otwiera się od razu.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from imagenotes.app import main  # noqa: E402  (import po ustawieniu ścieżki)

if __name__ == "__main__":
    raise SystemExit(main())
