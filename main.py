"""Tappy -- 타이핑이 빠를수록 더 빠르게 춤추는 데스크톱 펫."""

import sys
import time

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from app import autostart
from app.character_manager import CharacterManager, ensure_default_character
from app.config import Config
from app.keyboard_monitor import (
    KeyboardMonitor,
    keystroke_permission_granted,
    keystroke_permission_state,
    open_keystroke_permission_settings,
    request_keystroke_permission,
)
from app.paths import assets_dir, is_frozen
from app.pet_window import PetWindow
from app.settings_window import SettingsWindow
from app.speed_model import SpeedModel
from app.tray import Tray
from app.ui_style import stylesheet
from app.updater import UpdateChecker, UpdateState
from app.welcome_window import WelcomeWindow

POLL_INTERVAL_MS = 80
# 새로 허용된 키 입력 권한을 주기적으로 재확인. 권한이 없을 때만 실행되므로 느긋한 간격도 무방하다.
PERMISSION_POLL_MS = 1500
# 컨트롤러가 업데이터 작업자 큐를 비우는 주기 — 업데이트 확인/다운로드 중에만 동작한다.
UPDATE_POLL_MS = 200
# 무음 시작 업데이트 확인의 제한 간격 (수동 "다시 확인"은 제한 무시). GitHub 60 req/hr/IP 한도 회피용.
UPDATE_CHECK_INTERVAL_S = 6 * 3600
# 창·리스너 초기화와 경쟁하지 않도록 무음 시작 확인을 지연시킨다.
UPDATE_STARTUP_DELAY_MS = 4000


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

        # 권한이 없는 동안 허용 여부를 감지하고 즉시 반영한다. pynput의 macOS 이벤트 탭은
        # *허용 이후*에 생성해야 키를 받으므로, 전환 시 리스너를 재생성한다 --
        # 앱 재시작 없이 작동한다 (이전의 불편한 흐름을 개선).
        self.permission_timer = QTimer()
        self.permission_timer.timeout.connect(self._check_permission)
        self._permission_ok = keystroke_permission_granted()

        if self.monitor.failed:
            # 리스너 자체를 시작하지 못한 경우 -- 권한 부재와 다른, 드문 오류. 명확히 안내한다.
            self.tray.show_message(
                "Tappy — 키 입력 감지 실패",
                "키보드 리스너를 시작하지 못했습니다. 앱을 다시 실행해 주세요.",
            )
        elif not self.config.seen_welcome:
            self.show_welcome()
        elif not self._permission_ok:
            self._warn_permission()

        if not self._permission_ok:
            self.permission_timer.start(PERMISSION_POLL_MS)

        # 자동 업데이트. 체커 + 폴 타이머는 항상 존재한다 (비용 작음, quit()에서 타이머를
        # 조건 없이 중단). 무음 시작 확인만 frozen 빌드에 국한 --
        # 소스 실행 시에는 교체할 번들이 없다.
        self.updater = UpdateChecker()
        self.updater.on_state_change = self._on_update_state
        self.updater.on_progress = self._on_update_progress
        self.last_update_state: tuple = (UpdateState.IDLE, None, "")
        self.update_poll_timer = QTimer()
        self.update_poll_timer.timeout.connect(self.updater.poll)
        if is_frozen():
            QTimer.singleShot(UPDATE_STARTUP_DELAY_MS, self._start_update_check)

    # ---- 메인 루프: 키 입력 속도 → 애니메이션 FPS ----
    def _tick(self) -> None:
        rate = self.monitor.recent_rate()
        self.window.set_fps(self.speed.update(rate))

    # ---- 키 입력 권한 ----
    def _check_permission(self) -> None:
        """새로 허용된 권한을 감지하고 즉시 적용한다."""
        if not keystroke_permission_granted():
            return
        self._permission_ok = True
        self.permission_timer.stop()
        # pynput의 이벤트 탭이 허용을 인식하도록 리스너를 재생성한다.
        self.monitor.restart()
        if self.settings_window is not None:
            self.settings_window.refresh_permission()
        if self.welcome_window is not None:
            self.welcome_window.refresh_permission()

    def prompt_for_permission(self) -> None:
        """환영/설정 창에서 "허용" 버튼을 눌렀을 때 처리한다.

        *미결정* 권한은 기본 시스템 프롬프트로 요청할 수 있지만, *거부된* 권한은
        시스템 설정에서만 변경할 수 있으므로 프롬프트 대신 설정 페이지로 직접 이동한다.
        """
        if keystroke_permission_state() == "denied":
            open_keystroke_permission_settings()
        else:
            request_keystroke_permission()
            self._check_permission()

    # ---- 자동 업데이트 ----
    def _start_update_check(self) -> None:
        """무음 시작 확인 — 매 실행마다 동작하지 않도록 제한한다."""
        if time.time() - self.config.last_update_check < UPDATE_CHECK_INTERVAL_S:
            return
        self.update_poll_timer.start(UPDATE_POLL_MS)
        self.updater.check_async()

    def _on_update_state(self, state: UpdateState, info, message: str) -> None:
        self.last_update_state = (state, info, message)
        if state in (UpdateState.UP_TO_DATE, UpdateState.AVAILABLE):
            # 성공한 확인 시각을 기록해 시작 제한이 다음 확인을 건너뛸 수 있게 한다.
            self.config.last_update_check = time.time()
            self.config.save()
        if self.settings_window is not None:
            self.settings_window.set_update_state(state, info, message)
        # 진행 중인 작업이 없으면 폴링 중단; 다운로드/적용 시 재시작된다.
        if state in (
            UpdateState.UP_TO_DATE,
            UpdateState.AVAILABLE,
            UpdateState.READY,
            UpdateState.ERROR,
        ):
            self.update_poll_timer.stop()

    def _on_update_progress(self, done: int, total: int) -> None:
        if self.settings_window is not None:
            self.settings_window.set_update_progress(done, total)

    def request_update_check(self) -> None:
        """수동 "다시 확인" — 시작 제한을 무시하고 즉시 실행한다."""
        self.update_poll_timer.start(UPDATE_POLL_MS)
        self.updater.check_async()

    def request_update_download(self) -> None:
        # 다운로드할 릴리스는 마지막 확인에서 가져온 것이다.
        release = self.last_update_state[1]
        if release is None:
            return
        self.update_poll_timer.start(UPDATE_POLL_MS)
        self.updater.download_and_stage_async(release)

    def request_update_apply(self) -> None:
        # 분리된 교체 헬퍼를 실행한 뒤 앱이 종료되어 헬퍼가 이어받게 한다.
        if self.updater.apply_and_relaunch():
            self.quit()
        else:
            # 스테이징 내용 없음 또는 헬퍼 실행 불가 -- 카드가 "지금 재시작"에
            # 고정되지 않도록 오류를 표시한다.
            self._on_update_state(
                UpdateState.ERROR,
                None,
                "업데이트를 적용할 수 없어요. 다시 시도해 주세요.",
            )

    # ---- 창 관리 ----
    def show_welcome(self) -> None:
        self.welcome_window = WelcomeWindow(
            on_get_started=self._finish_welcome,
            on_request_permission=self.prompt_for_permission,
            needs_permission=not keystroke_permission_granted(),
        )
        self._center(self.welcome_window)
        self.welcome_window.present()

    def _finish_welcome(self) -> None:
        # WelcomeWindow.closeEvent (버튼 또는 기본 닫기 버튼)에 의해 호출됨.
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

    # ---- 설정 창에서 호출하는 동작 ----
    def select_character(self, char_id: str) -> None:
        char = self.characters.get(char_id)
        if char is None:
            return
        self.window.set_character(char)
        self.config.character_id = char_id
        self.config.save()

    def delete_character(self, char_id: str) -> bool:
        """사용자 캐릭터를 삭제하고, 선택된 상태였다면 기본 캐릭터로 대체한다."""
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
        self.permission_timer.stop()
        self.update_poll_timer.stop()
        self.monitor.stop()
        self.tray.hide()
        if self.settings_window is not None:
            self.settings_window.close()
        if self.welcome_window is not None:
            self.welcome_window.close()
        self.window.close()
        self.qapp.quit()

    # ---- 내부 유틸리티 ----
    def _warn_permission(self) -> None:
        self.tray.show_message(
            "Tappy — 권한 필요",
            "입력 모니터링 권한이 없어 캐릭터가 타이핑에 반응하지 않습니다. "
            "트레이 메뉴의 설정에서 권한을 허용해 주세요.",
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
    # 소스 실행 시 앱/독/태스크바 아이콘 설정 (빌드된 앱·exe는 Tappy.spec에서 아이콘을 가져옴).
    logo = assets_dir() / "tappy_logo.png"
    if logo.exists():
        qapp.setWindowIcon(QIcon(str(logo)))
    # exec() 동안 컨트롤러(및 그 창·타이머)가 살아있도록 qapp에 보관한다.
    qapp.tappy_app = TappyApp(qapp)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
