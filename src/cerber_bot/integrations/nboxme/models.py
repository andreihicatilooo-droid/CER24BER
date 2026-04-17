"""Модели данных библиотеки nboxme."""

from __future__ import annotations

import io
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


# ─── PhotoInput ───────────────────────────────────────────────────────────────

@dataclass
class PhotoInput:
    """Универсальный контейнер входных данных для одного фото."""

    data: bytes
    """Байтовое содержимое файла."""

    name: str
    """Имя файла с расширением."""

    mime: str = "image/jpeg"
    """MIME-тип файла."""

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "PhotoInput":
        """Создать из пути к файлу на диске."""
        path = Path(path)
        mime, _ = mimetypes.guess_type(str(path))
        return cls(data=path.read_bytes(), name=path.name, mime=mime or "image/jpeg")

    @classmethod
    def from_bytes(cls, data: bytes, name: str = "photo.jpg") -> "PhotoInput":
        """Создать из байтового объекта."""
        mime, _ = mimetypes.guess_type(name)
        return cls(data=data, name=name, mime=mime or "image/jpeg")

    @classmethod
    def from_bytesio(cls, bio: Union[io.IOBase, io.BytesIO], name: str = "photo.jpg") -> "PhotoInput":
        """Создать из объекта ввода-вывода (BytesIO, файловый дескриптор)."""
        mime, _ = mimetypes.guess_type(name)
        pos  = bio.tell() if hasattr(bio, "tell") else 0
        data = bio.read()
        if hasattr(bio, "seek"):
            bio.seek(pos)
        return cls(data=bytes(data), name=name, mime=mime or "image/jpeg")

    def __repr__(self) -> str:
        return f"PhotoInput(name={self.name!r}, size={len(self.data)} байт)"


# ─── Тип-алиас PhotoLike ──────────────────────────────────────────────────────

PhotoLike = Union[
    PhotoInput,    # готовый контейнер
    Path,          # путь (pathlib.Path)
    str,           # путь (строка)
    bytes,         # сырые байты
    tuple,         # кортеж (bytes, name) или (stream, name)
    io.IOBase,     # файловый дескриптор
    io.BytesIO,    # BytesIO поток
]
"""Объединённый тип входных данных для фото."""


def to_photo_input(photo: PhotoLike) -> PhotoInput:
    """Конвертирует любой ``PhotoLike`` в ``PhotoInput``."""
    if isinstance(photo, PhotoInput):
        return photo
    if isinstance(photo, (str, Path)):
        return PhotoInput.from_path(photo)
    if isinstance(photo, bytes):
        return PhotoInput.from_bytes(photo)
    if isinstance(photo, tuple):
        data, name = photo
        if isinstance(data, bytes):
            return PhotoInput.from_bytes(data, name)
        return PhotoInput.from_bytesio(data, name)  # type: ignore[arg-type]
    if isinstance(photo, (io.IOBase, io.BytesIO)):
        return PhotoInput.from_bytesio(photo)
    raise TypeError(
        f"Неподдерживаемый тип фото: {type(photo).__name__}. "
        f"Ожидается: PhotoInput, Path, str, bytes, tuple или BytesIO."
    )


# ─── NboxFile ─────────────────────────────────────────────────────────────────

@dataclass
class NboxFile:
    """Один файл, размещённый на nbox.me."""

    name: str
    """Имя файла."""

    url: str
    """Прямая ссылка для скачивания."""

    delete_url: Optional[str] = None
    """Ссылка для удаления файла с сервера."""

    thumbnail_url: Optional[str] = None
    """Ссылка на уменьшенное превью."""

    def __str__(self) -> str:
        return f"{self.name}  →  {self.url}"

    def __repr__(self) -> str:
        return f"NboxFile(name={self.name!r}, url={self.url!r})"


# ─── NboxPage ─────────────────────────────────────────────────────────────────

@dataclass
class NboxPage:
    """Результат одной загрузки на nbox.me."""

    page_url: str
    """URL страницы результата на nbox.me."""

    files: list[NboxFile] = field(default_factory=list)
    """Список загруженных файлов."""

    @property
    def links(self) -> list[str]:
        """Список прямых ссылок на все файлы страницы."""
        return [f.url for f in self.files]

    @property
    def count(self) -> int:
        """Количество файлов на странице."""
        return len(self.files)

    @property
    def first(self) -> Optional[NboxFile]:
        """Первый файл страницы, или ``None`` если страница пуста."""
        return self.files[0] if self.files else None

    def get_file(self, name: str) -> Optional[NboxFile]:
        """Найти файл по имени (регистронезависимо)."""
        nl = name.lower()
        return next((f for f in self.files if f.name.lower() == nl), None)

    def get_file_by_url(self, url: str) -> Optional[NboxFile]:
        """Найти файл по прямой ссылке."""
        return next((f for f in self.files if f.url == url), None)

    def get_deletable(self) -> list[NboxFile]:
        """Получить все файлы, у которых есть ссылка для удаления."""
        return [f for f in self.files if f.delete_url]

    def __str__(self) -> str:
        lines = [f"NboxPage: {self.page_url}  ({self.count} файлов)"]
        lines += [f"  {f}" for f in self.files]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"NboxPage(page_url={self.page_url!r}, count={self.count})"
