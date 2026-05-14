"""Discovers bundled and user-uploaded characters, and imports new ones."""

import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .character import Character, load_character
from .gif_utils import save_frames_as_png
from .paths import bundled_characters_dir, user_characters_dir


class CharacterManager:
    def __init__(self):
        self._cache: dict[str, Character] = {}

    def _dirs(self) -> dict[str, Path]:
        """Map character id -> directory. User characters override bundled."""
        result: dict[str, Path] = {}
        for base in (bundled_characters_dir(), user_characters_dir()):
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    result[d.name] = d
        return result

    def available_ids(self) -> list[str]:
        return sorted(self._dirs().keys())

    def get(self, char_id: str) -> Character | None:
        if char_id in self._cache:
            return self._cache[char_id]
        dirs = self._dirs()
        if char_id not in dirs:
            return None
        char = load_character(dirs[char_id])
        if char is not None:
            self._cache[char_id] = char
        return char

    def load_with_fallback(self, char_id: str) -> Character:
        char = self.get(char_id)
        if char is not None:
            return char
        ensure_default_character()
        char = self.get("default")
        if char is None:
            raise RuntimeError("failed to load or create the default character")
        return char

    def import_gif(self, file_path: Path) -> str:
        """Add a character by splitting an image into a PNG frame sequence.

        The chosen GIF/WebP is decoded frame-by-frame into ``frame_NNNN.png``
        files in a new folder under the user characters directory; static
        images become a single-frame character. Returns the new id.
        """
        name = file_path.stem.strip() or "character"
        dest_dir = user_characters_dir() / name
        suffix = 1
        while dest_dir.exists():
            dest_dir = user_characters_dir() / f"{name}_{suffix}"
            suffix += 1
        dest_dir.mkdir(parents=True)
        try:
            save_frames_as_png(file_path, dest_dir)
        except Exception:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise
        self._cache.pop(dest_dir.name, None)
        return dest_dir.name

    def is_user_character(self, char_id: str) -> bool:
        """Whether this character was uploaded by the user (and so deletable).

        Bundled characters live under ``assets/`` and cannot be deleted.
        """
        directory = self._dirs().get(char_id)
        if directory is None:
            return False
        try:
            directory.resolve().relative_to(user_characters_dir().resolve())
            return True
        except ValueError:
            return False

    def delete_character(self, char_id: str) -> bool:
        """Delete a user-uploaded character. Returns False for bundled ones."""
        if not self.is_user_character(char_id):
            return False
        directory = self._dirs().get(char_id)
        if directory is None:
            return False
        shutil.rmtree(directory, ignore_errors=True)
        self._cache.pop(char_id, None)
        return True


def ensure_default_character() -> None:
    """Make sure a 'default' character exists, generating a placeholder if not.

    Normally the bundled ``assets/characters/default/`` ships with the app. If
    it is missing (e.g. a build that did not include the assets folder, where
    the resource dir is also read-only), the placeholder is generated into the
    writable user data directory instead.
    """
    bundled = bundled_characters_dir() / "default"
    if bundled.is_dir() and any(bundled.iterdir()):
        return

    target = bundled
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = user_characters_dir() / "default"
        target.mkdir(parents=True, exist_ok=True)
    if not any(target.iterdir()):
        _generate_placeholder_frames(target)


def _generate_placeholder_frames(out_dir: Path) -> None:
    """A simple bouncing blob, saved as a transparent PNG sequence."""
    size = 96
    total = 8
    for i in range(total):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        phase = i / total
        squash = int(10 * abs(0.5 - phase) * 2)  # 0..10
        cx = size // 2
        top = 18 + squash
        bottom = size - 10 - squash
        draw.ellipse([cx - 28, top, cx + 28, bottom], fill=(255, 138, 0, 255))
        eye_y = top + 14
        draw.ellipse([cx - 15, eye_y, cx - 6, eye_y + 9], fill=(255, 255, 255, 255))
        draw.ellipse([cx + 6, eye_y, cx + 15, eye_y + 9], fill=(255, 255, 255, 255))
        draw.ellipse([cx - 13, eye_y + 3, cx - 9, eye_y + 7], fill=(0, 0, 0, 255))
        draw.ellipse([cx + 9, eye_y + 3, cx + 13, eye_y + 7], fill=(0, 0, 0, 255))
        img.save(out_dir / f"frame_{i:02d}.png")
