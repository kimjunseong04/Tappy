"""Pillow를 통해 GIF/이미지 파일에서 QPixmap 애니메이션 프레임을 추출한다."""

from pathlib import Path

from PIL import Image, ImageSequence
from PyQt6.QtGui import QImage, QPixmap


def _pil_to_qpixmap(im: Image.Image) -> QPixmap:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, QImage.Format.Format_RGBA8888)
    # .copy()로 Qt 소유 메모리로 분리해 `data`를 안전하게 해제할 수 있게 한다.
    return QPixmap.fromImage(qimg.copy())


def extract_frames(path: Path) -> list[QPixmap]:
    """애니메이션 GIF의 모든 프레임, 또는 정적 이미지의 단일 프레임을 반환한다."""
    frames: list[QPixmap] = []
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            frames.append(_pil_to_qpixmap(frame))
    return frames


def save_frames_as_png(src: Path, dest_dir: Path) -> int:
    """애니메이션 이미지를 ``frame_NNNN.png`` 파일로 분할해 ``dest_dir``에 저장한다.

    애니메이션 GIF/WebP(프레임당 PNG)와 정적 이미지(단일 프레임) 모두 지원한다.
    프레임을 RGBA PNG로 합성·저장해 투명도와 GIF 프레임 처리를 임포트 시 한 번만
    해결한다 -- 매 로드마다 다시 디코딩하지 않아도 된다. 프레임 수를 반환한다.
    """
    count = 0
    with Image.open(src) as im:
        for index, frame in enumerate(ImageSequence.Iterator(im)):
            frame.convert("RGBA").save(dest_dir / f"frame_{index:04d}.png")
            count = index + 1
    if count == 0:
        raise ValueError(f"no frames found in {src}")
    return count
