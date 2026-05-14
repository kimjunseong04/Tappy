"""First-launch welcome screen on a native glass window, with an entrance
animation that staggers the content into view."""

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
from .widgets import GlassWindow

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
        on_open_accessibility,
        needs_permission: bool,
    ):
        super().__init__("Tappy")
        self.setFixedSize(460, 640 if needs_permission else 560)
        self._on_get_started = on_get_started
        self._dismissed = False
        self._animated = False
        self._anims: list[QParallelAnimationGroup] = []

        content = QWidget()
        # Opaque on Windows -- a transparent child on the Mica window leaves
        # ghost trails when widgets repaint/move; transparent on macOS so the
        # glass shows through. See ui_style.content_bg.
        content.setStyleSheet(f"background: {content_bg()};")
        v = QVBoxLayout(content)
        # top margin clears the window controls (overlaid on macOS)
        v.setContentsMargins(40, self.titlebar_clearance() + 4, 40, 32)
        v.setSpacing(0)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(assets_dir() / "tappy_logo.png"))
        logo.setPixmap(
            pixmap.scaled(
                116,
                116,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        v.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(16)

        title = QLabel("Tappy")
        title.setProperty("klass", "hero")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(title)
        v.addSpacing(6)

        subtitle = QLabel("타이핑이 빠를수록\n캐릭터가 더 신나게 춤춰요")
        subtitle.setProperty("klass", "subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(subtitle)
        v.addSpacing(26)

        # widgets the entrance animation staggers into view, in order
        self._anim_targets: list[QWidget] = [logo, title, subtitle]

        for emoji, head, sub in _FEATURES:
            row = self._feature_row(emoji, head, sub)
            self._anim_targets.append(row)
            v.addWidget(row)
            v.addSpacing(14)

        if needs_permission:
            v.addSpacing(4)
            perm_card = self._permission_card(on_open_accessibility)
            self._anim_targets.append(perm_card)
            v.addWidget(perm_card)

        v.addStretch(1)
        v.addSpacing(20)  # keep the button clear of the content above it

        start = QPushButton("시작하기")
        start.setProperty("klass", "primary")
        start.setCursor(Qt.CursorShape.PointingHandCursor)
        start.setFixedHeight(36)
        start.clicked.connect(self.close)
        v.addWidget(start)
        self._anim_targets.append(start)

        # The staggered reveal uses QGraphicsOpacityEffect + a position
        # animation. On Windows' translucent Mica window that combination
        # ghosts -- the vacated widget regions are never cleared, leaving
        # vertical smears -- so the entrance animation is macOS-only. On
        # Windows the content just appears at full opacity.
        self._animate_enabled = sys.platform == "darwin"
        if self._animate_enabled:
            # start every target hidden; showEvent kicks off the reveal
            for widget in self._anim_targets:
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(0.0)
                widget.setGraphicsEffect(effect)

        self.body.addWidget(content)

    # ---- entrance animation ----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._animated:
            self._animated = True
            if self._animate_enabled:
                # wait for the glass + layout to settle, then reveal
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

    # ---- pieces ----
    def _feature_row(self, emoji: str, head: str, sub: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
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

    def _permission_card(self, on_open) -> QFrame:
        card = QFrame()
        card.setObjectName("permcard")
        card.setStyleSheet(
            "#permcard { background: rgba(255,159,10,0.16);"
            " border: 1px solid rgba(255,159,10,0.4); border-radius: 12px; }"
        )
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 12, 12, 12)
        h.setSpacing(11)

        icon = QLabel("⚠️")
        icon.setStyleSheet("font-size: 17px;")
        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        head = QLabel("키 입력 권한이 필요해요")
        head.setProperty("klass", "title")
        sub = QLabel("시스템 설정 › 손쉬운 사용에서 권한을 허용한 뒤\n앱을 다시 실행하세요.")
        sub.setProperty("klass", "rowsub")
        text.addWidget(head)
        text.addWidget(sub)
        h.addLayout(text)
        h.addStretch(1)

        button = QPushButton("열기")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(on_open)
        h.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    # ---- closing also counts as "get started" ----
    def closeEvent(self, event) -> None:
        if not self._dismissed:
            self._dismissed = True
            self._on_get_started()
        super().closeEvent(event)
