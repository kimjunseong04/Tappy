"""사용자 설정을 JSON으로 영속 저장한다. 저장 위치는 OS별 사용자 데이터 디렉터리."""

import json
from dataclasses import asdict, dataclass
from typing import Optional

from .paths import config_path


@dataclass
class Config:
    character_id: str = "default"
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    min_fps: float = 5.0
    max_fps: float = 30.0
    autostart: bool = False
    seen_welcome: bool = False
    char_scale: float = 1.0
    # 마지막으로 성공한 업데이트 확인의 에포크 초 -- 무음 시작 확인을 제한한다.
    # 하위 호환: `load()`가 미지의 키를 필터링하고, 이전 설정 파일은 이 기본값을 사용한다.
    last_update_check: float = 0.0

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                known = set(cls.__dataclass_fields__)
                return cls(**{k: v for k, v in data.items() if k in known})
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        cfg = cls()
        cfg.save()
        return cfg

    def save(self) -> None:
        config_path().write_text(
            json.dumps(asdict(self), indent=2), encoding="utf-8"
        )
