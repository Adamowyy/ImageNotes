"""Canvas: displays huge images, pans with the right button and hosts the annotations."""

from __future__ import annotations

import math
from typing import List, Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QLineEdit, QWidget

from . import config
from .annotations import (
    KIND_ARROW,
    KIND_CHECK,
    KIND_CROSS,
    KIND_STROKE,
    KIND_TEXT,
    Annotation,
    draw_selection,
    pick_annotation,
)

TOOL_SELECT = "select"
TOOL_TEXT = "text"
TOOL_ARROW = "arrow"
TOOL_CROSS = "cross"
TOOL_CHECK = "check"
TOOL_STROKE = "stroke"
TOOLS = (TOOL_SELECT, TOOL_TEXT, TOOL_ARROW, TOOL_CROSS, TOOL_CHECK, TOOL_STROKE)

DRAW_TOOLS = (TOOL_ARROW, TOOL_CROSS, TOOL_CHECK)

MAX_ZOOM = 64.0
UNDO_DEPTH = 120


class _TextEditor(QLineEdit):
    """Single-line annotation editor (Esc cancels, Enter/focus loss commits)."""

    escapePressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: D102
        if event.key() == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            return
        super().keyPressEvent(event)


class CanvasWidget(QWidget):
    """Image view with annotations."""

    edited = Signal()             # anything changed -> autosave
    selectionChanged = Signal()
    zoomChanged = Signal(float)
    documentChanged = Signal()
    resized = Signal()
    toolRequested = Signal(str)   # tool changed from the keyboard -> sync the panel

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._doc = None
        self._tool = TOOL_SELECT
        self._color = config.DEFAULT_COLOR
        self._width = config.DEFAULT_WIDTH
        self._size = config.DEFAULT_TEXT_SIZE
        self._angle = float(config.DEFAULT_ANGLE)

        self._scale = 1.0
        self._origin = QPointF(0.0, 0.0)

        self._sel: Optional[Annotation] = None
        self._drag = None
        self._gesture = False
        self._gesture_undo_done = False
        self._undo: List[List[dict]] = []
        self._redo: List[List[dict]] = []
        self._message = "Przeciągnij zdjęcie tutaj lub wybierz z listy w lewym górnym rogu"

        self._editor = _TextEditor(self)
        self._editor.hide()
        self._editor.setStyleSheet(
            "QLineEdit{background:rgba(16,17,21,225);color:#ffffff;"
            "border:1px dashed #ffd400;border-radius:3px;padding:1px 4px;}"
        )
        self._editor.editingFinished.connect(self.commit_edit)
        self._editor.escapePressed.connect(self.cancel_edit)
        self._editing: Optional[Annotation] = None

        self._bg = QColor(26, 27, 31)

    # --- document --------------------------------------------------------
    @property
    def document(self):
        return self._doc

    def set_document(self, doc) -> None:
        self.commit_edit()
        self._doc = doc
        self._sel = None
        self._drag = None
        self._undo.clear()
        self._redo.clear()
        self._message = "" if doc is not None else \
            "Przeciągnij zdjęcie tutaj lub wybierz z listy w lewym górnym rogu"
        if doc is not None:
            self.fit()
        self.selectionChanged.emit()
        self.documentChanged.emit()
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text or ""
        self.update()

    # --- view: transforms, pan, zoom -------------------------------------
    def view_transform(self) -> QTransform:
        return QTransform().translate(self._origin.x(), self._origin.y()).scale(self._scale, self._scale)

    def to_image(self, pos: QPointF) -> QPointF:
        return QPointF((pos.x() - self._origin.x()) / self._scale, (pos.y() - self._origin.y()) / self._scale)

    def to_screen(self, pt: QPointF) -> QPointF:
        return QPointF(self._origin.x() + pt.x() * self._scale, self._origin.y() + pt.y() * self._scale)

    def screen_rect(self, rect: QRectF) -> QRectF:
        return QRectF(
            self._origin.x() + rect.x() * self._scale,
            self._origin.y() + rect.y() * self._scale,
            rect.width() * self._scale,
            rect.height() * self._scale,
        )

    @property
    def scale(self) -> float:
        return self._scale

    def fit_scale(self) -> float:
        if self._doc is None or self._doc.width <= 0 or self._doc.height <= 0:
            return 1.0
        return min(self.width() / self._doc.width, self.height() / self._doc.height) * 0.99

    def fit(self) -> None:
        if self._doc is None:
            return
        self._scale = max(1e-4, min(1.0, self.fit_scale()))
        left = (self.width() - self._doc.width * self._scale) / 2.0
        top = (self.height() - self._doc.height * self._scale) / 2.0
        self._origin = QPointF(left, top)
        self._emit_zoom()

    def zoom_to(self, scale: float, anchor: Optional[QPointF] = None) -> None:
        if self._doc is None:
            return
        fit = self.fit_scale()
        scale = max(min(fit * 0.05, 0.05), min(MAX_ZOOM, scale))
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        before = self.to_image(anchor)
        self._scale = scale
        self._origin = QPointF(anchor.x() - before.x() * scale, anchor.y() - before.y() * scale)
        self._emit_zoom()

    def zoom_by(self, factor: float, anchor: Optional[QPointF] = None) -> None:
        self.zoom_to(self._scale * factor, anchor)

    def zoom_in(self) -> None:
        self.zoom_by(1.25)

    def zoom_out(self) -> None:
        self.zoom_by(1.0 / 1.25)

    def _emit_zoom(self) -> None:
        self.zoomChanged.emit(self._scale)
        self.update()

    # --- size / mouse / keyboard events ----------------------------------
    def resizeEvent(self, event) -> None:  # noqa: D102
        super().resizeEvent(event)
        self.resized.emit()
        if self._doc is not None and self._scale <= self.fit_scale() * 1.02:
            self.fit()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: D102
        if self._doc is None:
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            return
        factor = math.pow(1.0016, delta)
        self.zoom_by(factor, event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D102
        pos = event.position()
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._drag = {"mode": "pan", "pos": pos, "origin": QPointF(self._origin)}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton or self._doc is None:
            return
        if self._editing is not None:
            self.commit_edit()
            return

        img_pt = self.to_image(pos)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)

        if self._tool == TOOL_SELECT or alt:
            hit = pick_annotation(self._doc.annotations, img_pt, self._pick_tolerance())
            if hit is not None:
                self.push_undo()
                self.set_selection(hit)
                self._drag = {"mode": "move", "start": img_pt, "anno": hit}
            else:
                self.set_selection(None)
            self.update()
            return

        if self._tool == TOOL_TEXT:
            anno = Annotation(
                kind=KIND_TEXT, p1=img_pt, color=self._color, size=self._size, angle=self._angle
            )
            self.push_undo()
            self._doc.annotations.append(anno)
            self.set_selection(anno)
            self.begin_edit(anno, text="")
            self.update()
            return

        kind = {
            TOOL_ARROW: KIND_ARROW,
            TOOL_CROSS: KIND_CROSS,
            TOOL_CHECK: KIND_CHECK,
            TOOL_STROKE: KIND_STROKE,
        }.get(self._tool)
        if kind is None:
            return
        anno = Annotation(kind=kind, p1=img_pt, p2=img_pt, color=self._color, width=self._width, size=self._size)
        if kind == KIND_STROKE:
            anno.points = [img_pt]
        self.push_undo()
        self._doc.annotations.append(anno)
        self._sel = anno
        self._drag = {"mode": "shape", "anno": anno, "start": img_pt}
        self.selectionChanged.emit()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D102
        pos = event.position()
        if self._drag is None:
            if self._doc is not None and self._tool == TOOL_SELECT:
                img_pt = self.to_image(pos)
                hit = pick_annotation(self._doc.annotations, img_pt, self._pick_tolerance())
                self.setCursor(Qt.CursorShape.SizeAllCursor if hit else Qt.CursorShape.ArrowCursor)
            return
        mode = self._drag.get("mode")
        if mode == "pan":
            delta = pos - self._drag["pos"]
            self._origin = QPointF(self._drag["origin"].x() + delta.x(), self._drag["origin"].y() + delta.y())
            self.update()
        elif mode == "move":
            img_pt = self.to_image(pos)
            start = self._drag["start"]
            anno: Annotation = self._drag["anno"]
            anno.move(img_pt.x() - start.x(), img_pt.y() - start.y())
            self._drag["start"] = img_pt
            self.selectionChanged.emit()
            self.update()
        elif mode == "shape":
            anno: Annotation = self._drag["anno"]
            img_pt = self.to_image(pos)
            if anno.kind == KIND_STROKE:
                last = anno.points[-1]
                if math.hypot(img_pt.x() - last.x(), img_pt.y() - last.y()) * self._scale >= 1.5:
                    anno.points.append(img_pt)
            else:
                anno.p2 = img_pt
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: D102
        if self._drag is None:
            return
        mode = self._drag.get("mode")
        if mode == "pan":
            self._drag = None
            self.setCursor(self._cursor_for_tool())
            return
        if mode == "shape":
            anno: Annotation = self._drag["anno"]
            if anno.kind != KIND_STROKE:
                if anno.p2 is None or math.hypot(anno.p2.x() - anno.p1.x(), anno.p2.y() - anno.p1.y()) * self._scale < 6:
                    # A click without dragging: drop a sensible default-sized shape
                    size = 220.0 / max(self._scale, 1e-6)
                    anno.p2 = QPointF(anno.p1.x() + size, anno.p1.y() + size)
        self._drag = None
        self._finish_change()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: D102
        if self._doc is None or event.button() != Qt.MouseButton.LeftButton:
            return
        img_pt = self.to_image(event.position())
        hit = pick_annotation(self._doc.annotations, img_pt, self._pick_tolerance())
        if hit is not None and hit.kind == KIND_TEXT:
            self.set_selection(hit)
            self.begin_edit(hit)
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: D102
        key = event.key()
        if not event.modifiers():
            tool_keys = {
                Qt.Key.Key_V: TOOL_SELECT,
                Qt.Key.Key_T: TOOL_TEXT,
                Qt.Key.Key_A: TOOL_ARROW,
                Qt.Key.Key_X: TOOL_CROSS,
                Qt.Key.Key_C: TOOL_CHECK,
                Qt.Key.Key_B: TOOL_STROKE,
            }
            if key in tool_keys and self._editing is None:
                tool = tool_keys[key]
                self.set_tool(tool)
                self.toolRequested.emit(tool)
                return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._editing is None:
                self.delete_selection()
            return
        if key == Qt.Key.Key_Escape:
            if self._editing is not None:
                self.cancel_edit()
            elif self._drag is not None:
                self._drag = None
                self.update()
            else:
                self.set_selection(None)
            return
        step = 80.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 20.0
        moves = {
            Qt.Key.Key_Left: (step, 0.0),
            Qt.Key.Key_Right: (-step, 0.0),
            Qt.Key.Key_Up: (0.0, step),
            Qt.Key.Key_Down: (0.0, -step),
        }
        if key in moves:
            dx, dy = moves[key]
            self._origin = QPointF(self._origin.x() + dx, self._origin.y() + dy)
            self.update()
            return
        super().keyPressEvent(event)

    # --- tools and properties --------------------------------------------
    def set_tool(self, tool: str) -> None:
        if tool not in TOOLS:
            return
        self.commit_edit()
        self._tool = tool
        if tool != TOOL_SELECT:
            self.set_selection(None)
        self.setCursor(self._cursor_for_tool())

    @property
    def tool(self) -> str:
        return self._tool

    def _cursor_for_tool(self):
        return Qt.CursorShape.ArrowCursor if self._tool == TOOL_SELECT else Qt.CursorShape.CrossCursor

    def _pick_tolerance(self) -> float:
        return max(6.0, 12.0 / max(self._scale, 1e-6))

    def set_color(self, color: str) -> None:
        self._color = color
        if self._sel is not None:
            self._apply_to_selection(color=color)

    def set_width(self, width: int) -> None:
        self._width = int(width)
        if self._sel is not None and self._sel.kind != KIND_TEXT:
            self._apply_to_selection(width=int(width))

    def set_size(self, size: int) -> None:
        self._size = int(size)
        if self._sel is not None and self._sel.kind == KIND_TEXT:
            self._apply_to_selection(size=int(size))

    def set_angle(self, angle: float) -> None:
        self._angle = float(angle)
        if self._sel is not None and self._sel.kind == KIND_TEXT:
            self._apply_to_selection(angle=float(angle))

    def _apply_to_selection(self, **kwargs) -> None:
        if self._sel is None:
            return
        if self._sel is self._editing:
            return
        # A slider drag is one undo step, not a hundred, hence "gesture"
        if not self._gesture or not self._gesture_undo_done:
            self.push_undo()
            self._gesture_undo_done = True
        for key, value in kwargs.items():
            setattr(self._sel, key, value)
        self._finish_change(keep_selection=True)

    def begin_gesture(self) -> None:
        """Start of a continuous change (slider drag): one undo step per gesture."""
        self._gesture = True
        self._gesture_undo_done = False

    def end_gesture(self) -> None:
        self._gesture = False
        self._gesture_undo_done = False

    # --- selection, text editing, undo -----------------------------------
    @property
    def selection(self) -> Optional[Annotation]:
        return self._sel

    @property
    def editing(self) -> bool:
        return self._editing is not None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def set_selection(self, anno: Optional[Annotation]) -> None:
        if anno is not self._sel:
            self._sel = anno
            self.selectionChanged.emit()
            self.update()

    def begin_edit(self, anno: Annotation, text: Optional[str] = None) -> None:
        self._editing = anno
        self._editor.setText(anno.text if text is None else text)
        self._position_editor(anno)
        font = QFont(self._editor.font())
        font.setPixelSize(int(max(9, min(40, anno.size * self._scale))))
        self._editor.setFont(font)
        self._editor.show()
        self._editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self._editor.selectAll()
        self.update()

    def _position_editor(self, anno: Annotation) -> None:
        rect = self.screen_rect(anno.bounds())
        width = int(max(260, min(rect.width() + 90, self.width() - 24)))
        height = int(max(28, min(rect.height() + 10, 64)))
        x = int(max(4, min(rect.left(), self.width() - width - 4)))
        y = int(max(4, min(rect.top() - 2, self.height() - height - 4)))
        self._editor.setGeometry(x, y, width, height)

    def commit_edit(self) -> None:
        anno, self._editing = self._editing, None
        if anno is None or self._doc is None:
            return
        text = self._editor.text().strip()
        self._editor.hide()
        if anno not in self._doc.annotations:
            return
        if not text:
            if anno in self._doc.annotations:
                self._doc.annotations.remove(anno)
                self._sel = None
            self._finish_change()
            return
        anno.text = text
        self._sel = anno
        self._finish_change(keep_selection=True)

    def cancel_edit(self) -> None:
        anno, self._editing = self._editing, None
        self._editor.hide()
        if anno is not None and self._doc is not None and not anno.text and anno in self._doc.annotations:
            # A cancelled new annotation: do not leave empty text behind
            self._doc.annotations.remove(anno)
            if self._sel is anno:
                self._sel = None
        self.update()

    def delete_selection(self) -> None:
        if self._sel is None or self._doc is None:
            return
        self.push_undo()
        if self._sel in self._doc.annotations:
            self._doc.annotations.remove(self._sel)
        self._sel = None
        self.selectionChanged.emit()
        self._finish_change()

    def push_undo(self) -> None:
        if self._doc is None:
            return
        self._undo.append(self._doc.snapshot())
        del self._undo[: max(0, len(self._undo) - UNDO_DEPTH)]
        self._redo.clear()

    def undo(self) -> None:
        if self._doc is None or not self._undo:
            return
        self._redo.append(self._doc.snapshot())
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if self._doc is None or not self._redo:
            return
        self._undo.append(self._doc.snapshot())
        self._restore(self._redo.pop())

    def _restore(self, snapshot: List[dict]) -> None:
        self._editing = None
        self._editor.hide()
        self._doc.annotations = [Annotation.from_dict(d) for d in snapshot]
        self._sel = None
        self.selectionChanged.emit()
        self._finish_change()

    def _finish_change(self, keep_selection: bool = False) -> None:
        if self._doc is not None:
            self._doc.dirty = True
        if not keep_selection:
            self.selectionChanged.emit()
        self.edited.emit()
        self.update()

    # --- drawing ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: D102
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg)
        doc = self._doc
        if doc is None:
            self._paint_message(painter)
            return

        level, factor = doc.pick_level(self._scale)
        image_rect = QRectF(0.0, 0.0, float(doc.width), float(doc.height))
        visible = QRectF(self.to_image(QPointF(0.0, 0.0)), self.to_image(QPointF(self.width(), self.height())))
        visible = visible.intersected(image_rect)
        if visible.isEmpty():
            self._paint_message(painter)
            return

        src = QRectF(
            visible.x() / factor,
            visible.y() / factor,
            visible.width() / factor,
            visible.height() / factor,
        )
        target = QRectF(
            self._origin.x() + visible.x() * self._scale,
            self._origin.y() + visible.y() * self._scale,
            visible.width() * self._scale,
            visible.height() * self._scale,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, level, src)

        painter.save()
        painter.setTransform(self.view_transform())
        for anno in doc.annotations:
            if anno is self._editing:
                if anno.text:
                    draw_selection(painter, anno.bounds())
                continue
            anno.paint(painter, selected=anno is self._sel)
        painter.restore()

        if self._message:
            self._paint_message(painter)

    def _paint_message(self, painter: QPainter) -> None:
        if not self._message:
            return
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 210))
        rect = self.rect().adjusted(0, 0, 0, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._message)
