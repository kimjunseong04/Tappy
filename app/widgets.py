"""재사용 가능한 위젯: 플랫폼 네이티브 창 베이스와 토글 스위치.

`GlassWindow`는 모든 OS에서 네이티브 창 프레임을 유지하고 플랫폼별 배경을 선택한다:
  - macOS: pyqt-liquidglass를 통한 실제 Tahoe "Liquid Glass".
  - Windows: win32mica를 통한 Windows 11 Mica 배경 (Windows 10 또는 라이브러리 없을 때는
    불투명 네이티브 창으로 대체).
  - 기타: 일반 네이티브 창.
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
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .ui_style import SWITCH_ON, colors


def _lerp(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


class GlassWindow(QMainWindow):
    """플랫폼에 맞는 반투명 배경을 가진 네이티브 창.

    pyqt-liquidglass의 유리 주입은 콘텐츠 뷰에 수퍼뷰가 있을 때 가장 안정적이므로
    QWidget 대신 QMainWindow를 사용한다 -- 그렇지 않으면 불안정한 콘텐츠 뷰 교체로
    대체(fallback)되어 창이 내용 없는 덩어리로 렌더링된다.

    서브클래스는 ``self.body``에 콘텐츠를 구성하며, 컨트롤러는
    배경이 적절한 시점에 적용되도록 ``show()`` 대신 ``present()``를 호출한다.
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
        """콘텐츠가 창 컨트롤을 가리지 않기 위한 상단 패딩.

        macOS는 트래픽 라이트를 전체 크기 콘텐츠 뷰 위에 오버레이하므로
        콘텐츠가 공간을 비워야 한다. Windows/Linux는 별도 네이티브 타이틀바가 있으므로
        최소한의 여백만 필요하다.
        """
        return 44 if sys.platform == "darwin" else 14

    def present(self) -> None:
        if sys.platform == "darwin":
            import pyqt_liquidglass as glass

            # NSWindow를 구성(투명 타이틀바, 전체 크기 콘텐츠)하고 창을 표시한다.
            glass.prepare_window_for_glass(self)
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if not self._effect_applied:
            self._effect_applied = True
            # 레이아웃이 안정된 후 네이티브 배경을 주입한다.
            QTimer.singleShot(60, self._apply_effect)

    def _apply_effect(self) -> None:
        if sys.platform == "darwin":
            import pyqt_liquidglass as glass

            # 트래픽 라이트를 네이티브 위치에 그대로 둔다 --
            # setup_traffic_lights_inset()으로 재배치하면 둥근 창 모서리에서 잘린다.
            # titlebar_clearance()로 콘텐츠가 가려지지 않게 한다.
            glass.apply_glass_to_window(self)
        elif sys.platform == "win32":
            self._apply_mica()

    def _apply_mica(self) -> None:
        """Windows 11 Mica 배경을 적용한다; 실패 시 불투명 상태 유지."""
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
            # Windows 10, win32mica 없음, 또는 미지원 빌드:
            # 일반(테마 인식) 불투명 네이티브 창으로 대체.
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.update()


class ToggleSwitch(QWidget):
    """애니메이션이 있는 macOS 스타일 온/오프 스위치."""

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
    line.setStyleSheet(f"background: {colors()['divider']}; border: none;")
    return line


class PermissionCard(QFrame):
    """환영·설정 창이 공유하는 macOS 입력 모니터링 요청 카드.

    두 가지 시각 상태 -- 권한이 필요할 때 주황색 프롬프트 + 허용 버튼,
    허용됐을 때 차분한 확인 표시. ``set_granted``가 제자리에서 모핑하므로
    실시간 허용 시 주변 레이아웃이 재배치되지 않는다.
    """

    def __init__(self, on_request, parent=None):
        super().__init__(parent)
        self.setObjectName("permcard")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 13, 13, 13)
        h.setSpacing(12)

        self._icon = QLabel()
        self._icon.setStyleSheet("font-size: 18px;")
        h.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        self._head = QLabel()
        self._head.setProperty("klass", "title")
        self._sub = QLabel()
        self._sub.setProperty("klass", "rowsub")
        self._sub.setWordWrap(True)
        text.addWidget(self._head)
        text.addWidget(self._sub)
        h.addLayout(text, 1)

        self._button = QPushButton("허용")
        self._button.setProperty("klass", "primary")
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(on_request)
        h.addWidget(self._button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_granted(False)

    def set_granted(self, granted: bool) -> None:
        if granted:
            self.setStyleSheet(
                "#permcard { background: rgba(52,199,89,0.15);"
                " border: 1px solid rgba(52,199,89,0.42); border-radius: 14px; }"
            )
            self._icon.setText("✅")
            self._head.setText("입력 모니터링 허용됨")
            self._head.setStyleSheet(f"color: {SWITCH_ON};")
            self._sub.setText("이제 타이핑에 맞춰 캐릭터가 반응해요.")
            self._button.setVisible(False)
        else:
            self.setStyleSheet(
                "#permcard { background: rgba(255,159,10,0.16);"
                " border: 1px solid rgba(255,159,10,0.4); border-radius: 14px; }"
            )
            self._icon.setText("⌨️")
            self._head.setText("입력 모니터링 권한이 필요해요")
            self._head.setStyleSheet("")
            self._sub.setText(
                "타이핑 속도를 감지하려면 권한이 필요해요. "
                "'허용'을 누르면 시스템 창이 떠요."
            )
            self._button.setVisible(True)
