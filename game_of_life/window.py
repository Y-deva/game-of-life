"""Application window: menus, toolbar, pattern library and simulation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .model import (
    PRESETS,
    LifeGrid,
    RLEError,
    Rule,
    RuleError,
    dump_rle,
    parse_rle,
)
from .patterns import PATTERNS, PATTERNS_BY_NAME
from .view import LifeCanvas

STYLESHEET = """
QMainWindow, QWidget { background: #0b1220; color: #e2e8f0; }
QToolBar { background: #0f172a; border: 0; spacing: 4px; padding: 6px; }
QToolButton { padding: 6px 10px; border-radius: 6px; color: #e2e8f0; }
QToolButton:hover { background: #1e293b; }
QToolButton:checked { background: #2563eb; color: white; }
QToolButton:disabled { color: #64748b; }
QPushButton { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { background: #273449; }
QPushButton:pressed { background: #2563eb; }
QPushButton:disabled { color: #64748b; }
QComboBox, QSpinBox, QLineEdit, QSlider { background: #111c31; border: 1px solid #334155; border-radius: 6px; padding: 4px; }
QComboBox QAbstractItemView { background: #111c31; selection-background-color: #2563eb; }
QListWidget { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 6px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #2563eb; color: white; }
QStatusBar { background: #0f172a; color: #94a3b8; }
QStatusBar QLabel { padding: 0 10px; }
QMenuBar { background: #0f172a; }
QMenuBar::item:selected { background: #1e293b; }
QMenu { background: #0f172a; border: 1px solid #334155; }
QMenu::item { padding: 5px 22px; }
QMenu::item:selected { background: #2563eb; }
QDockWidget { color: #94a3b8; titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: #0f172a; padding: 6px 10px; border-bottom: 1px solid #1e293b; }
"""


class SizeDialog(QDialog):
    """Resize the universe while optionally keeping the cells."""

    def __init__(self, width: int, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Grid size")
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(10, 1000)
        self.width_spin.setValue(width)
        self.height_spin = QSpinBox(self)
        self.height_spin.setRange(10, 1000)
        self.height_spin.setValue(height)

        form = QFormLayout()
        form.addRow("Width:", self.width_spin)
        form.addRow("Height:", self.height_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)


class RuleDialog(QDialog):
    """Pick a life-like rule from the presets or type a custom one."""

    def __init__(self, rule: Rule, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Simulation rule")

        self.preset_combo = QComboBox(self)
        for name in PRESETS:
            self.preset_combo.addItem(name, name)
        self.preset_combo.addItem("Custom rule", None)

        self.rule_edit = QLineEdit(str(rule), self)
        self.rule_edit.setPlaceholderText("B3/S23")
        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #f87171;")

        form = QFormLayout()
        form.addRow("Preset:", self.preset_combo)
        form.addRow("Rule:", self.rule_edit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.buttons)

        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        self.rule_edit.textChanged.connect(self._validate)
        self._preset_changed(self.preset_combo.currentIndex())
        self._validate()

    def _preset_changed(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if name:
            self.rule_edit.setText(str(PRESETS[name]))

    def _validate(self) -> None:
        try:
            Rule.parse(self.rule_edit.text())
        except RuleError as exc:
            self.error_label.setText(str(exc))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            self.error_label.clear()
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def selected_rule(self) -> Rule:
        return Rule.parse(self.rule_edit.text())


class MainWindow(QMainWindow):
    """Main window: simulation controls, pattern library and file handling."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Game of Life")
        self.resize(1200, 780)
        self.setStyleSheet(STYLESHEET)

        self.settings = QSettings()
        self.grid = LifeGrid(160, 100, torus=True, rule=Rule())
        self.grid.randomize(0.22)
        self.canvas = LifeCanvas(self.grid, self)
        self.setCentralWidget(self.canvas)

        self.current_path: Path | None = None
        self._undo: list[tuple[frozenset[tuple[int, int]], int]] = []
        self._redo: list[tuple[frozenset[tuple[int, int]], int]] = []
        self._fps = 0.0
        self._last_tick: float | None = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self._build_actions()
        self._build_toolbar()
        self._build_library()
        self._build_menus()
        self._build_statusbar()

        self.speed_slider.valueChanged.connect(self._speed_changed)
        self.canvas.editStarted.connect(self._push_undo)
        self.canvas.cellsEdited.connect(self._refresh_stats)
        self.canvas.hovered.connect(self._hover)

        self._restore_settings()
        self._refresh_stats()

    # -- construction ----------------------------------------------------

    def _action(
        self,
        text: str,
        slot=None,
        shortcuts: list[str] | None = None,
        checkable: bool = False,
        checked: bool = False,
        tooltip: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if slot is not None:
            action.triggered.connect(slot)
        if shortcuts:
            action.setShortcuts([QKeySequence(key) for key in shortcuts])
        action.setCheckable(checkable)
        action.setChecked(checked)
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        self.play_action = self._action(
            "Play", self._set_running_action, ["Space"], checkable=True,
            tooltip="Run or pause the simulation",
        )
        self.step_action = self._action("Step", self.step_once, ["N"], tooltip="Advance one generation")
        self.random_action = self._action("Random", self.random_fill, ["R"], tooltip="Fill the grid randomly")
        self.clear_action = self._action("Clear", self.clear_grid, ["C"], tooltip="Clear the grid")
        self.undo_action = self._action("Undo", self.undo, ["Ctrl+Z"])
        self.redo_action = self._action("Redo", self.redo, ["Ctrl+Shift+Z", "Ctrl+Y"])
        self.copy_action = self._action("Copy", self.copy_pattern, ["Ctrl+C"], tooltip="Copy live cells as RLE")
        self.paste_action = self._action("Paste", self.paste_pattern, ["Ctrl+V"], tooltip="Paste RLE from the clipboard")
        self.grid_action = self._action(
            "Grid", self._toggle_grid, ["G"], checkable=True, checked=True,
            tooltip="Show or hide the grid lines",
        )
        self.age_action = self._action(
            "Age colours", self._toggle_age, ["A"], checkable=True, checked=True,
            tooltip="Colour cells by age",
        )
        self.torus_action = self._action(
            "Torus", self._toggle_torus, ["T"], checkable=True, checked=True,
            tooltip="Wrap the grid around its edges",
        )
        self.zoom_in_action = self._action("Zoom in", self.zoom_in, ["Ctrl++", "Ctrl+="], tooltip="Zoom in")
        self.zoom_out_action = self._action("Zoom out", self.zoom_out, ["Ctrl+-"], tooltip="Zoom out")
        self.fit_action = self._action("Fit", self.fit_view, ["F"], tooltip="Fit the grid to the window")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Controls", self)
        toolbar.setObjectName("controls")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        toolbar.addAction(self.play_action)
        toolbar.addAction(self.step_action)
        toolbar.addSeparator()
        toolbar.addAction(self.random_action)
        toolbar.addAction(self.clear_action)
        toolbar.addSeparator()

        self.speed_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.speed_slider.setRange(1, 60)
        self.speed_slider.setValue(10)
        self.speed_slider.setFixedWidth(150)
        self.speed_slider.setToolTip("Simulation speed, generations per second")
        self.speed_label = QLabel("10 gen/s", self)
        self.speed_label.setMinimumWidth(64)
        toolbar.addWidget(QLabel("Speed", self))
        toolbar.addWidget(self.speed_slider)
        toolbar.addWidget(self.speed_label)

        toolbar.addSeparator()
        toolbar.addAction(self.grid_action)
        toolbar.addAction(self.age_action)
        toolbar.addAction(self.torus_action)
        toolbar.addSeparator()
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.fit_action)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._action("New", self.new_grid, ["Ctrl+N"]))
        file_menu.addAction(self._action("Open RLE…", self.open_rle, ["Ctrl+O"]))
        file_menu.addAction(self._action("Save RLE", self.save_rle, ["Ctrl+S"]))
        file_menu.addAction(self._action("Save RLE as…", self.save_rle_as, ["Ctrl+Shift+S"]))
        file_menu.addAction(self._action("Export PNG…", self.export_png, ["Ctrl+E"]))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Quit", self.close, ["Ctrl+Q"]))

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._action("Grid size…", self.change_size))
        edit_menu.addAction(self._action("Random fill…", self.random_fill_with_density))

        sim_menu = self.menuBar().addMenu("&Simulation")
        sim_menu.addAction(self.play_action)
        sim_menu.addAction(self.step_action)
        sim_menu.addAction(self._action("Rule…", self.change_rule))

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.grid_action)
        view_menu.addAction(self.age_action)
        view_menu.addAction(self.torus_action)
        view_menu.addSeparator()
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addSeparator()
        self.library_action = self.library_dock.toggleViewAction()
        self.library_action.setText("Pattern library")
        view_menu.addAction(self.library_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self._action("Keyboard shortcuts", self.show_shortcuts))
        help_menu.addAction(self._action("About", self.show_about))

    def _build_library(self) -> None:
        self.library_dock = QDockWidget("Pattern library", self)
        self.library_dock.setObjectName("library")
        self.library_dock.setMinimumWidth(220)
        self.library_dock.setMaximumWidth(460)
        self.library_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        panel = QWidget(self.library_dock)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.library_list = QListWidget(panel)
        for pattern in PATTERNS:
            item = QListWidgetItem(pattern.name)
            item.setData(Qt.ItemDataRole.UserRole, pattern.name)
            item.setToolTip(pattern.description)
            self.library_list.addItem(item)
        layout.addWidget(self.library_list, 1)

        self.library_description = QLabel("", panel)
        self.library_description.setWordWrap(True)
        self.library_description.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.library_description)

        insert_button = QPushButton("Insert at centre", panel)
        insert_button.clicked.connect(self.insert_selected_pattern)
        layout.addWidget(insert_button)

        self.library_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.library_dock)
        self.library_list.currentItemChanged.connect(self._library_selection_changed)
        self.library_list.itemDoubleClicked.connect(lambda _item: self.insert_selected_pattern())
        self.library_list.setCurrentRow(0)

    def _build_statusbar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.generation_label = QLabel("Generation 0", self)
        self.population_label = QLabel("Population 0", self)
        self.rule_label = QLabel("B3/S23", self)
        self.speed_status = QLabel("10 gen/s", self)
        self.fps_label = QLabel("-- fps", self)
        self.cursor_label = QLabel("", self)
        for label in (
            self.generation_label,
            self.population_label,
            self.rule_label,
            self.speed_status,
            self.fps_label,
            self.cursor_label,
        ):
            status.addPermanentWidget(label)

    # -- settings --------------------------------------------------------

    def _restore_settings(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("window/state")
        if state:
            self.restoreState(state)

        self.speed_slider.setValue(int(self.settings.value("sim/speed", 10)))
        self.grid_action.setChecked(self._as_bool("sim/grid", True))
        self.age_action.setChecked(self._as_bool("sim/age", True))
        self.torus_action.setChecked(self._as_bool("sim/torus", True))
        self._toggle_grid(self.grid_action.isChecked())
        self._toggle_age(self.age_action.isChecked())
        self._toggle_torus(self.torus_action.isChecked())

        rule_text = str(self.settings.value("sim/rule", "B3/S23"))
        try:
            self.grid.set_rule(Rule.parse(rule_text))
        except RuleError:
            self.grid.set_rule(Rule())

        self.canvas.fit_to_view()

    def _as_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("sim/speed", self.speed_slider.value())
        self.settings.setValue("sim/grid", self.grid_action.isChecked())
        self.settings.setValue("sim/age", self.age_action.isChecked())
        self.settings.setValue("sim/torus", self.torus_action.isChecked())
        self.settings.setValue("sim/rule", str(self.grid.rule))
        super().closeEvent(event)

    # -- history ---------------------------------------------------------

    def _push_undo(self) -> None:
        self._undo.append((frozenset(self.grid.live), self.grid.generation))
        if len(self._undo) > 200:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append((frozenset(self.grid.live), self.grid.generation))
        cells, generation = self._undo.pop()
        self._restore(cells, generation)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append((frozenset(self.grid.live), self.grid.generation))
        cells, generation = self._redo.pop()
        self._restore(cells, generation)

    def _restore(self, cells: frozenset[tuple[int, int]], generation: int) -> None:
        self.grid.live = set(cells)
        self.grid.age = {cell: 0 for cell in self.grid.live}
        self.grid.generation = generation
        self._refresh_stats()

    # -- simulation ------------------------------------------------------

    def _set_running_action(self, running: bool) -> None:
        self._set_running(running)

    def _set_running(self, running: bool) -> None:
        if self.play_action.isChecked() != running:
            self.play_action.setChecked(running)
        self.play_action.setText("Pause" if running else "Play")
        if running:
            self._last_tick = None
            self.timer.start(max(1, round(1000 / self.speed_slider.value())))
        else:
            self.timer.stop()
            self._fps = 0.0
            self.fps_label.setText("-- fps")

    def _tick(self) -> None:
        now = time.monotonic()
        if self._last_tick is not None:
            delta = now - self._last_tick
            if delta > 0:
                instant = 1.0 / delta
                self._fps = instant if not self._fps else self._fps * 0.8 + instant * 0.2
        self._last_tick = now
        self.grid.step()
        self._refresh_stats()

    def _speed_changed(self, value: int) -> None:
        self.speed_label.setText(f"{value} gen/s")
        self.speed_status.setText(f"{value} gen/s")
        if self.timer.isActive():
            self.timer.start(max(1, round(1000 / value)))

    def _refresh_stats(self) -> None:
        self.generation_label.setText(f"Generation {self.grid.generation}")
        self.population_label.setText(f"Population {len(self.grid.live)}")
        self.rule_label.setText(str(self.grid.rule))
        self.speed_status.setText(f"{self.speed_slider.value()} gen/s")
        if self._fps:
            self.fps_label.setText(f"{self._fps:.1f} fps")
        self.undo_action.setEnabled(bool(self._undo))
        self.redo_action.setEnabled(bool(self._redo))
        self.canvas.update()

    def _hover(self, cell) -> None:
        self.cursor_label.setText(f"x={cell[0]} y={cell[1]}" if cell else "")

    # -- view ------------------------------------------------------------

    def _toggle_grid(self, checked: bool) -> None:
        self.canvas.show_grid = checked
        self.canvas.update()

    def _toggle_age(self, checked: bool) -> None:
        self.canvas.use_age_colors = checked
        self.canvas.update()

    def _toggle_torus(self, checked: bool) -> None:
        self.grid.torus = checked

    def fit_view(self) -> None:
        self.canvas.fit_to_view()

    def zoom_in(self) -> None:
        self.canvas.zoom_by(1.25)

    def zoom_out(self) -> None:
        self.canvas.zoom_by(1 / 1.25)

    # -- library ---------------------------------------------------------

    def _library_selection_changed(self, current: QListWidgetItem | None, _previous=None) -> None:
        name = current.data(Qt.ItemDataRole.UserRole) if current else None
        if not name:
            self.library_description.clear()
            self.canvas.pattern_provider = None
            return
        pattern = PATTERNS_BY_NAME[name]
        self.library_description.setText(pattern.description)
        self.canvas.pattern_provider = lambda: pattern.parse().cells

    def insert_selected_pattern(self) -> None:
        item = self.library_list.currentItem()
        if item is None:
            return
        pattern = PATTERNS_BY_NAME[item.data(Qt.ItemDataRole.UserRole)]
        self._push_undo()
        self.grid.place_centered(pattern.parse().cells)
        self._refresh_stats()
        self.statusBar().showMessage(
            f"{pattern.name} inserted at the centre (Shift+click places it under the cursor)",
            4000,
        )

    # -- commands --------------------------------------------------------

    def step_once(self) -> None:
        self.grid.step()
        self._refresh_stats()

    def random_fill(self) -> None:
        self._push_undo()
        self.grid.randomize(0.25)
        self._refresh_stats()

    def random_fill_with_density(self) -> None:
        density, accepted = QInputDialog.getInt(
            self, "Random fill", "Live cells, percent:", 25, 1, 100
        )
        if not accepted:
            return
        self._push_undo()
        self.grid.randomize(density / 100)
        self._refresh_stats()

    def clear_grid(self) -> None:
        self._push_undo()
        self.grid.clear()
        self._refresh_stats()

    def new_grid(self) -> None:
        self._push_undo()
        self.grid.clear()
        self.grid.randomize(0.22)
        self.current_path = None
        self._refresh_stats()

    def change_size(self) -> None:
        dialog = SizeDialog(self.grid.width, self.grid.height, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._push_undo()
        self.grid.resize(dialog.width_spin.value(), dialog.height_spin.value())
        self.canvas.fit_to_view()
        self._refresh_stats()

    def change_rule(self) -> None:
        dialog = RuleDialog(self.grid.rule, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.grid.set_rule(dialog.selected_rule())
        self._refresh_stats()
        self.statusBar().showMessage(f"Rule set to {self.grid.rule}", 3000)

    # -- clipboard -------------------------------------------------------

    def copy_pattern(self) -> None:
        if not self.grid.live:
            self.statusBar().showMessage("Nothing to copy", 3000)
            return
        text = dump_rle(self.grid.normalized_cells(), rule=str(self.grid.rule))
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Live cells copied as RLE", 3000)

    def paste_pattern(self) -> None:
        text = QApplication.clipboard().text()
        try:
            pattern = parse_rle(text)
        except RLEError as exc:
            self.statusBar().showMessage(f"Clipboard does not contain a valid RLE pattern: {exc}", 5000)
            return
        self._push_undo()
        self.grid.place_centered(pattern.cells)
        try:
            self.grid.set_rule(Rule.parse(pattern.rule))
        except RuleError:
            pass
        self._refresh_stats()
        self.statusBar().showMessage(f"Pasted {pattern.population} cells", 3000)

    # -- files -----------------------------------------------------------

    def _pattern_from_grid(self) -> str:
        return dump_rle(self.grid.normalized_cells(), rule=str(self.grid.rule))

    def open_rle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open RLE", str(self.settings.value("files/last", "")), "RLE (*.rle);;All files (*)"
        )
        if not path:
            return
        try:
            pattern = parse_rle(Path(path).read_text(encoding="utf-8"))
        except (OSError, RLEError) as exc:
            QMessageBox.warning(self, "Cannot open pattern", str(exc))
            return
        self._push_undo()
        self.grid.clear()
        self.grid.place_centered(pattern.cells)
        try:
            self.grid.set_rule(Rule.parse(pattern.rule))
        except RuleError:
            pass
        self.current_path = Path(path)
        self.settings.setValue("files/last", str(self.current_path.parent))
        self._refresh_stats()
        self.statusBar().showMessage(f"Loaded {self.current_path.name}", 4000)

    def save_rle(self) -> None:
        if self.current_path is None:
            self.save_rle_as()
            return
        self._write_rle(self.current_path)

    def save_rle_as(self) -> None:
        suggested = str(self.current_path or Path(str(self.settings.value("files/last", ""))) / "pattern.rle")
        path, _ = QFileDialog.getSaveFileName(self, "Save RLE", suggested, "RLE (*.rle)")
        if not path:
            return
        self.current_path = Path(path)
        self.settings.setValue("files/last", str(self.current_path.parent))
        self._write_rle(self.current_path)

    def _write_rle(self, path: Path) -> None:
        if not self.grid.live:
            QMessageBox.information(self, "Save RLE", "The grid is empty.")
            return
        try:
            path.write_text(self._pattern_from_grid(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot save pattern", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path.name}", 4000)

    def export_png(self) -> None:
        suggested = str(self.current_path.with_suffix(".png")) if self.current_path else "life.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", suggested, "PNG image (*.png)")
        if not path:
            return
        image = self.canvas.grab()
        if not image.save(path, "PNG"):
            QMessageBox.warning(self, "Export PNG", f"Could not write {path}")
            return
        self.statusBar().showMessage(f"Exported {Path(path).name}", 4000)

    # -- dialogs ---------------------------------------------------------

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Game of Life",
            "<h2>Game of Life</h2>"
            "<p>A Conway's Game of Life playground written with PyQt6.</p>"
            "<p>Cells are born with 3 neighbours and survive with 2 or 3 under the "
            "classic B3/S23 rule; other life-like rules are available from the "
            "Simulation menu.</p>",
        )

    def show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            "Space - play or pause\n"
            "N - single step\n"
            "R - random fill\n"
            "C - clear the grid\n"
            "A - toggle age colours\n"
            "G - toggle the grid lines\n"
            "T - toggle the torus\n"
            "F - fit the grid to the window\n"
            "Ctrl+Z / Ctrl+Shift+Z - undo / redo\n"
            "Ctrl+C / Ctrl+V - copy or paste RLE\n"
            "Ctrl+O / Ctrl+S - open or save an RLE file\n"
            "Left button - draw, right button - erase\n"
            "Middle button - pan, wheel - zoom\n"
            "Shift+left button - stamp the selected pattern",
        )


def run(argv: list[str] | None = None) -> int:
    """Create the application and start the event loop."""
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setOrganizationName("game-of-life")
    app.setApplicationName("GameOfLife")
    app.setApplicationDisplayName("Game of Life")

    window = MainWindow()
    window.show()
    window.canvas.fit_to_view()

    if "--smoke" in argv:
        QTimer.singleShot(1500, app.quit)

    return app.exec()
