"""첫 실행 환영 화면. 네이티브 유리 창 위에 콘텐츠를 순차적으로 나타내는 입장 애니메이션 포함."""

import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .paths import assets_dir
from .ui_style import content_bg
from .widgets import GlassWindow, PermissionCard

_FEATURES = [
    ("⌨️", "타이핑 속도에 반응", "치는 속도에 맞춰 애니메이션이 빨라져요"),
    ("🎭", "나만의 캐릭터", "GIF를 올려서 직접 캐릭터를 만들 수 있어요"),
    ("🚀", "부팅 시 자동 실행", "컴퓨터를 켜면 알아서 함께 시작해요"),
]


class WelcomeWindow(GlassWindow):
    def __init__(
        self,
        *,
        on_get_started,
        on_request_permission,
        needs_permission: bool,
    ):
        super().__init__("Tappy")
        self.setFixedSize(460, 648 if needs_permission else 560)
        self._on_get_started = on_get_started
        self._dismissed = False
        self._animated = False
        self._anims: list[QParallelAnimationGroup] = []
        self._perm_card: PermissionCard | None = None

        content = QWidget()
        # Windows에서는 불투명하게 설정 -- Mica 창의 투명 자식 위젯은
        # 위젯 재페인트/이동 시 잔상이 남는다. macOS에서는 유리가 비쳐 보이도록 투명 유지.
        # ui_style.content_bg 참고.
        content.setStyleSheet(f"background: {content_bg()};")
        v = QVBoxLayout(content)
        # 상단 여백으로 macOS의 창 컨트롤(트래픽 라이트)을 가리지 않게 한다
        v.setContentsMargins(40, self.titlebar_clearance() + 6, 40, 30)
        v.setSpacing(0)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(assets_dir() / "tappy_logo.png"))
        logo.setPixmap(
            pixmap.scaled(
                108,
                108,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        v.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(14)

        title = QLabel("Tappy")
        title.setProperty("klass", "hero")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(title)
        v.addSpacing(6)

        subtitle = QLabel("타이핑이 빠를수록\n캐릭터가 더 신나게 춤춰요")
        subtitle.setProperty("klass", "subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(subtitle)
        v.addSpacing(28)

        # 입장 애니메이션이 순서대로 나타낼 위젯들
        self._anim_targets: list[QWidget] = [logo, title, subtitle]

        feature_card = QFrame()
        feature_card.setProperty("klass", "card")
        fc = QVBoxLayout(feature_card)
        fc.setContentsMargins(18, 6, 18, 6)
        fc.setSpacing(0)
        for index, (emoji, head, sub) in enumerate(_FEATURES):
            if index:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet("background: rgba(128,128,128,0.16);")
                fc.addWidget(line)
            fc.addWidget(self._feature_row(emoji, head, sub))
        self._anim_targets.append(feature_card)
        v.addWidget(feature_card)

        if needs_permission:
            v.addSpacing(14)
            self._perm_card = PermissionCard(on_request_permission)
            self._anim_targets.append(self._perm_card)
            v.addWidget(self._perm_card)

        v.addStretch(1)
        v.addSpacing(22)  # 버튼이 위 콘텐츠와 충분히 떨어지도록 간격 확보

        start = QPushButton("시작하기")
        start.setProperty("klass", "primary")
        start.setCursor(Qt.CursorShape.PointingHandCursor)
        start.setFixedHeight(38)
        start.clicked.connect(self.close)
        v.addWidget(start)
        self._anim_targets.append(start)

        # 순차 나타내기는 QGraphicsOpacityEffect + 위치 애니메이션을 사용한다.
        # Windows의 반투명 Mica 창에서는 이 조합이 잔상을 남긴다 --
        # 비워진 위젯 영역이 지워지지 않아 세로 얼룩이 생긴다 --
        # 따라서 입장 애니메이션은 macOS 전용이다. Windows에서는 콘텐츠가 바로 표시된다.
        self._animate_enabled = sys.platform == "darwin"
        if self._animate_enabled:
            # 모든 대상을 숨긴 상태로 시작; showEvent에서 나타내기 시작
            for widget in self._anim_targets:
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(0.0)
                widget.setGraphicsEffect(effect)

        self.body.addWidget(content)

    # ---- 실시간 권한 업데이트 ----
    def refresh_permission(self) -> None:
        """컨트롤러가 권한이 실시간으로 허용됐을 때 호출한다."""
        if self._perm_card is not None:
            self._perm_card.set_granted(True)

    # ---- 입장 애니메이션 ----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._animated:
            self._animated = True
            if self._animate_enabled:
                # 유리 + 레이아웃이 안정된 후 나타내기 시작
                QTimer.singleShot(120, self._animate_in)

    def _animate_in(self) -> None:
        for index, widget in enumerate(self._anim_targets):
            effect = widget.graphicsEffect()
            final = widget.pos()
            start = QPoint(final.x(), final.y() + 16)
            widget.move(start)

            fade = QPropertyAnimation(effect, b"opacity", self)
            fade.setDuration(340)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setEasingCurve(QEasingCurve.Type.OutCubic)

            slide = QPropertyAnimation(widget, b"pos", self)
            slide.setDuration(400)
            slide.setStartValue(start)
            slide.setEndValue(final)
            slide.setEasingCurve(QEasingCurve.Type.OutCubic)

            group = QParallelAnimationGroup(self)
            group.addAnimation(fade)
            group.addAnimation(slide)
            self._anims.append(group)
            QTimer.singleShot(index * 65, group.start)

    # ---- 구성 요소 ----
    def _feature_row(self, emoji: str, head: str, sub: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 13, 0, 13)
        h.setSpacing(14)

        icon = QLabel(emoji)
        icon.setStyleSheet("font-size: 21px;")
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        h.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(2)
        head_label = QLabel(head)
        head_label.setProperty("klass", "title")
        sub_label = QLabel(sub)
        sub_label.setProperty("klass", "rowsub")
        text.addWidget(head_label)
        text.addWidget(sub_label)
        h.addLayout(text)
        h.addStretch(1)
        return row

    # ---- 닫기도 "시작하기"로 처리 ----
    def closeEvent(self, event) -> None:
        if not self._dismissed:
            self._dismissed = True
            self._on_get_started()
        super().closeEvent(event)
