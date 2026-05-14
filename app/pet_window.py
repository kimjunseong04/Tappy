"""항상 최상위에 표시되는 프레임리스 투명 캐릭터 창."""

import sys

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication, QWidget

from .character import Character
from .config import Config

MIN_SCALE = 0.4
MAX_SCALE = 3.0
# 드래그 해제 시 펫의 가장자리가 화면 가장자리에 이 픽셀 이내로 떨어지면
# 화면 끝에 딱 붙인다 -- 펫이 모서리에 깔끔하게 자리잡는다.
SNAP_THRESHOLD = 28


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
        # Windows에서는 Tool로 펫을 태스크바에서 제외한다. macOS에서 Tool 창은
        # 다른 앱이 포커스를 가지면 숨겨지므로 (본래 목적에 반함) 일반 창으로 둔다.
        if sys.platform == "win32":
            # NoDropShadow는 Windows가 캐릭터 픽셀이 아닌 *창* 주위에
            # 사각형 그림자를 그리는 것을 방지한다.
            flags |= Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _pos: self._on_right_click())
        # 열린 손 커서로 펫을 드래그할 수 있음을 알린다; 드래그 중에는 닫힌 손으로 바뀐다.
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("드래그로 이동 · 더블클릭으로 설정 · 휠로 크기 조절")

        self._apply_character_size()
        self._restore_position()

        self._fps = config.min_fps
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._timer.start(int(1000 / self._fps))

    # ---- 창 외형 ----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._strip_windows_border()

    def _strip_windows_border(self) -> None:
        """Windows 11이 프레임리스 창에도 그리는 1px DWM 테두리를 제거한다.

        DWM 테두리 색상을 "없음"으로 설정하면 캐릭터 픽셀만 보인다.
        macOS 또는 호출 실패 시 무작동.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            DWMWA_BORDER_COLOR = 34
            DWMWA_COLOR_NONE = 0xFFFFFFFE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()),
                DWMWA_BORDER_COLOR,
                ctypes.byref(ctypes.c_uint(DWMWA_COLOR_NONE)),
                ctypes.sizeof(ctypes.c_uint),
            )
        except Exception:
            pass

    # ---- 캐릭터 ----
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

    # ---- 크기 ----
    def set_scale(self, scale: float) -> None:
        """실시간으로 펫 크기를 조절하며 이전 중심점을 유지한다."""
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
            # 노치당 약 18% (한 노치 == 120 유닛)
            self.set_scale(self._scale * (1.0 + 0.0015 * delta))

    # ---- 재생 ----
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

    # ---- 위치 ----
    def _restore_position(self) -> None:
        x, y = self._config.window_x, self._config.window_y
        if x is not None and y is not None:
            # 저장된 위치가 마지막 실행 이후 디스플레이 레이아웃이 바뀌어 화면 밖일 수 있다 --
            # 이동 전에 유효성을 검사해 펫이 화면 밖에 갇히거나
            # Qt의 "알려진 화면 외부" 경고가 발생하지 않게 한다.
            rect = QRect(x, y, self.width(), self.height())
            if any(
                s.availableGeometry().intersects(rect)
                for s in QApplication.screens()
            ):
                self.move(x, y)
                return
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top())

    def _snap_to_edge(self) -> None:
        """가까운 화면 가장자리에 펫을 딱 붙인다."""
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x, y = self.x(), self.y()
        right = area.left() + area.width() - self.width()
        bottom = area.top() + area.height() - self.height()

        if abs(x - area.left()) <= SNAP_THRESHOLD:
            x = area.left()
        elif abs(x - right) <= SNAP_THRESHOLD:
            x = right
        if abs(y - area.top()) <= SNAP_THRESHOLD:
            y = area.top()
        elif abs(y - bottom) <= SNAP_THRESHOLD:
            y = bottom
        self.move(x, y)

    def _save_position(self) -> None:
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.save()

    # ---- 마우스: 드래그로 이동, 더블클릭으로 설정, 우클릭 메뉴 ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._snap_to_edge()
            self._save_position()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 더블클릭은 트레이 아이콘을 찾거나 움직이는 펫을 우클릭하는 것보다
            # 설정에 접근하기 편한 방법이다.
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._on_right_click()


def _clamp_scale(scale: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, scale))
