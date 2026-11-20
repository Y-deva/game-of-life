"""Canvas widget that renders the grid and handles mouse input."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSizeF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from .model import Cell, LifeGrid


class LifeCanvas(QWidget):
    """Draws the universe and lets the user draw, erase, pan and zoom."""

    cellsEdited = pyqtSignal()
    editStarted = pyqtSignal()
    hovered = pyqtSignal(object)

    MIN_CELL_SIZE = 2.0
    MAX_CELL_SIZE = 64.0

    # Colour ramp for cell age: newborns are bright blue, veterans turn pink.
    AGE_COLORS = (
        "#7dd3fc",
        "#60c8f8",
        "#4bbdf3",
        "#43b0ec",
        "#4aa3e2",
        "#5b96d6",
        "#7489c8",
        "#8f7cba",
        "#a973ab",
        "#bf6b9b",
        "#d1638a",
        "#e05b79",
        "#ec5568",
        "#f45d5d",
        "#fb7185",
    )
    ALIVE_COLOR = "#38bdf8"
    GRID_COLOR = "#16233c"
    BACKGROUND = "#0b1220"

    def __init__(self, grid: LifeGrid, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = grid
        self.cell_size = 10.0
        self.offset = QPointF(8.0, 8.0)
        self.show_grid = True
        self.use_age_colors = True
        self.pattern_provider = None  # callable returning cells for Shift+click

        self._painting = False
        self._erasing = False
        self._panning = False
        self._pan_start = QPointF()
        self._pan_origin = QPointF()
        self._last_cell: Cell | None = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 240)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # -- geometry --------------------------------------------------------

    def grid_rect(self) -> QRectF:
        return QRectF(
            self.offset,
            QSizeF(self.grid.width * self.cell_size, self.grid.height * self.cell_size),
        )

    def _clamp_offset(self) -> None:
        rect = self.grid_rect()
        margin = 24.0
        max_x = self.width() - margin
        max_y = self.height() - margin
        min_x = margin - rect.width()
        min_y = margin - rect.height()
        self.offset.setX(min(max(self.offset.x(), min_x), max_x))
        self.offset.setY(min(max(self.offset.y(), min_y), max_y))

    def fit_to_view(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        cell_size = min(
            (self.width() - 16) / self.grid.width,
            (self.height() - 16) / self.grid.height,
        )
        self.cell_size = max(self.MIN_CELL_SIZE, min(cell_size, 32.0))
        rect = self.grid_rect()
        self.offset = QPointF(
            (self.width() - rect.width()) / 2,
            (self.height() - rect.height()) / 2,
        )
        self._clamp_offset()
        self.update()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        new_cell = max(self.MIN_CELL_SIZE, min(self.cell_size * factor, self.MAX_CELL_SIZE))
        if abs(new_cell - self.cell_size) < 1e-6:
            return
        ratio = new_cell / self.cell_size
        self.offset = QPointF(
            anchor.x() - (anchor.x() - self.offset.x()) * ratio,
            anchor.y() - (anchor.y() - self.offset.y()) * ratio,
        )
        self.cell_size = new_cell
        self._clamp_offset()
        self.update()

    def cell_at(self, point: QPointF) -> Cell | None:
        x = int((point.x() - self.offset.x()) // self.cell_size)
        y = int((point.y() - self.offset.y()) // self.cell_size)
        if 0 <= x < self.grid.width and 0 <= y < self.grid.height:
            return x, y
        return None

    # -- painting --------------------------------------------------------

    def _cell_rect(self, cell: Cell) -> QRectF:
        x, y = cell
        return QRectF(
            self.offset.x() + x * self.cell_size,
            self.offset.y() + y * self.cell_size,
            self.cell_size,
            self.cell_size,
        )

    def _cell_color(self, cell: Cell) -> QColor:
        if not self.use_age_colors:
            return QColor(self.ALIVE_COLOR)
        age = self.grid.age.get(cell, 0)
        return QColor(self.AGE_COLORS[min(age, len(self.AGE_COLORS) - 1)])

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self.BACKGROUND))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        rect = self.grid_rect()
        if self.show_grid and self.cell_size >= 5:
            painter.setPen(QPen(QColor(self.GRID_COLOR), 1))
            for column in range(self.grid.width + 1):
                x = rect.left() + column * self.cell_size
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            for row in range(self.grid.height + 1):
                y = rect.top() + row * self.cell_size
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        painter.setPen(Qt.PenStyle.NoPen)
        radius = min(3.0, self.cell_size * 0.22)
        for cell in self.grid.live:
            box = self._cell_rect(cell).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setBrush(self._cell_color(cell))
            if self.cell_size >= 4:
                painter.drawRoundedRect(box, radius, radius)
            else:
                painter.drawRect(box)

        painter.setPen(QPen(QColor("#25365a"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        painter.end()

    # -- input -----------------------------------------------------------

    def _stamp(self, cell: Cell) -> None:
        cells = self.pattern_provider() if self.pattern_provider else None
        if cells:
            self.grid.place(cells, cell[0], cell[1])
            return
        self.grid.set_cell(cell[0], cell[1], True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        point = event.position()
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = point
            self._pan_origin = QPointF(self.offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        cell = self.cell_at(point)
        if cell is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.editStarted.emit()
            self._painting = True
            self._erasing = False
            self._last_cell = cell
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._stamp(cell)
            else:
                self.grid.set_cell(cell[0], cell[1], True)
            self.cellsEdited.emit()
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.editStarted.emit()
            self._painting = True
            self._erasing = True
            self._last_cell = cell
            self.grid.set_cell(cell[0], cell[1], False)
            self.cellsEdited.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        point = event.position()
        if self._panning:
            delta = point - self._pan_start
            self.offset = self._pan_origin + delta
            self._clamp_offset()
            self.update()
            return
        cell = self.cell_at(point)
        self.hovered.emit(cell)
        if not self._painting or cell is None:
            return
        if self._last_cell is not None and cell != self._last_cell:
            self._draw_line(self._last_cell, cell)
        else:
            self._apply(cell)
        self._last_cell = cell
        self.cellsEdited.emit()
        self.update()

    def _draw_line(self, start: Cell, end: Cell) -> None:
        x0, y0 = start
        x1, y1 = end
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for step in range(steps + 1):
            x = round(x0 + (x1 - x0) * step / steps)
            y = round(y0 + (y1 - y0) * step / steps)
            self._apply((x, y))

    def _apply(self, cell: Cell) -> None:
        self.grid.set_cell(cell[0], cell[1], not self._erasing)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._painting = False
            self._last_cell = None
            self.cellsEdited.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        self.zoom_by(1.15**steps, event.position())

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hovered.emit(None)
        super().leaveEvent(event)
