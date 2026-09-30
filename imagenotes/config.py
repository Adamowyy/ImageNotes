"""Ścieżki projektu, ustawienia użytkownika i stałe konfiguracyjne."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ImageNotes"
VERSION = "1.0.0"

# --- Autor (podpis w kodzie, w interfejsie, w metadanych plików i we właściwościach EXE) ---
AUTHOR = "Adam Warzecha"
YEAR = "2026"
COPYRIGHT = f"Copyright (c) {YEAR} {AUTHOR}. All rights reserved."
AUTHOR_LINE = f"\u00a9 {YEAR} {AUTHOR}"
AUTHOR_CREDIT = f"by {AUTHOR}"          # „by Adam Warzecha” — w tytule okna

# Wpisywane w metadane każdego zapisanego pliku (PNG: tEXt, JPEG: komentarz).
# Tylko znaki ASCII — tEXt w PNG jest Latin-1 i inne znaki mogłyby zostać odrzucone.
IMAGE_METADATA = {
    "Author": AUTHOR,
    "Artist": AUTHOR,
    "Copyright": COPYRIGHT,
    "Software": f"{APP_NAME} {VERSION}",
    "Source": f"{APP_NAME} - {AUTHOR}",
    "Description": f"Notatki na zdjeciu - {APP_NAME} by {AUTHOR}",
}


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_writable(folder: Path) -> bool:
    try:
        probe = folder / ".imagenotes_write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _data_root() -> Path:
    """Katalog na dane użytkownika (workspace + ustawienia)."""
    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if _is_writable(exe_dir):
            return exe_dir
        fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return fallback
    return Path(__file__).resolve().parent.parent


def _assets_root() -> Path:
    """Katalog z ikoną — w wersji spakowanej to katalog rozpakowania PyInstallera."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "assets"
    return PROJECT_ROOT / "assets"


APP_ROOT = _data_root()
PROJECT_ROOT = APP_ROOT          # zgodność z wcześniejszymi odwołaniami
ASSETS_DIR = _assets_root()
FROZEN = _is_frozen()

# Katalog roboczy: tu ląduje "wypalony" obraz z adnotacjami (nadpisywany przy każdej edycji)
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
THUMBS_DIR = WORKSPACE_DIR / ".thumbs"

SETTINGS_FILE = PROJECT_ROOT / "settings.json"

# Obsługiwane rozszerzenia (QImage czyta je natywnie)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

SAVE_FORMAT = "PNG"            # "PNG" (bezstratny, ostre napisy) albo "JPEG" (dużo szybszy)
SAVE_QUALITY = 85              # PNG: 85 ≈ 6 s/145 MB · JPEG: 92 ≈ 1,1 s/21 MB
SAVE_SUFFIX = ".png" if SAVE_FORMAT.upper() == "PNG" else ".jpg"

AUTOSAVE_DELAY_MS = 2000       # debounce autozapisu po ostatniej edycji
THUMB_PX = 320                 # maksymalny bok miniatury do bąbelka "ostatnie zdjęcia"
PYRAMID_MIN_PX = 1024          # piramida mipmap budowana aż największy bok < PYRAMID_MIN_PX

QIMAGE_ALLOC_LIMIT_MB = 4096

# --- Domyślne parametry narzędzi -----------------------------------------
DEFAULT_COLOR = "#ff2d2d"
DEFAULT_WIDTH = 10             # grubość linii w px zdjęcia
DEFAULT_TEXT_SIZE = 72         # rozmiar czcionki w px zdjęcia
DEFAULT_ANGLE = 0

PALETTE = ["#ff2d2d", "#ffd400", "#2bff5a", "#2ba7ff", "#ffffff", "#111111"]

DEFAULTS = {
    "tool": "select",
    "color": DEFAULT_COLOR,
    "width": DEFAULT_WIDTH,
    "text_size": DEFAULT_TEXT_SIZE,
    "angle": DEFAULT_ANGLE,
    "window": [1500, 950],
}


def ensure_dirs() -> None:
    """Tworzy katalogi robocze (bezpieczne przy wielokrotnym wywołaniu)."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    """Wczytuje ustawienia z settings.json, uzupełniając brakujące klucze domyślnymi."""
    data = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception:
        # Uszkodzone ustawienia nie mogą blokować startu aplikacji
        pass
    return data


def save_settings(data: dict) -> None:
    """Zapisuje ustawienia (best-effort — błąd zapisu nie przerywa pracy)."""
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
