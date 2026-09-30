"""Dokument (zdjęcie + adnotacje), piramida mipmap, loader w tle i autozapis."""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QSize, QThread, Qt, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QImageWriter, QPainter

from . import config, storage
from .annotations import Annotation, render_annotations

# Bez tego Qt odmawia otwarcia obrazów większych niż 256 MB (patrz config).
QImageReader.setAllocationLimit(config.QIMAGE_ALLOC_LIMIT_MB)


def _write_image(buffer: QImage, path: Path) -> bool:
    """Zapisuje obraz, wpisując w metadane autora programu."""
    writer = QImageWriter(str(path), config.SAVE_FORMAT.encode("ascii"))
    writer.setQuality(config.SAVE_QUALITY)
    for key, value in config.IMAGE_METADATA.items():
        writer.setText(key, value)
    if writer.write(buffer):
        return True
    return buffer.save(str(path), config.SAVE_FORMAT, config.SAVE_QUALITY)


class Document:
    """Otwarte zdjęcie: obraz bazowy (poziom 0), piramida mipmap i lista adnotacji."""

    def __init__(self, source: Path, base: QImage, annotations: Optional[List[Annotation]] = None):
        self.source = Path(source)
        self.key = storage.slug_for(self.source)
        self.work = storage.work_path(self.source)
        self.sidecar = storage.sidecar_path(self.source)
        self.thumb = storage.thumb_path(self.source)
        self.base = base
        self.annotations: List[Annotation] = annotations or []
        self.levels: List[QImage] = [base]
        self.dirty = False
        self.saved_at: float = 0.0
        self.loaded_at: float = time.time()

    # --- geometria obrazu ------------------------------------------------
    @property
    def width(self) -> int:
        return self.base.width()

    @property
    def height(self) -> int:
        return self.base.height()

    def build_pyramid(self, min_px: int = config.PYRAMID_MIN_PX) -> None:
        """Buduje poziomy o połowę mniejsze aż najdłuższy bok spadnie poniżej min_px."""
        level = self.base
        while max(level.width(), level.height()) > min_px and level.width() > 2 and level.height() > 2:
            level = level.scaled(
                QSize(max(1, level.width() // 2), max(1, level.height() // 2)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.levels.append(level)

    def pick_level(self, scale: float) -> Tuple[QImage, int]:
        """Poziom piramidy, z którego rysować, oraz jego mnożnik (2**poziom)."""
        level = 0
        if scale < 0.5 and scale > 0:
            level = int(math.ceil(math.log2(0.5 / scale)))
        level = max(0, min(level, len(self.levels) - 1))
        return self.levels[level], (1 << level)

    def snapshot(self) -> List[dict]:
        return [a.to_dict() for a in self.annotations]


# --- ładowanie w tle ------------------------------------------------------

class ImageLoader(QThread):
    """Dekoduje obraz i buduje piramidę poza wątkiem UI (10k+ pliki to kilka sekund)."""

    loaded = Signal(object)   # Document
    failed = Signal(str)

    def __init__(self, source: Path, parent=None):
        super().__init__(parent)
        self.source = Path(source)

    def run(self) -> None:  # noqa: D102 - kontrakt QThread
        try:
            if not self.source.exists():
                raise FileNotFoundError(f"Nie ma pliku: {self.source}")
            reader = QImageReader(str(self.source))
            reader.setAutoTransform(True)
            img = reader.read()
            if img.isNull():
                raise RuntimeError(f"Nie mogę odczytać obrazu ({reader.errorString()})")
            if img.format() != QImage.Format.Format_ARGB32:
                img = img.convertToFormat(QImage.Format.Format_ARGB32)
            annotations = [Annotation.from_dict(d) for d in storage.read_annotations(storage.sidecar_path(self.source))]
            doc = Document(self.source, img, annotations)
            doc.build_pyramid()
            # Miniatura od razu — pozycja pojawia się w "ostatnich" nawet bez edycji
            storage.write_thumbnail(img, doc.thumb)
            self.loaded.emit(doc)
        except Exception as exc:  # pragma: no cover - ścieżka awaryjna
            self.failed.emit(str(exc))


# --- autozapis ------------------------------------------------------------

@dataclass
class SaveJob:
    key: str
    base: QImage
    annotations: List[dict]
    work: Path
    sidecar: Path
    thumb: Path
    source: str


class Saver(QObject):
    """Wątek zapisu: wypala adnotacje w obraz i nadpisuje plik roboczy."""

    saved = Signal(str, bool, str)   # key, ok, komunikat

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cond = threading.Condition()
        self._jobs: Dict[str, SaveJob] = {}
        self._busy = False
        self._closing = False
        self._buffer: Optional[QImage] = None
        self._thread = threading.Thread(target=self._loop, name="imagenotes-saver", daemon=True)
        self._thread.start()

    # --- API -------------------------------------------------------------
    def submit(self, job: SaveJob) -> None:
        with self._cond:
            self._jobs[job.key] = job
            self._cond.notify_all()

    def has_pending(self) -> bool:
        with self._cond:
            return bool(self._jobs) or self._busy

    def flush(self, timeout: float = 20.0) -> bool:
        """Czeka, aż kolejka zapisu będzie pusta (używane przy zamykaniu/zmianie zdjęcia)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while (self._jobs or self._busy) and time.monotonic() < deadline:
                self._cond.wait(0.05)
            return not self._jobs and not self._busy

    def shutdown(self, timeout: float = 20.0) -> None:
        self.flush(timeout)
        with self._cond:
            self._closing = True
            self._cond.notify_all()
        self._thread.join(timeout=2.0)

    # --- wnętrze ---------------------------------------------------------
    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._jobs and not self._closing:
                    self._cond.wait(0.2)
                if self._closing and not self._jobs:
                    return
                jobs = list(self._jobs.values())
                self._jobs.clear()
                self._busy = True
            try:
                for job in jobs:
                    self._process(job)
            finally:
                with self._cond:
                    self._busy = False
                    self._cond.notify_all()

    def _process(self, job: SaveJob) -> None:
        try:
            buffer = self._buffer
            if buffer is None or buffer.size() != job.base.size():
                buffer = QImage(job.base.size(), QImage.Format.Format_ARGB32)
                self._buffer = buffer
            painter = QPainter(buffer)
            if config.SAVE_FORMAT.upper() == "JPEG" and job.base.hasAlphaChannel():
                # JPEG nie ma kanału alfa — przezroczystość komponujemy na biało
                buffer.fill(QColor(255, 255, 255))
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                painter.drawImage(0, 0, job.base)
            else:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                painter.drawImage(0, 0, job.base)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            render_annotations(painter, [Annotation.from_dict(d) for d in job.annotations])
            painter.end()

            job.work.parent.mkdir(parents=True, exist_ok=True)
            tmp = job.work.with_name(job.work.name + ".tmp")
            if not _write_image(buffer, tmp):
                raise RuntimeError("zapis obrazu nie powiódł się")
            os.replace(tmp, job.work)          # podmiana atomowa — brak uszkodzonych plików

            storage.write_thumbnail(buffer, job.thumb)
            storage.write_sidecar(job.sidecar, Path(job.source), job.annotations, job.key)
            self.saved.emit(job.key, True, str(job.work))
        except Exception as exc:
            self.saved.emit(job.key, False, str(exc))


def make_job(doc: Document) -> SaveJob:
    return SaveJob(
        key=doc.key,
        base=doc.base,
        annotations=doc.snapshot(),
        work=doc.work,
        sidecar=doc.sidecar,
        thumb=doc.thumb,
        source=str(doc.source),
    )
