"""앱 데이터와 번들 에셋을 위한 OS별 파일시스템 경로."""

import os
import sys
from functools import lru_cache
from pathlib import Path

APP_NAME = "tappy"


def user_data_dir() -> Path:
    """설정과 업로드된 캐릭터를 위한 사용자별 쓰기 가능 디렉터리."""
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
    """번들 리소스의 루트.

    소스 실행 시 리포지터리 루트. PyInstaller로 frozen된 경우(macOS ``.app`` 또는
    Windows ``.exe``) 번들된 ``assets/`` 폴더는 ``sys._MEIPASS`` 아래에 압축 해제되므로
    그 경로를 기준으로 반환한다.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return project_root() / "assets"


@lru_cache(maxsize=1)
def app_version() -> str:
    """번들된 ``VERSION`` 파일에서 앱 버전 문자열을 반환한다 (없으면 "").

    캐시됨 -- 번들된 파일은 실행 중 변경되지 않으며, 여러 UI 경로에서 호출된다.
    """
    try:
        return (project_root() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def is_frozen() -> bool:
    """PyInstaller 번들로 실행 중인지(소스 실행과 구분) 반환한다."""
    return getattr(sys, "frozen", False)


def installed_app_path() -> Path | None:
    """자동 업데이터가 교체해야 하는 디스크상의 아티팩트.

    소스 실행 시 ``None`` -- 교체할 번들이 없으므로 업데이트 기능은 비활성화된다.
    frozen 빌드에서는 ``sys.executable``에서 *설치된* 위치를 역추적한다
    (``project_root()``가 반환하는 임시 ``sys._MEIPASS`` 압축 해제 디렉터리가 아님):
      - macOS:   .../Tappy.app/Contents/MacOS/Tappy  → ``.app`` 번들
      - Windows: ...\\Tappy\\Tappy.exe               → ``Tappy\\`` 폴더
    """
    if not is_frozen():
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent
        return None
    return exe.parent


def bundled_characters_dir() -> Path:
    return assets_dir() / "characters"
