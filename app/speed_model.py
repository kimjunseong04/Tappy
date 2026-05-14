"""Maps a keystroke rate to an animation FPS, smoothed to avoid jitter."""


class SpeedModel:
    # Keystroke rate (keys/sec) that corresponds to full-speed playback.
    MAX_KPS = 8.0

    def __init__(self, min_fps: float, max_fps: float, smoothing: float = 0.25):
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.smoothing = smoothing
        self._fps = min_fps

    def update(self, rate: float) -> float:
        """Feed the latest keystroke rate, return the smoothed target FPS.

        When typing stops the rate decays to 0, so the FPS glides down to
        ``min_fps`` -- the character keeps dancing slowly rather than freezing.
        """
        norm = min(rate, self.MAX_KPS) / self.MAX_KPS
        target = self.min_fps + norm * (self.max_fps - self.min_fps)
        self._fps += (target - self._fps) * self.smoothing
        return self._fps

    @property
    def fps(self) -> float:
        return self._fps
