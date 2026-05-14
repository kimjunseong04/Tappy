"""A character is a named sequence of animation frames."""

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
    """Load a character from a directory.

    The directory holds either a single animated file (e.g. ``source.gif``)
    or a numbered image sequence (``frame_00.png`` ...).
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
