"""Autotest ImageNotes — realne sprawdzenie modelu, interakcji, autozapisu i wydajności."""

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


# A. model adnotacji: serializacja, geometria, wypalanie w obraz
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

    # serializacja w obie strony
    round_trip = [Annotation.from_dict(d) for d in [a.to_dict() for a in items]]
    same = all(
        a.kind == b.kind and a.text == b.text and abs(a.p1.x() - b.p1.x()) < 1e-6 and a.color == b.color
        for a, b in zip(items, round_trip)
    )
    check("A1 serializacja adnotacji (JSON round-trip)", same)

    # trafienia — każdy typ osobno, żeby od razu było widać co nie działa
    check("A2a trafienie: tekst", items[0].hits(QPointF(70, 110), 4) and not items[0].hits(QPointF(700, 480), 4))
    check("A2b trafienie: strzałka", items[1].hits(QPointF(250, 340), 4) and not items[1].hits(QPointF(100, 100), 4))
    check("A2c trafienie: krzyżyk X", items[2].hits(QPointF(560, 120), 4))
    check("A2d trafienie: checkmark", items[3].hits(QPointF(605, 341), 4))
    check("A2e trafienie: rysunek odręczny", items[4].hits(QPointF(260, 460), 4) and not items[4].hits(QPointF(600, 430), 4))

    # przesuwanie i obrysy
    before = items[1].p1.x()
    items[1].move(25, -10)
    check("A3 przesuwanie adnotacji", abs(items[1].p1.x() - (before + 25)) < 1e-6)

    bounds_ok = items[0].bounds().width() > 50 and items[2].bounds().width() > 100
    check("A4 obrysy (do zaznaczania)", bounds_ok)

    # wypalanie w obraz — sprawdzamy realne piksele
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
    check("A5 render: tekst/strzałka/X widoczne w pikselach", red and green and yellow)

    # grot strzałki: linia nie może wystawać za czubek (zaokrąglony koniec linii
    # przebijał się przez grot zwężający się do zera)
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
    check("A6 linia nie wystaje za czubek grota strzałki", leaking == 0, f"{leaking} pikseli za czubkiem")
    return {"rendered": img}


# B. dokument: piramida mipmap i dobór poziomu
def test_document() -> None:
    img = QImage(6000, 4000, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    doc = Document(Path("C:/test/demo.png"), img, [])
    started = time.perf_counter()
    doc.build_pyramid()
    elapsed = time.perf_counter() - started
    check("B1 piramida mipmap (6000x4000)", len(doc.levels) >= 3, f"{len(doc.levels)} poziomów, {elapsed:.2f}s")

    _, factor_fit = doc.pick_level(0.15)
    _, factor_zoom = doc.pick_level(4.0)
    check("B2 dobór poziomu: oddalenie używa mipmapy, zoom pełnej rozdzielczości",
          factor_fit > 1 and factor_zoom == 1, f"fit x{factor_fit}, zoom x{factor_zoom}")


# C. płótno: panowanie prawym przyciskiem, zoom pod kursorem, edycja tekstu
def test_canvas() -> None:
    canvas = CanvasWidget()
    canvas.resize(900, 600)
    canvas.show()

    img = QImage(4000, 2000, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    doc = Document(Path("C:/test/canvas.png"), img, [])
    doc.levels = [img]
    canvas.set_document(doc)

    # --- panowanie prawym przyciskiem myszy ---
    origin_before = QPointF(canvas._origin)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(400, 300), Qt.MouseButton.RightButton))
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, QPointF(500, 360), Qt.MouseButton.RightButton))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(500, 360), Qt.MouseButton.RightButton))
    dx = canvas._origin.x() - origin_before.x()
    dy = canvas._origin.y() - origin_before.y()
    check("C1 panowanie prawym przyciskiem (1:1 z ruchem myszy)", abs(dx - 100) < 1e-6 and abs(dy - 60) < 1e-6, f"dx={dx:.0f}, dy={dy:.0f}")

    # --- zoom pod kursorem ---
    anchor = QPointF(650.0, 250.0)
    before = canvas.to_image(anchor)
    wheel = QWheelEvent(anchor, anchor, QPoint(0, 0), QPoint(0, 360), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    canvas.wheelEvent(wheel)
    after = canvas.to_image(anchor)
    drift = max(abs(before.x() - after.x()), abs(before.y() - after.y()))
    check("C2 zoom pod kursorem (punkt pod myszką nie ucieka)", drift < 0.5 and canvas.scale > 0, f"zoom={canvas.scale:.3f}, dryf={drift:.3f}px")

    # --- tekst: klik, wpisanie, zatwierdzenie ---
    canvas.set_tool(TOOL_TEXT)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(300, 200)))
    editor_visible = canvas._editor.isVisible()
    canvas._editor.setText("Baza zombie")
    canvas.commit_edit()
    texts = [a for a in doc.annotations if a.kind == KIND_TEXT and a.text == "Baza zombie"]
    check("C3 tekst: pole edycji + zatwierdzenie Enter/klik", editor_visible and len(texts) == 1,
          f"adnotacji: {len(doc.annotations)}")
    check("C4 autozapis zgłoszony po edycji", doc.dirty)

    # --- zaznaczenie i przesunięcie myszką ---
    canvas.set_tool(TOOL_SELECT)
    anno = doc.annotations[0]
    press_pt = canvas.to_screen(QPointF(anno.p1.x() + 20, anno.p1.y() - 20))   # punkt wewnątrz liter
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, press_pt))
    selected = canvas.selection is anno
    start_p1 = QPointF(anno.p1)
    target_pt = QPointF(press_pt.x() + 120, press_pt.y() + 60)
    canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, target_pt))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, target_pt))
    moved = anno.p1.x() - start_p1.x()
    expected = 120.0 / canvas.scale
    check("C5 zaznaczenie i przeciągnięcie tekstu myszką", selected and abs(moved - expected) < 2.0,
          f"przesunięcie={moved:.1f}px (oczekiwane {expected:.1f}px)")

    # --- kolor, rozmiar i kąt dla zaznaczonego tekstu ---
    canvas.set_color("#2bff5a")
    canvas.set_size(120)
    canvas.set_angle(90)
    anno = doc.annotations[0]
    check("C6 zmiana koloru/rozmiaru/kąta zaznaczonego tekstu",
          anno.color == "#2bff5a" and anno.size == 120 and abs(anno.angle - 90) < 1e-6)

    # --- usunięcie i cofnięcie ---
    canvas.delete_selection()
    removed = len(doc.annotations) == 0
    canvas.undo()
    restored = len(doc.annotations) == 1
    check("C7 usunięcie (Del) i cofnięcie (Ctrl+Z)", removed and restored)

    # --- kształty z przeciągania i rysowanie odręczne ---
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
    check("C8 kształty (strzałka/X/check) + rysowanie odręczne",
          {KIND_ARROW, KIND_CROSS, KIND_CHECK, KIND_STROKE}.issubset(kinds), f"rodzaje: {sorted(kinds)}")

    # --- kliknięcie bez przeciągania nadal tworzy widoczny kształt ---
    canvas.set_tool(TOOL_ARROW)
    canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(760, 480)))
    canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, QPointF(760, 480)))
    last = doc.annotations[-1]
    check("C9 pojedynczy klik tworzy widoczny kształt", last.p2 is not None and abs(last.p2.x() - last.p1.x()) > 1)


# D. autozapis: nadpisywanie tego samego pliku, sidecar, brak śmieci
def test_autosave(app) -> None:
    tmp = ARTIFACTS / "autosave"
    tmp.mkdir(parents=True, exist_ok=True)
    src = make_sample_image(tmp / "proba.png", 1200, 800)

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
    check("D1 zapis po edycji (dwa kolejne zapisy)", ok1 and ok2 and all(e[1] for e in saved_events), f"pliki: {files}")
    check("D2 brak mnożenia plików (1 obraz + 1 sidecar, miniatura osobno)",
          len(images) == 1 and len(sidecars) == 1, f"{len(files)} plików w workspace")

    written = QImage(str(doc.work))
    check("D3 zapisany obraz ma pełną rozdzielczość i daje się wczytać",
          written.size() == QSize(1200, 800), str(written.size()))

    # czy obie adnotacje faktycznie są wypalone w pliku
    def pixel_has(x0, y0, x1, y1, predicate) -> bool:
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                if predicate(QColor(written.pixel(x, y))):
                    return True
        return False

    baked = pixel_has(45, 30, 260, 90, lambda c: c.red() > 170 and c.green() < 110) and \
        pixel_has(150, 230, 300, 280, lambda c: c.green() > 170 and c.red() < 120)
    check("D4 adnotacje wypalone w zapisanym pliku", baked)

    # sidecar pozwala wrócić do edycji obiektów
    raw = storage.read_annotations(doc.sidecar)
    check("D5 sidecar zachowuje adnotacje i pozwala edytować dalej", len(raw) == 2, f"{len(raw)} adnotacji")

    # powrót do sesji: ponowne wczytanie źródła odtwarza adnotacje
    annotations = [Annotation.from_dict(d) for d in raw]
    texts = [a.text for a in annotations if a.kind == KIND_TEXT]
    check("D6 ponowne otwarcie zdjęcia odtwarza notatki", texts == ["pierwszy"], str(texts))

    entries = storage.recent_entries(5)
    check("D7 lista ostatnich widzi zapisany plik", any(e.key == doc.key for e in entries), f"{len(entries)} pozycji")


# E. okno: nakładki w narożnikach, drag&drop, zrzut ekranu
def test_window(app) -> None:
    tmp = ARTIFACTS / "window"
    tmp.mkdir(parents=True, exist_ok=True)
    src = make_sample_image(tmp / "widok.png", 2000, 1250)

    settings = dict(config.DEFAULTS)
    window = MainWindow(settings, src)
    window.resize(1400, 900)
    window.show()

    loaded = wait_for(lambda: window.canvas.document is not None, 30, app)
    check("E1 okno wczytuje zdjęcie w tle i pokazuje je", loaded)

    doc_before = window.canvas.document
    check("E1b samo otwarcie zdjęcia nie tworzy kopii roboczej (bez edycji)",
          doc_before is not None and not doc_before.work.exists() and not doc_before.sidecar.exists())

    window.canvas.set_tool(TOOL_TEXT)
    window.canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, QPointF(300, 260)))
    window.canvas._editor.setText("Baza zombie")
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

    # nakładki: panel w prawym górnym, bąbelek w lewym górnym
    canvas = window.canvas
    panel = window.panel
    bubble = window.bubble
    right_gap = canvas.width() - (panel.x() + panel.width())
    panel_ok = 8 <= right_gap <= 16 and panel.y() <= 16
    bubble_ok = bubble.x() <= 16 and bubble.y() <= 16
    check("E2 panel narzędzi lewituje w prawym górnym narożniku", panel_ok, f"odstęp={right_gap}px, y={panel.y()}")
    check("E3 bąbelek ostatnich zdjęć w lewym górnym narożniku", bubble_ok, f"({bubble.x()},{bubble.y()})")

    # autozapis po edycji
    saved = wait_for(lambda: not window.canvas.document.dirty and not window.saver.has_pending(), 60, app)
    check("E4 autozapis zadziałał po edycji", saved and window.canvas.document.work.exists())

    shot = window.grab()
    shot_path = ARTIFACTS / "okno_glowne.png"
    shot.save(str(shot_path), "PNG")
    check("E5 zrzut ekranu okna zapisany", shot_path.exists(), str(shot_path))

    window.close()
    app.processEvents()


# F. wydajność na dużym zdjęciu (12 000 x 8 000, 384 MB w RAM) i limit Qt
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
    src_path = ARTIFACTS / "mapa_12k.png"
    t0 = time.perf_counter()
    big.save(str(src_path), "PNG", 30)
    t_encode = time.perf_counter() - t0

    # plik źródłowy musi dać się wczytać z dysku (limit alokacji Qt podniesiony w config)
    check("F1 12 000 x 8 000: obraz 384 MB wczytuje się z dysku",
          QImageReader(str(src_path)).read().size() == QSize(12000, 8000),
          f"limit Qt: {QImageReader.allocationLimit()} MB")

    # pełna ścieżka wczytywania aplikacji (osobny wątek + piramida)
    loaded: list = []
    loader = ImageLoader(src_path)
    loader.loaded.connect(lambda d: loaded.append(d))
    loader.failed.connect(lambda m: loaded.append(m))
    loader.start()
    ok_load = wait_for(lambda: bool(loaded), 120, app)
    doc = loaded[0] if ok_load and isinstance(loaded[0], Document) else None
    check("F2 12 000 x 8 000: wczytanie w tle + piramida mipmap",
          isinstance(doc, Document) and len(doc.levels) >= 4,
          f"{len(doc.levels)} poziomów" if isinstance(doc, Document) else str(loaded[:1]))
    if not isinstance(doc, Document):
        return
    doc.annotations = [
        Annotation(kind=KIND_TEXT, p1=QPointF(400, 400), text="GDZIE", color="#ff2d2d", size=220),
        Annotation(kind=KIND_ARROW, p1=QPointF(1000, 1200), p2=QPointF(2400, 900), color="#2bff5a", width=40),
    ]

    canvas = CanvasWidget()
    canvas.resize(1920, 1080)
    canvas.show()
    canvas.set_document(doc)
    frames = 25
    canvas.zoom_to(1.0, QPointF(960, 540))       # zoom 100%
    t0 = time.perf_counter()
    for i in range(frames):
        canvas._origin = QPointF(-i * 25, -i * 12)
        canvas.grab()                            # grab wymusza realne rysowanie klatki
    t_paint = (time.perf_counter() - t0) / frames * 1000.0

    canvas.zoom_to(canvas.fit_scale(), QPointF(960, 540))   # cała mapa w oknie
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
    check("F3 12 000 x 8 000: zapis w tle (nadpisanie pliku roboczego)",
          ok_save and events and events[0][0] and written.size() == QSize(12000, 8000),
          f"{t_save:.2f}s, komunikat: {events[0][1][:40] if events else 'brak'}")
    check("F4 12 000 x 8 000: klatka przy zoomie 100%", t_paint < 60,
          f"{t_paint:.1f} ms/klatkę (≈{1000 / max(t_paint, 0.01):.0f} FPS)")
    check("F5 12 000 x 8 000: klatka przy całości w oknie", t_paint_fit < 90,
          f"{t_paint_fit:.1f} ms/klatkę (≈{1000 / max(t_paint_fit, 0.01):.0f} FPS)")
    print(f"\n  ── orientacyjne czasy (12k) ──  miniatura-źródło {t_encode:.1f}s · "
          f"klatka zoom {t_paint:.1f}ms · klatka fit {t_paint_fit:.1f}ms · zapis {t_save:.2f}s\n", flush=True)


def main() -> int:
    big = "--no-big" not in sys.argv
    setup_temp_dirs()
    app = QApplication.instance() or QApplication([])

    print("=== ImageNotes — autotest ===\n", flush=True)
    test_model()
    test_document()
    test_canvas()
    test_autosave(app)
    test_window(app)
    if big:
        test_big_image(app)

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n=== wynik: {len(RESULTS) - len(failed)}/{len(RESULTS)} OK ===", flush=True)
    if failed:
        print("NIEUDANE: " + ", ".join(failed), flush=True)
        return 1
    print("Wszystkie sprawdzenia przeszły.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
