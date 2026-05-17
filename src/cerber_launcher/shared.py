from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
RUN_DIR = PROJECT_ROOT / ".run"
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"

if sys.platform == "win32":
    VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
else:
    VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python"


LOGS = {
    "shop": LOG_DIR / "cerber_bot.log",
    "shop_err": LOG_DIR / "cerber_bot_error.log",
    "admin": LOG_DIR / "admin.log",
    "admin_err": LOG_DIR / "admin_error.log",
    "ceer": LOG_DIR / "ceer.log",
    "ceer_err": LOG_DIR / "ceer_error.log",
    "tunnel": LOG_DIR / "tunnel.log",
    "launcher": LOG_DIR / "launcher.log",
}

PID_FILES = {
    "shop": RUN_DIR / "cerber_bot.pid.json",
    "admin": RUN_DIR / "cerber_admin.pid.json",
    "ceer": RUN_DIR / "ceer_bot.pid.json",
    "tunnel": RUN_DIR / "cloudflared.pid.json",
}


def ensure_runtime_dirs() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    RUN_DIR.mkdir(exist_ok=True)


def python_executable() -> Path:
    if VENV_PY.exists():
        return VENV_PY
    return Path(sys.executable)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def launcher_log(message: str) -> None:
    ensure_runtime_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOGS["launcher"].open("a", encoding="utf-8") as stream:
        stream.write(f"{timestamp}  {message}\n")


def read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8-sig").splitlines()


def get_env(key: str, default: str = "") -> str:
    for line in read_env_lines():
        match = re.match(rf"^\s*{re.escape(key)}\s*=(.*)", line)
        if match:
            value = match.group(1).strip()
            return value or default
    return default


def set_env(key: str, value: str) -> None:
    lines = read_env_lines()
    updated = False
    result: list[str] = []
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            result.append(f"{key}={value}")
            updated = True
        else:
            result.append(line)
    if not updated:
        result.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")


def unset_env(key: str) -> bool:
    lines = read_env_lines()
    result = [line for line in lines if not re.match(rf"^\s*{re.escape(key)}\s*=", line)]
    if len(result) == len(lines):
        return False
    ENV_FILE.write_text("\n".join(result) + ("\n" if result else ""), encoding="utf-8")
    return True


def init_env_file(*, force: bool = False) -> bool:
    if ENV_FILE.exists() and not force:
        return False
    template = ENV_EXAMPLE_FILE.read_text(encoding="utf-8-sig") if ENV_EXAMPLE_FILE.exists() else ""
    ENV_FILE.write_text(template, encoding="utf-8")
    return True


def write_pid_file(component: str, pid: int, command: list[str]) -> None:
    ensure_runtime_dirs()
    payload = {
        "pid": pid,
        "command": command,
        "started_at": utc_timestamp(),
    }
    PID_FILES[component].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_pid_file(component: str) -> dict[str, object] | None:
    path = PID_FILES[component]
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def remove_pid_file(component: str) -> None:
    PID_FILES[component].unlink(missing_ok=True)