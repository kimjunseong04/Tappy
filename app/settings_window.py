"""설정 창 (펫을 우클릭하거나 더블클릭하면 열림). 네이티브 유리 창 위에 표시된다."""

import sys
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPixmap
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

from .keyboard_monitor import keystroke_permission_granted
from .paths import app_version, assets_dir, is_frozen
from .ui_style import ACCENT, DANGER, colors, content_bg
from .updater import UpdateState
from .widgets import GlassWindow, PermissionCard, ToggleSwitch, divider

_FILE_FILTER = "이미지 (*.gif *.png *.webp *.jpg *.jpeg *.bmp)"
_GRID_COLUMNS = 3
# 창이 열려 있는 동안 실시간 반응 속도 미터를 재샘플링하는 주기.
_METER_INTERVAL_MS = 90


class _MeterBar(QWidget):
    """유리 미학에 맞춰 페인팅된 슬림 라운드 진행 바."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ratio = 0.0
        self.setFixedHeight(10)

    def set_ratio(self, ratio: float) -> None:
        ratio = max(0.0, min(1.0, ratio))
        if abs(ratio - self._ratio) < 0.005:
            return
        self._ratio = ratio
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        radius = h / 2

        track = QRectF(0, 0, self.width(), h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(128, 128, 128, 56))
        painter.drawRoundedRect(track, radius, radius)

        if self._ratio > 0:
            fill_w = max(h, self.width() * self._ratio)
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(QRectF(0, 0, fill_w, h), radius, radius)


class _ReactivityMeter(QFrame):
    """타이핑 속도 → 애니메이션 FPS 실시간 표시.

    권한 점검 기능도 겸한다: 키를 입력해도 바가 움직이지 않으면
    OS가 키 입력을 전달하지 않는 것 (macOS 입력 모니터링 공백) --
    이 경우 전용 권한 섹션이 원인을 설명한다.
    """

    def __init__(self):
        super().__init__()
        self.setProperty("klass", "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 15)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel("실시간 반응 속도")
        title.setProperty("klass", "row")
        self._sub = QLabel()
        self._sub.setProperty("klass", "rowsub")
        text.addWidget(title)
        text.addWidget(self._sub)
        top.addLayout(text)
        top.addStretch(1)

        self._fps_value = QLabel()
        self._fps_value.setStyleSheet(
            f"color: {ACCENT}; font-size: 22px; font-weight: 700;"
        )
        self._fps_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top.addWidget(self._fps_value)
        lay.addLayout(top)

        self._bar = _MeterBar()
        lay.addWidget(self._bar)

        self.update_reading(0.0, 0.0, 1.0, 30.0)

    def update_reading(self, kps: float, fps: float, lo: float, hi: float) -> None:
        span = max(0.001, hi - lo)
        self._bar.set_ratio((fps - lo) / span)
        self._fps_value.setText(f"{fps:.0f} fps")
        if kps > 0.05:
            self._sub.setText(f"입력 감지 중 · 초당 {kps:.1f}타")
        else:
            self._sub.setText("타이핑하면 캐릭터가 더 빨라져요")


class _UpdateCard(QFrame):
    """자동 업데이트 카드: UpdateState에 따라 모핑되는 단일 위젯.

    단일 버튼이 상태별로 분기 (확인/다시 확인/다시 시도 → check,
    업데이트 → download, 지금 재시작 → apply); 다운로드 중에는 버튼을
    재사용된 ``_MeterBar``로 교체한다. 설정 창이 컨트롤러에 전달하는
    세 가지 인텐트 시그널을 발행한다.
    """

    check_requested = pyqtSignal()
    download_requested = pyqtSignal()
    apply_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("klass", "card")
        self._state = UpdateState.IDLE

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 13, 13, 13)
        h.setSpacing(12)

        self._icon = QLabel()
        self._icon.setStyleSheet("font-size: 18px;")
        h.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        self._title = QLabel()
        self._title.setProperty("klass", "row")
        self._sub = QLabel()
        self._sub.setProperty("klass", "rowsub")
        self._sub.setWordWrap(True)
        text.addWidget(self._title)
        text.addWidget(self._sub)
        h.addLayout(text, 1)

        self._bar = _MeterBar()
        self._bar.setFixedWidth(120)
        h.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignVCenter)

        self._button = QPushButton()
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_button)
        h.addWidget(self._button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.set_state(UpdateState.IDLE, None, "")

    def _on_button(self) -> None:
        if self._state == UpdateState.AVAILABLE:
            self.download_requested.emit()
        elif self._state == UpdateState.READY:
            self.apply_requested.emit()
        else:  # IDLE / UP_TO_DATE / ERROR
            self.check_requested.emit()

    def _style_button(self, label: str, primary: bool, enabled: bool = True) -> None:
        self._button.setText(label)
        self._button.setEnabled(enabled)
        self._button.setProperty("klass", "primary" if primary else "")
        self._button.style().unpolish(self._button)
        self._button.style().polish(self._button)

    def set_state(self, state: UpdateState, info, message: str) -> None:
        self._state = state
        version = app_version()
        # 기본 레이아웃: 버튼 표시, 진행 바 숨김
        self._bar.setVisible(False)
        self._button.setVisible(True)
        self._sub.setVisible(True)

        if state == UpdateState.CHECKING:
            self._icon.setText("🔄")
            self._title.setText("업데이트 확인 중…")
            self._sub.setVisible(False)
            self._style_button("확인", primary=False, enabled=False)
        elif state == UpdateState.AVAILABLE:
            self._icon.setText("🎉")
            new_v = info.version if info else "?"
            self._title.setText(f"새 버전 v{new_v} 사용 가능")
            self._sub.setText("'업데이트'를 누르면 받아서 자동으로 교체해요.")
            self._style_button("업데이트", primary=True)
        elif state == UpdateState.DOWNLOADING:
            self._icon.setText("⬇️")
            self._title.setText("다운로드 중… 0%")
            self._sub.setVisible(False)
            self._button.setVisible(False)
            self._bar.setVisible(True)
            self._bar.set_ratio(0.0)
        elif state == UpdateState.READY:
            self._icon.setText("✅")
            self._title.setText("재시작하면 업데이트가 끝나요")
            self._sub.setText("지금 재시작하면 새 버전으로 다시 열려요.")
            self._style_button("지금 재시작", primary=True)
        elif state == UpdateState.ERROR:
            self._icon.setText("⚠️")
            self._title.setText("업데이트에 실패했어요")
            self._sub.setText(message or "잠시 후 다시 시도해 주세요.")
            self._style_button("다시 시도", primary=False)
        else:  # IDLE or UP_TO_DATE
            self._icon.setText("✨")
            self._title.setText("최신 버전입니다")
            self._sub.setText(f"v{version}" if version else "Tappy")
            self._style_button("다시 확인", primary=False)

    def set_progress(self, done: int, total: int) -> None:
        if self._state != UpdateState.DOWNLOADING:
            return
        ratio = done / total if total else 0.0
        self._bar.set_ratio(ratio)
        self._title.setText(f"다운로드 중… {ratio * 100:.0f}%")


class _ClickCard(QFrame):
    """캐릭터와 업로드 동작에 사용하는 클릭 가능한 타일."""

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
    # 카드 너비는 고정 98px -- 긴 id는 가운데 생략해 양쪽으로 넘치지 않게 한다;
    # 전체 이름은 툴팁으로 확인할 수 있다.
    name.setText(QFontMetrics(name.font()).elidedText(
        char_id, Qt.TextElideMode.ElideMiddle, 84))
    name.setToolTip(char_id)
    lay.addWidget(name)

    if deletable:
        # 모서리 배지 -- 자식 QPushButton은 자체 클릭을 소비하므로
        # 카드의 "선택" mousePressEvent를 발생시키지 않는다.
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
        self.setFixedSize(496, 668)
        # macOS·frozen 빌드에서만 생성하지만 (아래 참고), 접근 시 None이
        # AttributeError 대신 안전하게 반환되도록 여기서 선언한다.
        self._perm_card: PermissionCard | None = None
        self._update_card: _UpdateCard | None = None

        # 실시간 반응 속도 미터는 창이 실제로 화면에 있을 때만 타이머가 동작한다
        # (showEvent / hideEvent 참고).
        self._meter_timer = QTimer(self)
        self._meter_timer.timeout.connect(self._tick_meter)

        # --- 타이틀 스트립: macOS 트래픽 라이트를 가리지 않는 순수 여백;
        # 앱 정체성은 아래 콘텐츠 헤더가 담당한다. ---
        titlebar = QWidget()
        titlebar.setFixedHeight(
            44 if sys.platform == "darwin" else self.titlebar_clearance()
        )
        self.body.addWidget(titlebar)

        # Windows에서 뷰포트/콘텐츠는 불투명해야 한다 --
        # Mica 창의 투명 자식은 스크롤 영역 블릿 시 잔상을 남긴다.
        # content_bg()가 플랫폼별로 값을 반환한다.
        bg = content_bg()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setStyleSheet(f"background: {bg};")

        content = QWidget()
        content.setStyleSheet(f"background: {bg};")
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 0, 24, 22)
        v.setSpacing(18)

        v.addWidget(self._build_header())

        self._meter = _ReactivityMeter()
        v.addLayout(self._section("실시간 반응", self._meter))

        v.addLayout(self._section("캐릭터", self._build_character_card()))
        v.addLayout(self._section("애니메이션 속도", self._build_speed_card()))

        if sys.platform == "darwin":
            self._perm_card = PermissionCard(self._controller.prompt_for_permission)
            v.addLayout(self._section("입력 권한", self._perm_card))

        # 업데이트 섹션은 frozen 빌드에서만 의미가 있다 --
        # 소스 실행 시에는 자기 교체할 번들이 없다.
        if is_frozen():
            self._update_card = _UpdateCard()
            self._update_card.check_requested.connect(
                self._controller.request_update_check
            )
            self._update_card.download_requested.connect(
                self._controller.request_update_download
            )
            self._update_card.apply_requested.connect(
                self._controller.request_update_apply
            )
            v.addLayout(self._section("업데이트", self._update_card))

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

    # ---- 헤더 ----
    def _build_header(self) -> QWidget:
        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(2, 2, 2, 0)
        h.setSpacing(13)

        logo = QLabel()
        logo_path = assets_dir() / "tappy_logo.png"
        if logo_path.exists():
            logo.setPixmap(
                QPixmap(str(logo_path)).scaled(
                    44,
                    44,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        h.addWidget(logo)

        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("설정")
        title.setProperty("klass", "hero")
        text.addWidget(title)
        version = app_version()
        caption = QLabel(f"Tappy · v{version}" if version else "Tappy")
        caption.setProperty("klass", "subtitle")
        text.addWidget(caption)
        h.addLayout(text)
        h.addStretch(1)
        return header

    # ---- 실시간 반응 속도 미터 ----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._tick_meter()
        self._meter_timer.start(_METER_INTERVAL_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._meter_timer.stop()

    def _tick_meter(self) -> None:
        controller = self._controller
        self._meter.update_reading(
            controller.monitor.recent_rate(),
            controller.speed.fps,
            controller.config.min_fps,
            controller.config.max_fps,
        )

    # ---- 섹션 + 행 헬퍼 ----
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
        # 잘리지 않고 줄바꿈 -- 캡션이 고정 레이블 열보다 길어서 없으면 중간에 잘린다.
        sub_label.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(sub_label)
        text_holder = QWidget()
        text_holder.setLayout(text)
        text_holder.setFixedWidth(132)
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

    # ---- 캐릭터 섹션 ----
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
        self._size_slider.setRange(40, 300)  # 프레임 기본 크기 대비 퍼센트
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

    # ---- 속도 섹션 ----
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

    # ---- 일반 섹션 ----
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
        return card

    # ---- 열 때 새로고침 ----
    def refresh(self) -> None:
        self._reload_characters()
        # 펫을 스크롤로 크기 조절할 수 있으므로 슬라이더를 다시 동기화한다
        self._size_slider.blockSignals(True)
        self._size_slider.setValue(
            int(round(self._controller.config.char_scale * 100))
        )
        self._size_slider.blockSignals(False)
        self._sync_size_label()
        self._autostart_switch.setChecked(self._controller.config.autostart)
        self.refresh_permission()
        # 컨트롤러가 이미 알고 있는 업데이트 상태를 즉시 렌더링한다
        # (무음 시작 확인이 이 창이 열리기 전에 완료됐을 수 있음).
        if self._update_card is not None:
            self._update_card.set_state(*self._controller.last_update_state)

    def refresh_permission(self) -> None:
        """권한 카드만 재동기화 -- 창 전체를 재구성하지 않고 실시간 허용에 충분히 빠르다."""
        if self._perm_card is not None:
            self._perm_card.set_granted(keystroke_permission_granted())

    def set_update_state(self, state, info, message: str) -> None:
        """컨트롤러에서 받은 업데이트 상태 변경을 카드에 전달한다."""
        if self._update_card is not None:
            self._update_card.set_state(state, info, message)

    def set_update_progress(self, done: int, total: int) -> None:
        if self._update_card is not None:
            self._update_card.set_progress(done, total)
