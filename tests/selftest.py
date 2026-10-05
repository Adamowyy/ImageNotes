"""ImageNotes self-test: the model, interaction, autosave and performance, for real."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QImageReader, QMouseEvent, QPainter, QPen, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from imagenotes import config, storage  # noqa: E402
from imagenotes.annotations import (  # noqa: E402
    KIND_ARROW,
    KIND_CHECK,
    KIND_CROSS,
    KIND_STROKE,
    KIND_TEXT,
    Annotation,
    render_annotations,
)
from imagenotes.canvas import (  # noqa: E402
    TOOL_ARROW,
    TOOL_CHECK,
    TOOL_CROSS,
    TOOL_SELECT,
    TOOL_STROKE,
    TOOL_TEXT,
    CanvasWidget,
)
from imagenotes.document import Document, ImageLoader, Saver, make_job  # noqa: E402
from imagenotes.window import MainWindow  # noqa: E402

RESULTS: list = []
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def check(name: str, ok: bool, info: str = "") -> None:
    RESULTS.append((name, bool(ok), info))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   [{info}]" if info else ""), flush=True)


def wait_for(predicate, timeout: float = 90.0, app=None) -> bool:
    app = app or QApplication.instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def setup_temp_dirs() -> Path:
    base = Path(tempfile.gettempdir()) / "imagenotes_selftest"
    shutil.rmtree(base, ignore_errors=True)
    (base / "workspace").mkdir(parents=True, exist_ok=True)
    (base / "workspace" / ".thumbs").mkdir(parents=True, exist_ok=True)
    config.WORKSPACE_DIR = base / "workspace"
    config.THUMBS_DIR = base / "workspace" / ".thumbs"
    config.SETTINGS_FILE = base / "settings.json"
    config.ensure_dirs()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return base


def make_sample_image(path: Path, width: int = 1600, height: int = 1000) -> Path:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#f4f5f7"))
    painter = QPainter(img)
    painter.setPen(QPen(QColor("#c8ccd4"), 2))
    for x in range(0, width, 100):
        painter.drawLine(x, 0, x, height)
    for y in range(0, height, 100):
        painter.drawLine(0, y, width, y)
    painter.setPen(QPen(QColor("#5a6472"), 6))
    painter.drawRect(40, 40, width - 80, height - 80)
    painter.end()
    img.save(str(path), "PNG")
    return path


def mouse_event(kind, pos: QPointF, button=Qt.MouseButton.LeftButton, buttons=None, modifiers=Qt.KeyboardModifier.NoModifier):
    if kind == QEvent.Type.MouseButtonPress:
        buttons = button
    elif kind == QEvent.Type.MouseButtonRelease:
        buttons = Qt.MouseButton.NoButton
    return QMouseEvent(kind, pos, pos, button, buttons if buttons is not None else Qt.MouseButton.NoButton, modifiers)


# A. annotation model: serialization, geometry, baking into the image
def test_model() -> dict:
    img = QImage(800, 500, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.white)

    items = [
        Annotation(kind=KIND_TEXT, p1=QPointF(60, 120), text="NOTATKA", color="#ff2d2d", size=64, angle=0),
        Annotation(kind=KIND_ARROW, p1=QPointF(100, 300), p2=QPointF(400, 380), color="#2bff5a", width=12),
        Annotation(kind=KIND_CROSS, p1=QPointF(500, 60), p2=QPointF(620, 180), color="#ffd400", width=10),
        Annotation(kind=KIND_CHECK, p1=QPointF(500, 260), p2=QPointF(660, 420), color="#2ba7ff", width=10),
        Annotation(kind=KIND_STROKE, p1=QPointF(200, 430), points=[QPointF(200, 430), QPointF(260, 460), QPointF(320, 420)], color="#111111", width=8),
        Annotation(kind=KIND_TEXT, p1=QPointF(60, 200), text="Kąt 45°", color="#ffffff", size=48, angle=45),
    ]

    # serialize both ways
    round_trip = [Annotation.from_dict(d) for d in [a.to_dict() for a in items]]
    same = all(
        a.kind == b.kind and a.text == b.text and abs(a.p1.x() - b.p1.x()) < 1e-6 and a.color == b.color
        for a, b in zip(items, round_trip)
    )
    check("A1 annotation serialization (JSON round-trip)", same)

    # hit tests, one per type, so a failure names itself
    check("A2a hit: text", items[0].hits(QPointF(70, 110), 4) and not items[0].hits(QPointF(700, 480), 4))
    check("A2b hit: arrow", items[1].hits(QPointF(250, 340), 4) and not items[1].hits(QPointF(100, 100), 4))
    check("A2c hit: cross", items[2].hits(QPointF(560, 120), 4))
    check("A2d hit: checkmark", items[3].hits(QPointF(605, 341), 4))
    check("A2e hit: freehand stroke", items[4].hits(QPointF(260, 460), 4) and not items[4].hits(QPointF(600, 430), 4))

    # move and bounds
    before = items[1].p1.x()
    items[1].move(25, -10)
    check("A3 annotation move", abs(items[1].p1.x() - (before + 25)) < 1e-6)

    bounds_ok = items[0].bounds().width() > 50 and items[2].bounds().width() > 100
    check("A4 bounds (for selection)", bounds_ok)

    # bake into the image, then check the actual pixels
    painter = QPainter(img)
    render_annotations(painter, items)
    painter.end()

    def has_color(x0, y0, x1, y1, predicate) -> bool:
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                if predicate(QColor(img.pixel(x, y))):
                    return True
        return False

    red = has_color(60, 60, 320, 130, lambda c: c.red() > 170 and c.green() < 110)
    green = has_color(150, 320, 340, 370, lambda c: c.green() > 170 and c.red() < 120)
    yellow = has_color(500, 70, 620, 180, lambda c: c.red() > 190 and c.green() > 170 and c.blue() < 120)
    check("A5 render: text/arrow/cross visible in the pixels", red and green and yellow)

    # arrow head: the shaft must not stick out past the tip (a rounded line cap
    # poked through a head that tapers down to nothing)
    tip_img = QImage(1000, 220, QImage.Format.Format_ARGB32)
    tip_img.fill(Qt.GlobalColor.white)
    arrow = Annotation(kind=KIND_ARROW, p1=QPointF(60, 110), p2=QPointF(900, 110), color="#ff2d2d", width=40)
    tip_painter = QPainter(tip_img)
    render_annotations(tip_painter, [arrow])
    tip_painter.end()
    leaking = 0
    for x in range(902, 960):
        for y in range(60, 160):
            color = QColor(tip_img.pixel(x, y))
            if color.red() > 200 and color.green() < 160:
                leaking += 1
    check("A6 the shaft does not stick out past the arrow tip", leaking == 0, f"{leaking} px past the tip")
    return {"rendered": img}


# B. document: mipmap pyramid and level picking
def test_document() -> None:
    img = QImage(6000, 4000, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    doc = Document(Path("C:/test/demo.png"), img, [])
    started = time.perf_counter()
    doc.build_pyramid()
    elapsed = time.perf_counter() - started
    check("B1 mipmap pyramid (6000x4000)", len(doc.levels) >= 3, f"{len(doc.levels)} levels, {elapsed:.2f}s")

    _, factor_fit = doc.pick_level(0.15)
    _, factor_zoom = doc.pick_level(4.0)
    check("B2 level pick: zoomed out uses a mipmap, zoomed in the full resolution",
          factor_fit > 1 and factor_zoom == 1, f"fit x{factor_fit}, zoom x{factor_zoom}")


# C. canvas: right-button pan, zoom under the cursor, text editing
def test_canvas() -> None:
    canvas = CanvasWidget()
    canvas.resize(900, 600)
    canvas.show()

    img = QImage(4000, 2000, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    doc = Document(Path("C:/test/canvas.png"), img, [])
    doc.levels = [img]
    canvas.set_document(doc)

    # --- right-button pan ---
    origin_before = QPointF(canvas._origin)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(400, 300), Qt.MouseButton.RightButton))
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(500, 360), Qt.MouseButton.RightButton))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(500, 360), Qt.MouseButton.RightButton))
    dx = canvas._origin.x() - origin_before.x()
    dy = canvas._origin.y() - origin_before.y()
    check("C1 right-button pan (1:1 with the mouse)", abs(dx - 100) < 1e-6 and abs(dy - 60) < 1e-6, f"dx={dx:.0f}, dy={dy:.0f}")

    # --- zoom under the cursor ---
    anchor = QPointF(650.0, 250.0)
    before = canvas.to_image(anchor)
    wheel = QWheelEvent(anchor, anchor, QPoint(0, 0), QPoint(0, 360), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    canvas.wheelEvent(wheel)
    after = canvas.to_image(anchor)
    drift = max(abs(before.x() - after.x()), abs(before.y() - after.y()))
    check("C2 zoom under the cursor (the point under the mouse stays put)", drift < 0.5 and canvas.scale > 0, f"zoom={canvas.scale:.3f}, drift={drift:.3f}px")

    # --- text: click, type, commit ---
    canvas.set_tool(TOOL_TEXT)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(300, 200)))
    editor_visible = canvas._editor.isVisible()
    canvas._editor.setText("Notatka")
    canvas.commit_edit()
    texts = [a for a in doc.annotations if a.kind == KIND_TEXT and a.text == "Notatka"]
    check("C3 text: editor opens and Enter/click commits", editor_visible and len(texts) == 1,
          f"annotations: {len(doc.annotations)}")
    check("C4 autosave requested after the edit", doc.dirty)

    # --- select and drag with the mouse ---
    canvas.set_tool(TOOL_SELECT)
    anno = doc.annotations[0]
    press_pt = canvas.to_screen(QPointF(anno.p1.x() + 20, anno.p1.y() - 20))   # a point inside the glyphs
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, press_pt))
    selected = canvas.selection is anno
    start_p1 = QPointF(anno.p1)
    target_pt = QPointF(press_pt.x() + 120, press_pt.y() + 60)
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, target_pt))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, target_pt))
    moved = anno.p1.x() - start_p1.x()
    expected = 120.0 / canvas.scale
    check("C5 select and drag a text with the mouse", selected and abs(moved - expected) < 2.0,
          f"moved={moved:.1f}px (expected {expected:.1f}px)")

    # --- colour, size and angle of the selected text ---
    canvas.set_color("#2bff5a")
    canvas.set_size(120)
    canvas.set_angle(90)
    anno = doc.annotations[0]
    check("C6 colour/size/angle of the selected text",
          anno.color == "#2bff5a" and anno.size == 120 and abs(anno.angle - 90) < 1e-6)

    # --- delete and undo ---
    canvas.delete_selection()
    removed = len(doc.annotations) == 0
    canvas.undo()
    restored = len(doc.annotations) == 1
    check("C7 delete (Del) and undo (Ctrl+Z)", removed and restored)

    # --- shapes from dragging and freehand ---
    for tool, kind in ((TOOL_ARROW, KIND_ARROW), (TOOL_CROSS, KIND_CROSS), (TOOL_CHECK, KIND_CHECK)):
        canvas.set_tool(tool)
        canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(500, 300)))
        canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(700, 400)))
        canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(700, 400)))
    canvas.set_tool(TOOL_STROKE)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(200, 400)))
    for x in range(210, 400, 10):
        canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(x, 400 + (x % 30))))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(400, 410)))
    kinds = {a.kind for a in doc.annotations}
    check("C8 shapes (arrow/cross/check) + freehand",
          {KIND_ARROW, KIND_CROSS, KIND_CHECK, KIND_STROKE}.issubset(kinds), f"kinds: {sorted(kinds)}")

    # --- a click without dragging still creates a visible shape ---
    canvas.set_tool(TOOL_ARROW)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(760, 480)))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(760, 480)))
    last = doc.annotations[-1]
    check("C9 a single click still creates a visible shape", last.p2 is not None and abs(last.p2.x() - last.p1.x()) > 1)


# D. autosave: overwriting the same file, the sidecar, no leftovers
def test_autosave(app) -> None:
    tmp = ARTIFACTS / "autosave"
    tmp.mkdir(parents=True, exist_ok=True)
    src = make_sample_image(tmp / "sample.png", 1200, 800)

    saver = Saver()
    saved_events: list = []
    saver.saved.connect(lambda key, ok, message: saved_events.append((key, ok, message)))

    img = QImage(str(src))
    doc = Document(src, img.convertToFormat(QImage.Format.Format_ARGB32), [
        Annotation(kind=KIND_TEXT, p1=QPointF(50, 80), text="pierwszy", color="#ff2d2d", size=48)
    ])
    saver.submit(make_job(doc))
    ok1 = wait_for(lambda: bool(saved_events), 30, app)

    doc.annotations.append(Annotation(kind=KIND_ARROW, p1=QPointF(100, 200), p2=QPointF(400, 300), color="#2bff5a", width=14))
    saved_events.clear()
    saver.submit(make_job(doc))
    ok2 = wait_for(lambda: bool(saved_events), 30, app)
    saver.shutdown(10)

    files = sorted(p.name for p in config.WORKSPACE_DIR.iterdir() if p.is_file())
    images = [f for f in files if f.endswith(config.SAVE_SUFFIX)]
    sidecars = [f for f in files if f.endswith(".json")]
    check("D1 save after the edit (two writes in a row)", ok1 and ok2 and all(e[1] for e in saved_events), f"files: {files}")
    check("D2 no pile-up of files (one image + one sidecar, thumbnail separate)",
          len(images) == 1 and len(sidecars) == 1, f"{len(files)} files in workspace")

    written = QImage(str(doc.work))
    check("D3 the saved image keeps full resolution and loads back",
          written.size() == QSize(1200, 800), str(written.size()))

    # are both annotations actually baked into the file
    def pixel_has(x0, y0, x1, y1, predicate) -> bool:
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                if predicate(QColor(written.pixel(x, y))):
                    return True
        return False

    baked = pixel_has(45, 30, 260, 90, lambda c: c.red() > 170 and c.green() < 110) and \
        pixel_has(150, 230, 300, 280, lambda c: c.green() > 170 and c.red() < 120)
    check("D4 annotations baked into the saved file", baked)

    # the sidecar allows going back to editing objects
    raw = storage.read_annotations(doc.sidecar)
    check("D5 the sidecar keeps the annotations editable", len(raw) == 2, f"{len(raw)} annotations")

    # back to the session: reloading the source restores the annotations
    annotations = [Annotation.from_dict(d) for d in raw]
    texts = [a.text for a in annotations if a.kind == KIND_TEXT]
    check("D6 reopening the image restores the notes", texts == ["pierwszy"], str(texts))

    entries = storage.recent_entries(5)
    check("D7 the recent list sees the saved file", any(e.key == doc.key for e in entries), f"{len(entries)} entries")


# E. window: corner overlays, drag & drop, screenshot
def test_window(app) -> None:
    tmp = ARTIFACTS / "window"
    tmp.mkdir(parents=True, exist_ok=True)
    src = make_sample_image(tmp / "view.png", 2000, 1250)

    settings = dict(config.DEFAULTS)
    window = MainWindow(settings, src)
    window.resize(1400, 900)
    window.show()

    loaded = wait_for(lambda: window.canvas.document is not None, 30, app)
    check("E1 the window loads the image in the background and shows it", loaded)

    doc_before = window.canvas.document
    check("E1b merely opening an image creates no working copy",
          doc_before is not None and not doc_before.work.exists() and not doc_before.sidecar.exists())

    window.canvas.set_tool(TOOL_TEXT)
    window.canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(300, 260)))
    window.canvas._editor.setText("Notatka")
    window.canvas.commit_edit()
    window.canvas.set_tool(TOOL_ARROW)
    window.canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(500, 300)))
    window.canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(760, 460)))
    window.canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(760, 460)))
    window.canvas.set_tool(TOOL_STROKE)
    window.canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(200, 600)))
    for x in range(210, 520, 12):
        window.canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(x, 600 + int(40 * ((x % 60) / 60.0)))))
    window.canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(520, 620)))
    app.processEvents()

    # overlays: panel top-right, bubble top-left
    canvas = window.canvas
    panel = window.panel
    bubble = window.bubble
    right_gap = canvas.width() - (panel.x() + panel.width())
    panel_ok = 8 <= right_gap <= 16 and panel.y() <= 16
    bubble_ok = bubble.x() <= 16 and bubble.y() <= 16
    check("E2 the tool panel floats in the top-right corner", panel_ok, f"gap={right_gap}px, y={panel.y()}")
    check("E3 the recent-images bubble sits in the top-left corner", bubble_ok, f"({bubble.x()},{bubble.y()})")

    # autosave after the edit
    saved = wait_for(lambda: not window.canvas.document.dirty and not window.saver.has_pending(), 60, app)
    check("E4 autosave ran after the edit", saved and window.canvas.document.work.exists())

    shot = window.grab()
    shot_path = ARTIFACTS / "window_main.png"
    shot.save(str(shot_path), "PNG")
    check("E5 window screenshot written", shot_path.exists(), str(shot_path))

    window.close()
    app.processEvents()


# F. performance on a large image (12000x8000, 384 MB in RAM) and the Qt limit
def test_big_image(app) -> None:
    big = QImage(12000, 8000, QImage.Format.Format_ARGB32)
    big.fill(QColor("#eef0f3"))
    painter = QPainter(big)
    painter.setPen(QPen(QColor("#9aa3b2"), 3))
    for x in range(0, 12000, 250):
        painter.drawLine(x, 0, x, 8000)
    for y in range(0, 8000, 250):
        painter.drawLine(0, y, 12000, y)
    painter.end()
    src_path = ARTIFACTS / "map_12k.png"
    t0 = time.perf_counter()
    big.save(str(src_path), "PNG", 30)
    t_encode = time.perf_counter() - t0

    # the source file must load from disk (the Qt allocation limit is raised in config)
    check("F1 12000x8000: a 384 MB image loads from disk",
          QImageReader(str(src_path)).read().size() == QSize(12000, 8000),
          f"Qt limit: {QImageReader.allocationLimit()} MB")

    # the app's full load path (separate thread + pyramid)
    loaded: list = []
    loader = ImageLoader(src_path)
    loader.loaded.connect(lambda d: loaded.append(d))
    loader.failed.connect(lambda m: loaded.append(m))
    loader.start()
    ok_load = wait_for(lambda: bool(loaded), 120, app)
    doc = loaded[0] if ok_load and isinstance(loaded[0], Document) else None
    check("F2 12000x8000: background load + mipmap pyramid",
          isinstance(doc, Document) and len(doc.levels) >= 4,
          f"{len(doc.levels)} levels" if isinstance(doc, Document) else str(loaded[:1]))
    if not isinstance(doc, Document):
        return
    doc.annotations = [
        Annotation(kind=KIND_TEXT, p1=QPointF(400, 400), text="WHERE", color="#ff2d2d", size=220),
        Annotation(kind=KIND_ARROW, p1=QPointF(1000, 1200), p2=QPointF(2400, 900), color="#2bff5a", width=40),
    ]

    canvas = CanvasWidget()
    canvas.resize(1920, 1080)
    canvas.show()
    canvas.set_document(doc)
    frames = 25
    canvas.zoom_to(1.0, QPointF(960, 540))       # 100% zoom
    t0 = time.perf_counter()
    for i in range(frames):
        canvas._origin = QPointF(-i * 25, -i * 12)
        canvas.grab()                            # grab forces a real frame render
    t_paint = (time.perf_counter() - t0) / frames * 1000.0

    canvas.zoom_to(canvas.fit_scale(), QPointF(960, 540))   # the whole map in the window
    t0 = time.perf_counter()
    for i in range(frames):
        canvas._origin = QPointF(-i * 4, -i * 2)
        canvas.grab()
    t_paint_fit = (time.perf_counter() - t0) / frames * 1000.0

    saver = Saver()
    events: list = []
    saver.saved.connect(lambda key, ok, message: events.append((ok, message)))
    t0 = time.perf_counter()
    saver.submit(make_job(doc))
    ok_save = wait_for(lambda: bool(events), 180, app)
    t_save = time.perf_counter() - t0
    saver.shutdown(20)

    written = QImage(str(doc.work))
    check("F3 12000x8000: background save (working file overwritten)",
          ok_save and events and events[0][0] and written.size() == QSize(12000, 8000),
          f"{t_save:.2f}s, message: {events[0][1][:40] if events else 'none'}")
    check("F4 12000x8000: frame at 100% zoom", t_paint < 60,
          f"{t_paint:.1f} ms/frame (~{1000 / max(t_paint, 0.01):.0f} FPS)")
    check("F5 12000x8000: frame with the whole image in the window", t_paint_fit < 90,
          f"{t_paint_fit:.1f} ms/frame (~{1000 / max(t_paint_fit, 0.01):.0f} FPS)")
    print(f"\n  -- rough timings (12k) --  source encode {t_encode:.1f}s · "
          f"frame zoom {t_paint:.1f}ms · frame fit {t_paint_fit:.1f}ms · save {t_save:.2f}s\n", flush=True)


def main() -> int:
    big = "--no-big" not in sys.argv
    setup_temp_dirs()
    app = QApplication.instance() or QApplication([])

    print("=== ImageNotes self-test ===\n", flush=True)
    test_model()
    test_document()
    test_canvas()
    test_autosave(app)
    test_window(app)
    if big:
        test_big_image(app)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n=== result: {len(RESULTS) - len(failed)}/{len(RESULTS)} OK ===", flush=True)
    if failed:
        print("FAILED: " + ", ".join(failed), flush=True)
        return 1
    print("All checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
