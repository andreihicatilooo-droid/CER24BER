"""Исключения библиотеки nboxme.

Иерархия исключений::

    NboxError                    # Базовое исключение
    ├── NboxClientError          # Ошибки HTTP-клиента
    │   ├── NboxUploadError      # Ошибка загрузки файла
    │   └── NboxDeleteError      # Ошибка удаления файла
    ├── NboxParseError           # Ошибка разбора HTML-страницы
    └── NboxAlbumError           # Логические ошибки альбома
        └── NboxEmptyAlbumError  # Операция над пустым альбомом
"""

from __future__ import annotations


class NboxError(Exception):
    """Базовое исключение библиотеки nboxme."""


class NboxClientError(NboxError):
    """Ошибка HTTP-клиента при обращении к nbox.me."""


class NboxUploadError(NboxClientError):
    """Ошибка загрузки файла на nbox.me."""

    def __init__(self, message: str, files: list[str] | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.files:  list[str]  = files or []
        self.status: int | None = status


class NboxDeleteError(NboxClientError):
    """Ошибка удаления файла с nbox.me."""

    def __init__(self, message: str, url: str | None = None) -> None:
        super().__init__(message)
        self.url: str | None = url


class NboxParseError(NboxError):
    """Ошибка разбора HTML-ответа nbox.me."""

    def __init__(self, message: str, page_url: str | None = None) -> None:
        super().__init__(message)
        self.page_url: str | None = page_url


class NboxAlbumError(NboxError):
    """Логическая ошибка при работе с альбомом."""


class NboxEmptyAlbumError(NboxAlbumError):
    """Операция выполнена над пустым альбомом."""
