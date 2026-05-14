"""Extract animation frames from GIF / image files into QPixmaps via Pillow."""

from pathlib import Path

from PIL import Image, ImageSequence
from PyQt6.QtGui import QImage, QPixmap


def _pil_to_qpixmap(im: Image.Image) -> QPixmap:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, QImage.Format.Format_RGBA8888)
    # .copy() detaches into Qt-owned memory so `data` can be freed safely.
    return QPixmap.fromImage(qimg.copy())


def extract_frames(path: Path) -> list[QPixmap]:
    """All frames of an animated GIF, or the single frame of a static image."""
    frames: list[QPixmap] = []
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            frames.append(_pil_to_qpixmap(frame))
    return frames


def save_frames_as_png(src: Path, dest_dir: Path) -> int:
    """Split an animated image into ``frame_NNNN.png`` files in ``dest_dir``.

    Works for animated GIF/WebP (one PNG per frame) and static images (a
    single frame). Frames are composited and saved as RGBA PNGs, so
    transparency and GIF frame-disposal are resolved once at import time
    instead of being re-decoded on every load. Returns the frame count.
    """
    count = 0
    with Image.open(src) as im:
        for index, frame in enumerate(ImageSequence.Iterator(im)):
            frame.convert("RGBA").save(dest_dir / f"frame_{index:04d}.png")
            count = index + 1
    if count == 0:
        raise ValueError(f"no frames found in {src}")
    return count
