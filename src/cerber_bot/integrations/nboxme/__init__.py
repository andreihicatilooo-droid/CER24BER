"""nboxme — асинхронная Python-библиотека для работы с nbox.me."""

from __future__ import annotations

from .album     import NboxAlbum
from .client    import NboxClient
from .constants import IMAGE_EXTENSIONS, MAX_FILES_PER_BATCH, BASE_URL
from .exceptions import (
    NboxAlbumError,
    NboxClientError,
    NboxDeleteError,
    NboxEmptyAlbumError,
    NboxError,
    NboxParseError,
    NboxUploadError,
)
from .models import NboxFile, NboxPage, PhotoInput, PhotoLike, to_photo_input

__version__ = "0.1.0"
__author__  = "nboxme contributors"

__all__ = [
    "NboxClient",
    "NboxAlbum",
    "NboxFile",
    "NboxPage",
    "PhotoInput",
    "PhotoLike",
    "to_photo_input",
    "NboxError",
    "NboxClientError",
    "NboxUploadError",
    "NboxDeleteError",
    "NboxParseError",
    "NboxAlbumError",
    "NboxEmptyAlbumError",
    "BASE_URL",
    "IMAGE_EXTENSIONS",
    "MAX_FILES_PER_BATCH",
    "__version__",
]
