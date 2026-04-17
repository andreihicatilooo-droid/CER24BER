"""Константы библиотеки nboxme."""

from __future__ import annotations

import aiohttp

# ─── URL ──────────────────────────────────────────────────────────────────────

BASE_URL        = "https://nbox.me"
"""Базовый URL сервиса nbox.me."""

UPLOAD_ENDPOINT = f"{BASE_URL}/put"
"""Эндпоинт для загрузки файлов."""

# ─── Ограничения ──────────────────────────────────────────────────────────────

MAX_FILES_PER_BATCH = 20
"""Максимальное количество файлов в одном запросе загрузки."""

MAX_STORAGE_DAYS = 180
"""Максимальный срок хранения файлов на сервере (дней)."""

# ─── Форматы изображений ──────────────────────────────────────────────────────

IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".bmp", ".tiff", ".tif", ".svg", ".heic", ".heif",
})
"""Поддерживаемые расширения файлов изображений."""

# ─── HTTP ─────────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=300, connect=10)
"""Таймаут HTTP-запросов: 300 сек. на загрузку, 10 сек. на подключение."""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
"""User-Agent заголовок для HTTP-запросов."""
