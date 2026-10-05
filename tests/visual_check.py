"""Visual check on the REAL Qt backend (windows): fonts, layout, HUD."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFontDatabase, QFontInfo, QImage, QMouseEvent, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from imagenotes import config  # noqa: E402
from imagenotes.annotations import font_for, text_local_rect  # noqa: E402
from imagenotes.canvas import TOOL_ARROW, TOOL_CROSS, TOOL_SELECT, TOOL_STROKE, TOOL_TEXT  # noqa: E402
from imagenotes.window import MainWindow  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def sample(path: Path, width: int = 2400, height: int = 1500) -> Path:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#eef1f5"))
    painter = QPainter(img)
    painter.setPen(QPen(QColor("#cfd5de"), 2))
    for x in range(0, width, 120):
        painter.drawLine(x, 0, x, height)
    for y in range(0, height, 120):
        painter.drawLine(0, y, width, y)
    painter.setPen(QPen(QColor("#8a93a1"), 4))
    painter.drawRect(60, 60, width - 120, height - 120)
    painter.setPen(QPen(QColor("#4c88c8"), 8))
    painter.drawLine(200, 1200, 900, 400)
    painter.drawLine(900, 400, 2000, 1100)
    painter.end()
    img.save(str(path), "PNG")
    return path


def press(canvas, pos, button=Qt.MouseButton.LeftButton, kind=QEvent.Type.MouseButtonPress):
    buttons = button if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    canvas.mousePressEvent(QMouseEvent(kind, pos, pos, button, buttons, Qt.KeyboardModifier.NoModifier)) \
        if kind == QEvent.Type.MouseButtonPress else canvas.mouseReleaseEvent(
            QMouseEvent(kind, pos, pos, button, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        )


def move(canvas, pos):
    canvas.mouseMoveEvent(
        QMouseEvent(QEvent.Type.MouseMove, pos, pos, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    )


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else sample(ARTIFACTS / "sample_2400x1500.png")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # The visual check must not litter the real workspace/ or the recent list
    import tempfile
    scratch = Path(tempfile.gettempdir()) / "imagenotes_visual_check"
    (scratch / "workspace" / ".thumbs").mkdir(parents=True, exist_ok=True)
    config.WORKSPACE_DIR = scratch / "workspace"
    config.THUMBS_DIR = scratch / "workspace" / ".thumbs"
    config.SETTINGS_FILE = scratch / "settings.json"
    config.ensure_dirs()

    app = QApplication.instance() or QApplication([])
    print(f"Qt backend: {app.platformName()} | font families: {len(QFontDatabase.families())}")
    print(f"Annotation font: {QFontInfo(font_for(64)).family()!r}")
    box_width = text_local_rect("NOTATKA", 64).width()
    print(f"Width of 'NOTATKA' at 64 px: {box_width:.1f} px "
          f"({'OK - real glyphs' if box_width < 340 else 'SUSPICIOUS - empty boxes'})")

    settings = dict(config.DEFAULTS)
    window = MainWindow(settings, target)
    window.show()
    window.resize(1500, 940)

    def build() -> None:
        canvas = window.canvas
        canvas.zoom_to(canvas.fit_scale())
        # text
        canvas.set_tool(TOOL_TEXT)
        canvas.set_color("#ff2d2d")
        canvas.set_size(140)
        press(canvas, canvas.to_screen(QPointF(300, 380)))
        canvas._editor.setText("Notatka  \u2192  tutaj")
        canvas.commit_edit()
        # second text, rotated
        canvas.set_color("#ffd400")
        canvas.set_size(110)
        canvas.set_angle(0)
        press(canvas, canvas.to_screen(QPointF(1500, 700)))
        canvas._editor.setText("Loot")
        canvas.commit_edit()
        canvas.set_angle(35)
        # arrow
        canvas.set_tool(TOOL_ARROW)
        canvas.set_color("#2bff5a")
        canvas.set_width(22)
        press(canvas, canvas.to_screen(QPointF(700, 1000)))
        move(canvas, canvas.to_screen(QPointF(1250, 620)))
        press(canvas, canvas.to_screen(QPointF(1250, 620)), kind=QEvent.Type.MouseButtonRelease)
        # cross
        canvas.set_tool(TOOL_CROSS)
        canvas.set_color("#ff2d2d")
        canvas.set_width(18)
        press(canvas, canvas.to_screen(QPointF(1750, 300)))
        move(canvas, canvas.to_screen(QPointF(2050, 560)))
        press(canvas, canvas.to_screen(QPointF(2050, 560)), kind=QEvent.Type.MouseButtonRelease)
        # freehand
        canvas.set_tool(TOOL_STROKE)
        canvas.set_color("#2ba7ff")
        canvas.set_width(16)
        press(canvas, canvas.to_screen(QPointF(400, 1150)))
        for step in range(1, 40):
            x = 400 + step * 22
            y = 1150 - int(180 * ((step % 20) / 20.0))
            move(canvas, canvas.to_screen(QPointF(x, y)))
        press(canvas, canvas.to_screen(QPointF(400 + 40 * 22, 1150)), kind=QEvent.Type.MouseButtonRelease)
        canvas.set_tool(TOOL_SELECT)
        window._reposition_overlays()
        app.processEvents()

        window.grab().save(str(ARTIFACTS / "window_real.png"), "PNG")
        print(f"Screenshot: {ARTIFACTS / 'window_real.png'}")

        # second shot: close-up on a note (checks text sharpness at full resolution)
        canvas.zoom_to(0.8, QPointF(canvas.width() * 0.35, canvas.height() * 0.5))
        app.processEvents()
        window.grab().save(str(ARTIFACTS / "window_zoom.png"), "PNG")
        window.close()
        app.quit()

    QTimer.singleShot(1200, build)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
