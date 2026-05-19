from __future__ import annotations

import re
import time
from collections import deque
from pathlib import Path

from cerber_launcher.models import ComponentOverview, LauncherSummary
from cerber_launcher.runtime import (
    BOT_COMPONENTS,
    COMPONENT_ORDER,
    COMPONENT_SPECS,
    TUNNEL_COMPONENTS,
    ComponentStatus,
    LauncherRuntimeError,
    build_component_command,
    component_status,
    default_start_targets,
    ensure_component_ready,
    expand_component_names,
    start_component,
    terminate_component,
)
from cerber_launcher.shared import LOGS, get_env, set_env


ERROR_PATTERN = re.compile(r"(traceback|exception|error|fatal|failed|critical|ошиб)", re.IGNORECASE)
TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")


class LauncherSupervisor:
    def default_targets(self, *, with_tunnel: bool = False) -> list[str]:
        targets = default_start_targets()
        if with_tunnel and "tunnel" not in targets:
            targets.append("tunnel")
        return targets

    def resolve_targets(self, raw_components: list[str] | None, *, default: list[str]) -> list[str]:
        return expand_component_names(raw_components, default=default)

    def start_components(self, components: list[str]) -> list[ComponentStatus]:
        statuses = [start_component(component) for component in components]
        self._sync_tunnel_env_after_start(components)

        return statuses

    def stop_components(self, components: list[str]) -> list[ComponentStatus]:
        return [terminate_component(component) for component in components]

    def restart_components(self, components: list[str]) -> list[ComponentStatus]:
        statuses: list[ComponentStatus] = []
        for component in components:
            terminate_component(component)
            statuses.append(start_component(component))
        self._sync_tunnel_env_after_start(components)
        return statuses

    def _sync_tunnel_env_after_start(self, components: list[str]) -> None:
        if "tunnel" not in components:
            return

        tunnel_url = self.wait_for_tunnel_url()
        if tunnel_url:
            self.update_tunnel_url_in_env(tunnel_url)
            return

        current_web_base_url = get_env("WEB_BASE_URL", "").strip()
        if "trycloudflare.com" in current_web_base_url:
            self.update_tunnel_url_in_env("")

    def collect_component_overviews(self, components: list[str]) -> list[ComponentOverview]:
        return [self.build_component_overview(component) for component in components]

    def build_component_overview(self, component: str) -> ComponentOverview:
        status = component_status(component)
        enabled, readiness_detail, command = self.readiness_snapshot(component)
        has_logs = any(self.path_has_content(path) for _, path in self.log_paths_for_target(component))
        error_summary = self.component_error_summary(component)
        has_errors = error_summary is not None

        if not enabled and status.running:
            detail = f"{status.detail}; {readiness_detail}"
        elif not enabled:
            detail = readiness_detail
        elif error_summary:
            detail = error_summary
        else:
            detail = status.detail

        return ComponentOverview(
            key=component,
            label=COMPONENT_SPECS[component].label,
            kind="tunnel" if component in TUNNEL_COMPONENTS else "bot",
            enabled=enabled,
            running=status.running,
            pid=status.pid,
            has_logs=has_logs,
            has_errors=has_errors,
            detail=detail,
            command=command,
        )

    def tunnel_url_from_log(self) -> str | None:
        """Извлекает актуальный URL тоннеля из лог-файла cloudflared (последнее вхождение)."""
        log_path = LOGS.get("tunnel")
        if not log_path or not log_path.exists():
            return None
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                match = TUNNEL_URL_PATTERN.search(line)
                if match:
                    return match.group(0)
        except OSError:
            return None
        return None

    def wait_for_tunnel_url(self, timeout_seconds: float = 12.0) -> str | None:
        """Ждёт появления URL cloudflared в логе ограниченное время."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            url = self.tunnel_url_from_log()
            if url:
                return url
            time.sleep(0.3)
        return None

    def update_tunnel_url_in_env(self, url: str) -> None:
        """Записывает URL тоннеля в .env как WEB_BASE_URL."""
        set_env("WEB_BASE_URL", url)

    def build_summary(self, components: list[str]) -> LauncherSummary:
        overviews = self.collect_component_overviews(components)
        return LauncherSummary(
            total_components=len(overviews),
            enabled_components=sum(1 for item in overviews if item.enabled),
            running_components=sum(1 for item in overviews if item.running),
            components_with_logs=sum(1 for item in overviews if item.has_logs),
            components_with_errors=sum(1 for item in overviews if item.has_errors),
        )

    def readiness_snapshot(self, component: str) -> tuple[bool, str, str | None]:
        try:
            ensure_component_ready(component)
            return True, "готов к запуску", " ".join(build_component_command(component))
        except LauncherRuntimeError as error:
            return False, str(error), None

    def component_error_summary(self, component: str) -> str | None:
        spec = COMPONENT_SPECS[component]
        if spec.error_log_key is not None:
            return self.last_matching_line(LOGS[spec.error_log_key])
        return self.last_matching_line(LOGS[spec.log_key])

    def resolve_log_targets(self, raw_targets: list[str] | None) -> list[str]:
        if not raw_targets:
            raw_targets = ["launcher", *COMPONENT_ORDER]

        normalized = [item.lower() for item in raw_targets]
        groups = {
            "all": ("launcher", *COMPONENT_ORDER),
            "bots": BOT_COMPONENTS,
            "tunnels": TUNNEL_COMPONENTS,
        }
        aliases = {
            "launcher": "launcher",
            "bot": "shop",
            "shop": "shop",
            "admin": "admin",
            "ceer": "ceer",
            "tunnel": "tunnel",
        }

        targets: list[str] = []
        for item in normalized:
            members = groups.get(item)
            if members is not None:
                for member in members:
                    if member not in targets:
                        targets.append(member)
                continue

            mapped = aliases.get(item)
            if mapped is None:
                raise LauncherRuntimeError(f"Неизвестная цель логов: {item}")
            if mapped not in targets:
                targets.append(mapped)
        return targets

    def log_paths_for_target(self, target: str, *, error_only: bool = False) -> list[tuple[str, Path]]:
        if error_only:
            return self.error_log_paths_for_target(target)

        entries = self.primary_log_paths_for_target(target)
        if target == "launcher":
            return entries

        spec = COMPONENT_SPECS[target]
        if spec.error_log_key is not None:
            error_path = LOGS[spec.error_log_key]
            if error_path != entries[0][1]:
                entries.append((f"{spec.label}:stderr", error_path))
        return entries

    def primary_log_paths_for_target(self, target: str) -> list[tuple[str, Path]]:
        if target == "launcher":
            return [("launcher", LOGS["launcher"])]

        spec = COMPONENT_SPECS[target]
        return [(spec.label, LOGS[spec.log_key])]

    def error_log_paths_for_target(self, target: str) -> list[tuple[str, Path]]:
        if target == "launcher":
            return [("launcher", LOGS["launcher"])]

        spec = COMPONENT_SPECS[target]
        if spec.error_log_key is not None:
            error_path = LOGS[spec.error_log_key]
            return [(f"{spec.label}:stderr", error_path)]
        return self.primary_log_paths_for_target(target)

    def tail_entries(self, entries: list[tuple[str, Path]], lines: int) -> list[tuple[str, Path, list[str]]]:
        return [(label, path, self.tail_lines(path, lines)) for label, path in entries]

    @staticmethod
    def path_has_content(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    def last_nonempty_line(self, path: Path) -> str | None:
        for line in reversed(self.tail_lines(path, 120)):
            text = line.strip()
            if text:
                return self.shorten(text, 96)
        return None

    def last_matching_line(self, path: Path) -> str | None:
        for line in reversed(self.tail_lines(path, 120)):
            text = line.strip()
            if text and ERROR_PATTERN.search(text):
                return self.shorten(text, 96)
        return None

    @staticmethod
    def shorten(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3].rstrip() + "..."

    @staticmethod
    def tail_lines(path: Path, limit: int) -> list[str]:
        if not path.exists():
            return []
        buffer: deque[str] = deque(maxlen=limit)
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                buffer.append(line.rstrip("\n"))
        return list(buffer)
