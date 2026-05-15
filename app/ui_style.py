"""시스템 라이트/다크 모드에 맞게 조정되는 공유 팔레트와 스타일시트.

창 배경은 실제 네이티브 반투명 소재(macOS Liquid Glass / Windows Mica)이므로
Qt 컨트롤은 네이티브 렌더링에 맡기고, 텍스트 레이블과 미묘한 그룹형 "카드"만 스타일링한다.
해당 색상은 시스템 모드를 따라야 한다: 고정 라이트 팔레트는 다크 유리 창에서 보이지 않는다.
``colors()``는 호출 시점에 값을 확정한다 -- 실행 중인 QApplication이 필요하므로
임포트 시점에 처리할 수 없다.
"""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

# 포화된 강조 색상 -- 라이트·다크 유리 모두에서 가독성이 좋다.
ACCENT = "#0A84FF"
SWITCH_ON = "#34C759"
DANGER = "#FF453A"
WARNING = "#FF9F0A"

_LIGHT = {
    "text_secondary": "#86868B",
    # 불투명 콘텐츠 배경, Windows 전용 (content_bg 참고).
    "window_bg": "#F3F3F3",
    "divider": "rgba(60,60,67,0.16)",
    "card_bg": "rgba(255,255,255,0.42)",
    "card_border": "rgba(255,255,255,0.55)",
    "tile_bg": "rgba(255,255,255,0.34)",
    "tile_border": "rgba(255,255,255,0.60)",
    "tile_hover": "rgba(255,255,255,0.55)",
    "tile_selected_bg": "rgba(10,132,255,0.14)",
    "upload_bg": "rgba(255,255,255,0.22)",
    "upload_border": "rgba(120,120,128,0.55)",
    "upload_hover": "rgba(255,255,255,0.42)",
}

_DARK = {
    "text_secondary": "#AEAEB2",
    "window_bg": "#202020",
    "divider": "rgba(255,255,255,0.14)",
    "card_bg": "rgba(255,255,255,0.07)",
    "card_border": "rgba(255,255,255,0.14)",
    "tile_bg": "rgba(255,255,255,0.07)",
    "tile_border": "rgba(255,255,255,0.16)",
    "tile_hover": "rgba(255,255,255,0.14)",
    "tile_selected_bg": "rgba(10,132,255,0.28)",
    "upload_bg": "rgba(255,255,255,0.05)",
    "upload_border": "rgba(255,255,255,0.22)",
    "upload_hover": "rgba(255,255,255,0.11)",
}


def is_dark() -> bool:
    """현재 시스템이 다크 모드인지 반환한다 (판단 불가 시 False)."""
    app = QGuiApplication.instance()
    if app is None:
        return False
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def colors() -> dict[str, str]:
    """현재 시스템 테마에 따른 모드별 색상을 반환한다."""
    return _DARK if is_dark() else _LIGHT


def content_bg() -> str:
    """창 배경 위에 겹쳐지는 콘텐츠의 배경색.

    Windows를 제외한 모든 플랫폼에서 투명. Windows Mica 창(``WA_TranslucentBackground`` 설정)에서
    ``background: transparent`` 자식은 부분 재페인트 시 이전 픽셀을 지우지 않아
    스크롤 영역 블릿이나 이동한 위젯이 잔상을 남긴다. 불투명 배경은 Qt가 그 위를
    지울 면을 제공한다. macOS Liquid Glass는 네이티브로 합성되므로 투명을 유지하고
    유리가 비쳐 보인다.
    """
    if sys.platform == "win32":
        return colors()["window_bg"]
    return "transparent"


def stylesheet() -> str:
    """현재 모드로 구성된 전역 스타일시트.

    명시적 ``color``가 없는 레이블은 Qt 팔레트를 상속하며 이미 시스템 모드를 따르므로
    보조(회색) 텍스트만 명시적·모드 인식 색상이 필요하다.
    """
    c = colors()
    return f"""
QLabel[klass="hero"]     {{ font-size: 25px; font-weight: 700; }}
QLabel[klass="title"]    {{ font-size: 15px; font-weight: 600; }}
QLabel[klass="subtitle"] {{ font-size: 13px; color: {c['text_secondary']}; }}
QLabel[klass="section"]  {{ font-size: 12px; font-weight: 600; color: {c['text_secondary']}; }}
QLabel[klass="row"]      {{ font-size: 13px; font-weight: 500; }}
QLabel[klass="rowsub"]   {{ font-size: 11px; color: {c['text_secondary']}; }}
QLabel[klass="value"]    {{ font-size: 12px; color: {c['text_secondary']}; }}
QLabel[klass="cardname"] {{ font-size: 11px; font-weight: 500; }}

QFrame[klass="card"] {{
    background: {c['card_bg']};
    border: 1px solid {c['card_border']};
    border-radius: 12px;
}}

/* macOS QPushButton은 QSS의 `background` 단축 속성을 무시한다 --
   `background-color` (+ border)를 설정해야 네이티브 렌더링을 벗어난다. */
QPushButton[klass="primary"] {{
    background-color: {ACCENT}; color: white;
    border: 1px solid {ACCENT}; border-radius: 9px;
    padding: 9px 20px; font-size: 13px; font-weight: 600;
}}
QPushButton[klass="primary"]:hover {{
    background-color: #339DFF; border-color: #339DFF;
}}
QPushButton[klass="primary"]:pressed {{
    background-color: #0062CC; border-color: #0062CC;
}}

QPushButton[klass="danger"] {{
    background-color: {DANGER}; color: white;
    border: 1px solid {DANGER}; border-radius: 9px;
    padding: 9px 20px; font-size: 13px; font-weight: 600;
}}
QPushButton[klass="danger"]:hover {{
    background-color: #FF6961; border-color: #FF6961;
}}
QPushButton[klass="danger"]:pressed {{
    background-color: #D70015; border-color: #D70015;
}}
"""
