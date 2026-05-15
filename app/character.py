"""캐릭터는 이름과 애니메이션 프레임 시퀀스로 구성된다."""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QPixmap

from .gif_utils import extract_frames

_IMAGE_EXTS = {".png", ".gif", ".webp", ".jpg", ".jpeg", ".bmp"}


@dataclass
class Character:
    id: str
    name: str
    frames: list[QPixmap]

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def load_character(char_dir: Path) -> Character | None:
    """디렉터리에서 캐릭터를 로드한다.

    디렉터리에는 단일 애니메이션 파일(예: ``source.gif``) 또는
    번호가 매겨진 이미지 시퀀스(``frame_00.png`` ...)가 들어있다.
    """
    if not char_dir.is_dir():
        return None

    files = sorted(
        p for p in char_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS
    )
    if not files:
        return None

    frames: list[QPixmap] = []
    if len(files) == 1:
        frames = extract_frames(files[0])
    else:
        for f in files:
            frames.extend(extract_frames(f))

    if not frames:
        return None

    return Character(id=char_dir.name, name=char_dir.name, frames=frames)
