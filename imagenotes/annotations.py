"""Annotation model: text, arrow, cross, checkmark and freehand stroke."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (  # noqa: F401
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)

KIND_TEXT = "text"
KIND_ARROW = "arrow"
KIND_CROSS = "cross"
KIND_CHECK = "check"
KIND_STROKE = "stroke"

LINE_KINDS = (KIND_ARROW, KIND_CROSS, KIND_CHECK, KIND_STROKE)

# Dark outline under the text, readable on a light and a dark map alike
TEXT_OUTLINE = QColor(0, 0, 0, 175)

_FONT_FAMILY: Optional[str] = None


def _font_family() -> str:
    """Font family with a fallback; 'Segoe UI' does not exist off Windows."""
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        try:
            available = set(QFontDatabase.families())
        except Exception:
            available = set()
        for candidate in ("Segoe UI", "Verdana", "Tahoma", "Arial", "DejaVu Sans", "Noto Sans"):
            if candidate in available:
                _FONT_FAMILY = candidate
                break
        else:
            _FONT_FAMILY = ""      # empty name = Qt's default font
    return _FONT_FAMILY


def font_for(size: float) -> QFont:
    """Font for a text annotation; the size is in image pixels."""
    f = QFont(_font_family())
    f.setPixelSize(max(4, int(round(size))))
    f.setWeight(QFont.Weight.DemiBold)
    return f


def text_local_rect(text: str, size: float) -> QRectF:
    """Text outline in local coordinates (origin = the text baseline)."""
    if not text:
        return QRectF(0.0, 0.0, 0.0, 0.0)
    path = QPainterPath()
    path.addText(0.0, 0.0, font_for(size), text)
    return path.boundingRect()


def _seg_distance(a: QPointF, b: QPointF, p: QPointF) -> float:
    """Distance from point p to the segment a-b."""
    ax, ay, bx, by, px, py = a.x(), a.y(), b.x(), b.y(), p.x(), p.y()
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polyline_distance(points: Sequence[QPointF], p: QPointF) -> float:
    if len(points) == 1:
        return math.hypot(p.x() - points[0].x(), p.y() - points[0].y())
    return min(_seg_distance(points[i - 1], points[i], p) for i in range(1, len(points)))


@dataclass(eq=False)
class Annotation:
    """A single annotation on the image."""

    kind: str
    p1: QPointF
    p2: Optional[QPointF] = None
    points: List[QPointF] = field(default_factory=list)
    text: str = ""
    color: str = "#ff2d2d"
    width: int = 10
    size: int = 72
    angle: float = 0.0

    # --- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "p1": [self.p1.x(), self.p1.y()],
            "p2": [self.p2.x(), self.p2.y()] if self.p2 is not None else None,
            "points": [[p.x(), p.y()] for p in self.points],
            "text": self.text,
            "color": self.color,
            "width": self.width,
            "size": self.size,
            "angle": self.angle,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Annotation":
        def pt(v):
            return QPointF(float(v[0]), float(v[1])) if v else None

        return cls(
            kind=str(d.get("kind", KIND_TEXT)),
            p1=pt(d.get("p1")) or QPointF(0, 0),
            p2=pt(d.get("p2")),
            points=[p for p in (pt(v) for v in d.get("points", [])) if p is not None],
            text=str(d.get("text", "")),
            color=str(d.get("color", "#ff2d2d")),
            width=int(d.get("width", 10)),
            size=int(d.get("size", 72)),
            angle=float(d.get("angle", 0.0)),
        )

    def copy(self) -> "Annotation":
        return Annotation.from_dict(self.to_dict())

    # --- geometry --------------------------------------------------------
    @property
    def qcolor(self) -> QColor:
        c = QColor(self.color)
        return c if c.isValid() else QColor("#ff2d2d")

    def _bbox(self) -> QRectF:
        """Rect spanned between p1 and p2 (normalized)."""
        if self.p2 is None:
            return QRectF(self.p1, self.p1)
        return QRectF(self.p1, self.p2).normalized()

    def _check_points(self) -> List[QPointF]:
        r = self._bbox()
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        norm = [(0.06, 0.58), (0.34, 0.94), (0.98, 0.08)]
        return [QPointF(x + nx * w, y + ny * h) for nx, ny in norm]

    def bounds(self) -> QRectF:
        """Annotation outline in image px (used for selection and hit tests)."""
        if self.kind == KIND_TEXT:
            rect = text_local_rect(self.text, self.size)
            t = QTransform().translate(self.p1.x(), self.p1.y()).rotate(self.angle)
            return t.mapRect(rect)
        if self.kind == KIND_STROKE:
            if not self.points:
                return QRectF(self.p1, self.p1)
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return self._bbox()

    def move(self, dx: float, dy: float) -> None:
        self.p1 = QPointF(self.p1.x() + dx, self.p1.y() + dy)
        if self.p2 is not None:
            self.p2 = QPointF(self.p2.x() + dx, self.p2.y() + dy)
        self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]

    def hits(self, pt: QPointF, tol: float) -> bool:
        """Whether a point (image px) hits the annotation. `tol` is in image px."""
        if self.kind == KIND_TEXT:
            if not self.text:
                return False
            inv, ok = QTransform().translate(self.p1.x(), self.p1.y()).rotate(self.angle).inverted()
            if not ok:
                return False
            local = inv.map(pt)
            rect = text_local_rect(self.text, self.size)
            pad = max(tol, self.size * 0.15)
            return rect.adjusted(-pad, -pad, pad, pad).contains(local)
        slack = max(tol, self.width * 0.6)
        if self.kind == KIND_ARROW:
            if self.p2 is None:
                return False
            return _seg_distance(self.p1, self.p2, pt) <= slack
        if self.kind == KIND_CROSS:
            r = self._bbox()
            a, b = QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom())
            c, d = QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top())
            return min(_seg_distance(a, b, pt), _seg_distance(c, d, pt)) <= slack
        if self.kind == KIND_CHECK:
            pts = self._check_points()
            return _polyline_distance(pts, pt) <= slack
        if self.kind == KIND_STROKE:
            if not self.points:
                return False
            return _polyline_distance(self.points, pt) <= slack
        return False

    # --- drawing ---------------------------------------------------------
    def _pen(self) -> QPen:
        pen = QPen(self.qcolor)
        pen.setWidthF(max(1.0, float(self.width)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def paint(self, painter: QPainter, selected: bool = False) -> None:
        if self.kind == KIND_TEXT:
            self._paint_text(painter)
        elif self.kind == KIND_ARROW:
            self._paint_arrow(painter)
        elif self.kind == KIND_CROSS:
            r = self._bbox()
            painter.setPen(self._pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(r.topLeft(), r.bottomRight())
            painter.drawLine(r.bottomLeft(), r.topRight())
        elif self.kind == KIND_CHECK:
            painter.setPen(self._pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pts = self._check_points()
            path = QPainterPath(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            painter.drawPath(path)
        elif self.kind == KIND_STROKE:
            self._paint_stroke(painter)

        if selected:
            draw_selection(painter, self.bounds())

    def _paint_text(self, painter: QPainter) -> None:
        if not self.text:
            return
        font = font_for(self.size)
        path = QPainterPath()
        path.addText(0.0, 0.0, font, self.text)
        painter.save()
        painter.translate(self.p1)
        painter.rotate(self.angle)
        outline = QPen(TEXT_OUTLINE)
        outline.setWidthF(max(1.5, self.size * 0.14))
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.fillPath(path, self.qcolor)
        painter.restore()

    def _paint_arrow(self, painter: QPainter) -> None:
        if self.p2 is None:
            return
        dx, dy = self.p2.x() - self.p1.x(), self.p2.y() - self.p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        head = min(max(16.0, self.width * 3.4), length * 0.75)
        base = QPointF(self.p2.x() - ux * head, self.p2.y() - uy * head)

        # The shaft ends INSIDE the head (15% of the head length before its base).
        end = QPointF(self.p2.x() - ux * head * 0.85, self.p2.y() - uy * head * 0.85)
        painter.setPen(self._pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(self.p1, end)

        half = head * 0.42
        poly = QPolygonF(
            [
                QPointF(self.p2),
                QPointF(base.x() + px * half, base.y() + py * half),
                QPointF(base.x() - px * half, base.y() - py * half),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.qcolor)
        painter.drawPolygon(poly)

    def _paint_stroke(self, painter: QPainter) -> None:
        if not self.points:
            return
        pen = self._pen()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(self.points) == 1:
            painter.drawPoint(self.points[0])
            return
        path = QPainterPath(self.points[0])
        for i in range(1, len(self.points)):
            a, b = self.points[i - 1], self.points[i]
            mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            path.quadTo(a, mid)
        path.lineTo(self.points[-1])
        painter.drawPath(path)


def draw_selection(painter: QPainter, rect: QRectF) -> None:
    """Selection frame drawn with a cosmetic pen (always 1-2 px on screen)."""
    pen = QPen(QColor(255, 212, 0))
    pen.setCosmetic(True)
    pen.setWidth(2)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect.adjusted(-4, -4, 4, 4))


def render_annotations(painter: QPainter, annotations: Iterable[Annotation]) -> None:
    """Shared renderer for the on-screen preview and the file write."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    for a in annotations:
        a.paint(painter)


def pick_annotation(annotations: Sequence[Annotation], pt: QPointF, tol: float) -> Optional[Annotation]:
    """Topmost annotation under the cursor (from the end of the list)."""
    for a in reversed(annotations):
        if a.hits(pt, tol):
            return a
    return None
