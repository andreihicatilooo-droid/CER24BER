from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from cerber_launcher.runtime import (
    BOT_COMPONENTS,
    COMPONENT_ORDER,
    COMPONENT_SPECS,
    TUNNEL_COMPONENTS,
    LauncherRuntimeError,
    build_component_command,
    component_status,
    default_start_targets,
    ensure_component_ready,
    expand_component_names,
    start_component,
    terminate_component,
)
from cerber_launcher.server import run_server
from cerber_launcher.shared import ENV_FILE, LOGS, get_env, init_env_file, launcher_log, read_env_lines, set_env, unset_env


DEFAULT_LOG_LINES = 20
MENU_LOG_LINES = 40
ERROR_PATTERN = re.compile(r"(traceback|exception|error|fatal|failed|critical|ошиб)", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class ComponentOverview:
    key: str
    label: str
    kind: str
    enabled: bool
    running: bool
    pid: int | None
    has_logs: bool
    has_errors: bool
    detail: str
    command: str | None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        if sys.stdin.isatty():
            return _run_menu()
        parser.print_help()
        return 0

    try:
        if args.command == "start":
            return _handle_start(args)
        if args.command == "stop":
            return _handle_stop(args)
        if args.command == "restart":
            return _handle_restart(args)
        if args.command == "serve":
            return _handle_serve(args)
        if args.command == "status":
            return _handle_status(args)
        if args.command == "bots":
            return _handle_bots(args)
        if args.command == "tunnels":
            return _handle_tunnels(args)
        if args.command == "doctor":
            return _handle_doctor(args)
        if args.command == "logs":
            return _handle_logs(args)
        if args.command == "menu":
            return _handle_menu(args)
        if args.command == "env":
            return _handle_env(args)
        parser.print_help()
        return 0
    except LauncherRuntimeError as error:
        print(f"[launcher] {error}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CERBER launcher CLI")
    subparsers = parser.add_subparsers(dest="command")

    component_choices = [*COMPONENT_ORDER, "all", "bot", "bots", "tunnels"]

    start_parser = subparsers.add_parser("start", help="Запустить компоненты в фоне")
    start_parser.add_argument("components", nargs="*", choices=component_choices)
    start_parser.add_argument("--with-tunnel", action="store_true", help="Добавить cloudflared к стандартному набору")

    stop_parser = subparsers.add_parser("stop", help="Остановить компоненты")
    stop_parser.add_argument("components", nargs="*", choices=component_choices)

    restart_parser = subparsers.add_parser("restart", help="Перезапустить компоненты")
    restart_parser.add_argument("components", nargs="*", choices=component_choices)
    restart_parser.add_argument("--with-tunnel", action="store_true", help="При пустом списке перезапустить и tunnel тоже")

    serve_parser = subparsers.add_parser("serve", help="Запустить компоненты в текущем терминале")
    serve_parser.add_argument("components", nargs="*", choices=component_choices)
    serve_parser.add_argument("--with-tunnel", action="store_true", help="Добавить cloudflared к стандартному набору")

    status_parser = subparsers.add_parser("status", help="Показать статус компонентов")
    status_parser.add_argument("components", nargs="*", choices=component_choices)

    subparsers.add_parser("bots", help="Показать список всех ботов")
    subparsers.add_parser("tunnels", help="Показать список туннелей")

    doctor_parser = subparsers.add_parser("doctor", help="Проверить готовность компонентов к запуску")
    doctor_parser.add_argument("components", nargs="*", choices=component_choices)
    doctor_parser.add_argument("--with-tunnel", action="store_true", help="Добавить cloudflared к стандартному набору")

    log_choices = [*COMPONENT_ORDER, "launcher", "all", "bot", "bots", "tunnels"]
    logs_parser = subparsers.add_parser("logs", help="Показать последние строки логов")
    logs_parser.add_argument("targets", nargs="*", choices=log_choices)
    logs_parser.add_argument("--lines", type=_positive_int, default=DEFAULT_LOG_LINES, help="Сколько последних строк вывести")
    logs_parser.add_argument("--errors", action="store_true", help="Показать только error-логи")

    subparsers.add_parser("menu", help="Открыть интерактивное меню управления")

    env_parser = subparsers.add_parser("env", help="Управление .env из CLI")
    env_subparsers = env_parser.add_subparsers(dest="env_command", required=True)
    env_subparsers.add_parser("list", help="Показать содержимое .env")

    env_get = env_subparsers.add_parser("get", help="Получить значение переменной")
    env_get.add_argument("key")

    env_set = env_subparsers.add_parser("set", help="Установить значение переменной")
    env_set.add_argument("key")
    env_set.add_argument("value")

    env_unset = env_subparsers.add_parser("unset", help="Удалить переменную из .env")
    env_unset.add_argument("key")

    env_init = env_subparsers.add_parser("init", help="Создать .env из .env.example")
    env_init.add_argument("--force", action="store_true", help="Перезаписать существующий .env")

    return parser


def _default_targets(with_tunnel: bool = False) -> list[str]:
    targets = default_start_targets()
    if with_tunnel and "tunnel" not in targets:
        targets.append("tunnel")
    return targets


def _resolve_targets(raw_components: list[str], *, default: list[str]) -> list[str]:
    return expand_component_names(raw_components, default=default)


def _handle_start(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=_default_targets(with_tunnel=args.with_tunnel))
    _print_statuses([start_component(component) for component in targets])
    return 0


def _handle_stop(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=list(COMPONENT_ORDER))
    _print_statuses([terminate_component(component) for component in targets])
    return 0


def _handle_restart(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=_default_targets(with_tunnel=args.with_tunnel))
    for component in targets:
        terminate_component(component)
    _print_statuses([start_component(component) for component in targets])
    return 0


def _handle_serve(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=_default_targets(with_tunnel=args.with_tunnel))
    return run_server(targets)


def _handle_status(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=list(COMPONENT_ORDER))
    _print_component_table(_collect_component_overviews(targets))
    return 0


def _handle_bots(_: argparse.Namespace) -> int:
    _print_component_table(_collect_component_overviews(list(BOT_COMPONENTS)))
    return 0


def _handle_tunnels(_: argparse.Namespace) -> int:
    _print_component_table(_collect_component_overviews(list(TUNNEL_COMPONENTS)))
    return 0


def _handle_doctor(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=_default_targets(with_tunnel=args.with_tunnel))
    return _print_doctor(targets)


def _handle_logs(args: argparse.Namespace) -> int:
    targets = _resolve_log_targets(args.targets)
    _print_logs_for_targets(targets, args.lines, error_only=args.errors)
    return 0


def _handle_menu(_: argparse.Namespace) -> int:
    return _run_menu()


def _print_doctor(components: list[str]) -> int:
    blocked = 0
    rows: list[tuple[str, str, str, str, str]] = []
    for component in components:
        overview = _build_component_overview(component)
        ready = "READY" if overview.enabled else "BLOCKED"
        if not overview.enabled:
            blocked += 1
        rows.append(
            (
                overview.label,
                ready,
                _toggle_marker(overview.running),
                "-" if overview.pid is None else str(overview.pid),
                _shorten(overview.detail, 72),
            )
        )

    _print_rows(("Компонент", "Готов", "Работает", "PID", "Причина"), rows)
    for component in components:
        overview = _build_component_overview(component)
        command = overview.command
        if command:
            print(f"  command: {command}")
    return 1 if blocked else 0


def _handle_env(args: argparse.Namespace) -> int:
    if args.env_command == "list":
        if not ENV_FILE.exists():
            print(".env отсутствует")
            return 0
        for line in read_env_lines():
            print(line)
        return 0

    if args.env_command == "get":
        value = get_env(args.key)
        if value:
            print(value)
            return 0
        print(f"Переменная {args.key} не задана", file=sys.stderr)
        return 1

    if args.env_command == "set":
        set_env(args.key, args.value)
        launcher_log(f"env set {args.key}")
        print(f"{args.key} updated")
        return 0

    if args.env_command == "unset":
        removed = unset_env(args.key)
        print(f"{args.key} removed" if removed else f"{args.key} not found")
        return 0

    if args.env_command == "init":
        created = init_env_file(force=args.force)
        print(".env created" if created else ".env already exists")
        return 0

    raise LauncherRuntimeError(f"Неизвестная env-команда: {args.env_command}")


def _collect_component_overviews(components: list[str]) -> list[ComponentOverview]:
    return [_build_component_overview(component) for component in components]


def _build_component_overview(component: str) -> ComponentOverview:
    status = component_status(component)
    enabled, readiness_detail, command = _readiness_snapshot(component)
    has_logs = any(_path_has_content(path) for _, path in _log_paths_for_target(component))
    error_summary = _component_error_summary(component)
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


def _readiness_snapshot(component: str) -> tuple[bool, str, str | None]:
    try:
        ensure_component_ready(component)
        return True, "готов к запуску", " ".join(build_component_command(component))
    except LauncherRuntimeError as error:
        return False, str(error), None


def _component_error_summary(component: str) -> str | None:
    spec = COMPONENT_SPECS[component]
    if spec.error_log_key is not None:
        return _last_matching_line(LOGS[spec.error_log_key])
    return _last_matching_line(LOGS[spec.log_key])


def _print_component_table(overviews: list[ComponentOverview]) -> None:
    rows: list[tuple[str, str, str, str, str, str, str, str, str]] = []
    for index, overview in enumerate(overviews, start=1):
        rows.append(
            (
                str(index),
                overview.label,
                overview.kind,
                _toggle_marker(overview.enabled),
                _toggle_marker(overview.running),
                _presence_marker(overview.has_logs),
                _presence_marker(overview.has_errors),
                "-" if overview.pid is None else str(overview.pid),
                _shorten(overview.detail, 64),
            )
        )

    _print_rows(("#", "Компонент", "Тип", "Вкл", "Работает", "Логи", "Ошибки", "PID", "Статус"), rows)


def _print_rows(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    header_line = "  ".join(value.ljust(widths[index]) for index, value in enumerate(headers))
    separator_line = "  ".join("-" * width for width in widths)
    print(header_line)
    print(separator_line)
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _print_statuses(statuses) -> None:
    for item in statuses:
        marker = "RUNNING" if item.running else "STOPPED"
        pid = "-" if item.pid is None else str(item.pid)
        print(f"{item.label:<12} {marker:<8} pid={pid:<8} {item.detail}")


def _run_menu() -> int:
    while True:
        print()
        print("CERBER launcher")
        _print_component_table(_collect_component_overviews(list(COMPONENT_ORDER)))
        print()
        print("Команды: [номер], start, stop, restart, bots, tunnels, doctor, logs, refresh, quit")

        choice = _read_menu_input("launcher> ")
        if choice in {"quit", "q", "exit"}:
            return 0
        if choice in {"", "refresh", "r"}:
            continue
        if choice == "start":
            _run_menu_action(_default_targets(), "start")
            continue
        if choice == "stop":
            _run_menu_action(list(COMPONENT_ORDER), "stop")
            continue
        if choice == "restart":
            _run_menu_action(list(COMPONENT_ORDER), "restart")
            continue
        if choice == "bots":
            _print_component_table(_collect_component_overviews(list(BOT_COMPONENTS)))
            _pause()
            continue
        if choice == "tunnels":
            _print_component_table(_collect_component_overviews(list(TUNNEL_COMPONENTS)))
            _pause()
            continue
        if choice == "doctor":
            _print_doctor(list(COMPONENT_ORDER))
            _pause()
            continue
        if choice == "logs":
            _print_logs_for_targets(["launcher"], MENU_LOG_LINES)
            _pause()
            continue
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(COMPONENT_ORDER):
                _run_component_menu(COMPONENT_ORDER[index])
                continue
        print("Неизвестная команда.")


def _run_component_menu(component: str) -> None:
    while True:
        overview = _build_component_overview(component)
        print()
        print(f"Компонент: {overview.label}")
        _print_component_table([overview])
        if overview.command:
            print(f"Команда запуска: {overview.command}")
        print("Команды: start, stop, restart, status, doctor, log, error, logs, back")

        choice = _read_menu_input(f"{overview.label}> ")
        if choice in {"back", "b", "0", "quit", "q"}:
            return
        if choice == "start":
            _run_menu_action([component], "start")
            continue
        if choice == "stop":
            _run_menu_action([component], "stop")
            continue
        if choice == "restart":
            _run_menu_action([component], "restart")
            continue
        if choice == "status":
            _print_component_table([_build_component_overview(component)])
            _pause()
            continue
        if choice == "doctor":
            _print_doctor([component])
            _pause()
            continue
        if choice == "log":
            _print_log_entries(_primary_log_paths_for_target(component), MENU_LOG_LINES)
            _pause()
            continue
        if choice == "error":
            _print_log_entries(_error_log_paths_for_target(component), MENU_LOG_LINES)
            _pause()
            continue
        if choice == "logs":
            _print_logs_for_targets([component], MENU_LOG_LINES)
            _pause()
            continue
        print("Неизвестная команда.")


def _run_menu_action(components: list[str], action: str) -> None:
    try:
        if action == "start":
            statuses = [start_component(component) for component in components]
        elif action == "stop":
            statuses = [terminate_component(component) for component in components]
        elif action == "restart":
            statuses = []
            for component in components:
                terminate_component(component)
                statuses.append(start_component(component))
        else:
            raise LauncherRuntimeError(f"Неизвестное действие: {action}")
        _print_statuses(statuses)
    except LauncherRuntimeError as error:
        print(f"[launcher] {error}")
    _pause()


def _read_menu_input(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "quit"


def _pause() -> None:
    if not sys.stdin.isatty():
        return
    try:
        input("Нажмите Enter, чтобы продолжить...")
    except (EOFError, KeyboardInterrupt):
        print()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Значение должно быть положительным числом")
    return parsed


def _resolve_log_targets(raw_targets: list[str]) -> list[str]:
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


def _log_paths_for_target(target: str) -> list[tuple[str, Path]]:
    entries = _primary_log_paths_for_target(target)
    if target == "launcher":
        return entries

    spec = COMPONENT_SPECS[target]
    if spec.error_log_key is not None:
        error_path = LOGS[spec.error_log_key]
        if error_path != entries[0][1]:
            entries.append((f"{spec.label}:stderr", error_path))
    return entries


def _primary_log_paths_for_target(target: str) -> list[tuple[str, Path]]:
    if target == "launcher":
        return [("launcher", LOGS["launcher"])]

    spec = COMPONENT_SPECS[target]
    return [(spec.label, LOGS[spec.log_key])]


def _error_log_paths_for_target(target: str) -> list[tuple[str, Path]]:
    if target == "launcher":
        return [("launcher", LOGS["launcher"])]

    spec = COMPONENT_SPECS[target]
    if spec.error_log_key is not None:
        error_path = LOGS[spec.error_log_key]
        return [(f"{spec.label}:stderr", error_path)]
    return _primary_log_paths_for_target(target)


def _print_logs_for_targets(targets: list[str], lines: int, *, error_only: bool = False) -> None:
    for index, target in enumerate(targets):
        if index:
            print()
        entries = _error_log_paths_for_target(target) if error_only else _log_paths_for_target(target)
        _print_log_entries(entries, lines)


def _print_log_entries(entries: list[tuple[str, Path]], lines: int) -> None:
    for index, (label, path) in enumerate(entries):
        if index:
            print()
        print(f"== {label}: {path} ==")
        if not path.exists():
            print("(лог не найден)")
            continue

        content = _tail_lines(path, lines)
        if not content:
            print("(лог пуст)")
            continue

        for line in content:
            print(line)


def _toggle_marker(value: bool) -> str:
    return "ON" if value else "OFF"


def _presence_marker(value: bool) -> str:
    return "YES" if value else "NO"


def _path_has_content(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _last_nonempty_line(path: Path) -> str | None:
    for line in reversed(_tail_lines(path, 120)):
        text = line.strip()
        if text:
            return _shorten(text, 96)
    return None


def _last_matching_line(path: Path) -> str | None:
    for line in reversed(_tail_lines(path, 120)):
        text = line.strip()
        if text and ERROR_PATTERN.search(text):
            return _shorten(text, 96)
    return None


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    buffer: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            buffer.append(line.rstrip("\n"))
    return list(buffer)
