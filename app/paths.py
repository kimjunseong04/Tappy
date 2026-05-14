"""OS-specific filesystem locations for app data and bundled assets."""

import os
import sys
from pathlib import Path

APP_NAME = "tappy"


def user_data_dir() -> Path:
    """Per-user writable directory for config and uploaded characters."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_characters_dir() -> Path:
    path = user_data_dir() / "characters"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return user_data_dir() / "config.json"


def project_root() -> Path:
    """Root for bundled resources.

    Running from source this is the repo root. When frozen by PyInstaller
    (a macOS ``.app`` or a Windows ``.exe``) the bundled ``assets/`` folder is
    unpacked under ``sys._MEIPASS``, so resolve relative to that instead.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return project_root() / "assets"


def bundled_characters_dir() -> Path:
    return assets_dir() / "characters"
