"""Shared palette and stylesheet, adapted to the system light/dark appearance.

The window background is a real native translucent material (macOS Liquid
Glass / Windows Mica), so Qt controls are left to render natively -- we only
style text labels and the subtle grouped "cards". Those few colours have to
follow the system appearance: a fixed light palette is invisible on a dark
glass window. ``colors()`` resolves them at call time -- it needs a running
QApplication, so it cannot be done at import time.
"""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

# Saturated accent colours -- legible on both light and dark glass.
ACCENT = "#0A84FF"
SWITCH_ON = "#34C759"
DANGER = "#FF453A"
WARNING = "#FF9F0A"

_LIGHT = {
    "text_secondary": "#86868B",
    # Opaque content background, used on Windows only (see content_bg).
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
    """Whether the system is currently in dark mode (False if undeterminable)."""
    app = QGuiApplication.instance()
    if app is None:
        return False
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def colors() -> dict[str, str]:
    """Appearance-dependent colours for the current system theme."""
    return _DARK if is_dark() else _LIGHT


def content_bg() -> str:
    """Background for content layered on the window backdrop.

    Transparent everywhere except Windows. On a Windows Mica window (which
    sets ``WA_TranslucentBackground``), a child with ``background: transparent``
    never clears its stale pixels on a partial repaint -- a scroll-area blit or
    a moved widget leaves ghost trails. An opaque background gives Qt a surface
    to clear against. macOS Liquid Glass composites natively, so it stays
    transparent there and the glass shows through.
    """
    if sys.platform == "win32":
        return colors()["window_bg"]
    return "transparent"


def stylesheet() -> str:
    """The global stylesheet, built for the current appearance.

    Labels without an explicit ``color`` inherit the Qt palette, which already
    follows the system appearance -- only the secondary (greyed) text needs an
    explicit, appearance-aware colour.
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

/* macOS QPushButton ignores the `background` shorthand from QSS -- it only
   leaves native rendering once `background-color` (+ border) is set. */
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
