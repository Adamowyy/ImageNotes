"""Bootstrap aplikacji: pojedyncza instancja, ciemny motyw, otwieranie pliku z argumentu."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import config, storage
from .window import MainWindow

IPC_NAME = os.environ.get("IMAGENOTES_IPC") or f"ImageNotes-{os.environ.get('USERNAME', 'user')}"
IPC_TIMEOUT_MS = 400


def _target_from_args(argv: List[str]) -> Optional[Path]:
    """Wyciąga ścieżkę zdjęcia z argumentów (obsługuje też `--open <plik>`)."""
    args = list(argv)
    if "--open" in args:
        index = args.index("--open")
        if index + 1 < len(args):
            candidate = Path(args[index + 1])
            if candidate.exists():
                return candidate
    for raw in args[1:]:
        if raw.startswith("-"):
            continue
        candidate = Path(raw)
        if candidate.exists() and candidate.suffix.lower() in config.IMAGE_SUFFIXES:
            return candidate
    return None


def _send_to_running_instance(target: Optional[Path]) -> bool:
    """Próbuje przekazać ścieżkę do działającej instancji. True = przekazano i wychodzimy."""
    socket = QLocalSocket()
    socket.connectToServer(IPC_NAME)
    if not socket.waitForConnected(IPC_TIMEOUT_MS):
        return False
    payload = (str(target) if target is not None else "").encode("utf-8")
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(IPC_TIMEOUT_MS)
    socket.disconnectFromServer()
    return True


def _start_ipc_server(window: MainWindow) -> Optional[QLocalServer]:
    """Serwer lokalnego gniazda: kolejny start aplikacji tylko otwiera zdjęcie tutaj."""
    try:
        QLocalServer.removeServer(IPC_NAME)   # osierocony socket po ewentualnym crashu
        server = QLocalServer(window)
        if not server.listen(IPC_NAME):
            return None

        def on_connection() -> None:
            sock = server.nextPendingConnection()
            if sock is None:
                return
            try:
                sock.waitForReadyRead(IPC_TIMEOUT_MS)
                payload = bytes(sock.readAll()).decode("utf-8", "replace").strip()
            finally:
                sock.disconnectFromServer()
                sock.deleteLater()
            if payload:
                window.open_image(payload)
            else:
                window._raise()

        server.newConnection.connect(on_connection)
        return server
    except Exception:
        return None


def _dark_palette() -> QPalette:
    """Ciemny motyw (Fusion), żeby okna dialogowe nie raziły bielą."""
    palette = QPalette()
    base = QColor(26, 27, 31)
    alt = QColor(36, 38, 43)
    text = QColor(232, 233, 237)
    palette.setColor(QPalette.ColorRole.Window, base)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, QColor(18, 19, 23))
    palette.setColor(QPalette.ColorRole.AlternateBase, alt)
    palette.setColor(QPalette.ColorRole.ToolTipBase, alt)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, alt)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 90, 90))
    palette.setColor(QPalette.ColorRole.Link, QColor(255, 212, 0))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(255, 212, 0))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(20, 20, 24))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(130, 130, 140))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(130, 130, 140))
    return palette


def main(argv: Optional[List[str]] = None) -> int:
    config.ensure_dirs()
    storage.cleanup_temp_files()   # po crashu mogły zostać pliki .tmp
    args = list(sys.argv if argv is None else argv)
    target = _target_from_args(args)

    app = QApplication(args)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    icon_file = config.ASSETS_DIR / "imagenotes.ico"
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    # Druga instancja tylko przekazuje ścieżkę i kończy pracę
    if _send_to_running_instance(target):
        return 0

    settings = config.load_settings()
    window = MainWindow(settings, target)
    server = _start_ipc_server(window)   # trzymamy referencję przez cały czas życia aplikacji
    window.show()
    window.raise_()
    window.activateWindow()
    code = app.exec()
    if server is not None:
        server.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
