"""Main window: the canvas plus its floating overlays, autosave, drag & drop and shortcuts."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from . import config, document, storage
from .canvas import TOOL_ARROW, TOOL_CHECK, TOOL_CROSS, TOOL_SELECT, TOOL_STROKE, TOOL_TEXT, CanvasWidget
from .document import ImageLoader
from .overlay import RecentBubble, RecentPopup, ToolPanel


class MainWindow(QMainWindow):
    """Minimal window: just the image and two floating overlays."""

    def __init__(self, settings: dict, initial_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumSize(700, 460)
        self.setAcceptDrops(True)

        size = settings.get("window") or config.DEFAULTS["window"]
        try:
            self.resize(int(size[0]), int(size[1]))
        except Exception:
            self.resize(1500, 950)

        self.canvas = CanvasWidget(self)
        self.setCentralWidget(self.canvas)

        self.panel = ToolPanel(self.canvas)
        self.bubble = RecentBubble(self.canvas)
        self.popup = RecentPopup(self)

        self.saver = document.Saver(self)
        self.saver.saved.connect(self._on_saved)
        self._loader: Optional[ImageLoader] = None

        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(config.AUTOSAVE_DELAY_MS)
        self._autosave.timeout.connect(self._save_now)

        self._wire()
        self._build_shortcuts()
        self._refresh_bubble()
        self._reposition_overlays()

        if initial_path is not None:
            self.open_image(initial_path)

    # --- signal wiring ---------------------------------------------------
    def _wire(self) -> None:
        self.canvas.edited.connect(self._on_edited)
        self.canvas.selectionChanged.connect(self._sync_selection)
        self.canvas.zoomChanged.connect(lambda _=0.0: self._update_title())
        self.canvas.documentChanged.connect(self._update_title)
        self.canvas.resized.connect(self._reposition_overlays)
        self.canvas.toolRequested.connect(self.panel.set_tool)

        self.panel.toolChanged.connect(self.canvas.set_tool)
        self.panel.colorChanged.connect(self.canvas.set_color)
        self.panel.widthChanged.connect(self.canvas.set_width)
        self.panel.sizeChanged.connect(self.canvas.set_size)
        self.panel.angleChanged.connect(self.canvas.set_angle)
        self.panel.gestureStarted.connect(self.canvas.begin_gesture)
        self.panel.gestureEnded.connect(self.canvas.end_gesture)
        self.panel.undoRequested.connect(self._undo)
        self.panel.redoRequested.connect(self._redo)
        self.panel.deleteRequested.connect(self.canvas.delete_selection)
        self.panel.saveRequested.connect(lambda: self._save_now(force=True))
        self.panel.fitRequested.connect(self.canvas.fit)

        self.bubble.clickedBubble.connect(self._show_recent_popup)
        self.popup.openRequested.connect(self.open_image)
        self.popup.pickRequested.connect(self.choose_file)
        self.popup.folderRequested.connect(self.open_workspace_folder)

    def _build_shortcuts(self) -> None:
        def sc(sequence: str, slot) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

        sc("Ctrl+O", self.choose_file)
        sc("Ctrl+S", lambda: self._save_now(force=True))
        sc("Ctrl+Z", self._undo)
        sc("Ctrl+Shift+Z", self._redo)
        sc("Ctrl+Y", self._redo)
        sc("Ctrl+0", self.canvas.fit)
        sc("Ctrl++", self.canvas.zoom_in)
        sc("Ctrl+=", self.canvas.zoom_in)
        sc("Ctrl+-", self.canvas.zoom_out)
        sc("F11", self._toggle_fullscreen)

    # --- editing / saving ------------------------------------------------
    def _on_edited(self) -> None:
        self.panel.set_state("dirty")
        self._autosave.start()
        self._sync_selection()
        self._update_title()

    def _undo(self) -> None:
        if self.canvas.editing:
            return
        self.canvas.undo()

    def _redo(self) -> None:
        if self.canvas.editing:
            return
        self.canvas.redo()

    def _save_now(self, force: bool = False) -> None:
        """Write the working file. Nothing changed means nothing to write (force = Ctrl+S / button)."""
        doc = self.canvas.document
        if doc is None:
            return
        if not doc.dirty and not force:
            return
        self._autosave.stop()
        self.saver.submit(document.make_job(doc))
        self.panel.set_state("saving")

    def _on_saved(self, key: str, ok: bool, message: str) -> None:
        doc = self.canvas.document
        if doc is not None and doc.key == key:
            if ok:
                doc.dirty = False
                doc.saved_at = time.time()
            self.panel.set_state("saved" if ok else "error", message)
        if ok:
            self._refresh_bubble(reffresh=True)
        else:
            print(f"[ImageNotes] błąd zapisu ({key}): {message}")

    # --- opening images --------------------------------------------------
    def open_image(self, path) -> None:
        path = Path(str(path))
        if not path.exists():
            self._warn(f"Nie ma takiego pliku:\n{path}")
            return
        if path.suffix.lower() not in config.IMAGE_SUFFIXES:
            self._warn(f"Nieobsługiwany format pliku:\n{path.name}")
            return
        current = self.canvas.document
        if current is not None and current.key == storage.slug_for(path):
            self._raise()
            return

        self._save_now()  # close the previous image (the write happens in the background)
        self.canvas.set_message(f"Wczytuj\u0119 {path.name}\u2026")
        self.panel.set_state("idle", str(path))
        self._loader = ImageLoader(path, self)
        self._loader.loaded.connect(self._on_loaded)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.start()
        self._raise()

    def _on_loaded(self, doc) -> None:
        self.canvas.set_document(doc)
        self.panel.set_state("idle", str(doc.work))
        self._refresh_bubble()
        self._reposition_overlays()
        self._update_title()
        self._raise()

    def _on_load_failed(self, message: str) -> None:
        if self.canvas.document is None:
            self.canvas.set_message(
                "Nie uda\u0142o si\u0119 otworzy\u0107 zdj\u0119cia.\n"
                "Przeci\u0105gnij plik tutaj lub wybierz z listy w lewym g\u00f3rnym rogu."
            )
        else:
            self.canvas.set_message("")
        self._warn(message)

    def choose_file(self) -> None:
        last_dir = self.settings.get("last_dir") or str(Path.home() / "Desktop")
        pattern = " ".join(f"*{s}" for s in sorted(config.IMAGE_SUFFIXES))
        path, _ = QFileDialog.getOpenFileName(
            self, "Wybierz zdj\u0119cie", last_dir, f"Zdj\u0119cia ({pattern});;Wszystkie pliki (*)"
        )
        if path:
            self.settings["last_dir"] = str(Path(path).parent)
            config.save_settings(self.settings)
            self.open_image(path)

    def open_workspace_folder(self) -> None:
        config.ensure_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.WORKSPACE_DIR)))

    # --- overlays --------------------------------------------------------
    def _reposition_overlays(self) -> None:
        margin = 12
        self.panel.adjustSize()
        self.panel.move(
            max(margin, self.canvas.width() - self.panel.width() - margin),
            margin,
        )
        self.bubble.move(margin, margin)
        self.panel.raise_()
        self.bubble.raise_()

    def _show_recent_popup(self) -> None:
        self.popup.set_entries(storage.recent_entries(8))
        self.popup.adjustSize()
        pos = self.bubble.mapToGlobal(QPoint(0, self.bubble.height() + 6))
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            pos.setX(min(max(pos.x(), screen.left() + 4), screen.right() - self.popup.width() - 4))
            pos.setY(min(pos.y(), screen.bottom() - self.popup.height() - 4))
        self.popup.move(pos)
        self.popup.show()

    def _refresh_bubble(self, reffresh: bool = False) -> None:
        doc = self.canvas.document
        entry = None
        if doc is not None:
            entry = storage.RecentEntry(
                key=doc.key,
                source=doc.source,
                work=doc.work,
                sidecar=doc.sidecar,
                thumb=doc.thumb,
                saved_at="",
                mtime=0.0,
            )
        else:
            entry = storage.last_entry()
        pixmap = storage.thumb_pixmap(entry, reffresh=reffresh) if entry is not None else None
        self.bubble.set_thumbnail(pixmap)

    def _sync_selection(self) -> None:
        sel = self.canvas.selection
        self.panel.set_has_selection(sel is not None)
        self.panel.set_can_undo(self.canvas.can_undo, self.canvas.can_redo)
        if sel is not None:
            self.panel.set_values(width=sel.width, size=sel.size, angle=sel.angle, color=sel.color)

    def _update_title(self) -> None:
        doc = self.canvas.document
        if doc is None:
            self.setWindowTitle(f"{config.APP_NAME} \u2014 bez zdj\u0119cia \u2022 {config.AUTHOR_CREDIT}")
            return
        zoom = self.canvas.scale * 100.0
        zoom_text = f"{zoom:.0f}%" if zoom >= 10 else f"{zoom:.1f}%"
        dirty = " \u2022" if doc.dirty else ""
        self.setWindowTitle(
            f"{config.APP_NAME} \u2014 {doc.source.name} \u2022 {doc.width}\u00d7{doc.height} \u2022 "
            f"{zoom_text} \u2022 notatki: {len(doc.annotations)}{dirty} \u2022 {config.AUTHOR_CREDIT}"
        )

    # --- drag & drop, closing --------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: D102
        if self._dropped_image(event) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: D102
        if self._dropped_image(event) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: D102
        path = self._dropped_image(event)
        if path is not None:
            event.acceptProposedAction()
            self.open_image(path)

    def _dropped_image(self, event) -> Optional[Path]:
        try:
            mime = event.mimeData()
            if not mime.hasUrls():
                return None
            for url in mime.urls():
                local = url.toLocalFile()
                if local and Path(local).suffix.lower() in config.IMAGE_SUFFIXES:
                    return Path(local)
        except Exception:
            return None
        return None

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event) -> None:  # noqa: D102
        self.popup.hide()
        self._save_now()
        if self.saver.has_pending():
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.saver.shutdown(timeout=45.0)
            self.unsetCursor()
        self.settings["window"] = [self.width(), self.height()]
        config.save_settings(self.settings)
        super().closeEvent(event)

    # --- helpers ---------------------------------------------------------
    def _raise(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, config.APP_NAME, message)
