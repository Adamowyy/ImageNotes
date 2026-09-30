"""Generuje ikonę aplikacji (assets/imagenotes.ico + .png) bez zależności zewnętrznych."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

from imagenotes import config  # noqa: E402

SIZES = (16, 32, 48, 64, 128, 256)
BASE = 256


def render_icon(size: int = BASE) -> QImage:
    """Rysuje ikonę w zadanym rozmiarze (baza 256 px, potem skalowanie)."""
    img = QImage(BASE, BASE, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # tło: ciemny zaokrąglony kwadrat z delikatnym gradientem
    bg = QLinearGradient(0, 0, 0, BASE)
    bg.setColorAt(0.0, QColor("#2b2f38"))
    bg.setColorAt(1.0, QColor("#15171c"))
    painter.setBrush(bg)
    painter.setPen(QPen(QColor(255, 255, 255, 45), 3))
    painter.drawRoundedRect(QRectF(6, 6, BASE - 12, BASE - 12), 54, 54)

    # "kartka mapy"
    sheet = QRectF(46, 52, 164, 152)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#e9ebf1"))
    painter.drawRoundedRect(sheet, 14, 14)

    # drogi / siatka na mapie
    painter.setPen(QPen(QColor("#b9c0cd"), 7))
    painter.drawLine(QPointF(70, 170), QPointF(150, 92))
    painter.setPen(QPen(QColor("#cdd3dd"), 5))
    painter.drawLine(QPointF(66, 100), QPointF(192, 148))
    # "góry"
    mountains = QPainterPath()
    mountains.moveTo(70, 190)
    mountains.lineTo(118, 138)
    mountains.lineTo(150, 172)
    mountains.lineTo(172, 152)
    mountains.lineTo(196, 190)
    mountains.closeSubpath()
    painter.setBrush(QColor("#9aa3b2"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(mountains)

    # czerwona strzałka-notatka (czytelna nawet w 16 px)
    pen = QPen(QColor("#ff2d2d"), 26)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(178, 196), QPointF(96, 96))
    head = QPainterPath()
    head.moveTo(88, 86)
    head.lineTo(136, 92)
    head.lineTo(96, 134)
    head.closeSubpath()
    painter.setBrush(QColor("#ff2d2d"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(head)

    painter.end()
    if size != BASE:
        img = img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return img


def png_bytes(img: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    return bytes(buffer.data())


def write_ico(path: Path, images) -> None:
    """Składa wielorozmiarowy plik ICO z payloadów PNG."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    directory = b""
    payload = b""
    offset = 6 + 16 * count
    for size, data in images:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        payload += data
    path.write_bytes(header + directory + payload)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - wymagane przez QPainter
    config.ensure_dirs()
    images = [(size, png_bytes(render_icon(size))) for size in SIZES]
    ico_path = config.ASSETS_DIR / "imagenotes.ico"
    write_ico(ico_path, images)
    render_icon(BASE).save(str(config.ASSETS_DIR / "imagenotes.png"), "PNG")
    print(f"Ikona: {ico_path} ({ico_path.stat().st_size} B, {len(images)} rozmiarow)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
