"""전역 키 입력 리스너.

pynput 리스너는 별도의 데몬 스레드에서 실행된다. 콜백은 락으로 보호된 deque에
타임스탬프를 추가하는 것만 수행하며 Qt 객체를 절대 건드리지 않는다. Qt 메인 스레드는
대신 ``recent_rate()``를 폴링한다.

macOS 권한 참고
---------------
pynput의 키보드 리스너는 *수신 전용* CGEventTap을 설치한다. macOS 10.15부터
이 탭은 **입력 모니터링** 개인정보 권한(``kTCCServiceListenEvent``)으로 제어되며,
이는 **손쉬운 사용**(``kTCCServiceAccessibility``)과 *별개의* 권한이다.
손쉬운 사용만 허용하면 탭은 조용히 빈 상태로 유지된다: 리스너 스레드는 동작하지만
어떤 키도 전달되지 않는다. 따라서 입력 모니터링 권한을 확인·요청·안내해야 한다.
Windows에는 이런 분리가 없어서 "그냥 동작"한다.
"""

import ctypes
import subprocess
import sys
import threading
import time
from collections import deque

from pynput import keyboard

# IOKit IOHIDRequestType — 이벤트 *청취* 여부만 확인한다.
_kIOHIDRequestTypeListenEvent = 1
# IOHIDCheckAccess가 반환하는 IOHIDAccessType.
_kIOHIDAccessTypeGranted = 0
_kIOHIDAccessTypeDenied = 1
_kIOHIDAccessTypeUnknown = 2  # 아직 미결정 — 요청 시 시스템 프롬프트 표시


_iokit_lib = None
_iokit_loaded = False


def _iokit():
    """IOKit 프레임워크를 반환한다. 로드할 수 없으면 None (비macOS 또는 오류).

    한 번만 로드하고 메모이제이션 — 권한 감시 타이머가 1.5초마다 호출하므로
    매번 프레임워크를 다시 열 필요가 없다.
    """
    global _iokit_lib, _iokit_loaded
    if _iokit_loaded:
        return _iokit_lib
    _iokit_loaded = True
    if sys.platform != "darwin":
        return None
    try:
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/IOKit.framework/IOKit"
        )
        lib.IOHIDCheckAccess.restype = ctypes.c_int
        lib.IOHIDCheckAccess.argtypes = [ctypes.c_uint]
        lib.IOHIDRequestAccess.restype = ctypes.c_bool
        lib.IOHIDRequestAccess.argtypes = [ctypes.c_uint]
        _iokit_lib = lib
    except Exception:
        _iokit_lib = None
    return _iokit_lib


def keystroke_permission_granted() -> bool:
    """이 프로세스가 키 입력을 모니터링할 수 있는지 여부를 반환한다.

    macOS에서는 pynput의 이벤트 탭이 실제로 필요로 하는 **입력 모니터링** 권한을
    ``IOHIDCheckAccess``로 확인한다. 다른 플랫폼에서는 항상 True (확인 자체가 실패해도
    앱이 권한 요청으로 방해받지 않고 계속 실행된다).
    """
    lib = _iokit()
    if lib is None:
        return True
    try:
        return lib.IOHIDCheckAccess(_kIOHIDRequestTypeListenEvent) == (
            _kIOHIDAccessTypeGranted
        )
    except Exception:
        return True


def keystroke_permission_state() -> str:
    """입력 모니터링 상태를 세 값으로 반환: ``granted`` / ``denied`` /
    ``undetermined``. 비macOS 또는 확인 실패 시 항상 ``granted``.

    "허용" 버튼 동작에 중요: *미결정* 상태는 기본 시스템 프롬프트로 요청할 수 있지만,
    *거부된* 상태는 사용자가 시스템 설정에서만 변경할 수 있다.
    """
    lib = _iokit()
    if lib is None:
        return "granted"
    try:
        access = lib.IOHIDCheckAccess(_kIOHIDRequestTypeListenEvent)
    except Exception:
        return "granted"
    if access == _kIOHIDAccessTypeGranted:
        return "granted"
    if access == _kIOHIDAccessTypeDenied:
        return "denied"
    if access == _kIOHIDAccessTypeUnknown:
        return "undetermined"
    return "undetermined"  # 예상치 못한 값: 여전히 요청 가능한 것으로 간주


def request_keystroke_permission() -> bool:
    """macOS에 입력 모니터링 접근 권한을 요청하고, 허용 여부를 반환한다.

    권한이 *미결정*이면 기본 시스템 프롬프트를 표시하고 앱을 입력 모니터링 목록에 등록한다.
    이미 *거부된* 경우 macOS는 재프롬프트를 표시하지 않으므로, 호출자는
    :func:`open_keystroke_permission_settings`로 대체해야 한다. 비macOS에서는 무작동
    (True 반환).

    참고: ``IOHIDRequestAccess``는 모달 프롬프트가 닫힐 때까지 블로킹하므로
    미결정 경로에서 Qt UI가 잠시 멈춘다. 이는 일회성의 예상된 현상이므로
    스레드에서 실행하지 않고 인라인으로 호출한다.
    """
    lib = _iokit()
    if lib is None:
        return True
    try:
        return bool(lib.IOHIDRequestAccess(_kIOHIDRequestTypeListenEvent))
    except Exception:
        return keystroke_permission_granted()


def open_keystroke_permission_settings() -> None:
    """macOS 입력 모니터링 개인정보 패널을 연다 (다른 플랫폼에서는 무작동)."""
    if sys.platform == "darwin":
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security"
            "?Privacy_ListenEvent",
        ])


class KeyboardMonitor:
    # 1초 윈도우로 `recent_rate()`가 즉각 반응하게 한다: 윈도우가 길수록 더 많은 초로
    # 나누므로, 빠른 타이핑 급증도 윈도우가 채워진 후에야 실제 속도로 읽힌다 --
    # 이 지연이 캐릭터가 느리게 반응하는 원인이었다.
    def __init__(self, window_seconds: float = 1.0):
        self._window = window_seconds
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self._listener: keyboard.Listener | None = None
        self.failed = False

    def start(self) -> None:
        try:
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()
            self.failed = False
        except Exception:
            self._listener = None
            self.failed = True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def restart(self) -> None:
        """리스너를 해제하고 재생성한다.

        pynput의 macOS 이벤트 탭은 리스너 시작 시 한 번만 생성된다 — 앱 실행 후에
        입력 모니터링 권한이 허용되면 기존 탭은 빈 상태로 남는다. 리스너를 재생성하면
        앱 재시작 없이 새로 허용된 권한을 반영한다.

        새 리스너를 시작하기 전에 이전 리스너 스레드를 *join*한다:
        두 리스너가 동시에 시작·종료되면 pynput의 macOS 이벤트 탭 해제가 불안정해지고,
        join을 통해 deque 초기화 후 이전 키 입력이 끼어드는 것도 방지한다.
        """
        old = self._listener
        self._listener = None
        if old is not None:
            old.stop()
            old.join(timeout=2.0)
        with self._lock:
            self._timestamps.clear()
        self.start()

    def _on_press(self, key) -> None:
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)

    def recent_rate(self) -> float:
        """최근 윈도우 내 초당 키 입력 횟수를 반환한다."""
        cutoff = time.monotonic() - self._window
        with self._lock:
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            count = len(self._timestamps)
        return count / self._window
