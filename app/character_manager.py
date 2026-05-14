"""번들 캐릭터와 사용자가 업로드한 캐릭터를 탐색하고, 새 캐릭터를 임포트한다."""

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
        """캐릭터 id → 디렉터리 매핑을 반환한다. 사용자 캐릭터가 번들 캐릭터를 덮어쓴다."""
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
        """이미지를 PNG 프레임 시퀀스로 분할해 캐릭터를 추가한다.

        선택한 GIF/WebP를 프레임별로 디코딩해 사용자 캐릭터 디렉터리 내 새 폴더에
        ``frame_NNNN.png`` 파일로 저장한다. 정적 이미지는 단일 프레임 캐릭터가 된다.
        새 id를 반환한다.
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
        """사용자가 업로드한 캐릭터인지 (따라서 삭제 가능한지) 반환한다.

        번들 캐릭터는 ``assets/`` 아래에 있으며 삭제할 수 없다.
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
        """사용자가 업로드한 캐릭터를 삭제한다. 번들 캐릭터에는 False를 반환한다."""
        if not self.is_user_character(char_id):
            return False
        directory = self._dirs().get(char_id)
        if directory is None:
            return False
        shutil.rmtree(directory, ignore_errors=True)
        self._cache.pop(char_id, None)
        return True


def ensure_default_character() -> None:
    """'default' 캐릭터가 없으면 플레이스홀더를 생성해 항상 존재하게 한다.

    일반적으로 번들 ``assets/characters/default/``가 앱에 포함된다.
    없는 경우(에셋 폴더가 누락된 빌드, 또는 리소스 디렉터리가 읽기 전용인 경우)
    플레이스홀더를 쓰기 가능한 사용자 데이터 디렉터리에 생성한다.
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
    """투명 PNG 시퀀스로 저장되는 단순한 통통 튀기는 블롭."""
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
