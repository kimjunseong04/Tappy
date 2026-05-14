"""Shared palette and a light stylesheet.

The window background is real macOS Tahoe "Liquid Glass" supplied by
pyqt-liquidglass, so Qt controls (buttons, sliders, scrollbars) are left
to render with their native macOS style -- we only style text labels and
the subtle grouped "cards".
"""

TEXT = "#1D1D1F"
TEXT_SECONDARY = "#86868B"
ACCENT = "#007AFF"
SWITCH_ON = "#34C759"
DANGER = "#FF3B30"
WARNING = "#FF9500"

DIVIDER = "rgba(60,60,67,0.16)"
CARD_BG = "rgba(255,255,255,0.42)"
CARD_BORDER = "rgba(255,255,255,0.55)"

STYLESHEET = f"""
QLabel[klass="hero"]     {{ font-size: 25px; font-weight: 700; }}
QLabel[klass="title"]    {{ font-size: 15px; font-weight: 600; }}
QLabel[klass="subtitle"] {{ font-size: 13px; color: {TEXT_SECONDARY}; }}
QLabel[klass="section"]  {{ font-size: 12px; font-weight: 600; color: {TEXT_SECONDARY}; }}
QLabel[klass="row"]      {{ font-size: 13px; font-weight: 500; }}
QLabel[klass="rowsub"]   {{ font-size: 11px; color: {TEXT_SECONDARY}; }}
QLabel[klass="value"]    {{ font-size: 12px; color: {TEXT_SECONDARY}; }}

QFrame[klass="card"] {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
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
    background-color: #1A86FF; border-color: #1A86FF;
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
    background-color: #FF564D; border-color: #FF564D;
}}
QPushButton[klass="danger"]:pressed {{
    background-color: #D70015; border-color: #D70015;
}}
"""
