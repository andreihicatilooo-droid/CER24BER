"""
CERBER Bot Launcher — GUI на tkinter (CerberDarkStyle).

Содержит:
  • Анимированный баннер CERBER
  • Боковая панель управления: запуск/стоп бота и туннеля, перезапуск
  • Переключатель логов: Bot / Bot Errors / Tunnel / Launcher
  • Диалог настройки .env со всеми секциями (аналог CLI env_wizard)
  • Проверка доступности внешних сервисов
  • Индикаторы статуса в шапке и боковой панели

Запуск:
    python launcher_gui.py
"""
from __future__ import annotations

import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
import tkinter as tk
import tkinter.font as tkfont

# ═══════════════════════════════════════════════════════════════
# ПУТИ
# ═══════════════════════════════════════════════════════════════

ROOT     = Path(__file__).resolve().parent
LOG_DIR  = ROOT / "logs"
VENV_PY  = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_FILE = ROOT / ".env"

LOG_DIR.mkdir(exist_ok=True)

LOGS: dict[str, Path] = {
    "bot":         LOG_DIR / "bot.log",
    "bot_err":     LOG_DIR / "bot_error.log",
    "admin":       LOG_DIR / "admin.log",
    "admin_err":   LOG_DIR / "admin_error.log",
    "ceer":        LOG_DIR / "ceer.log",
    "ceer_err":    LOG_DIR / "ceer_error.log",
    "tunnel":      LOG_DIR / "tunnel.log",
    "ceer_tunnel": LOG_DIR / "ceer_tunnel.log",
    "launcher":    LOG_DIR / "launcher.log",
}

# ═══════════════════════════════════════════════════════════════
# ПАЛИТРА — CerberDarkStyle (из web/static/style.css)
# --bg: #060101  --accent: #e0001e  --accent-green: #00ff41
# ═══════════════════════════════════════════════════════════════

BG        = "#060101"    # фон окна
BG_PANEL  = "#0a0303"    # боковая панель
BG_CARD   = "#100404"    # карточки / лог
BG_BTN    = "#160508"    # кнопки
BG_HDR    = "#040101"    # шапка / подвал

ACCENT    = "#c8001a"    # тёмно-красный (основной акцент)
ACCENT_B  = "#ff2a40"    # яркий красный (ошибки, стоп)
ACCENT_G  = "#00ff41"    # зелёный (OK, запущен)
ACCENT_C  = "#00c8e8"    # cyan (информация)
ACCENT_W  = "#f0b820"    # жёлтый (предупреждения)

TEXT      = "#e0d8d8"    # основной текст
TEXT_M    = "#8a8080"    # приглушённый
TEXT_D    = "#3c2828"    # очень тёмный (декоративный)

BORDER    = "#1e0008"    # тонкая граница
BORDER_A  = "#c8001a"    # активная граница

# Цвета тегов лога
TAG_COLORS: dict[str, str] = {
    "ok":   ACCENT_G,
    "info": ACCENT_C,
    "warn": ACCENT_W,
    "err":  ACCENT_B,
    "dim":  "#3c2424",
    "gray": TEXT_M,
    "":     TEXT,
}

# ═══════════════════════════════════════════════════════════════
# ASCII БАННЕР
# ═══════════════════════════════════════════════════════════════

BANNER = [
    r"  ██████╗███████╗██████╗ ██████╗ ███████╗██████╗ ",
    r" ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗",
    r" ██║     █████╗  ██████╔╝██████╔╝█████╗  ██████╔╝",
    r" ██║     ██╔══╝  ██╔══██╗██╔══██╗██╔══╝  ██╔══██╗",
    r" ╚██████╗███████╗██║  ██║██████╔╝███████╗██║  ██║",
    r"  ╚═════╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

BANNER_COLS = ["#00ff41", "#00f05a", "#00dc6e", "#00c87d", "#00b469", "#00a055"]
GLITCH_CHR  = list("░▒▓!@#$%^&*<>?/|~^█")
GLITCH_FG   = ["#ff0050", "#00ffff", "#ff00ff", "#ffffff", "#7800dc"]


# ═══════════════════════════════════════════════════════════════
# .ENV HELPERS
# ═══════════════════════════════════════════════════════════════

def _env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8-sig").splitlines()


def get_env(key: str, default: str = "") -> str:
    for ln in _env_lines():
        m = re.match(rf"^\s*{re.escape(key)}\s*=(.*)", ln)
        if m:
            v = m.group(1).strip()
            if v:
                return v
    return default


def set_env(key: str, value: str) -> None:
    lines = _env_lines()
    found, result = False, []
    for ln in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", ln):
            result.append(f"{key}={value}")
            found = True
        else:
            result.append(ln)
    if not found:
        result.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")


def launcher_log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGS["launcher"], "a", encoding="utf-8") as f:
        f.write(f"{ts}  {msg}\n")


# ═══════════════════════════════════════════════════════════════
# ENV SECTIONS — аналог CLI env_wizard (все секции .env)
# ═══════════════════════════════════════════════════════════════
# Формат: (ключ, метка, подсказка/пример, значение по умолчанию)

ENV_SECTIONS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    ("Telegram Bot", [
        ("BOT_TOKEN",
         "Токен бота от @BotFather. Без него бот не запустится.",
         "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ", ""),
        ("ADMIN_BOT_TOKEN",
         "Токен второго бота для админки (опционально).",
         "123456789:ABCdefGHI... (или пусто)", ""),
        ("BOT_USERNAME",
         "Username бота без символа @.",
         "cerber_shop_bot", ""),
        ("SUPPORT_URL",
         "Ссылка на аккаунт поддержки (показывается в боте).",
         "https://t.me/cerber_support", "https://t.me/cerber_support"),
    ]),
    ("База данных", [
        ("DATABASE_URL",
         "Строка подключения к БД. SQLite — без сервера, PostgreSQL — для прода.",
         "sqlite+aiosqlite:///./data/cerber.db", "sqlite+aiosqlite:///./data/cerber.db"),
    ]),
    ("Платежи (общие)", [
        ("WALLET_CURRENCY",      "Основная валюта кошелька.",            "RUB / USD",  "RUB"),
        ("PAYMENTS_CURRENCY",    "Валюта платежей через NicePay.",        "RUB / USD",  "RUB"),
        ("PAYMENTS_MIN_AMOUNT",  "Минимальная сумма пополнения.",         "100",        "100"),
        ("PAYMENTS_MAX_AMOUNT",  "Максимальная сумма пополнения.",        "10000",      "10000"),
    ]),
    ("NicePay", [
        ("NICEPAY_BASE_URL",     "Базовый URL API NicePay.",
         "https://nicepay.io",   "https://nicepay.io"),
        ("NICEPAY_MERCHANT_ID",  "Merchant ID из личного кабинета NicePay.",
         "из кабинета NicePay",  ""),
        ("NICEPAY_SECRET",       "Секретный ключ NicePay для подписи запросов.",
         "из кабинета NicePay",  ""),
        ("NICEPAY_PROXY",        "Прокси только для NicePay (если нужен).",
         "socks5://127.0.0.1:1080 / пусто", ""),
        ("NICEPAY_METHOD",       "H2H-метод оплаты по умолчанию (пусто = ссылка).",
         "bankcard_rub / sbp_rub / yoomoney_rub / payeer_rub / пусто", ""),
        ("NICEPAY_WEBHOOK_PORT", "Порт для webhook от NicePay.",
         "8080", "8080"),
    ]),
    ("Rukassa", [
        ("RUKASSA_BASE_URL",    "URL API Rukassa.",
         "https://lk.rukassa.io/api/v1", "https://lk.rukassa.io/api/v1"),
        ("RUKASSA_SHOP_ID",     "ID магазина из кабинета Rukassa.",
         "число", ""),
        ("RUKASSA_TOKEN",       "API-токен из кабинета Rukassa.",
         "строка", ""),
        ("RUKASSA_SUCCESS_URL", "URL при успешной оплате.",
         "https://your-site.com/success / пусто", ""),
        ("RUKASSA_FAIL_URL",    "URL при неуспешной оплате.",
         "https://your-site.com/fail / пусто", ""),
    ]),
    ("GiftAPI", [
        ("GIFTAPI_BASE_URL",
         "URL API GiftAPI. Sandbox — для тестов, Production — боевой.",
         "https://api.giftapi.io/v1/partner", "https://api.giftapi.io/v1/partner"),
        ("GIFTAPI_TOKEN",  "API-токен партнёра GiftAPI.",  "строка", ""),
        ("GIFTAPI_SECRET", "HMAC-секрет для подписи GiftAPI.", "строка", ""),
    ]),
    ("Web-панель / Mini App", [
        ("WEB_ENABLED",  "Включить веб-панель (витрина в браузере).",
         "true / false", "true"),
        ("WEB_PORT",     "Порт веб-панели и Cloudflare Tunnel.",
         "8088", "8088"),
        ("WEB_BASE_URL", "Публичный HTTPS URL (заполняется при запуске туннеля).",
         "https://xxx.trycloudflare.com / пусто", ""),
    ]),
    ("Прокси для Telegram", [
        ("TELEGRAM_PROXY",   "Прокси для подключения к Telegram API.",
         "socks5://user:pass@host:port / пусто", ""),
        ("TELEGRAM_API_URL", "Кастомный URL Telegram Bot API (локальный сервер).",
         "http://localhost:8081 / пусто", ""),
    ]),
    ("CEER Bot (игровой)", [
        ("CEER_BOT_TOKEN",
         "Токен игрового бота CEER. Пусто — CEER не запускается. Баланс из CERBER БД.",
         "123456789:ABCdefGHI... (или пусто)", ""),
        ("GAME_MIN_BET",  "Минимальная ставка в играх CEER.", "1.00",   "1.00"),
        ("GAME_MAX_BET",  "Максимальная ставка (0 = без ограничения).", "100.00", "100.00"),
        ("CEER_WEB_PORT", "Порт внутреннего веб-сервера Mini App (FastAPI/uvicorn).",
         "8089", "8089"),
        ("CEER_WEB_URL",  "Публичный HTTPS URL Mini App (заполняется при запуске CEER-туннеля).",
         "https://xxx.trycloudflare.com / пусто", ""),
    ]),
    ("Дополнительно", [
        ("MODERATOR_IDS",           "Telegram ID модераторов через запятую.",
         "123456789,987654321", ""),
        ("REQUEST_TIMEOUT_SECONDS", "Таймаут HTTP-запросов к внешним API (секунды).",
         "15", "15"),
        ("CATALOG_CACHE_TTL",       "Кеш каталога товаров (секунды).",
         "120", "120"),
    ]),
]

_SECRET_KEYS = {"TOKEN", "SECRET", "MERCHANT_ID"}


def _is_secret(key: str) -> bool:
    return any(s in key for s in _SECRET_KEYS)


# ═══════════════════════════════════════════════════════════════
# ПРОВЕРКА СЕРВИСОВ
# ═══════════════════════════════════════════════════════════════

SERVICE_CHECKS: list[tuple[str, str, Optional[str], str]] = [
    ("Telegram API", "TELEGRAM_API_URL", "TELEGRAM_PROXY", "https://api.telegram.org"),
    ("NicePay",      "NICEPAY_BASE_URL", "NICEPAY_PROXY",  "https://nicepay.io"),
    ("GiftAPI",      "GIFTAPI_BASE_URL", None,             "https://api.giftapi.io"),
    ("nbox.me",      "NBOX_BASE_URL",    None,             "https://nbox.me"),
]


def _check_url(url: str, proxy_url: Optional[str] = None, timeout: int = 10) -> tuple[bool, str]:
    """HEAD-запрос к url (опционально через прокси). Возвращает (ok, сообщение)."""
    try:
        if proxy_url:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "CERBER-Launcher/1.0")
        resp = opener.open(req, timeout=timeout)
        return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, str(exc)


# ═══════════════════════════════════════════════════════════════
# LOG TAILER
# ═══════════════════════════════════════════════════════════════

class LogTailer(threading.Thread):
    """Фоновый поток: читает новые строки из лог-файла и кладёт в очередь."""

    def __init__(self, path: Path, q: "queue.Queue[tuple[str, str]]", log_key: str) -> None:
        super().__init__(daemon=True)
        self.path    = path
        self.q       = q
        self.log_key = log_key
        self._stop   = threading.Event()

    def run(self) -> None:
        pos = self.path.stat().st_size if self.path.exists() else 0
        while not self._stop.is_set():
            if self.path.exists():
                try:
                    with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        for line in f:
                            s = line.rstrip()
                            if s:
                                self.q.put((self.log_key, s))
                        pos = f.tell()
                except OSError:
                    pass
            self._stop.wait(0.4)

    def stop(self) -> None:
        self._stop.set()


# ═══════════════════════════════════════════════════════════════
# ENV DIALOG
# ═══════════════════════════════════════════════════════════════

class EnvDialog(tk.Toplevel):
    """Модальный диалог настройки .env — аналог CLI env_wizard."""

    def __init__(self, parent: tk.Tk, fonts: dict) -> None:
        super().__init__(parent)
        self.title("⚙  Настройка .env")
        self.configure(bg=BG)
        self.geometry("780x600")
        self.minsize(640, 440)
        self.resizable(True, True)

        self._f_mono   = fonts["mono"]
        self._f_mono_b = fonts["mono_b"]
        self._f_mono_s = fonts["mono_s"]

        # Переменные для ВСЕХ ключей (инициализируем сразу, чтобы смена секций не сбрасывала)
        self._vars: dict[str, tk.StringVar] = {}
        for _, variables in ENV_SECTIONS:
            for key, _, _, default in variables:
                current = get_env(key, "")
                self._vars[key] = tk.StringVar(value=current if current else default)

        self._build()
        self.grab_set()
        self.focus_force()

    # ── построение ────────────────────────────────────────────

    def _build(self) -> None:
        # Шапка
        hdr = tk.Frame(self, bg=BG_HDR)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="▌ НАСТРОЙКА .env", fg=TEXT, bg=BG_HDR,
                 font=self._f_mono_b, padx=12, pady=8).pack(side=tk.LEFT)
        tk.Label(hdr, text="Изменения применяются после перезапуска бота",
                 fg=TEXT_M, bg=BG_HDR, font=self._f_mono_s).pack(side=tk.RIGHT, padx=12)
        tk.Frame(self, bg=ACCENT, height=1).pack(fill=tk.X)

        # Основная область: список секций (LEFT) + форма (RIGHT)
        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        # LEFT — список секций
        left = tk.Frame(main, bg=BG_PANEL, width=190)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        tk.Frame(main, bg=BORDER_A, width=1).pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(left, text="  СЕКЦИИ", fg=ACCENT, bg=BG_PANEL,
                 font=self._f_mono_s, anchor="w").pack(fill=tk.X, pady=(10, 4), padx=4)

        self._section_lb = tk.Listbox(
            left,
            bg=BG_PANEL, fg=TEXT_M,
            selectbackground=BG_CARD, selectforeground=TEXT,
            font=self._f_mono_s,
            relief=tk.FLAT, bd=0,
            activestyle="none",
            highlightthickness=0,
        )
        self._section_lb.pack(fill=tk.BOTH, expand=True, padx=4)
        for _, (name, _) in enumerate(ENV_SECTIONS):
            self._section_lb.insert(tk.END, f"  {name}")
        self._section_lb.bind("<<ListboxSelect>>", self._on_section_select)

        # RIGHT — скролл-форма
        right = tk.Frame(main, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._form_canvas = tk.Canvas(right, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(right, orient=tk.VERTICAL, command=self._form_canvas.yview,
                           bg=BG_PANEL, troughcolor=BG_PANEL, activebackground=ACCENT)
        self._form_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._form_inner = tk.Frame(self._form_canvas, bg=BG)
        self._form_win = self._form_canvas.create_window(
            (0, 0), window=self._form_inner, anchor="nw"
        )

        def _on_form_configure(_e: tk.Event) -> None:
            self._form_canvas.configure(scrollregion=self._form_canvas.bbox("all"))
            self._form_canvas.itemconfig(self._form_win, width=self._form_canvas.winfo_width())

        def _on_canvas_configure(e: tk.Event) -> None:
            self._form_canvas.itemconfig(self._form_win, width=e.width)

        self._form_inner.bind("<Configure>", _on_form_configure)
        self._form_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e: tk.Event) -> None:
            self._form_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self._form_canvas.bind("<MouseWheel>", _on_mousewheel)
        self._form_inner.bind("<MouseWheel>", _on_mousewheel)

        # Подвал
        tk.Frame(self, bg=ACCENT, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(self, bg=BG_HDR, height=46)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)

        tk.Button(
            foot, text="💾  Сохранить", command=self._save,
            fg=ACCENT_G, bg=BG_BTN,
            activeforeground=TEXT, activebackground=BG_CARD,
            font=self._f_mono_b, relief=tk.FLAT, bd=0,
            padx=14, pady=6, cursor="hand2",
        ).pack(side=tk.LEFT, padx=(10, 4), pady=6)

        tk.Button(
            foot, text="Отмена", command=self.destroy,
            fg=TEXT_M, bg=BG_HDR,
            activeforeground=TEXT, activebackground=BG_CARD,
            font=self._f_mono_s, relief=tk.FLAT, bd=0,
            padx=10, pady=6, cursor="hand2",
        ).pack(side=tk.LEFT, pady=6)

        # Выбрать первую секцию
        self._section_lb.selection_set(0)
        self._show_section(0)

    # ── секция ────────────────────────────────────────────────

    def _on_section_select(self, _event: tk.Event) -> None:
        sel = self._section_lb.curselection()
        if sel:
            self._show_section(sel[0])

    def _show_section(self, idx: int) -> None:
        for w in self._form_inner.winfo_children():
            w.destroy()

        section_name, variables = ENV_SECTIONS[idx]

        tk.Label(self._form_inner, text=f"  ▌ {section_name.upper()}",
                 fg=ACCENT, bg=BG, font=self._f_mono_b, anchor="w").pack(
            fill=tk.X, padx=14, pady=(14, 4))
        tk.Frame(self._form_inner, bg=ACCENT, height=1).pack(
            fill=tk.X, padx=14, pady=(0, 10))

        for key, label, hint, _ in variables:
            card = tk.Frame(self._form_inner, bg=BG_CARD)
            card.pack(fill=tk.X, padx=14, pady=4)

            # Имя ключа (цвет зависит от типа)
            key_color = ACCENT_W if _is_secret(key) else ACCENT_C
            tk.Label(card, text=f"  {key}",
                     fg=key_color, bg=BG_CARD, font=self._f_mono_b,
                     anchor="w").pack(fill=tk.X, padx=4, pady=(8, 1))

            # Описание
            tk.Label(card, text=f"  {label}",
                     fg=TEXT_M, bg=BG_CARD, font=self._f_mono_s,
                     anchor="w", wraplength=560, justify=tk.LEFT).pack(
                fill=tk.X, padx=4, pady=(0, 4))

            # Поле ввода
            entry_row = tk.Frame(card, bg=BG_CARD)
            entry_row.pack(fill=tk.X, padx=4, pady=(0, 2))

            show_char = "*" if _is_secret(key) else ""
            entry = tk.Entry(
                entry_row,
                textvariable=self._vars[key],
                bg=BG_BTN, fg=TEXT,
                insertbackground=ACCENT_G,
                selectbackground="#280018",
                font=self._f_mono_s,
                relief=tk.FLAT, bd=0,
                show=show_char,
                highlightthickness=1,
                highlightbackground=BORDER,
                highlightcolor=BORDER_A,
            )
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0), ipady=4)

            if _is_secret(key):
                def _toggle(e=entry) -> None:
                    e.configure(show="" if e.cget("show") else "*")

                tk.Button(
                    entry_row, text="👁", command=_toggle,
                    fg=TEXT_M, bg=BG_BTN, relief=tk.FLAT, bd=0,
                    font=self._f_mono_s, cursor="hand2", padx=6,
                    activeforeground=TEXT, activebackground=BG_CARD,
                ).pack(side=tk.LEFT, padx=(2, 4))
            else:
                entry_row.pack_configure(padx=(4, 12))

            # Подсказка
            tk.Label(card, text=f"  Пример: {hint}",
                     fg=TEXT_D, bg=BG_CARD, font=self._f_mono_s,
                     anchor="w").pack(fill=tk.X, padx=4, pady=(0, 8))

        self._form_canvas.yview_moveto(0)

    # ── сохранение ────────────────────────────────────────────

    def _save(self) -> None:
        saved = 0
        for key, var in self._vars.items():
            val = var.get().strip()
            if val:
                set_env(key, val)
                saved += 1
        launcher_log(f"Сохранено {saved} env-переменных через GUI")
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# MAIN GUI
# ═══════════════════════════════════════════════════════════════

class CerberGUI:
    POLL_MS = 120
    ANIM_MS = 65

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("CERBER Bot Launcher")
        root.configure(bg=BG)
        root.geometry("1100x760")
        root.minsize(900, 600)

        # ── Шрифты ────────────────────────────────────────────
        self._f_mono   = tkfont.Font(family="Consolas", size=10)
        self._f_mono_b = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._f_mono_s = tkfont.Font(family="Consolas", size=9)
        self._f_brand  = tkfont.Font(family="Consolas", size=13, weight="bold")
        self._f_sec    = tkfont.Font(family="Consolas", size=8)

        # ── Состояние процессов ────────────────────────────────
        self._bot_proc:         Optional[subprocess.Popen] = None
        self._admin_proc:       Optional[subprocess.Popen] = None
        self._ceer_proc:        Optional[subprocess.Popen] = None
        self._tunnel_proc:      Optional[subprocess.Popen] = None
        self._ceer_tunnel_proc: Optional[subprocess.Popen] = None
        self._tunnel_url      = ""
        self._ceer_tunnel_url = ""

        # ── Логи: per-key буферы + общая очередь ─────────────
        self._log_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._log_buffers: dict[str, deque] = {k: deque(maxlen=600) for k in LOGS}
        self._ceer_enabled = tk.BooleanVar(value=bool(get_env("CEER_BOT_TOKEN")))
        self._active_log = "bot"
        self._tailers: list[LogTailer] = []

        # ── Анимация ───────────────────────────────────────────
        self._anim_frame = 0

        # ── Построение UI ──────────────────────────────────────
        self._build_header()
        self._build_banner()   # полноширинный CERBER-баннер
        self._build_footer()

        content = tk.Frame(root, bg=BG)
        content.pack(fill=tk.BOTH, expand=True)
        self._build_sidebar(content)
        self._build_log_panel(content)

        # ── Фоновые задачи ─────────────────────────────────────
        self._start_tailers()
        self._schedule_poll()
        self._schedule_anim()

        # Приветственный лог
        self._add_log("launcher", "─" * 64, "dim")
        self._add_log("launcher", "   CERBER Bot Launcher  [GUI — CerberDarkStyle]", "ok")
        self._add_log("launcher", f"   ROOT: {ROOT}", "gray")
        self._add_log("launcher", "─" * 64, "dim")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Control-q>", lambda _: self._on_close())
        root.bind("<Control-Q>", lambda _: self._on_close())

    # ──────────────────────────────────────────────────────────
    # BUILD: HEADER
    # ──────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=BG_HDR, height=54)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="▌", fg=ACCENT_B, bg=BG_HDR,
                 font=self._f_brand).pack(side=tk.LEFT, padx=(12, 0), pady=6)
        tk.Label(hdr, text="CERBER", fg=TEXT, bg=BG_HDR,
                 font=self._f_brand).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(hdr, text=" BOT LAUNCHER", fg=TEXT_M, bg=BG_HDR,
                 font=self._f_mono).pack(side=tk.LEFT)

        status_fr = tk.Frame(hdr, bg=BG_HDR)
        status_fr.pack(side=tk.RIGHT, padx=14)

        self._hdr_bot_var = tk.StringVar(value="○  Core")
        self._hdr_admin_var = tk.StringVar(value="○  Admin")
        self._hdr_tun_var = tk.StringVar(value="○  Tunnel")

        self._hdr_tun_lbl = tk.Label(status_fr, textvariable=self._hdr_tun_var,
                                      fg=TEXT_M, bg=BG_HDR, font=self._f_mono_s)
        self._hdr_tun_lbl.pack(side=tk.RIGHT, padx=10)

        self._hdr_admin_lbl = tk.Label(status_fr, textvariable=self._hdr_admin_var,
                        fg=TEXT_M, bg=BG_HDR, font=self._f_mono_s)
        self._hdr_admin_lbl.pack(side=tk.RIGHT, padx=10)

        self._hdr_bot_lbl = tk.Label(status_fr, textvariable=self._hdr_bot_var,
                                      fg=TEXT_M, bg=BG_HDR, font=self._f_mono_s)
        self._hdr_bot_lbl.pack(side=tk.RIGHT, padx=10)

        self._hdr_ceer_var = tk.StringVar(value="○  CEER")
        self._hdr_ceer_lbl = tk.Label(status_fr, textvariable=self._hdr_ceer_var,
                                       fg=TEXT_M, bg=BG_HDR, font=self._f_mono_s)
        self._hdr_ceer_lbl.pack(side=tk.RIGHT, padx=10)

        self._hdr_miniapp_var = tk.StringVar(value="")
        self._hdr_miniapp_lbl = tk.Label(status_fr, textvariable=self._hdr_miniapp_var,
                                          fg=ACCENT_C, bg=BG_HDR, font=self._f_mono_s)
        self._hdr_miniapp_lbl.pack(side=tk.RIGHT, padx=10)

        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill=tk.X)

    # ──────────────────────────────────────────────────────────
    # BUILD: BANNER (полноширинный)
    # ──────────────────────────────────────────────────────────

    def _build_banner(self) -> None:
        """Полноширинный анимированный CERBER-баннер под шапкой."""
        banner_h = len(BANNER) * 17 + 40
        self._canvas = tk.Canvas(
            self.root, bg=BG_HDR,
            highlightthickness=0,
            height=banner_h,
        )
        self._canvas.pack(fill=tk.X)
        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill=tk.X)

    # ──────────────────────────────────────────────────────────
    # BUILD: FOOTER
    # ──────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        foot = tk.Frame(self.root, bg=BG_HDR, height=36)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)

        tk.Button(
            foot, text="✕  Выход", command=self._on_close,
            fg=ACCENT_B, bg=BG_HDR,
            activeforeground=TEXT, activebackground=BG_CARD,
            font=self._f_mono_s, relief=tk.FLAT, bd=0,
            padx=10, pady=4, cursor="hand2",
        ).pack(side=tk.LEFT, padx=8)

        tk.Label(foot,
                 text="Ctrl+Q — выход   │   колёсико мыши — прокрутка лога",
                 fg=TEXT_D, bg=BG_HDR, font=self._f_mono_s).pack(side=tk.LEFT, padx=6)

        self._foot_url_var = tk.StringVar(value="")
        tk.Label(foot, textvariable=self._foot_url_var,
                 fg=ACCENT_C, bg=BG_HDR, font=self._f_mono_s).pack(side=tk.RIGHT, padx=12)

    # ──────────────────────────────────────────────────────────
    # BUILD: SIDEBAR
    # ──────────────────────────────────────────────────────────

    def _build_sidebar(self, parent: tk.Frame) -> None:
        sidebar_outer = tk.Frame(parent, bg=BG_PANEL, width=244)
        sidebar_outer.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_outer.pack_propagate(False)

        tk.Frame(parent, bg=BORDER_A, width=1).pack(side=tk.LEFT, fill=tk.Y)

        sb_canvas = tk.Canvas(sidebar_outer, bg=BG_PANEL, highlightthickness=0, width=242)
        sb_vsb = tk.Scrollbar(sidebar_outer, orient=tk.VERTICAL, command=sb_canvas.yview,
                               bg=BG_PANEL, troughcolor=BG_PANEL, activebackground=ACCENT)
        sb_canvas.configure(yscrollcommand=sb_vsb.set)
        sb_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        sb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(sb_canvas, bg=BG_PANEL)
        inner_id = sb_canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_cfg(_e: tk.Event) -> None:
            sb_canvas.configure(scrollregion=sb_canvas.bbox("all"))
            sb_canvas.itemconfig(inner_id, width=sb_canvas.winfo_width())

        def _on_sb_cfg(e: tk.Event) -> None:
            sb_canvas.itemconfig(inner_id, width=e.width)

        inner.bind("<Configure>", _on_inner_cfg)
        sb_canvas.bind("<Configure>", _on_sb_cfg)

        # Прокрутка колёсиком только в боковой панели
        def _sb_mw(e: tk.Event) -> None:
            sb_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_sb_wheel(_e: tk.Event) -> None:
            sb_canvas.bind_all("<MouseWheel>", _sb_mw)

        def _unbind_sb_wheel(_e: tk.Event) -> None:
            sb_canvas.unbind_all("<MouseWheel>")

        sb_canvas.bind("<Enter>", _bind_sb_wheel)
        sb_canvas.bind("<Leave>", _unbind_sb_wheel)
        inner.bind("<Enter>", _bind_sb_wheel)
        inner.bind("<Leave>", _unbind_sb_wheel)

        # ── ПРОЦЕССЫ ──────────────────────────────────────────
        self._section_hdr(inner, "CERBER BOT")
        self._btn(inner, "▶   Запуск бота",  self._start_bot,   fg=ACCENT_G)
        self._btn(inner, "■   Стоп бота",    self._stop_bot,    fg=ACCENT_B)
        self._btn(inner, "↺   Перезапуск",   self._restart_bot, fg=ACCENT_W)
        self._sep(inner)

        # ── CEER BOT ──────────────────────────────────────────
        self._section_hdr(inner, "CEER BOT (игровой)")
        self._btn(inner, "▶   Запуск CEER",  self._start_ceer,  fg=ACCENT_G)
        self._btn(inner, "■   Стоп CEER",    self._stop_ceer,   fg=ACCENT_B)
        self._sep(inner)

        # ── CEER MINI APP ─────────────────────────────────────
        self._section_hdr(inner, "CEER MINI APP")
        self._btn(inner, "🎮  Туннель Mini App",     self._start_ceer_tunnel, fg=ACCENT_C)
        self._btn(inner, "✕   Стоп туннель Mini App", self._stop_ceer_tunnel,  fg=ACCENT_B)
        self._sep(inner)

        # ── ТУННЕЛЬ ───────────────────────────────────────────
        self._section_hdr(inner, "ТУННЕЛЬ")
        self._btn(inner, "🌐  Туннель вкл",  self._start_tunnel, fg=ACCENT_C)
        self._btn(inner, "✕   Туннель выкл", self._stop_tunnel,  fg=ACCENT_B)
        self._sep(inner)

        # ── ИНСТРУМЕНТЫ ──────────────────────────────────────
        self._section_hdr(inner, "ИНСТРУМЕНТЫ")
        self._btn(inner, "⚙   Настройки .env",       self._open_env_dialog,  fg=TEXT_M)
        self._btn(inner, "🔍  Проверка сервисов",     self._check_services,   fg=TEXT_M)
        self._btn(inner, "📋  Открыть лог бота",      self._open_bot_log,     fg=TEXT_M)
        self._btn(inner, "📁  Открыть папку логов",   self._open_logs_folder, fg=TEXT_M)
        self._btn(inner, "🗑   Очистить вывод",       self._clear_log,        fg=TEXT_M)
        self._sep(inner)

        # ── СТАТУС ────────────────────────────────────────────
        self._section_hdr(inner, "СТАТУС")
        status_fr = tk.Frame(inner, bg=BG_PANEL)
        status_fr.pack(fill=tk.X, padx=10, pady=(4, 8))

        self._sb_bot_var  = tk.StringVar(value="○  Core: Остановлен")
        self._sb_admin_var = tk.StringVar(value="○  Admin: Остановлен")
        self._sb_ceer_var = tk.StringVar(value="○  CEER: Остановлен")
        self._sb_tun_var  = tk.StringVar(value="○  Туннель: Выкл")
        self._sb_ctun_var = tk.StringVar(value="○  Mini App: Выкл")
        self._sb_url_var  = tk.StringVar(value="")
        self._sb_curl_var = tk.StringVar(value="")

        self._sb_bot_lbl = tk.Label(status_fr, textvariable=self._sb_bot_var,
                                     fg=ACCENT_B, bg=BG_PANEL,
                                     font=self._f_mono_s, anchor="w")
        self._sb_bot_lbl.pack(fill=tk.X, pady=1)

        self._sb_admin_lbl = tk.Label(status_fr, textvariable=self._sb_admin_var,
                           fg=TEXT_M, bg=BG_PANEL,
                           font=self._f_mono_s, anchor="w")
        self._sb_admin_lbl.pack(fill=tk.X, pady=1)

        self._sb_ceer_lbl = tk.Label(status_fr, textvariable=self._sb_ceer_var,
                                      fg=TEXT_M, bg=BG_PANEL,
                                      font=self._f_mono_s, anchor="w")
        self._sb_ceer_lbl.pack(fill=tk.X, pady=1)

        self._sb_tun_lbl = tk.Label(status_fr, textvariable=self._sb_tun_var,
                                     fg=TEXT_M, bg=BG_PANEL,
                                     font=self._f_mono_s, anchor="w")
        self._sb_tun_lbl.pack(fill=tk.X, pady=1)

        tk.Label(status_fr, textvariable=self._sb_url_var,
                 fg=ACCENT_C, bg=BG_PANEL,
                 font=self._f_mono_s, anchor="w",
                 wraplength=218, justify=tk.LEFT).pack(fill=tk.X, pady=1)

        self._sb_ctun_lbl = tk.Label(status_fr, textvariable=self._sb_ctun_var,
                                      fg=TEXT_M, bg=BG_PANEL,
                                      font=self._f_mono_s, anchor="w")
        self._sb_ctun_lbl.pack(fill=tk.X, pady=1)

        tk.Label(status_fr, textvariable=self._sb_curl_var,
                 fg=ACCENT_C, bg=BG_PANEL,
                 font=self._f_mono_s, anchor="w",
                 wraplength=218, justify=tk.LEFT).pack(fill=tk.X, pady=1)

    # ──────────────────────────────────────────────────────────
    # BUILD: LOG PANEL
    # ──────────────────────────────────────────────────────────

    def _build_log_panel(self, parent: tk.Frame) -> None:
        log_frame = tk.Frame(parent, bg=BG)
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── Tab bar ───────────────────────────────────────────
        tab_bar = tk.Frame(log_frame, bg=BG_PANEL, height=36)
        tab_bar.pack(fill=tk.X)
        tab_bar.pack_propagate(False)

        tabs: list[tuple[str, str]] = [
            ("bot",         "Bot Output"),
            ("bot_err",     "Bot Errors"),
            ("admin",       "Admin Output"),
            ("admin_err",   "Admin Errors"),
            ("ceer",        "CEER Output"),
            ("ceer_err",    "CEER Errors"),
            ("tunnel",      "Tunnel"),
            ("ceer_tunnel", "Mini App"),
            ("launcher",    "Launcher"),
        ]
        self._tab_btns: dict[str, tk.Button] = {}
        for key, label in tabs:
            b = tk.Button(
                tab_bar, text=label,
                command=lambda k=key: self._switch_tab(k),
                fg=TEXT_M, bg=BG_PANEL,
                activeforeground=TEXT, activebackground=BG_CARD,
                font=self._f_mono_s, relief=tk.FLAT, bd=0,
                padx=14, pady=6, cursor="hand2",
            )
            b.pack(side=tk.LEFT)
            self._tab_btns[key] = b

        # Кнопки справа: Копировать и Очистить
        tk.Button(
            tab_bar, text="✕ Очистить",
            command=self._clear_log,
            fg=TEXT_D, bg=BG_PANEL,
            activeforeground=ACCENT_B, activebackground=BG_PANEL,
            font=self._f_mono_s, relief=tk.FLAT, bd=0,
            padx=8, pady=6, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=4)

        self._btn_copy_log = tk.Button(
            tab_bar, text="⎘ Копировать",
            command=self._copy_logs,
            fg=ACCENT_C, bg=BG_PANEL,
            activeforeground=TEXT, activebackground=BG_PANEL,
            font=self._f_mono_s, relief=tk.FLAT, bd=0,
            padx=8, pady=6, cursor="hand2",
        )
        self._btn_copy_log.pack(side=tk.RIGHT, padx=2)

        # Акцентная линия
        tk.Frame(log_frame, bg=ACCENT, height=1).pack(fill=tk.X)

        # ── Text widget ────────────────────────────────────────
        txt_fr = tk.Frame(log_frame, bg=BG)
        txt_fr.pack(fill=tk.BOTH, expand=True)

        self._log_txt = tk.Text(
            txt_fr,
            bg=BG_CARD, fg=TEXT,
            font=self._f_mono_s,
            wrap=tk.NONE,
            state=tk.DISABLED,
            relief=tk.FLAT, bd=0,
            insertbackground=ACCENT_G,
            selectbackground="#280018",
            padx=10, pady=6,
        )
        vsb = tk.Scrollbar(txt_fr, command=self._log_txt.yview,
                           bg=BG_PANEL, troughcolor=BG_PANEL, activebackground=ACCENT)
        hsb = tk.Scrollbar(txt_fr, orient=tk.HORIZONTAL, command=self._log_txt.xview,
                           bg=BG_PANEL, troughcolor=BG_PANEL, activebackground=ACCENT)
        self._log_txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._log_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Прокрутка колёсиком в зоне лога
        def _log_mw(e: tk.Event) -> None:
            self._log_txt.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_log_wheel(_e: tk.Event) -> None:
            self.root.bind("<MouseWheel>", _log_mw)

        def _unbind_log_wheel(_e: tk.Event) -> None:
            self.root.unbind("<MouseWheel>")

        self._log_txt.bind("<Enter>", _bind_log_wheel)
        self._log_txt.bind("<Leave>", _unbind_log_wheel)

        # Теги цветов
        for tag, color in TAG_COLORS.items():
            self._log_txt.tag_config(tag if tag else "default", foreground=color)

        self._switch_tab("bot")

    # ──────────────────────────────────────────────────────────
    # HELPER WIDGETS
    # ──────────────────────────────────────────────────────────

    def _sep(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=BORDER_A, height=1).pack(fill=tk.X, pady=2)

    def _section_hdr(self, parent: tk.Frame, text: str) -> None:
        tk.Label(parent, text=f"  {text}",
                 fg=ACCENT, bg=BG_PANEL,
                 font=self._f_sec, anchor="w").pack(fill=tk.X, pady=(6, 1))

    def _btn(self, parent: tk.Frame, text: str, command,
             fg: str = TEXT) -> tk.Button:
        b = tk.Button(
            parent, text=text, command=command,
            fg=fg, bg=BG_BTN,
            activeforeground=TEXT, activebackground=BG_CARD,
            font=self._f_mono_s,
            relief=tk.FLAT, bd=0,
            anchor="w",
            padx=12, pady=5,
            cursor="hand2",
        )
        b.pack(fill=tk.X, pady=1)
        return b

    # ──────────────────────────────────────────────────────────
    # LOG MANAGEMENT
    # ──────────────────────────────────────────────────────────

    def _switch_tab(self, key: str) -> None:
        self._active_log = key
        for k, b in self._tab_btns.items():
            b.configure(fg=TEXT if k == key else TEXT_M,
                        bg=BG_CARD if k == key else BG_PANEL)
        self._repopulate_log()

    def _repopulate_log(self) -> None:
        w = self._log_txt
        w.configure(state=tk.NORMAL)
        w.delete("1.0", tk.END)
        for text, tag in self._log_buffers[self._active_log]:
            w.insert(tk.END, text + "\n", tag if tag else "default")
        w.configure(state=tk.DISABLED)
        w.see(tk.END)

    def _add_log(self, key: str, text: str, tag: str = "") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self._log_buffers[key].append((line, tag))
        if key == self._active_log:
            self._append_to_widget(line, tag)

    def _append_to_widget(self, text: str, tag: str = "") -> None:
        w = self._log_txt
        w.configure(state=tk.NORMAL)
        w.insert(tk.END, text + "\n", tag if tag else "default")
        n = int(w.index(tk.END).split(".")[0])
        if n > 800:
            w.delete("1.0", f"{n - 600}.0")
        w.configure(state=tk.DISABLED)
        w.see(tk.END)

    def _copy_logs(self) -> None:
        """Копирует содержимое активного лога в буфер обмена и на 1 с подсвечивает кнопку."""
        text = self._log_txt.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._btn_copy_log.configure(text="✓ Скопировано", fg=ACCENT_G)
        self.root.after(1000, lambda: self._btn_copy_log.configure(text="⎘ Копировать", fg=ACCENT_C))

    def _clear_log(self) -> None:
        self._log_buffers[self._active_log].clear()
        w = self._log_txt
        w.configure(state=tk.NORMAL)
        w.delete("1.0", tk.END)
        w.configure(state=tk.DISABLED)

    @staticmethod
    def _detect_tag(log_key: str, text: str) -> str:
        tl = text.lower()
        if any(w in tl for w in ("error", "exception", "traceback", "critical", "✗", "[!]")):
            return "err"
        if any(w in tl for w in ("warning", "warn", "⚠")):
            return "warn"
        if any(w in tl for w in ("✓", "[ok]", "started", "running", "success", "ready")):
            return "ok"
        if log_key == "tunnel" or any(w in tl for w in ("cloudflare", "trycloudflare")):
            return "info"
        return ""

    # ──────────────────────────────────────────────────────────
    # BACKGROUND: TAILERS + POLLING
    # ──────────────────────────────────────────────────────────

    def _start_tailers(self) -> None:
        for t in self._tailers:
            t.stop()
        self._tailers = [
            LogTailer(LOGS["bot"],         self._log_q, "bot"),
            LogTailer(LOGS["bot_err"],     self._log_q, "bot_err"),
            LogTailer(LOGS["admin"],       self._log_q, "admin"),
            LogTailer(LOGS["admin_err"],   self._log_q, "admin_err"),
            LogTailer(LOGS["ceer"],        self._log_q, "ceer"),
            LogTailer(LOGS["ceer_err"],    self._log_q, "ceer_err"),
            LogTailer(LOGS["tunnel"],      self._log_q, "tunnel"),
            LogTailer(LOGS["ceer_tunnel"], self._log_q, "ceer_tunnel"),
            LogTailer(LOGS["launcher"],    self._log_q, "launcher"),
        ]
        for t in self._tailers:
            t.start()

    def _drain_queue(self) -> None:
        try:
            while True:
                log_key, text = self._log_q.get_nowait()
                tag = self._detect_tag(log_key, text)
                self._log_buffers[log_key].append((text, tag))
                if log_key == self._active_log:
                    self._append_to_widget(text, tag)
        except queue.Empty:
            pass

    def _schedule_poll(self) -> None:
        self._drain_queue()
        self._update_status()
        self.root.after(self.POLL_MS, self._schedule_poll)

    def _update_status(self) -> None:
        # Бот
        if self._bot_proc and self._bot_proc.poll() is None:
            self._sb_bot_var.set("●  Core: Запущен")
            self._sb_bot_lbl.configure(fg=ACCENT_G)
            self._hdr_bot_var.set("●  Core")
            self._hdr_bot_lbl.configure(fg=ACCENT_G)
        else:
            if self._bot_proc and self._bot_proc.poll() is not None:
                code = self._bot_proc.returncode
                if code != 0:
                    self._add_log("launcher", f"[!] CERBER Core завершился (код {code})", "err")
                self._bot_proc = None
            self._sb_bot_var.set("○  Core: Остановлен")
            self._sb_bot_lbl.configure(fg=ACCENT_B)
            self._hdr_bot_var.set("○  Core")
            self._hdr_bot_lbl.configure(fg=TEXT_M)

        # Admin Bot
        if self._admin_proc and self._admin_proc.poll() is None:
            self._sb_admin_var.set("●  Admin: Запущен")
            self._sb_admin_lbl.configure(fg=ACCENT_G)
            self._hdr_admin_var.set("●  Admin")
            self._hdr_admin_lbl.configure(fg=ACCENT_G)
        else:
            if self._admin_proc and self._admin_proc.poll() is not None:
                code = self._admin_proc.returncode
                if code != 0:
                    self._add_log("launcher", f"[!] CERBER Admin завершился (код {code})", "err")
                self._admin_proc = None
            self._sb_admin_var.set("○  Admin: Остановлен")
            self._sb_admin_lbl.configure(fg=TEXT_M)
            self._hdr_admin_var.set("○  Admin")
            self._hdr_admin_lbl.configure(fg=TEXT_M)

        # CEER Bot
        if self._ceer_proc and self._ceer_proc.poll() is None:
            self._sb_ceer_var.set("●  CEER: Запущен")
            self._sb_ceer_lbl.configure(fg=ACCENT_G)
            self._hdr_ceer_var.set("●  CEER")
            self._hdr_ceer_lbl.configure(fg=ACCENT_G)
        else:
            if self._ceer_proc and self._ceer_proc.poll() is not None:
                code = self._ceer_proc.returncode
                if code != 0:
                    self._add_log("launcher", f"[!] CEER завершился (код {code})", "err")
                self._ceer_proc = None
            self._sb_ceer_var.set("○  CEER: Остановлен")
            self._sb_ceer_lbl.configure(fg=TEXT_M)
            self._hdr_ceer_var.set("○  CEER")
            self._hdr_ceer_lbl.configure(fg=TEXT_M)

        # Туннель
        if self._tunnel_proc and self._tunnel_proc.poll() is None:
            if not self._tunnel_url and LOGS["tunnel"].exists():
                try:
                    content = LOGS["tunnel"].read_text(encoding="utf-8", errors="replace")
                    matches = re.findall(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)", content)
                    if matches:
                        self._tunnel_url = matches[-1]  # берём самый свежий URL
                        self._add_log("launcher", f"Tunnel URL: {self._tunnel_url}", "info")
                        set_env("WEB_BASE_URL", self._tunnel_url)
                        self._add_log("launcher", "WEB_BASE_URL обновлён в .env", "gray")
                        # Перезапускаем бота чтобы он подхватил новый URL
                        if self._bot_proc and self._bot_proc.poll() is None:
                            self._add_log("launcher",
                                          "Перезапуск бота (новый Tunnel URL)...", "warn")
                            self.root.after(500, self._restart_bot)
                except OSError:
                    pass

            self._sb_tun_var.set("●  Туннель: Активен")
            self._sb_tun_lbl.configure(fg=ACCENT_C)
            self._hdr_tun_var.set("●  Tunnel")
            self._hdr_tun_lbl.configure(fg=ACCENT_C)

            if self._tunnel_url:
                self._sb_url_var.set(self._tunnel_url.replace("https://", ""))
                self._foot_url_var.set(f"🌐 {self._tunnel_url}")
            else:
                self._sb_url_var.set("⏳ Ожидание URL...")
                self._foot_url_var.set("")
        else:
            if self._tunnel_proc and self._tunnel_proc.poll() is not None:
                self._add_log("launcher", "[!] Туннель завершился", "warn")
                self._tunnel_proc = None
                self._tunnel_url  = ""
            self._sb_tun_var.set("○  Туннель: Выкл")
            self._sb_tun_lbl.configure(fg=TEXT_M)
            self._hdr_tun_var.set("○  Tunnel")
            self._hdr_tun_lbl.configure(fg=TEXT_M)
            self._sb_url_var.set("")
            self._foot_url_var.set("")

        # CEER Mini App туннель
        if self._ceer_tunnel_proc and self._ceer_tunnel_proc.poll() is None:
            if not self._ceer_tunnel_url and LOGS["ceer_tunnel"].exists():
                try:
                    content = LOGS["ceer_tunnel"].read_text(encoding="utf-8", errors="replace")
                    matches = re.findall(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)", content)
                    if matches:
                        self._ceer_tunnel_url = matches[-1]
                        self._add_log("launcher", f"Mini App URL: {self._ceer_tunnel_url}", "info")
                        set_env("CEER_WEB_URL", self._ceer_tunnel_url)
                        self._add_log("launcher", "CEER_WEB_URL обновлён в .env", "gray")
                        if self._ceer_proc and self._ceer_proc.poll() is None:
                            self._add_log("launcher",
                                          "Перезапуск CEER (новый Mini App URL)...", "warn")
                            self.root.after(500, self._restart_ceer)
                except OSError:
                    pass

            self._sb_ctun_var.set("●  Mini App: Активен")
            self._sb_ctun_lbl.configure(fg=ACCENT_C)
            if self._ceer_tunnel_url:
                short = self._ceer_tunnel_url.replace("https://", "")
                self._sb_curl_var.set(short)
                self._hdr_miniapp_var.set(f"🎮 {short[:28]}…" if len(short) > 30 else f"🎮 {short}")
            else:
                self._sb_curl_var.set("⏳ Ожидание URL...")
                self._hdr_miniapp_var.set("🎮 ⏳")
        else:
            if self._ceer_tunnel_proc and self._ceer_tunnel_proc.poll() is not None:
                self._add_log("launcher", "[!] CEER Mini App туннель завершился", "warn")
                self._ceer_tunnel_proc = None
                self._ceer_tunnel_url  = ""
            self._sb_ctun_var.set("○  Mini App: Выкл")
            self._sb_ctun_lbl.configure(fg=TEXT_M)
            self._hdr_miniapp_var.set("")
            self._sb_curl_var.set("")

    # ──────────────────────────────────────────────────────────
    # ANIMATION: BANNER
    # ──────────────────────────────────────────────────────────

    def _schedule_anim(self) -> None:
        self._draw_banner()
        self.root.after(self.ANIM_MS, self._schedule_anim)

    def _draw_banner(self) -> None:
        c = self._canvas
        c.delete("all")
        f = self._anim_frame
        self._anim_frame += 1

        char_h = 17
        char_w = 9

        # Центрируем баннер по горизонтали
        cw = c.winfo_width() or 1100
        banner_text_w = max(len(line) for line in BANNER) * char_w
        x_off = max(0, (cw - banner_text_w) // 2)

        corrupt_row = random.randint(0, len(BANNER) - 1) if random.random() < 0.015 else -1
        scan_pos    = (f % 120) / 120.0 * (len(BANNER) + 4) - 2

        for i, line in enumerate(BANNER):
            base_hex = BANNER_COLS[min(i, len(BANNER_COLS) - 1)]
            br  = int(base_hex[1:3], 16)
            bg_ = int(base_hex[3:5], 16)
            bb  = int(base_hex[5:7], 16)

            pulse = math.sin(f * 0.06 + i * 0.4) * 0.15
            br  = max(0, min(255, int(br  + 50 * pulse)))
            bg_ = max(0, min(255, int(bg_ + 80 * pulse)))
            bb  = max(0, min(255, int(bb  + 50 * pulse)))

            scan_dist  = abs(i - scan_pos)
            is_corrupt = (i == corrupt_row)
            y = 6 + i * char_h

            for j, ch in enumerate(line):
                x = x_off + j * char_w
                if is_corrupt and random.random() < 0.25:
                    ch    = random.choice(GLITCH_CHR)
                    color = random.choice(GLITCH_FG)
                elif random.random() < 0.004:
                    ch    = random.choice(GLITCH_CHR)
                    color = random.choice(GLITCH_FG)
                elif scan_dist < 1.5:
                    t = (1.5 - scan_dist) / 1.5
                    r = min(255, int(br  + (255 - br)  * t * 0.5))
                    g = min(255, int(bg_ + (255 - bg_) * t * 0.5))
                    b = min(255, int(bb  + (255 - bb)  * t * 0.5))
                    color = f"#{r:02x}{g:02x}{b:02x}"
                else:
                    w = math.sin(f * 0.04 + j * 0.12) * 0.08
                    r = max(0, min(255, int(br  + 40 * w)))
                    g = max(0, min(255, int(bg_ + 40 * w)))
                    b = max(0, min(255, int(bb  + 40 * w)))
                    color = f"#{r:02x}{g:02x}{b:02x}"

                c.create_text(x, y, text=ch, anchor="nw", fill=color, font=self._f_mono)

        sub_y   = 6 + len(BANNER) * char_h + 4
        glow_t  = (math.sin(f * 0.05) + 1) / 2
        gr  = int(50 * glow_t)
        gg  = int(180 + 75 * glow_t)
        gbb = int(80  + 60 * glow_t)
        c.create_text(cw // 2, sub_y, text="▓▒░  Bot Launcher  ░▒▓",
                      anchor="n", fill=f"#{gr:02x}{gg:02x}{gbb:02x}", font=self._f_mono_s)

    # ──────────────────────────────────────────────────────────
    # ACTIONS: ПРОЦЕССЫ
    # ──────────────────────────────────────────────────────────

    def _start_bot(self) -> None:
        if self._bot_proc and self._bot_proc.poll() is None:
            self._add_log("launcher", "CERBER Core уже запущен", "warn")
            return
        if not VENV_PY.exists():
            self._add_log("launcher", f"[!] .venv не найден: {VENV_PY}", "err")
            self._add_log("launcher",
                          "    python -m venv .venv && pip install -e .[dev]", "warn")
            return
        if not ENV_FILE.exists():
            self._add_log("launcher", "[!] .env не найден. Создайте из .env.example", "err")
            return
        if not get_env("BOT_TOKEN", ""):
            self._add_log("launcher", "[!] BOT_TOKEN не задан в .env", "err")
            return
        try:
            out = open(LOGS["bot"],     "a", encoding="utf-8")
            err = open(LOGS["bot_err"], "a", encoding="utf-8")
            self._bot_proc = subprocess.Popen(
                [str(VENV_PY), "-m", "cerber_core"],
                cwd=str(ROOT), stdout=out, stderr=err,
            )
            self._add_log("launcher", f"CERBER Core запущен  PID {self._bot_proc.pid}", "ok")
            launcher_log(f"CERBER Core started PID {self._bot_proc.pid}")

            admin_token = get_env("ADMIN_BOT_TOKEN", "")
            if admin_token:
                admin_out = open(LOGS["admin"],     "a", encoding="utf-8")
                admin_err = open(LOGS["admin_err"], "a", encoding="utf-8")
                self._admin_proc = subprocess.Popen(
                    [str(VENV_PY), "-m", "cerber_admin"],
                    cwd=str(ROOT), stdout=admin_out, stderr=admin_err,
                )
                self._add_log("launcher", f"CERBER Admin запущен  PID {self._admin_proc.pid}", "ok")
                launcher_log(f"CERBER Admin started PID {self._admin_proc.pid}")
            else:
                self._add_log("launcher", "CERBER Admin: пропуск (ADMIN_BOT_TOKEN не задан)", "gray")
            self._switch_tab("bot")
        except Exception as e:
            self._add_log("launcher", f"Ошибка запуска бота: {e}", "err")

    def _stop_bot(self) -> None:
        if (not self._bot_proc or self._bot_proc.poll() is not None) and (not self._admin_proc or self._admin_proc.poll() is not None):
            self._add_log("launcher", "CERBER Core/Admin не запущены", "gray")
            self._bot_proc = None
            self._admin_proc = None
            return
        if self._bot_proc and self._bot_proc.poll() is None:
            pid = self._bot_proc.pid
            self._bot_proc.terminate()
            try:
                self._bot_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._bot_proc.kill()
            self._add_log("launcher", f"CERBER Core остановлен  PID {pid}", "warn")
            launcher_log(f"CERBER Core stopped PID {pid}")
            self._bot_proc = None
        if self._admin_proc and self._admin_proc.poll() is None:
            admin_pid = self._admin_proc.pid
            self._admin_proc.terminate()
            try:
                self._admin_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._admin_proc.kill()
            self._add_log("launcher", f"CERBER Admin остановлен  PID {admin_pid}", "warn")
            launcher_log(f"CERBER Admin stopped PID {admin_pid}")
            self._admin_proc = None

    def _restart_bot(self) -> None:
        self._add_log("launcher", "Перезапуск бота...", "warn")
        self._stop_bot()
        self.root.after(1500, self._start_bot)

    # ──────────────────────────────────────────────────────────
    # ACTIONS: CEER BOT
    # ──────────────────────────────────────────────────────────

    def _start_ceer(self) -> None:
        if self._ceer_proc and self._ceer_proc.poll() is None:
            self._add_log("launcher", "CEER уже запущен", "warn")
            return
        if not VENV_PY.exists():
            self._add_log("launcher", f"[!] .venv не найден: {VENV_PY}", "err")
            return
        token = get_env("CEER_BOT_TOKEN", "")
        if not token or token == "your_ceer_bot_token_from_botfather":
            self._add_log("launcher",
                          "[!] CEER_BOT_TOKEN не задан в .env — укажите через ⚙ Настройки",
                          "err")
            return
        try:
            out = open(LOGS["ceer"],     "a", encoding="utf-8")
            err = open(LOGS["ceer_err"], "a", encoding="utf-8")
            self._ceer_proc = subprocess.Popen(
                [str(VENV_PY), "-m", "ceer_bot"],
                cwd=str(ROOT), stdout=out, stderr=err,
            )
            self._add_log("launcher", f"CEER Bot запущен  PID {self._ceer_proc.pid}", "ok")
            launcher_log(f"CEER Bot started PID {self._ceer_proc.pid}")
            self._switch_tab("ceer")
        except Exception as e:
            self._add_log("launcher", f"Ошибка запуска CEER: {e}", "err")

    def _stop_ceer(self) -> None:
        if not self._ceer_proc or self._ceer_proc.poll() is not None:
            self._add_log("launcher", "CEER не запущен", "gray")
            self._ceer_proc = None
            return
        pid = self._ceer_proc.pid
        self._ceer_proc.terminate()
        try:
            self._ceer_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._ceer_proc.kill()
        self._add_log("launcher", f"CEER Bot остановлен  PID {pid}", "warn")
        launcher_log(f"CEER Bot stopped PID {pid}")
        self._ceer_proc = None

    def _restart_ceer(self) -> None:
        self._add_log("launcher", "Перезапуск CEER...", "warn")
        self._stop_ceer()
        self.root.after(1500, self._start_ceer)

    # ──────────────────────────────────────────────────────────
    # ACTIONS: CEER MINI APP ТУННЕЛЬ
    # ──────────────────────────────────────────────────────────

    def _start_ceer_tunnel(self) -> None:
        if self._ceer_tunnel_proc and self._ceer_tunnel_proc.poll() is None:
            self._add_log("launcher", "CEER Mini App туннель уже запущен", "warn")
            return
        import shutil as _sh
        cf = _sh.which("cloudflared") or _sh.which("cloudflared.exe")
        if not cf:
            self._add_log("launcher", "[!] cloudflared не найден в PATH", "err")
            self._add_log("launcher",
                          "    https://github.com/cloudflare/cloudflared/releases", "info")
            return
        ceer_port = get_env("CEER_WEB_PORT", "8089")
        try:
            out = open(LOGS["ceer_tunnel"], "w", encoding="utf-8")
            self._ceer_tunnel_proc = subprocess.Popen(
                [cf, "tunnel", "--url", f"http://localhost:{ceer_port}"],
                cwd=str(ROOT), stdout=out, stderr=out,
            )
            self._ceer_tunnel_url = ""
            self._add_log("launcher",
                          f"CEER Mini App туннель запущен  PID {self._ceer_tunnel_proc.pid}", "info")
            self._add_log("launcher",
                          f"Порт: {ceer_port}  — ожидаю trycloudflare URL...", "gray")
            launcher_log(f"CEER Mini App tunnel started PID {self._ceer_tunnel_proc.pid}")
            self._switch_tab("ceer_tunnel")
        except Exception as e:
            self._add_log("launcher", f"Ошибка запуска CEER туннеля: {e}", "err")

    def _stop_ceer_tunnel(self) -> None:
        if not self._ceer_tunnel_proc or self._ceer_tunnel_proc.poll() is not None:
            self._add_log("launcher", "CEER Mini App туннель не запущен", "gray")
            self._ceer_tunnel_proc = None
            return
        pid = self._ceer_tunnel_proc.pid
        self._ceer_tunnel_proc.terminate()
        try:
            self._ceer_tunnel_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._ceer_tunnel_proc.kill()
        self._add_log("launcher", f"CEER Mini App туннель остановлен  PID {pid}", "warn")
        launcher_log(f"CEER Mini App tunnel stopped PID {pid}")
        self._ceer_tunnel_proc = None
        self._ceer_tunnel_url  = ""

    # ──────────────────────────────────────────────────────────
    # ACTIONS: ТУННЕЛЬ (CERBER)
    # ──────────────────────────────────────────────────────────

    def _start_tunnel(self) -> None:
        if self._tunnel_proc and self._tunnel_proc.poll() is None:
            self._add_log("launcher", "Туннель уже запущен", "warn")
            return
        import shutil as _sh
        cf = _sh.which("cloudflared") or _sh.which("cloudflared.exe")
        if not cf:
            self._add_log("launcher", "[!] cloudflared не найден в PATH", "err")
            self._add_log("launcher",
                          "    https://github.com/cloudflare/cloudflared/releases", "info")
            return
        if get_env("WEB_ENABLED", "true").lower() not in ("true", "1", "yes"):
            self._add_log("launcher", "[!] WEB_ENABLED=false — туннель не нужен", "warn")
            return
        try:
            web_port = get_env("WEB_PORT", "8088")
            # Перезаписываем лог туннеля — чтобы не накапливались старые URL
            out = open(LOGS["tunnel"], "w", encoding="utf-8")
            self._tunnel_proc = subprocess.Popen(
                [cf, "tunnel", "--url", f"http://localhost:{web_port}"],
                cwd=str(ROOT), stdout=out, stderr=out,
            )
            self._tunnel_url = ""
            self._add_log("launcher", f"Туннель запущен  PID {self._tunnel_proc.pid}", "info")
            self._add_log("launcher", f"Порт: {web_port}  — ожидаю trycloudflare URL...", "gray")
            launcher_log(f"Tunnel started PID {self._tunnel_proc.pid}")
            self._switch_tab("tunnel")
        except Exception as e:
            self._add_log("launcher", f"Ошибка запуска туннеля: {e}", "err")

    def _stop_tunnel(self) -> None:
        if not self._tunnel_proc or self._tunnel_proc.poll() is not None:
            self._add_log("launcher", "Туннель не запущен", "gray")
            self._tunnel_proc = None
            return
        pid = self._tunnel_proc.pid
        self._tunnel_proc.terminate()
        try:
            self._tunnel_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._tunnel_proc.kill()
        self._add_log("launcher", f"Туннель остановлен  PID {pid}", "warn")
        launcher_log(f"Tunnel stopped PID {pid}")
        self._tunnel_proc = None
        self._tunnel_url  = ""

    # ──────────────────────────────────────────────────────────
    # ACTIONS: ИНСТРУМЕНТЫ
    # ──────────────────────────────────────────────────────────

    def _open_env_dialog(self) -> None:
        fonts = {"mono": self._f_mono, "mono_b": self._f_mono_b, "mono_s": self._f_mono_s}
        EnvDialog(self.root, fonts)

    def _check_services(self) -> None:
        self._switch_tab("launcher")
        self._add_log("launcher", "─" * 60, "dim")
        self._add_log("launcher", "Проверка доступности сервисов...", "info")

        def _run() -> None:
            all_ok = True
            for name, url_key, proxy_key, default_url in SERVICE_CHECKS:
                url   = get_env(url_key, default_url) or default_url
                proxy = get_env(proxy_key, "") if proxy_key else ""
                via   = f" → прокси {proxy}" if proxy else ""
                self._add_log("launcher", f"  {name}  ({url}){via}", "gray")
                ok, msg = _check_url(url, proxy or None)
                if ok:
                    self._add_log("launcher", f"    ✓ Доступен: {msg}", "ok")
                else:
                    all_ok = False
                    self._add_log("launcher", f"    ✗ Недоступен: {msg}", "err")
                    if proxy:
                        self._add_log("launcher",
                                      f"    ⚠ Проверьте {proxy_key} в .env", "warn")
                    else:
                        self._add_log("launcher",
                                      "    ⚠ Проверьте интернет/VPN/прокси в .env", "warn")
            self._add_log("launcher",
                          "[OK] Все сервисы доступны" if all_ok
                          else "[!] Некоторые сервисы недоступны",
                          "ok" if all_ok else "warn")
            self._add_log("launcher", "─" * 60, "dim")

        threading.Thread(target=_run, daemon=True).start()

    def _open_bot_log(self) -> None:
        p = LOGS["bot"]
        if p.exists():
            os.startfile(str(p))
        else:
            self._add_log("launcher", f"Лог не найден: {p}", "err")

    def _open_logs_folder(self) -> None:
        os.startfile(str(LOG_DIR))

    # ──────────────────────────────────────────────────────────
    # CLOSE
    # ──────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        for t in self._tailers:
            t.stop()
        for proc in (self._bot_proc, self._admin_proc, self._ceer_proc, self._tunnel_proc, self._ceer_tunnel_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
        launcher_log("Launcher closed")
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def run_gui() -> None:
    """Запустить tkinter-лаунчер."""
    root = tk.Tk()
    root.withdraw()        # скрыть до инициализации
    app = CerberGUI(root)  # noqa: F841
    root.deiconify()       # показать
    root.mainloop()


if __name__ == "__main__":
    run_gui()

