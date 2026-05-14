"""Settings window (opened by right-clicking the pet) on a native glass window."""

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .keyboard_monitor import macos_accessibility_trusted, open_accessibility_settings
from .ui_style import ACCENT, DANGER, SWITCH_ON, WARNING, colors, content_bg
from .widgets import GlassWindow, ToggleSwitch, divider

_FILE_FILTER = "이미지 (*.gif *.png *.webp *.jpg *.jpeg *.bmp)"
_GRID_COLUMNS = 3


class _ClickCard(QFrame):
    """A clickable tile used for characters and the upload action."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(98, 112)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _character_card(
    char_id: str,
    pixmap: QPixmap,
    selected: bool,
    deletable: bool,
    on_delete,
) -> _ClickCard:
    card = _ClickCard()
    card.setObjectName("charCard")
    c = colors()
    if selected:
        card.setStyleSheet(
            "#charCard { border: 2px solid %s; border-radius: 16px;"
            " background: %s; }" % (ACCENT, c["tile_selected_bg"])
        )
    else:
        card.setStyleSheet(
            "#charCard { border: 1px solid %s;"
            " border-radius: 16px; background: %s; }"
            "#charCard:hover { background: %s; }"
            % (c["tile_border"], c["tile_bg"], c["tile_hover"])
        )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(6, 10, 6, 8)
    lay.setSpacing(5)

    thumb = QLabel()
    thumb.setFixedSize(64, 64)
    thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    thumb.setPixmap(
        pixmap.scaled(
            64,
            64,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    lay.addWidget(thumb, 0, Qt.AlignmentFlag.AlignHCenter)

    name = QLabel()
    name.setProperty("klass", "cardname")
    name.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # The card is a fixed 98px wide -- middle-elide long ids so they don't
    # spill past the edges; the full name stays available as a tooltip.
    name.setText(QFontMetrics(name.font()).elidedText(
        char_id, Qt.TextElideMode.ElideMiddle, 84))
    name.setToolTip(char_id)
    lay.addWidget(name)

    if deletable:
        # Corner badge -- a child QPushButton consumes its own click, so it
        # never triggers the card's "select" mousePressEvent.
        delete_btn = QPushButton("✕", card)
        delete_btn.setObjectName("delBtn")
        delete_btn.setFixedSize(20, 20)
        delete_btn.setToolTip("캐릭터 삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(
            "#delBtn { background-color: rgba(0,0,0,0.55); color: white;"
            " border: none; border-radius: 10px; font-size: 10px;"
            " font-weight: 700; }"
            "#delBtn:hover { background-color: %s; }" % DANGER
        )
        delete_btn.move(card.width() - delete_btn.width() - 4, 4)
        delete_btn.clicked.connect(lambda: on_delete(char_id))
        delete_btn.raise_()

    return card


def _upload_card() -> _ClickCard:
    card = _ClickCard()
    card.setObjectName("uploadCard")
    c = colors()
    card.setStyleSheet(
        "#uploadCard { border: 1px dashed %s;"
        " border-radius: 16px; background: %s; }"
        "#uploadCard:hover { background: %s; }"
        % (c["upload_border"], c["upload_bg"], c["upload_hover"])
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(6, 10, 6, 8)
    lay.setSpacing(5)

    plus = QLabel("＋")
    plus.setStyleSheet(f"font-size: 28px; color: {c['text_secondary']};")
    plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
    plus.setFixedHeight(64)
    lay.addWidget(plus)

    label = QLabel("GIF 추가")
    label.setProperty("klass", "rowsub")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(label)
    return card


class SettingsWindow(GlassWindow):
    def __init__(self, controller):
        super().__init__("설정")
        self._controller = controller
        self.setFixedSize(496, 640)

        # --- title strip ---
        # On macOS the native traffic lights are overlaid on this strip and the
        # title is drawn here; on Windows/Linux the native title bar already
        # shows the window title, so this is just a small spacer.
        titlebar = QWidget()
        if sys.platform == "darwin":
            titlebar.setFixedHeight(44)
            tb = QHBoxLayout(titlebar)
            tb.setContentsMargins(0, 0, 0, 0)
            title = QLabel("설정")
            title.setProperty("klass", "title")
            tb.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            titlebar.setFixedHeight(self.titlebar_clearance())
        self.body.addWidget(titlebar)

        # On Windows the viewport/content must be opaque, not transparent --
        # a transparent child on the Mica window leaves ghost trails when the
        # scroll area blits on scroll. content_bg() resolves this per platform.
        bg = content_bg()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet(f"background: {bg};")

        content = QWidget()
        content.setStyleSheet(f"background: {bg};")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 2, 24, 22)
        v.setSpacing(20)

        v.addLayout(self._section("캐릭터", self._build_character_card()))
        v.addLayout(self._section("애니메이션 속도", self._build_speed_card()))
        v.addLayout(self._section("일반", self._build_general_card()))
        v.addStretch(1)

        quit_btn = QPushButton("Tappy 종료")
        quit_btn.setProperty("klass", "danger")
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.clicked.connect(self._controller.quit)
        v.addWidget(quit_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        scroll.setWidget(content)
        self.body.addWidget(scroll)

        self.refresh()

    # ---- section + row helpers ----
    def _section(self, title: str, card: QWidget) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(7)
        label = QLabel(title)
        label.setProperty("klass", "section")
        label.setContentsMargins(6, 0, 0, 0)
        lay.addWidget(label)
        lay.addWidget(card)
        return lay

    def _info_row(self, title: str, sub: str, right: QWidget) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 12, 0, 12)
        h.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("klass", "row")
        text.addWidget(title_label)
        if sub:
            sub_label = QLabel(sub)
            sub_label.setProperty("klass", "rowsub")
            text.addWidget(sub_label)
        h.addLayout(text)
        h.addStretch(1)
        h.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _slider_row(
        self, title: str, sub: str, slider: QSlider, value_label: QLabel
    ) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 12, 0, 12)
        h.setSpacing(14)

        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("klass", "row")
        sub_label = QLabel(sub)
        sub_label.setProperty("klass", "rowsub")
        text.addWidget(title_label)
        text.addWidget(sub_label)
        text_holder = QWidget()
        text_holder.setLayout(text)
        text_holder.setFixedWidth(114)
        h.addWidget(text_holder)

        slider.setMinimumWidth(120)
        h.addWidget(slider, 1)

        value_label.setProperty("klass", "value")
        value_label.setFixedWidth(52)
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        h.addWidget(value_label)
        return row

    # ---- character section ----
    def _build_character_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("klass", "card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(13, 13, 13, 13)
        lay.setSpacing(2)

        self._char_grid = QGridLayout()
        self._char_grid.setSpacing(9)
        lay.addLayout(self._char_grid)

        lay.addSpacing(4)
        lay.addWidget(divider())

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(40, 300)  # percent of the frame's native size
        self._size_slider.setValue(int(round(self._controller.config.char_scale * 100)))
        self._size_value = QLabel()
        self._size_slider.valueChanged.connect(self._on_size_changed)
        lay.addWidget(
            self._slider_row(
                "크기", "화면에 표시되는 캐릭터 크기", self._size_slider, self._size_value
            )
        )
        self._sync_size_label()
        return card

    def _on_size_changed(self) -> None:
        self._sync_size_label()
        self._controller.set_char_scale(self._size_slider.value() / 100.0)

    def _sync_size_label(self) -> None:
        self._size_value.setText(f"{self._size_slider.value()}%")

    def _reload_characters(self) -> None:
        while self._char_grid.count():
            item = self._char_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        characters = self._controller.characters
        current = self._controller.config.character_id
        row = col = 0
        for char_id in characters.available_ids():
            char = characters.get(char_id)
            if char is None:
                continue
            card = _character_card(
                char_id,
                char.frames[0],
                char_id == current,
                characters.is_user_character(char_id),
                self._delete,
            )
            card.clicked.connect(lambda cid=char_id: self._select(cid))
            self._char_grid.addWidget(card, row, col)
            col += 1
            if col >= _GRID_COLUMNS:
                col, row = 0, row + 1

        upload = _upload_card()
        upload.clicked.connect(self._upload)
        self._char_grid.addWidget(upload, row, col)

    def _select(self, char_id: str) -> None:
        self._controller.select_character(char_id)
        self._reload_characters()

    def _upload(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "GIF 또는 이미지 선택", "", _FILE_FILTER
        )
        if not path:
            return
        try:
            new_id = self._controller.characters.import_gif(Path(path))
        except Exception as error:
            QMessageBox.warning(
                self, "추가 실패", f"이미지를 불러오지 못했습니다.\n{error}"
            )
            return
        self._controller.select_character(new_id)
        self._reload_characters()

    def _delete(self, char_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "캐릭터 삭제",
            f"'{char_id}' 캐릭터를 삭제할까요?\n삭제하면 복구할 수 없습니다.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._controller.delete_character(char_id)
            self._reload_characters()

    # ---- speed section ----
    def _build_speed_card(self) -> QFrame:
        config = self._controller.config

        self._min_slider = QSlider(Qt.Orientation.Horizontal)
        self._min_slider.setRange(1, 30)
        self._min_slider.setValue(int(config.min_fps))
        self._min_value = QLabel()

        self._max_slider = QSlider(Qt.Orientation.Horizontal)
        self._max_slider.setRange(5, 60)
        self._max_slider.setValue(int(config.max_fps))
        self._max_value = QLabel()

        self._min_slider.valueChanged.connect(self._on_speed_changed)
        self._max_slider.valueChanged.connect(self._on_speed_changed)

        card = QFrame()
        card.setProperty("klass", "card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 2, 16, 2)
        lay.setSpacing(0)
        lay.addWidget(
            self._slider_row(
                "최소 속도", "타이핑을 멈췄을 때", self._min_slider, self._min_value
            )
        )
        lay.addWidget(divider())
        lay.addWidget(
            self._slider_row(
                "최대 속도", "가장 빠르게 칠 때", self._max_slider, self._max_value
            )
        )
        self._sync_speed_labels()
        return card

    def _on_speed_changed(self) -> None:
        lo = self._min_slider.value()
        hi = self._max_slider.value()
        if lo > hi:
            if self.sender() is self._min_slider:
                hi = lo
                self._max_slider.blockSignals(True)
                self._max_slider.setValue(hi)
                self._max_slider.blockSignals(False)
            else:
                lo = hi
                self._min_slider.blockSignals(True)
                self._min_slider.setValue(lo)
                self._min_slider.blockSignals(False)
        self._sync_speed_labels()
        self._controller.set_fps_range(float(lo), float(hi))

    def _sync_speed_labels(self) -> None:
        self._min_value.setText(f"{self._min_slider.value()} fps")
        self._max_value.setText(f"{self._max_slider.value()} fps")

    # ---- general section ----
    def _build_general_card(self) -> QFrame:
        self._autostart_switch = ToggleSwitch(self._controller.config.autostart)
        self._autostart_switch.toggled.connect(self._controller.set_autostart)

        card = QFrame()
        card.setProperty("klass", "card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 2, 16, 2)
        lay.setSpacing(0)
        lay.addWidget(
            self._info_row(
                "부팅 시 자동 실행",
                "컴퓨터를 켤 때 함께 시작해요",
                self._autostart_switch,
            )
        )

        if sys.platform == "darwin":
            self._perm_status = QLabel()
            self._perm_button = QPushButton("열기")
            self._perm_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._perm_button.clicked.connect(open_accessibility_settings)

            right = QWidget()
            right_layout = QHBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(10)
            right_layout.addWidget(self._perm_status)
            right_layout.addWidget(self._perm_button)

            lay.addWidget(divider())
            lay.addWidget(
                self._info_row("키 입력 권한", "손쉬운 사용 접근 권한 상태", right)
            )
        return card

    # ---- refresh on open ----
    def refresh(self) -> None:
        self._reload_characters()
        # the pet can also be resized by scrolling on it, so re-sync the slider
        self._size_slider.blockSignals(True)
        self._size_slider.setValue(
            int(round(self._controller.config.char_scale * 100))
        )
        self._size_slider.blockSignals(False)
        self._sync_size_label()
        self._autostart_switch.setChecked(self._controller.config.autostart)
        if sys.platform == "darwin":
            trusted = macos_accessibility_trusted()
            self._perm_status.setText("허용됨" if trusted else "권한 필요")
            color = SWITCH_ON if trusted else WARNING
            self._perm_status.setStyleSheet(
                f"color: {color}; font-size: 12px; font-weight: 600;"
            )
            self._perm_button.setVisible(not trusted)
