"""Maps a keystroke rate to an animation FPS, smoothed to avoid jitter."""


class SpeedModel:
    # Keystroke rate (keys/sec) that corresponds to full-speed playback.
    MAX_KPS = 8.0

    def __init__(
        self,
        min_fps: float,
        max_fps: float,
        attack: float = 0.6,
        release: float = 0.18,
    ):
        self.min_fps = min_fps
        self.max_fps = max_fps
        # Asymmetric smoothing. `attack` is applied when the target FPS is
        # above the current one (typing sped up) -- kept high so the character
        # reacts almost immediately. `release` is applied on the way down
        # (typing slowed/stopped) -- kept low so it glides gently to min_fps
        # and keeps dancing instead of snapping to a stop.
        self.attack = attack
        self.release = release
        self._fps = min_fps

    def update(self, rate: float) -> float:
        """Feed the latest keystroke rate, return the smoothed target FPS.

        When typing stops the rate decays to 0, so the FPS glides down to
        ``min_fps`` -- the character keeps dancing slowly rather than freezing.
        """
        norm = min(rate, self.MAX_KPS) / self.MAX_KPS
        target = self.min_fps + norm * (self.max_fps - self.min_fps)
        smoothing = self.attack if target > self._fps else self.release
        self._fps += (target - self._fps) * smoothing
        return self._fps

    @property
    def fps(self) -> float:
        return self._fps
