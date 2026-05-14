"""Reusable widgets: a platform-native window base and a toggle switch.

`GlassWindow` keeps the native window frame on every OS and picks the
backdrop per platform:
  - macOS: real Tahoe "Liquid Glass" via pyqt-liquidglass.
  - Windows: a Windows 11 Mica backdrop via win32mica (opaque native
    window as the fallback on Windows 10 / when the library is missing).
  - Other: a plain native window.
"""

import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFrame, QMainWindow, QVBoxLayout, QWidget

from .ui_style import DIVIDER, SWITCH_ON


def _lerp(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


class GlassWindow(QMainWindow):
    """A native window with a platform-appropriate translucent backdrop.

    A QMainWindow (not a bare QWidget) is used because pyqt-liquidglass'
    glass injection is most reliable when the content view has a superview --
    otherwise it falls back to a fragile content-view swap.

    Subclasses build their content into ``self.body``; the controller calls
    ``present()`` (not ``show()``) so the backdrop is applied at the right time.
    """

    def __init__(self, title: str):
        super().__init__()
        self.setWindowTitle(title)
        self._effect_applied = False
        central = QWidget()
        self.setCentralWidget(central)
        self.body = QVBoxLayout(central)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

    @staticmethod
    def titlebar_clearance() -> int:
        """Top padding the content needs to clear the window controls.

        macOS overlays the traffic lights on a full-size content view, so the
        content must leave room. Windows/Linux have a separate native title
        bar, so only a small breathing margin is needed.
        """
        return 44 if sys.platform == "darwin" else 14

    def present(self) -> None:
        if sys.platform == "darwin":
            import pyqt_liquidglass as glass

            # Configures the NSWindow (transparent titlebar, full-size content)
            # and shows the window.
            glass.prepare_window_for_glass(self)
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if not self._effect_applied:
            self._effect_applied = True
            # Let the layout settle before injecting the native backdrop.
            QTimer.singleShot(60, self._apply_effect)

    def _apply_effect(self) -> None:
        if sys.platform == "darwin":
            import pyqt_liquidglass as glass

            # Leave the traffic lights at their native position -- repositioning
            # them with setup_traffic_lights_inset() clipped them against the
            # rounded window corner. titlebar_clearance() keeps content clear.
            glass.apply_glass_to_window(self)
        elif sys.platform == "win32":
            self._apply_mica()

    def _apply_mica(self) -> None:
        """Apply a Windows 11 Mica backdrop; stay opaque on any failure."""
        try:
            from win32mica import ApplyMica, MicaStyle, MicaTheme

            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            ApplyMica(
                HWND=int(self.winId()),
                Theme=MicaTheme.AUTO,
                Style=MicaStyle.DEFAULT,
            )
            self.update()
        except Exception:
            # Windows 10, win32mica missing, or an unsupported build: fall
            # back to the plain (theme-aware) opaque native window.
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.update()


class ToggleSwitch(QWidget):
    """An animated macOS-style on/off switch."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"pos_ratio", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool) -> None:
        if value == self._checked:
            return
        self._checked = value
        self._animate()

    def _animate(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if self._checked else 0.0)
        self._anim.start()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate()
            self.toggled.emit(self._checked)

    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, value: float) -> None:
        self._pos = value
        self.update()

    pos_ratio = pyqtProperty(float, _get_pos, _set_pos)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width() - 1, self.height() - 1)

        track = _lerp(QColor("#E9E9EA"), QColor(SWITCH_ON), self._pos)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        diameter = rect.height() - 4
        x = 2 + (rect.width() - diameter - 4) * self._pos
        painter.setBrush(QColor(0, 0, 0, 35))
        painter.drawEllipse(QRectF(x, 3.5, diameter, diameter))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, 2, diameter, diameter))


def divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {DIVIDER}; border: none;")
    return line
