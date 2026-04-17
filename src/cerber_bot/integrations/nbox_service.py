"""Сервис загрузки фото на nbox.me для использования в чате сделок."""

from __future__ import annotations

import logging
from io import BytesIO

from cerber_bot.integrations.nboxme import NboxClient
from cerber_bot.integrations.nboxme.exceptions import NboxError

logger = logging.getLogger(__name__)


class NboxService:
    """Тонкая обёртка над NboxClient для загрузки фото из сделок.

    Каждый вызов создаёт собственную aiohttp-сессию (stateless per call).
    Ошибки загрузки не пробрасываются — логируются как WARNING.
    """

    async def upload_photo(self, data: BytesIO, *, filename: str = "photo.jpg") -> str | None:
        """Загрузить фото на nbox.me и вернуть прямую ссылку.

        Аргументы:
            data:     байты фото (BytesIO от bot.download()).
            filename: имя файла для загрузки.

        Возвращает:
            Прямая ссылка на файл на nbox.me, или ``None`` при ошибке.
        """
        try:
            async with NboxClient() as client:
                page = await client.upload_one((data, filename))
            if page.first is None:
                logger.warning("nbox.me: загрузка прошла, но ссылка не получена (filename=%s)", filename)
                return None
            return page.first.url
        except NboxError as exc:
            logger.warning("nbox.me: ошибка загрузки фото (%s): %s", filename, exc)
            return None
        except Exception as exc:
            logger.warning("nbox.me: неожиданная ошибка при загрузке фото (%s): %s", filename, exc)
            return None
