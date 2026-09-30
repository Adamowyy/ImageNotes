"""Magazyn plików: ścieżki robocze, sidecar z adnotacjami, miniatury i lista ostatnich."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap

from . import config

# Bez tego Qt odmawia otwarcia obrazów większych niż 256 MB (patrz config).
QImageReader.setAllocationLimit(config.QIMAGE_ALLOC_LIMIT_MB)


# --- ścieżki --------------------------------------------------------------

def slug_for(source: Path) -> str:
    """Stabilny identyfikator pliku źródłowego (nazwa + hash ścieżki)."""
    try:
        raw = str(Path(source).resolve()).lower()
    except Exception:
        raw = str(source).lower()
    digest = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:8]
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", Path(source).stem)[:48].strip("_") or "image"
    return f"{stem}-{digest}"


def work_path(source: Path) -> Path:
    return config.WORKSPACE_DIR / f"{slug_for(source)}{config.SAVE_SUFFIX}"


def sidecar_path(source: Path) -> Path:
    return config.WORKSPACE_DIR / f"{slug_for(source)}.json"


def thumb_path(source: Path) -> Path:
    return config.THUMBS_DIR / f"{slug_for(source)}.png"


# --- sidecar --------------------------------------------------------------

def read_annotations(sidecar: Path) -> List[dict]:
    """Wczytuje surowe słowniki adnotacji; brak/uszkodzenie pliku => pusta lista."""
    try:
        if not sidecar.exists():
            return []
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        items = raw.get("annotations", raw if isinstance(raw, list) else [])
        return [d for d in items if isinstance(d, dict)]
    except Exception:
        return []


def write_sidecar(sidecar: Path, source: Path, annotations: List[dict], key: str) -> None:
    payload = {
        "key": key,
        "source": str(source),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(annotations),
        "annotations": annotations,
    }
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, sidecar)


# --- miniatury ------------------------------------------------------------

def write_thumbnail(img: QImage, dest: Path) -> bool:
    """Zapisuje miniaturę (maks. bok THUMB_PX). Zwraca False, gdy się nie udało."""
    try:
        if img.isNull():
            return False
        scaled = img.scaled(
            QSize(config.THUMB_PX, config.THUMB_PX),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        if not scaled.save(str(tmp), "PNG", 80):
            return False
        os.replace(tmp, dest)
        return True
    except Exception:
        return False


_thumb_cache: Dict[str, Tuple[float, QPixmap]] = {}


def thumb_pixmap(entry: "RecentEntry", reffresh: bool = False) -> Optional[QPixmap]:
    """Miniatura pozycji z listy ostatnich (z cache po czasie modyfikacji pliku)."""
    key = entry.key
    try:
        stamp = entry.thumb.stat().st_mtime if entry.thumb.exists() else 0.0
        cached = _thumb_cache.get(key)
        if cached and cached[0] == stamp and not reffresh:
            return cached[1]
        pm = QPixmap(str(entry.thumb)) if entry.thumb.exists() else None
        if pm is None or pm.isNull():
            pm = _thumbnail_from_work(entry.work)
        if pm is None or pm.isNull():
            return None
        _thumb_cache[key] = (stamp, pm)
        return pm
    except Exception:
        return None


def _thumbnail_from_work(work: Path) -> Optional[QPixmap]:
    """Awaryjne generowanie miniatury bez dekodowania całego (10k+) obrazu."""
    try:
        if not work.exists():
            return None
        reader = QImageReader(str(work))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            scale = config.THUMB_PX / float(max(size.width(), size.height()))
            reader.setScaledSize(QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
        img = reader.read()
        return QPixmap.fromImage(img) if not img.isNull() else None
    except Exception:
        return None


# --- lista ostatnich ------------------------------------------------------

@dataclass
class RecentEntry:
    key: str
    source: Optional[Path]
    work: Path
    sidecar: Path
    thumb: Path
    saved_at: str
    mtime: float

    @property
    def display_name(self) -> str:
        return self.source.name if self.source else self.work.name

    @property
    def folder(self) -> Path:
        return self.source.parent if self.source else self.work.parent

    @property
    def open_target(self) -> Path:
        """Co realnie otwieramy: źródło, a gdy zniknęło — wypalony obraz z notatkami."""
        if self.source and self.source.exists():
            return self.source
        return self.work


def recent_entries(limit: int = 10) -> List[RecentEntry]:
    """Lista ostatnio edytowanych zdjęć, najnowsze pierwsze."""
    entries: List[RecentEntry] = []
    try:
        files = sorted(config.WORKSPACE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return entries
    for path in files[: max(1, limit * 3)]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or path.stem)
        source_raw = raw.get("source") or ""
        source = Path(source_raw) if source_raw else None
        entries.append(
            RecentEntry(
                key=key,
                source=source,
                work=config.WORKSPACE_DIR / f"{key}{config.SAVE_SUFFIX}",
                sidecar=path,
                thumb=config.THUMBS_DIR / f"{key}.png",
                saved_at=str(raw.get("saved_at") or ""),
                mtime=path.stat().st_mtime,
            )
        )
        if len(entries) >= limit:
            break
    return entries


def last_entry() -> Optional[RecentEntry]:
    items = recent_entries(1)
    return items[0] if items else None


def cleanup_temp_files() -> int:
    """Usuwa pliki .tmp osierocone przez przerwany zapis (świeży start = brak konfliktów,
    bo aplikacja wymusza pojedynczą instancję)."""
    removed = 0
    for folder in (config.WORKSPACE_DIR, config.THUMBS_DIR):
        try:
            for path in folder.glob("*.tmp"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        except OSError:
            pass
    return removed
