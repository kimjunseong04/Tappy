"""Persisted user settings, stored as JSON in the user data directory."""

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
