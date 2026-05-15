"""키 입력 속도를 애니메이션 FPS로 변환하며, 떨림 방지를 위해 스무딩을 적용한다."""


class SpeedModel:
    # 초당 키 입력 횟수(keys/sec) 중 최고 속도 재생에 해당하는 값.
    MAX_KPS = 12.0

    def __init__(
        self,
        min_fps: float,
        max_fps: float,
        attack: float = 0.35,
        release: float = 0.18,
    ):
        self.min_fps = min_fps
        self.max_fps = max_fps
        # 비대칭 스무딩. `attack`은 목표 FPS가 현재보다 높을 때 (타이핑 속도 증가)
        # 적용 -- 높게 유지해 캐릭터가 즉각 반응하게 한다. `release`는 속도가 낮아질 때
        # (타이핑 감소/중단) 적용 -- 낮게 유지해 min_fps까지 부드럽게 글라이드하므로
        # 갑자기 멈추지 않고 천천히 계속 춤춘다.
        self.attack = attack
        self.release = release
        self._fps = min_fps

    def update(self, rate: float) -> float:
        """최신 키 입력 속도를 입력받아 스무딩된 목표 FPS를 반환한다.

        타이핑이 멈추면 속도가 0으로 감소하므로 FPS는 ``min_fps``까지 부드럽게
        내려간다 -- 캐릭터가 완전히 멈추지 않고 천천히 계속 춤춘다.
        """
        norm = min(rate, self.MAX_KPS) / self.MAX_KPS
        target = self.min_fps + norm * (self.max_fps - self.min_fps)
        smoothing = self.attack if target > self._fps else self.release
        self._fps += (target - self._fps) * smoothing
        return self._fps

    @property
    def fps(self) -> float:
        return self._fps
