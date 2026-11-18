"""File types the reader knows: which extensions are pictures, videos and books."""
from __future__ import annotations

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff", ".jxl", ".heic", ".heif")


# no browser but Safari shows these: transcoded to PNG before reading, cached for a while
JXL_EXT = (".jxl",)


HEIC_EXT = (".heic", ".heif")


TRANSCODE_EXT = JXL_EXT + HEIC_EXT


LOSSLESS_EXT = (".png", ".bmp", ".tif", ".tiff")     # → the RAW pill


BROWSER_UNSAFE = (".tif", ".tiff")                  # only Safari shows TIFF: served as PNG (still lossless)


VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v")


BOOK_EXT = (".cbz", ".zip", ".cb7", ".epub")


MEDIA_EXT = IMG_EXT + VIDEO_EXT


def is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO_EXT)
