"""크로스 플랫폼 "로그인 시 실행" 토글.

Windows: HKCU ...\\CurrentVersion\\Run 레지스트리 항목.
macOS:   ~/Library/LaunchAgents의 LaunchAgent plist.

등록된 명령은 현재 Python 인터프리터와 이 프로젝트의 main.py를 가리킨다.
패키징된 배포본에서는 패키지 바이너리를 가리키도록 변경해야 한다.
"""

import sys
from pathlib import Path

APP_ID = "Tappy"
PLIST_LABEL = "com.tappy.app"


def _command() -> list[str]:
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(main_py)]


# ---- macOS ----
def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _mac_enable() -> None:
    args = "\n".join(f"        <string>{c}</string>" for c in _command())
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")


def _mac_disable() -> None:
    p = _plist_path()
    if p.exists():
        p.unlink()


def _mac_is_enabled() -> bool:
    return _plist_path().exists()


# ---- Windows ----
def _win_open_key():
    import winreg

    return winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    )


def _win_enable() -> None:
    import winreg

    value = " ".join(f'"{c}"' for c in _command())
    with _win_open_key() as key:
        winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, value)


def _win_disable() -> None:
    import winreg

    with _win_open_key() as key:
        try:
            winreg.DeleteValue(key, APP_ID)
        except FileNotFoundError:
            pass


def _win_is_enabled() -> bool:
    import winreg

    try:
        with _win_open_key() as key:
            winreg.QueryValueEx(key, APP_ID)
        return True
    except FileNotFoundError:
        return False


# ---- 공개 API ----
def enable() -> None:
    if sys.platform == "darwin":
        _mac_enable()
    elif sys.platform == "win32":
        _win_enable()


def disable() -> None:
    if sys.platform == "darwin":
        _mac_disable()
    elif sys.platform == "win32":
        _win_disable()


def is_enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_is_enabled()
    if sys.platform == "win32":
        return _win_is_enabled()
    return False
