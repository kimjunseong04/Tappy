"""Global keystroke listener.

The pynput listener runs on its own daemon thread. Its callback only appends
timestamps to a lock-protected deque -- it never touches Qt objects. The Qt
main thread polls ``recent_rate()`` instead.
"""

import ctypes
import subprocess
import sys
import threading
import time
from collections import deque

from pynput import keyboard


def open_accessibility_settings() -> None:
    """Open the macOS Accessibility privacy pane (no-op on other platforms)."""
    if sys.platform == "darwin":
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security"
            "?Privacy_Accessibility",
        ])


def macos_accessibility_trusted() -> bool:
    """Whether this process may monitor input events on macOS.

    pynput fails *silently* without Accessibility permission -- the listener
    runs but never receives a key -- so we check up front via AXIsProcessTrusted.
    Always True on non-macOS platforms (or if the check itself fails).
    """
    if sys.platform != "darwin":
        return True
    try:
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/"
            "ApplicationServices"
        )
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True


class KeyboardMonitor:
    # A 1s window keeps `recent_rate()` responsive: a longer window divides the
    # keystroke count by more seconds, so a burst of fast typing only reads as
    # its true rate after the whole window fills -- that lag is what made the
    # character feel slow to react.
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
        except Exception:
            self.failed = True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        now = time.monotonic()
        with self._lock:
            self._timestamps.append(now)

    def recent_rate(self) -> float:
        """Keystrokes per second over the trailing window."""
        cutoff = time.monotonic() - self._window
        with self._lock:
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            count = len(self._timestamps)
        return count / self._window
