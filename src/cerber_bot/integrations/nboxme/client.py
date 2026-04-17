"""HTTP-клиент для nbox.me."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Optional, Sequence, Union

import aiohttp

from .constants import (
    DEFAULT_TIMEOUT,
    IMAGE_EXTENSIONS,
    MAX_FILES_PER_BATCH,
    UPLOAD_ENDPOINT,
    USER_AGENT,
)
from .exceptions import NboxUploadError
from .models import NboxFile, NboxPage, PhotoInput, PhotoLike, to_photo_input
from ._parser import _PageParser


class NboxClient:
    """Низкоуровневый асинхронный HTTP-клиент для nbox.me."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None) -> None:
        self._session:     Optional[aiohttp.ClientSession] = session
        self._own_session: bool                            = session is None

    # ── Управление жизненным циклом ──

    async def open(self) -> "NboxClient":
        """Открыть HTTP-сессию."""
        if self._own_session:
            self._session = aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        return self

    async def close(self) -> None:
        """Закрыть HTTP-сессию."""
        if self._own_session and self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "NboxClient":
        return await self.open()

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    # ── Внутренние методы ──

    def _require_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError(
                "Клиент не открыт. Используйте 'async with NboxClient()' "
                "или вызовите await client.open()."
            )
        return self._session

    @staticmethod
    def _parse_html(html: str, url: str) -> NboxPage:
        parser = _PageParser()
        parser.feed(html)
        return parser.build_page(url)

    def _build_form(
        self,
        photos:   list[PhotoInput],
        password: str = "",
        days:     int = 0,
    ) -> aiohttp.FormData:
        form = aiohttp.FormData()
        if password:
            form.add_field("protect", "on")
            form.add_field("password", password)
        if days > 0:
            form.add_field("delete",   "on")
            form.add_field("quantity", str(days))
        for p in photos:
            form.add_field(
                "files",
                io.BytesIO(p.data),
                filename=p.name,
                content_type=p.mime,
            )
        return form

    # ── Загрузка ──

    async def upload_one(
        self,
        photo:    PhotoLike,
        *,
        password: str = "",
        days:     int = 0,
    ) -> NboxPage:
        """Загрузить одно фото на nbox.me."""
        return await self.upload([photo], password=password, days=days)

    async def upload(
        self,
        photos:   Sequence[PhotoLike],
        *,
        password: str = "",
        days:     int = 0,
    ) -> NboxPage:
        """Загрузить несколько фото (до 20) за один запрос."""
        inputs = [to_photo_input(p) for p in photos]

        if not inputs:
            raise ValueError("Список фото пуст.")
        if len(inputs) > MAX_FILES_PER_BATCH:
            raise ValueError(
                f"Максимум {MAX_FILES_PER_BATCH} фото за один запрос. "
                "Для загрузки большего числа фото используйте NboxAlbum.add_photos()."
            )

        session = self._require_session()
        form    = self._build_form(inputs, password, days)

        try:
            async with session.post(
                UPLOAD_ENDPOINT, data=form, timeout=DEFAULT_TIMEOUT
            ) as resp:
                if resp.status not in (200, 201):
                    raise NboxUploadError(
                        f"Сервер вернул код {resp.status}.",
                        files=[p.name for p in inputs],
                        status=resp.status,
                    )
                html = await resp.text(errors="replace")
                return self._parse_html(html, str(resp.url))
        except aiohttp.ClientError as e:
            raise NboxUploadError(
                f"Ошибка сети при загрузке: {e}",
                files=[p.name for p in inputs],
            ) from e

    async def upload_folder(
        self,
        folder:   Union[str, Path],
        *,
        password: str  = "",
        days:     int  = 0,
        parallel: bool = True,
    ) -> list[NboxPage]:
        """Загрузить все изображения из папки."""
        folder = Path(folder)
        files  = sorted(
            [f for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda f: f.name.lower(),
        )
        if not files:
            raise FileNotFoundError(f"Нет изображений в папке: {folder}")

        photos  = [PhotoInput.from_path(f) for f in files]
        batches = [
            photos[i:i + MAX_FILES_PER_BATCH]
            for i in range(0, len(photos), MAX_FILES_PER_BATCH)
        ]

        if parallel:
            return list(await asyncio.gather(
                *[self.upload(b, password=password, days=days) for b in batches]
            ))

        pages: list[NboxPage] = []
        for batch in batches:
            pages.append(await self.upload(batch, password=password, days=days))
        return pages

    # ── Получение данных ──

    async def get_page(self, url: str) -> NboxPage:
        """Получить информацию о странице nbox.me по URL."""
        session = self._require_session()
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            resp.raise_for_status()
            html = await resp.text(errors="replace")
            return self._parse_html(html, str(resp.url))

    async def get_links(self, url: str) -> list[str]:
        """Получить список прямых ссылок на файлы страницы."""
        return (await self.get_page(url)).links

    async def get_count(self, url: str) -> int:
        """Получить количество файлов на странице."""
        return (await self.get_page(url)).count

    async def get_photo_bytes(self, url: str) -> bytes:
        """Скачать содержимое файла по прямой ссылке."""
        session = self._require_session()
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.read()

    # ── Удаление ──

    async def delete_file(self, file: NboxFile) -> bool:
        """Удалить файл с сервера nbox.me."""
        if not file.delete_url:
            raise ValueError(
                f"У файла {file.name!r} нет ссылки для удаления."
            )
        session = self._require_session()
        async with session.get(file.delete_url, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.status in (200, 204, 301, 302)

    async def delete_page(self, page: NboxPage) -> dict[str, bool]:
        """Удалить все файлы страницы, у которых есть ``delete_url``."""
        deletable = page.get_deletable()
        if not deletable:
            raise ValueError("Ни у одного файла на странице нет ссылки для удаления.")
        results = await asyncio.gather(
            *[self.delete_file(f) for f in deletable],
            return_exceptions=True,
        )
        return {
            f.name: (isinstance(r, bool) and r)
            for f, r in zip(deletable, results)
        }

    # ── Утилиты ──

    @staticmethod
    def find_images(folder: Union[str, Path]) -> list[Path]:
        """Найти все изображения в папке."""
        folder = Path(folder)
        return sorted(
            [f for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda f: f.name.lower(),
        )

    def album(self) -> "NboxAlbum":  # type: ignore[name-defined]
        """Создать новый NboxAlbum, привязанный к этому клиенту."""
        from .album import NboxAlbum
        return NboxAlbum(self)
