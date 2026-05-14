"""인앱 자동 업데이트: GitHub Releases 확인, 다운로드, 자기 교체.

배포 모델 (``.github/workflows/release.yml`` 참고): ``product`` 브랜치 푸시 시
PyInstaller로 macOS·Windows를 빌드하고 ``v{VERSION}`` 태그로 GitHub Release를 발행한다.
에셋은 ``Tappy-macOS.zip`` (압축된 ``Tappy.app``)과 ``Tappy-Windows.zip``
(압축된 ``Tappy/`` 폴더). 이 모듈은 해당 에셋을 그대로 소비한다.

스레딩 모델은 ``keyboard_monitor``와 동일: 모든 네트워크/디스크 작업은
데몬 스레드에서 실행하고 결과를 ``queue.Queue``에 넣는다; Qt 메인 스레드는
``UpdateChecker.poll()``로 큐를 비운다. Qt 객체는 메인 스레드 외에서 절대 건드리지 않는다.

의도적으로 표준 라이브러리(및 ``QObject``)만 사용한다 --
``requirements.txt``에 새 항목을 추가하지 않는다.

범위 외: macOS 코드 서명·공증. 빌드에 서명이 없으므로 교체 스크립트가 quarantine 플래그를
제거해 Gatekeeper가 새로 다운로드한 번들을 허용한다; 서명+공증 도입 후에도 이 단계는 무해하다.
"""

import enum
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject

from .paths import app_version, installed_app_path

GITHUB_API = "https://api.github.com/repos/kimjunseong04/Tappy/releases/latest"
# 이 플랫폼 빌드에 해당하는 릴리스 에셋명.
_ASSET_NAME = "Tappy-macOS.zip" if sys.platform == "darwin" else "Tappy-Windows.zip"
_USER_AGENT = "Tappy-Updater"  # GitHub API는 UA 헤더 없는 요청을 거부한다
_NET_TIMEOUT = 15  # 요청당 초
_CHUNK = 64 * 1024
# 다운로드 상한선 — 잘못된/리다이렉트된/탈취된 에셋 URL이 사용자 디스크를 조용히 채우지 못하게 한다.
_MAX_DOWNLOAD = 500 * 1024 * 1024


# ---- 버전 비교 (외부 semver 의존성 없음) ----
def parse_version(text: str) -> tuple[int, ...] | None:
    """``'v0.3.0'`` / ``'0.3.0'`` → ``(0, 3, 0)``; 파싱 불가 시 ``None``.

    점으로 구분된 각 컴포넌트의 선행 숫자만 취하므로
    ``1.2.0-beta`` 같은 접미사도 ``(1, 2, 0)``으로 읽힌다.
    빈 컴포넌트(``1..2``)가 있으면 전체 문자열을 파싱 불가로 처리한다.
    """
    text = text.strip().lstrip("vV")
    if not text:
        return None
    parts: list[int] = []
    for chunk in text.split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) if parts else None


def is_newer(remote: str, local: str) -> bool:
    """``remote``가 ``local``보다 엄격히 최신 버전인지 반환한다.

    어느 쪽이든 파싱할 수 없으면 ``False`` -- 판단할 수 없는 업데이트는 절대 제안하지 않는다
    (로컬에서 ``VERSION``을 올린 dev 빌드가 "다운그레이드"를 제안받지 않는다).
    """
    remote_v, local_v = parse_version(remote), parse_version(local)
    if remote_v is None or local_v is None:
        return False
    length = max(len(remote_v), len(local_v))
    remote_v += (0,) * (length - len(remote_v))
    local_v += (0,) * (length - len(local_v))
    return remote_v > local_v


# ---- 데이터 모델 ----
@dataclass(frozen=True)
class ReleaseInfo:
    version: str  # 정규화된 버전, 선행 'v' 없음
    tag: str  # 원본 태그, 예: 'v0.3.0'
    notes: str  # 릴리스 본문 (마크다운)
    asset_url: str  # 이 플랫폼 zip의 browser_download_url
    asset_name: str
    asset_size: int  # 바이트 (GitHub가 보고하지 않으면 0)


class UpdateState(enum.Enum):
    IDLE = "idle"
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    READY = "ready"
    ERROR = "error"


class UpdateError(Exception):
    """사용자에게 그대로 표시되는 업데이트 실패 메시지 (한국어)."""


# ---- 스레드 측 순수 함수 (Qt 미접촉) ----
def fetch_latest_release() -> ReleaseInfo:
    """GitHub에서 최신 릴리스와 이 플랫폼의 에셋을 조회한다."""
    request = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_NET_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0":
            raise UpdateError(
                "GitHub 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요."
            ) from error
        if error.code == 404:
            raise UpdateError("아직 게시된 릴리스가 없어요.") from error
        raise UpdateError(
            f"업데이트 정보를 가져오지 못했어요 (HTTP {error.code})."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise UpdateError("네트워크에 연결할 수 없어요.") from error
    except (json.JSONDecodeError, ValueError) as error:
        raise UpdateError("업데이트 정보를 해석하지 못했어요.") from error

    tag = payload.get("tag_name", "")
    asset = next(
        (a for a in payload.get("assets", []) if a.get("name") == _ASSET_NAME),
        None,
    )
    if asset is None:
        raise UpdateError("이 플랫폼용 업데이트 파일을 찾을 수 없어요.")
    return ReleaseInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        notes=(payload.get("body") or "").strip(),
        asset_url=asset["browser_download_url"],
        asset_name=asset["name"],
        asset_size=int(asset.get("size", 0)),
    )


def download_asset(release: ReleaseInfo, dest_dir: Path, progress_cb) -> Path:
    """릴리스 zip을 ``dest_dir``로 스트리밍한다; ``progress_cb(done, total)``은
    청크마다 호출된다 (큐에 숫자만 넣어야 하며, Qt를 건드려서는 안 된다)."""
    dest = dest_dir / release.asset_name
    request = urllib.request.Request(
        release.asset_url, headers={"User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=_NET_TIMEOUT) as response:
            total = release.asset_size or int(
                response.headers.get("Content-Length", 0)
            )
            done = 0
            with open(dest, "wb") as handle:
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if done > _MAX_DOWNLOAD:
                        raise UpdateError("업데이트 파일이 비정상적으로 커요.")
                    progress_cb(done, total)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise UpdateError("다운로드에 실패했어요.") from error
    if release.asset_size and dest.stat().st_size != release.asset_size:
        raise UpdateError("다운로드가 손상됐어요. 다시 시도해 주세요.")
    return dest


def extract_asset(zip_path: Path, dest_dir: Path) -> Path:
    """릴리스 zip을 추출하고 새 앱 아티팩트 경로를 반환한다
    (macOS: ``Tappy.app``, Windows: ``Tappy/`` 폴더)."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            if archive.testzip() is not None:
                raise UpdateError("압축 파일이 손상됐어요.")
            # 추출 전 경로 탐색("Zip Slip") 항목을 거부한다.
            dest_root = dest_dir.resolve()
            for name in archive.namelist():
                target = (dest_dir / name).resolve()
                if target != dest_root and dest_root not in target.parents:
                    raise UpdateError("업데이트 파일에 비정상적인 경로가 있어요.")
            archive.extractall(dest_dir)
    except zipfile.BadZipFile as error:
        raise UpdateError("압축 파일을 열 수 없어요.") from error
    except OSError as error:
        raise UpdateError(f"압축을 푸는 중 오류가 났어요: {error}") from error

    if sys.platform == "darwin":
        app = dest_dir / "Tappy.app"
        if not app.is_dir():
            raise UpdateError("업데이트 파일 구조가 올바르지 않아요.")
        # `ditto`는 실행 비트를 보존하지만, 실행 불가능한 런처는 조용히 재실행에 실패할 수 있다 -- 보험용.
        launcher = app / "Contents" / "MacOS" / "Tappy"
        if launcher.exists():
            launcher.chmod(
                launcher.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
        return app
    folder = dest_dir / "Tappy"
    if not folder.is_dir():
        raise UpdateError("업데이트 파일 구조가 올바르지 않아요.")
    return folder


def _make_staging_dir() -> Path:
    """다운로드·추출용 임시 디렉터리를 생성한다.

    최종 교체가 빠른 원자적 동일 볼륨 rename이 되도록 설치된 앱 옆에 배치한다;
    쓰기가 불가능하면 시스템 임시 디렉터리로 대체한다 (교체 스크립트의 rename 기반 롤백이
    중간에 실패한 크로스 볼륨 이동을 처리한다).
    """
    installed = installed_app_path()
    if installed is not None:
        try:
            return Path(
                tempfile.mkdtemp(prefix=".tappy-update-", dir=installed.parent)
            )
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix="tappy-update-"))


# ---- 자기 교체 헬퍼 스크립트 ----
# 실행 중인 프로세스는 자신의 번들/폴더를 안정적으로 덮어쓸 수 없으므로
# 교체를 분리된 헬퍼에 위임한다. 경로는 argv($1..$4 / %1..%4)로 전달하며
# 스크립트 본문에 보간하지 않는다 -- 경로의 공백이나 셸 메타문자가 스크립트를 망가뜨리거나
# 인젝션을 일으킬 수 없다.
_SWAP_SH = r"""#!/bin/sh
# Tappy 자동 업데이트 -- 앱 종료 후 분리 실행되는 생성 스크립트.
PID="$1"
OLD="$2"
NEW="$3"
STAGING="$4"
# 종료 시 스테이징 디렉터리와 이 스크립트를 정리한다
trap 'rm -rf "$STAGING"; rm -f "$0"' EXIT

# 실행 중인 Tappy가 종료될 때까지 대기 (최대 ~10초)
i=0
while kill -0 "$PID" 2>/dev/null; do
    if [ "$i" -ge 100 ]; then
        exit 1  # 앱이 종료되지 않음 -- 실행 중 교체하지 않고 중단
    fi
    sleep 0.1
    i=$((i + 1))
done

# 동일 볼륨 원자적 rename으로 기존 번들 백업 (롤백 지점)
rm -rf "$OLD.bak"
if ! mv "$OLD" "$OLD.bak"; then
    open "$OLD" 2>/dev/null
    exit 1
fi
# 새 번들을 제자리로 이동; 실패 시 부분 파일을 제거하고 롤백
if ! mv "$NEW" "$OLD"; then
    rm -rf "$OLD"
    mv "$OLD.bak" "$OLD"
    open "$OLD" 2>/dev/null
    exit 1
fi
# 미서명 빌드가 Gatekeeper에 막히지 않도록 quarantine 플래그 제거
xattr -dr com.apple.quarantine "$OLD" 2>/dev/null
rm -rf "$OLD.bak"
open "$OLD"
"""

_SWAP_BAT = r"""@echo off
set "PID=%~1"
set "OLD=%~2"
set "NEW=%~3"
set "STAGING=%~4"

set /a i=0
:wait
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if errorlevel 1 goto exited
set /a i+=1
if %i% geq 100 goto cleanup
timeout /t 1 /nobreak >nul
goto wait

:exited
rem 추가 대기 -- Windows는 .exe/.dll 잠금을 느리게 해제한다
timeout /t 1 /nobreak >nul
if exist "%OLD%.old" rmdir /s /q "%OLD%.old"
move "%OLD%" "%OLD%.old" >nul
if errorlevel 1 (
    start "" "%OLD%\Tappy.exe"
    goto cleanup
)
move "%NEW%" "%OLD%" >nul
if errorlevel 1 (
    rmdir /s /q "%OLD%" 2>nul
    move "%OLD%.old" "%OLD%" >nul
    start "" "%OLD%\Tappy.exe"
    goto cleanup
)
rmdir /s /q "%OLD%.old"
start "" "%OLD%\Tappy.exe"

:cleanup
rmdir /s /q "%STAGING%" 2>nul
(goto) 2>nul & del "%~f0"
"""


def _write_swap_script() -> Path:
    """(정적) 플랫폼 교체 스크립트를 별도 임시 파일에 작성한다 --
    스크립트가 스테이징 디렉터리를 삭제할 때 자기 자신을 지우지 않도록
    스테이징 디렉터리 *외부*에 위치시킨다. 경로는 argv로 전달, 스크립트에 삽입하지 않는다."""
    if sys.platform == "darwin":
        fd, path = tempfile.mkstemp(suffix="-tappy-swap.sh")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_SWAP_SH)
        os.chmod(path, 0o755)
        return Path(path)
    fd, path = tempfile.mkstemp(suffix="-tappy-swap.bat")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(_SWAP_BAT)
    return Path(path)


# ---- Qt 측 코디네이터 ----
class UpdateChecker(QObject):
    """업데이트 생명 주기를 관리한다: 확인 → 다운로드/스테이징 → 적용.

    무거운 작업은 데몬 스레드에서 실행하고, 결과는 ``poll()``을 통해 메인 스레드에 전달된다
    (컨트롤러 소유 ``QTimer``가 구동). 컨트롤러가 ``on_state_change``와
    ``on_progress``를 연결한다 -- 둘 다 ``poll()``에서만, 즉 메인 스레드에서만 호출된다.

    재진입 방지: 모든 공개 ``*_async`` 메서드와 ``apply_and_relaunch``는
    작업자가 이미 실행 중이면 조기 반환하므로, 작업자는 동시에 하나만 존재하며
    ``_staged_path`` / ``_staging_dir``은 생성 작업자가 완료·터미널 상태를 방출한 뒤에만 읽힌다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._release: ReleaseInfo | None = None
        self._staged_path: Path | None = None  # 추출된 Tappy.app / Tappy/
        self._staging_dir: Path | None = None
        # 컨트롤러가 연결하기 전까지는 no-op.
        self.on_state_change = lambda state, info, message: None
        self.on_progress = lambda done, total: None

    # ---- 작업자 배관 ----
    def _busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _emit_state(self, state: UpdateState, info: ReleaseInfo | None = None,
                    message: str = "") -> None:
        self._queue.put(("state", state, info, message))

    def _emit_progress(self, done: int, total: int) -> None:
        self._queue.put(("progress", done, total))

    def _run(self, target) -> None:
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    # ---- 공개 API (메인 스레드에서 호출) ----
    def check_async(self) -> None:
        if self._busy():
            return
        self._emit_state(UpdateState.CHECKING)
        self._run(self._do_check)

    def download_and_stage_async(self, release: ReleaseInfo) -> None:
        if self._busy():
            return
        # 작업자가 시작하기 전 메인 스레드에서 설정한다 (스레드 시작은 happens-before 장벽),
        # 작업자가 일관된 값을 읽을 수 있도록 보장한다.
        self._release = release
        self._emit_state(UpdateState.DOWNLOADING, release)
        self._run(self._do_download)

    def apply_and_relaunch(self) -> bool:
        """분리된 교체 헬퍼를 실행한다. 성공 시 ``True``를 반환하며
        호출자는 앱을 종료해 헬퍼가 이어받을 수 있게 해야 한다."""
        if self._busy():
            return False
        if self._staged_path is None or self._staging_dir is None:
            return False
        installed = installed_app_path()
        if installed is None:
            return False
        try:
            script = _write_swap_script()
        except OSError:
            return False
        args = [
            str(os.getpid()),
            str(installed),
            str(self._staged_path),
            str(self._staging_dir),
        ]
        if sys.platform == "darwin":
            subprocess.Popen(
                ["/bin/sh", str(script), *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            subprocess.Popen(
                ["cmd", "/c", str(script), *args],
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NO_WINDOW
                ),
            )
        return True

    # ---- 작업자 본체 (백그라운드 스레드; Qt 미접촉) ----
    def _do_check(self) -> None:
        try:
            release = fetch_latest_release()
        except UpdateError as error:
            self._emit_state(UpdateState.ERROR, None, str(error))
            return
        self._release = release
        if is_newer(release.version, app_version()):
            self._emit_state(UpdateState.AVAILABLE, release)
        else:
            self._emit_state(UpdateState.UP_TO_DATE, release)

    def _do_download(self) -> None:
        release = self._release
        if release is None:
            self._emit_state(
                UpdateState.ERROR, None, "먼저 업데이트를 확인해 주세요."
            )
            return
        staging: Path | None = None
        try:
            staging = _make_staging_dir()
            zip_path = download_asset(release, staging, self._emit_progress)
            extracted = extract_asset(zip_path, staging / "new")
        except UpdateError as error:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            self._emit_state(UpdateState.ERROR, release, str(error))
            return
        except OSError as error:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            self._emit_state(
                UpdateState.ERROR, release, f"디스크 오류로 실패했어요: {error}"
            )
            return
        self._staging_dir = staging
        self._staged_path = extracted
        self._emit_state(UpdateState.READY, release)

    # ---- 메인 스레드 폴 ----
    def poll(self) -> None:
        """작업자 큐를 비우며 메인 스레드에서 콜백을 실행한다."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item[0] == "state":
                _, state, info, message = item
                self.on_state_change(state, info, message)
            elif item[0] == "progress":
                _, done, total = item
                self.on_progress(done, total)
