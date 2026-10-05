"""Paths, user settings and build-time constants."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ImageNotes"
VERSION = "1.0.0"

# --- Author (signature in source, UI, saved-file metadata and exe properties) ---
AUTHOR = "Adam Warzecha"
YEAR = "2026"
COPYRIGHT = f"Copyright (c) {YEAR} {AUTHOR}"
AUTHOR_LINE = f"\u00a9 {YEAR} {AUTHOR}"
AUTHOR_CREDIT = f"by {AUTHOR}"          # "by Adam Warzecha" in the window title

# Written into every saved file (PNG tEXt, JPEG comment). ASCII only: PNG tEXt is
# Latin-1, so other characters can be rejected.
IMAGE_METADATA = {
    "Author": AUTHOR,
    "Artist": AUTHOR,
    "Copyright": COPYRIGHT,
    "Software": f"{APP_NAME} {VERSION}",
    "Source": f"{APP_NAME} - {AUTHOR}",
    "Description": f"{APP_NAME} - image annotation by {AUTHOR}",
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
    """Directory holding user data (workspace + settings)."""
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
    """Icon directory: the PyInstaller unpack dir in a frozen build."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "assets"
    return PROJECT_ROOT / "assets"


APP_ROOT = _data_root()
PROJECT_ROOT = APP_ROOT          # kept for older references
ASSETS_DIR = _assets_root()
FROZEN = _is_frozen()

# Scratch directory: the baked image with its annotations lands here, overwritten on every edit
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
THUMBS_DIR = WORKSPACE_DIR / ".thumbs"

SETTINGS_FILE = PROJECT_ROOT / "settings.json"

# Suffixes QImage decodes natively
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

# Saving a big map (10234x8314, 325 MB in RAM): PNG 20 about 50 s / 128 MB, JPEG 90 about 1.1 s / 21 MB. For PNG a higher "quality" means less zlib work, so the write is faster and the file larger.
SAVE_FORMAT = "PNG"            # "PNG" (lossless, sharp text) or "JPEG" (much faster)
SAVE_QUALITY = 85              # PNG: 85 ~ 6 s/145 MB · JPEG: 92 ~ 1.1 s/21 MB
SAVE_SUFFIX = ".png" if SAVE_FORMAT.upper() == "PNG" else ".jpg"

AUTOSAVE_DELAY_MS = 2000       # debounce after the last edit
THUMB_PX = 320                 # longest side of the recent-images thumbnail
PYRAMID_MIN_PX = 1024          # mipmap levels are built until the longest side drops below this

QIMAGE_ALLOC_LIMIT_MB = 4096

# --- Tool defaults --------------------------------------------------------
DEFAULT_COLOR = "#ff2d2d"
DEFAULT_WIDTH = 10             # line width in image px
DEFAULT_TEXT_SIZE = 72         # font size in image px
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
    """Create the working directories (safe to call repeatedly)."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    """Read settings.json, filling in every missing key with its default."""
    data = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception:
        # Broken settings must not stop the app from starting
        pass
    return data


def save_settings(data: dict) -> None:
    """Write the settings; a failed write is not fatal."""
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
