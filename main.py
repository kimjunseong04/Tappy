"""Tappy -- a desktop pet that dances faster the faster you type."""

import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from app import autostart
from app.character_manager import CharacterManager, ensure_default_character
from app.config import Config
from app.keyboard_monitor import (
    KeyboardMonitor,
    macos_accessibility_trusted,
    open_accessibility_settings,
)
from app.paths import assets_dir
from app.pet_window import PetWindow
from app.settings_window import SettingsWindow
from app.speed_model import SpeedModel
from app.tray import Tray
from app.ui_style import stylesheet
from app.welcome_window import WelcomeWindow

POLL_INTERVAL_MS = 80


class TappyApp:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        self.config = Config.load()

        ensure_default_character()
        self.characters = CharacterManager()
        character = self.characters.load_with_fallback(self.config.character_id)
        self.config.character_id = character.id

        self.speed = SpeedModel(self.config.min_fps, self.config.max_fps)
        self.monitor = KeyboardMonitor()

        self.window = PetWindow(character, self.config, self.open_settings)
        self.tray = Tray(self._load_icon(), self.open_settings, self.quit)
        self.settings_window: SettingsWindow | None = None
        self.welcome_window: WelcomeWindow | None = None

        self.window.show()
        self.monitor.start()

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._tick)
        self.poll_timer.start(POLL_INTERVAL_MS)

        if not self.config.seen_welcome:
            self.show_welcome()
        elif not macos_accessibility_trusted():
            self._warn_permission()

    # ---- main loop: keystroke rate -> animation FPS ----
    def _tick(self) -> None:
        rate = self.monitor.recent_rate()
        self.window.set_fps(self.speed.update(rate))

    # ---- windows ----
    def show_welcome(self) -> None:
        self.welcome_window = WelcomeWindow(
            on_get_started=self._finish_welcome,
            on_open_accessibility=open_accessibility_settings,
            needs_permission=not macos_accessibility_trusted(),
        )
        self._center(self.welcome_window)
        self.welcome_window.present()

    def _finish_welcome(self) -> None:
        # Driven by WelcomeWindow.closeEvent (button or native close button).
        self.config.seen_welcome = True
        self.config.save()
        self.welcome_window = None

    def open_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self._center(self.settings_window)
        self.settings_window.refresh()
        self.settings_window.present()

    def _center(self, widget) -> None:
        geo = self.qapp.primaryScreen().availableGeometry()
        widget.move(
            geo.center().x() - widget.width() // 2,
            geo.center().y() - widget.height() // 2,
        )

    # ---- actions invoked from the settings window ----
    def select_character(self, char_id: str) -> None:
        char = self.characters.get(char_id)
        if char is None:
            return
        self.window.set_character(char)
        self.config.character_id = char_id
        self.config.save()

    def delete_character(self, char_id: str) -> bool:
        """Delete a user character; if it was selected, fall back to default."""
        if not self.characters.delete_character(char_id):
            return False
        if self.config.character_id == char_id:
            fallback = self.characters.load_with_fallback("default")
            self.window.set_character(fallback)
            self.config.character_id = fallback.id
            self.config.save()
        return True

    def set_char_scale(self, scale: float) -> None:
        self.window.set_scale(scale)

    def set_fps_range(self, lo: float, hi: float) -> None:
        lo = max(1.0, min(lo, hi))
        self.config.min_fps = lo
        self.config.max_fps = hi
        self.speed.min_fps = lo
        self.speed.max_fps = hi
        self.config.save()

    def set_autostart(self, enabled: bool) -> None:
        if enabled:
            autostart.enable()
        else:
            autostart.disable()
        self.config.autostart = autostart.is_enabled()
        self.config.save()

    def quit(self) -> None:
        self.poll_timer.stop()
        self.monitor.stop()
        self.tray.hide()
        if self.settings_window is not None:
            self.settings_window.close()
        if self.welcome_window is not None:
            self.welcome_window.close()
        self.window.close()
        self.qapp.quit()

    # ---- helpers ----
    def _warn_permission(self) -> None:
        self.tray.show_message(
            "Tappy — 권한 필요",
            "키 입력 권한이 없어 캐릭터가 타이핑에 반응하지 않습니다. "
            "설정에서 손쉬운 사용 권한을 허용한 뒤 다시 실행하세요.",
        )

    def _load_icon(self) -> QIcon:
        logo_path = assets_dir() / "tappy_logo.png"
        if logo_path.exists():
            return QIcon(str(logo_path))
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 138, 0))
        painter.setPen(QColor(255, 138, 0))
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        return QIcon(pixmap)


def main() -> int:
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setStyleSheet(stylesheet())
    # App/Dock/taskbar icon when running from source (a built app/exe gets its
    # icon from Tappy.spec instead).
    logo = assets_dir() / "tappy_logo.png"
    if logo.exists():
        qapp.setWindowIcon(QIcon(str(logo)))
    # Stash on qapp so the controller (and its windows/timers) stays alive.
    qapp.tappy_app = TappyApp(qapp)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
