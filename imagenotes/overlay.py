"""Lewitujące elementy interfejsu: panel narzędzi (prawy górny róg) i bąbelek ostatnich zdjęć.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import config, storage
from .canvas import (
    TOOL_ARROW,
    TOOL_CHECK,
    TOOL_CROSS,
    TOOL_SELECT,
    TOOL_STROKE,
    TOOL_TEXT,
)

PANEL_QSS = """
#panel { background: rgba(19,20,24,215); border: 1px solid rgba(255,255,255,34); border-radius: 14px; }
#panel QLabel { color: #dfe2e8; font-size: 13px; }
#panel QLabel#title { color: #9aa1ae; font-size: 12px; font-weight: 600; letter-spacing: 2px; }
#panel QLabel#state { font-size: 16px; }
#panel QToolButton {
    color: #eceef2; background: rgba(255,255,255,16);
    border: 1px solid rgba(255,255,255,30); border-radius: 9px;
    padding: 2px 6px; font-size: 18px;
}
#panel QToolButton:hover { background: rgba(255,255,255,42); }
#panel QToolButton:checked { background: rgba(255,212,0,70); border: 1px solid #ffd400; color: #fff6c9; }
#panel QToolButton:disabled { color: rgba(255,255,255,85); background: rgba(255,255,255,8); }
#panel QSlider { min-height: 22px; }
#panel QSlider::groove:horizontal { height: 7px; background: rgba(255,255,255,45); border-radius: 3px; }
#panel QSlider::sub-page:horizontal { background: rgba(255,212,0,150); border-radius: 3px; }
#panel QSlider::handle:horizontal { width: 16px; height: 16px; margin: -5px 0; background: #ffd400; border-radius: 8px; }
"""

TOOLS = [
    (TOOL_SELECT, "\u2725", "Zaznacz / przesuwaj adnotacje  (V)"),
    (TOOL_TEXT, "T", "Dodaj tekst  (T)"),
    (TOOL_ARROW, "\u279c", "Strzałka  (A)"),
    (TOOL_CROSS, "\u2715", "Krzyżyk / błąd  (X)"),
    (TOOL_CHECK, "\u2713", "Checkmark / OK  (C)"),
    (TOOL_STROKE, "\u270e", "Rysowanie odręczne  (B)"),
]


class ToolPanel(QWidget):
    """Panel narzędzi: tryb, kolor, grubość, rozmiar, kąt i akcje. Zawsze w prawym górnym rogu."""

    toolChanged = Signal(str)
    colorChanged = Signal(str)
    widthChanged = Signal(int)
    sizeChanged = Signal(int)
    angleChanged = Signal(int)
    gestureStarted = Signal()
    gestureEnded = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    deleteRequested = Signal()
    saveRequested = Signal()
    fitRequested = Signal()
    collapseToggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(PANEL_QSS)
        self.setFixedWidth(316)

        self._tool_buttons: dict[str, QToolButton] = {}
        self._swatches: dict[str, QToolButton] = {}
        self._current_color = config.DEFAULT_COLOR

        root = QVBoxLayout(self)
        root.setContentsMargins(13, 11, 13, 13)
        root.setSpacing(9)

        # --- nagłówek: tytuł + wskaźnik zapisu ---
        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("NOTATKI")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self._state = QLabel("\u25cf")
        self._state.setObjectName("state")
        self._state.setStyleSheet("color:#6ee27a;")
        self._state.setToolTip("Zapisane (autozapis po każdej edycji)")
        header.addWidget(self._state)
        root.addLayout(header)

        # --- narzędzia ---
        root.addWidget(self._row_tools())
        # --- kolory ---
        root.addWidget(self._row_colors())
        # --- suwaki ---
        self._width_slider, self._width_label, row = self._slider_row(
            "Grubo\u015b\u0107", 1, 80, config.DEFAULT_WIDTH, self.widthChanged
        )
        root.addWidget(row)
        self._size_slider, self._size_label, row = self._slider_row(
            "Rozmiar", 8, 400, config.DEFAULT_TEXT_SIZE, self.sizeChanged
        )
        root.addWidget(row)
        self._angle_slider, self._angle_label, row = self._slider_row(
            "K\u0105t", 0, 359, config.DEFAULT_ANGLE, self.angleChanged, suffix="\u00b0"
        )
        root.addWidget(row)
        # --- akcje ---
        root.addWidget(self._row_actions())
        # --- podpis autora ---
        root.addWidget(self._signature_label())

        self.set_tool(TOOL_SELECT)

    # ------------------------------------------------------------------
    def _row_tools(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for tool, glyph, tip in TOOLS:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFixedSize(44, 38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, t=tool: self.toolChanged.emit(t))
            group.addButton(btn)
            layout.addWidget(btn)
            self._tool_buttons[tool] = btn
        return row

    def _row_colors(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for color in config.PALETTE:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setFixedSize(30, 28)
            btn.setToolTip(f"Kolor {color}")
            btn.setStyleSheet(
                "QToolButton{border:1px solid rgba(0,0,0,150); border-radius:7px; background:%s;}"
                "QToolButton:checked{border:2px solid #ffd400;}" % color
            )
            btn.clicked.connect(lambda _=False, c=color: self._pick_color(c))
            group.addButton(btn)
            layout.addWidget(btn)
            self._swatches[color] = btn
        custom = QToolButton()
        custom.setText("\u2026")
        custom.setToolTip("W\u0142asny kolor\u2026")
        custom.setFixedSize(30, 28)
        custom.setCursor(Qt.CursorShape.PointingHandCursor)
        custom.clicked.connect(self._pick_custom_color)
        layout.addWidget(custom)
        layout.addStretch(1)
        self._swatches[config.DEFAULT_COLOR].setChecked(True)
        return row

    def _slider_row(self, name: str, minimum: int, maximum: int, value: int, signal, suffix: str = " px"):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(name)
        label.setFixedWidth(66)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        value_label = QLabel(f"{value}{suffix}")
        value_label.setFixedWidth(56)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.sliderPressed.connect(self.gestureStarted.emit)
        slider.sliderReleased.connect(self.gestureEnded.emit)

        def on_change(v: int, target=value_label, emit=signal, unit=suffix) -> None:
            target.setText(f"{v}{unit}")
            emit.emit(v)

        slider.valueChanged.connect(on_change)
        layout.addWidget(label)
        layout.addWidget(slider, 1)
        layout.addWidget(value_label)
        return slider, value_label, row

    def _signature_label(self) -> QLabel:
        """Podpis autora w panelu — kliknięcie otwiera okno »O programie«."""
        label = QLabel(config.AUTHOR_LINE)
        label.setStyleSheet("color:#8b93a1; font-size:11px; letter-spacing:1px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setCursor(Qt.CursorShape.PointingHandCursor)
        label.setToolTip(
            f"{config.APP_NAME} {config.VERSION} — autor: {config.AUTHOR}\n"
            "Kliknij, aby zobaczyć szczegóły."
        )
        label.mousePressEvent = self._show_about          # type: ignore[method-assign]
        return label

    def _show_about(self, event) -> None:
        QMessageBox.about(
            self,
            f"O programie — {config.APP_NAME}",
            f"<b>{config.APP_NAME} {config.VERSION}</b><br><br>"
            f"Program i kod źródłowy: <b>{config.AUTHOR}</b><br>"
            f"{config.COPYRIGHT}<br><br>"
            "Narzędzie do błyskawicznego notowania na zdjęciach i mapach, "
            "także powyżej 10 000 px.<br><br>"
            "Podpis autora jest też wpisywany w metadane każdego zapisanego pliku "
            "(Author / Artist / Copyright) oraz we właściwości pliku ImageNotes.exe.",
        )

    def _row_actions(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self._undo_btn = self._action("\u21b6", "Cofnij  (Ctrl+Z)", self.undoRequested)
        self._redo_btn = self._action("\u21b7", "Pon\u00f3w  (Ctrl+Shift+Z)", self.redoRequested)
        self._delete_btn = self._action("\U0001f5d1", "Usu\u0144 zaznaczone  (Del)", self.deleteRequested)
        self._save_btn = self._action("\U0001f4be", "Zapisz teraz  (Ctrl+S)", self.saveRequested)
        fit_btn = self._action("\u26f6", "Dopasuj do okna  (Ctrl+0)", self.fitRequested)
        for btn in (self._undo_btn, self._redo_btn, self._delete_btn, self._save_btn, fit_btn):
            layout.addWidget(btn)
        layout.addStretch(1)
        self._delete_btn.setEnabled(False)
        return row

    def _action(self, glyph: str, tip: str, signal) -> QToolButton:
        btn = QToolButton()
        btn.setText(glyph)
        btn.setToolTip(tip)
        btn.setFixedSize(42, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(signal.emit)
        return btn

    # ------------------------------------------------------------------
    def _pick_color(self, color: str) -> None:
        self.gestureStarted.emit()
        self._current_color = color
        self.colorChanged.emit(color)
        self.gestureEnded.emit()

    def _pick_custom_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._current_color), self, "Kolor notatki")
        if not chosen.isValid():
            return
        color = chosen.name()
        self._current_color = color
        for btn in self._swatches.values():
            btn.setChecked(False)
        self.gestureStarted.emit()
        self.colorChanged.emit(color)
        self.gestureEnded.emit()

    def set_tool(self, tool: str) -> None:
        btn = self._tool_buttons.get(tool)
        if btn is not None:
            btn.setChecked(True)

    def set_color(self, color: str, block: bool = True) -> None:
        self._current_color = color
        for value, btn in self._swatches.items():
            btn.setChecked(value.lower() == color.lower())

    def set_values(self, width: Optional[int] = None, size: Optional[int] = None,
                   angle: Optional[float] = None, color: Optional[str] = None) -> None:
        """Ustawia suwaki bez emitowania sygnałów (synchronizacja z zaznaczoną adnotacją)."""
        if width is not None:
            self._width_slider.blockSignals(True)
            self._width_slider.setValue(int(width))
            self._width_label.setText(f"{int(width)} px")
            self._width_slider.blockSignals(False)
        if size is not None:
            self._size_slider.blockSignals(True)
            self._size_slider.setValue(int(size))
            self._size_label.setText(f"{int(size)} px")
            self._size_slider.blockSignals(False)
        if angle is not None:
            self._angle_slider.blockSignals(True)
            self._angle_slider.setValue(int(angle) % 360)
            self._angle_label.setText(f"{int(angle) % 360}\u00b0")
            self._angle_slider.blockSignals(False)
        if color:
            self.set_color(color)

    def set_can_undo(self, undo: bool, redo: bool) -> None:
        self._undo_btn.setEnabled(undo)
        self._redo_btn.setEnabled(redo)

    def set_has_selection(self, has: bool) -> None:
        self._delete_btn.setEnabled(has)

    def set_state(self, state: str, detail: str = "") -> None:
        """state: idle | dirty | saving | saved | error"""
        mapping = {
            "idle": ("\u25cf", "#7a7f8a", "Brak zmian do zapisania"),
            "dirty": ("\u25cf", "#ffd400", "Zmiany czekaj\u0105 na zapis\u2026"),
            "saving": ("\u27f3", "#ffd400", "Zapisuj\u0119\u2026"),
            "saved": ("\u25cf", "#6ee27a", "Zapisane na dysku"),
            "error": ("\u26a0", "#ff5f56", "B\u0142\u0105d zapisu!"),
        }
        glyph, color, tip = mapping.get(state, mapping["idle"])
        self._state.setText(glyph)
        self._state.setStyleSheet(f"color:{color};")
        self._state.setToolTip(f"{tip}\n{detail}".strip())


class RecentPopup(QWidget):
    """Lista ostatnio edytowanych zdjęć (otwierana z bąbelka w lewym górnym rogu)."""

    openRequested = Signal(str)     # ścieżka do otwarcia
    pickRequested = Signal()        # wybór pliku z dysku
    folderRequested = Signal()      # pokaż folder ostatniego pliku
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("recent")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(384)
        self.setStyleSheet(
            "#recent { background: rgba(19,20,24,242); border: 1px solid rgba(255,255,255,38); border-radius: 14px; }"
            "#recent QLabel { color: #9aa1ae; font-size: 12px; font-weight: 600; letter-spacing: 2px; }"
            "#recent QToolButton { color:#eceef2; background: transparent; border: none; border-radius: 10px;"
            " padding: 6px 8px; font-size: 13px; text-align: left; }"
            "#recent QToolButton:hover { background: rgba(255,255,255,34); }"
            "#recent QToolButton#plain { text-align:center; font-size: 14px; }"
        )
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(3)
        self._entries: List[QToolButton] = []

    def set_entries(self, entries: List[storage.RecentEntry]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        header = QLabel("OSTATNIE ZDJ\u0118CIA")
        self._layout.addWidget(header)

        if not entries:
            empty = QToolButton()
            empty.setObjectName("plain")
            empty.setText("(brak \u2014 nic jeszcze nie by\u0142o edytowane)")
            empty.setEnabled(False)
            self._layout.addWidget(empty)

        for entry in entries:
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIconSize(QSize(84, 64))
            thumb = storage.thumb_pixmap(entry)
            if thumb is not None:
                btn.setIcon(QIcon(thumb))
            note = "  \u2713" if entry.source and entry.source.exists() else "  (orygina\u0142 niedost\u0119pny)"
            btn.setText(f"{entry.display_name}\n{entry.saved_at}{note}")
            btn.setToolTip(str(entry.open_target))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            target = str(entry.open_target)
            btn.clicked.connect(lambda _=False, p=target: self._emit_open(p))
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._layout.addWidget(btn)
            self._entries.append(btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: rgba(255,255,255,30);")
        self._layout.addWidget(line)

        pick = QToolButton()
        pick.setObjectName("plain")
        pick.setText("Otw\u00f3rz zdj\u0119cie\u2026   (Ctrl+O)")
        pick.setCursor(Qt.CursorShape.PointingHandCursor)
        pick.clicked.connect(self._emit_pick)
        self._layout.addWidget(pick)

        folder = QToolButton()
        folder.setObjectName("plain")
        folder.setText("Poka\u017c folder projektu")
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(self._emit_folder)
        self._layout.addWidget(folder)

    def _emit_open(self, path: str) -> None:
        self.close()
        self.openRequested.emit(path)

    def _emit_pick(self) -> None:
        self.close()
        self.pickRequested.emit()

    def _emit_folder(self) -> None:
        self.close()
        self.folderRequested.emit()

    def popup_at(self, global_pos: QPoint) -> None:
        self.adjustSize()
        self.move(global_pos)
        self.show()


class RecentBubble(QToolButton):
    """Okrągły bąbelek w lewym górnym rogu: miniatura ostatnio edytowanego zdjęcia."""

    clickedBubble = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setIconSize(QSize(44, 44))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Ostatnio edytowane zdjęcia")
        self.setStyleSheet(
            "QToolButton{background: rgba(19,20,24,230); border:1px solid rgba(255,255,255,70);"
            " border-radius: 28px; padding: 5px;}"
            "QToolButton:hover{background: rgba(45,47,54,245); border:1px solid #ffd400;}"
        )
        self.setIcon(self._fallback_icon())
        self.clicked.connect(self.clickedBubble.emit)

    @staticmethod
    def _fallback_icon() -> QIcon:
        pix = QPixmap(44, 44)
        pix.fill(Qt.GlobalColor.transparent)
        return QIcon(pix)

    def set_thumbnail(self, pixmap: Optional[QPixmap]) -> None:
        self.setIcon(QIcon(pixmap) if pixmap is not None else self._fallback_icon())
