"""Высокоуровневый менеджер коллекции фото — NboxAlbum."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from .exceptions import NboxEmptyAlbumError
from .models import NboxFile, NboxPage, PhotoLike, to_photo_input
from .constants import MAX_FILES_PER_BATCH

if TYPE_CHECKING:
    from .client import NboxClient


class NboxAlbum:
    """Высокоуровневый менеджер коллекции фото на nbox.me."""

    def __init__(self, client: "NboxClient") -> None:
        self._client: "NboxClient"   = client
        self._files:  list[NboxFile] = []
        self._pages:  list[NboxPage] = []

    # ── Свойства ──

    @property
    def count(self) -> int:
        return len(self._files)

    @property
    def links(self) -> list[str]:
        return [f.url for f in self._files]

    @property
    def files(self) -> list[NboxFile]:
        return list(self._files)

    @property
    def pages(self) -> list[NboxPage]:
        return list(self._pages)

    @property
    def is_empty(self) -> bool:
        return not self._files

    def __len__(self)  -> int:  return self.count
    def __bool__(self) -> bool: return bool(self._files)
    def __repr__(self) -> str:
        return f"NboxAlbum(count={self.count}, pages={len(self._pages)})"

    # ── Проверка индекса ──

    def _check_index(self, index: int) -> None:
        if not 0 <= index < len(self._files):
            raise IndexError(
                f"Индекс {index} вне диапазона. "
                f"Допустимо: 0–{len(self._files) - 1}. "
                f"Всего фото: {self.count}."
            )

    # ── Доступ к файлам ──

    def get_file(self, index: int) -> NboxFile:
        self._check_index(index)
        return self._files[index]

    def get_link(self, index: int) -> str:
        return self.get_file(index).url

    async def get_photo_bytes(self, index: int) -> bytes:
        return await self._client.get_photo_bytes(self.get_file(index).url)

    # ── Добавление фото ──

    async def add_photo(
        self,
        photo:    PhotoLike,
        *,
        password: str = "",
        days:     int = 0,
    ) -> NboxFile:
        """Загрузить одно фото и добавить в конец альбома."""
        page = await self._client.upload_one(photo, password=password, days=days)
        self._pages.append(page)
        if not page.files:
            raise RuntimeError("nbox.me не вернул ссылку на загруженный файл.")
        file = page.files[0]
        self._files.append(file)
        return file

    async def add_photos(
        self,
        photos:   Sequence[PhotoLike],
        *,
        password: str = "",
        days:     int = 0,
    ) -> list[NboxFile]:
        """Загрузить несколько фото и добавить в конец альбома."""
        if not photos:
            raise ValueError("Список фото пуст.")

        inputs  = [to_photo_input(p) for p in photos]
        batches = [
            inputs[i:i + MAX_FILES_PER_BATCH]
            for i in range(0, len(inputs), MAX_FILES_PER_BATCH)
        ]
        added: list[NboxFile] = []
        for batch in batches:
            page = await self._client.upload(batch, password=password, days=days)
            self._pages.append(page)
            self._files.extend(page.files)
            added.extend(page.files)
        return added

    async def append_photo(self, photo: PhotoLike, **kw: object) -> NboxFile:
        return await self.add_photo(photo, **kw)  # type: ignore[arg-type]

    async def append_photos(self, photos: Sequence[PhotoLike], **kw: object) -> list[NboxFile]:
        return await self.add_photos(photos, **kw)  # type: ignore[arg-type]

    # ── Удаление ──

    async def delete_photo(self, index: int) -> bool:
        self._check_index(index)
        file    = self._files[index]
        success = False
        if file.delete_url:
            try:
                success = await self._client.delete_file(file)
            except Exception:
                pass
        self._files.pop(index)
        return success

    async def delete_all(self) -> int:
        count = 0
        for file in self._files:
            if file.delete_url:
                try:
                    if await self._client.delete_file(file):
                        count += 1
                except Exception:
                    pass
        self._files.clear()
        self._pages.clear()
        return count

    # ── Замена ──

    async def replace_photo(
        self,
        index:     int,
        new_photo: PhotoLike,
        *,
        password:  str = "",
        days:      int = 0,
    ) -> NboxFile:
        self._check_index(index)
        old_file = self._files[index]

        page = await self._client.upload_one(new_photo, password=password, days=days)
        self._pages.append(page)
        if not page.files:
            raise RuntimeError("nbox.me не вернул ссылку на новый файл.")
        new_file = page.files[0]

        if old_file.delete_url:
            try:
                await self._client.delete_file(old_file)
            except Exception:
                pass

        self._files[index] = new_file
        return new_file

    # ── Отчёт ──

    def report(self, *, html: bool = False) -> str:
        """Сформировать текстовый отчёт со всеми ссылками."""
        if not self._files:
            return "Альбом пуст."

        lines: list[str] = []
        if html:
            lines.append(f"<b>📷 Альбом — {self.count} фото:</b>\n")
            for i, f in enumerate(self._files, 1):
                lines.append(f'{i}. <a href="{f.url}">{f.name}</a>')
            lines.append(f"\n<i>📁 Загрузок на nbox.me: {len(self._pages)}</i>")
        else:
            lines.append(f"📷 Альбом — {self.count} фото:\n")
            for i, f in enumerate(self._files, 1):
                lines.append(f"{i}. {f.name}\n   {f.url}")
            lines.append(f"\n📁 Загрузок на nbox.me: {len(self._pages)}")

        return "\n".join(lines)
