"""The always-on-top, frameless, transparent character window."""

import sys

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from .character import Character
from .config import Config

MIN_SCALE = 0.4
MAX_SCALE = 3.0


class PetWindow(QWidget):
    def __init__(self, character: Character, config: Config, on_right_click):
        super().__init__()
        self._config = config
        self._on_right_click = on_right_click
        self._character = character
        self._frame_index = 0
        self._drag_offset: QPoint | None = None
        self._scale = _clamp_scale(config.char_scale)

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # On Windows, Tool keeps the pet out of the taskbar. On macOS a Tool
        # window hides itself whenever another app is focused, which would
        # defeat the whole point, so we leave it as a plain window there.
        if sys.platform == "win32":
            flags |= Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _pos: self._on_right_click())

        self._apply_character_size()
        self._restore_position()

        self._fps = config.min_fps
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._timer.start(int(1000 / self._fps))

    # ---- character ----
    def set_character(self, character: Character) -> None:
        self._character = character
        self._frame_index = 0
        self._apply_character_size()
        self.update()

    def _apply_character_size(self) -> None:
        base = self._character.frames[0].size()
        self.resize(
            max(1, round(base.width() * self._scale)),
            max(1, round(base.height() * self._scale)),
        )

    # ---- size ----
    def set_scale(self, scale: float) -> None:
        """Resize the pet in real time, keeping it centred on its old centre."""
        scale = _clamp_scale(scale)
        if abs(scale - self._scale) < 0.001:
            return
        center = self.geometry().center()
        self._scale = scale
        self._apply_character_size()
        geo = self.geometry()
        geo.moveCenter(center)
        self.move(geo.topLeft())
        self.update()

        self._config.char_scale = scale
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.save()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            # ~18% per notch (one notch == 120 units)
            self.set_scale(self._scale * (1.0 + 0.0015 * delta))

    # ---- playback ----
    def set_fps(self, fps: float) -> None:
        fps = max(0.5, fps)
        if abs(fps - self._fps) < 0.1:
            return
        self._fps = fps
        self._timer.setInterval(int(1000 / fps))

    def _next_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % self._character.frame_count
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self._character.frames[self._frame_index])

    # ---- position ----
    def _restore_position(self) -> None:
        if self._config.window_x is not None and self._config.window_y is not None:
            self.move(self._config.window_x, self._config.window_y)
            return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top())

    # ---- mouse: drag to move, right-click for menu ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._config.window_x = self.x()
            self._config.window_y = self.y()
            self._config.save()


def _clamp_scale(scale: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, scale))
