"""System tray icon: a quick menu plus click-to-open-settings."""

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class Tray:
    def __init__(self, icon: QIcon, on_open_settings, on_quit, parent=None):
        self._tray = QSystemTrayIcon(icon, parent)
        self._tray.setToolTip("Tappy")

        menu = QMenu(parent)
        open_action = QAction("설정 열기", menu)
        open_action.triggered.connect(on_open_settings)
        menu.addAction(open_action)
        menu.addSeparator()
        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)

        self._menu = menu  # keep a reference; the tray icon does not own it
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: on_open_settings()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self._tray.show()

    def show_message(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message)

    def hide(self) -> None:
        self._tray.hide()
