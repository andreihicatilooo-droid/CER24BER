from __future__ import annotations

import argparse
import sys

from cerber_launcher.runtime import (
    COMPONENT_ORDER,
    LauncherRuntimeError,
    default_start_targets,
    expand_component_names,
    start_component,
    status_for_components,
    terminate_component,
)
from cerber_launcher.shared import ENV_FILE, init_env_file, launcher_log, read_env_lines, get_env, set_env, unset_env


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "start":
            return _handle_start(args)
        if args.command == "stop":
            return _handle_stop(args)
        if args.command == "restart":
            return _handle_restart(args)
        if args.command == "status":
            return _handle_status(args)
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

    component_choices = [*COMPONENT_ORDER, "all", "bot"]

    start_parser = subparsers.add_parser("start", help="Запустить компоненты в фоне")
    start_parser.add_argument("components", nargs="*", choices=component_choices)
    start_parser.add_argument("--with-tunnel", action="store_true", help="Добавить cloudflared к стандартному набору")

    stop_parser = subparsers.add_parser("stop", help="Остановить компоненты")
    stop_parser.add_argument("components", nargs="*", choices=component_choices)

    restart_parser = subparsers.add_parser("restart", help="Перезапустить компоненты")
    restart_parser.add_argument("components", nargs="*", choices=component_choices)
    restart_parser.add_argument("--with-tunnel", action="store_true", help="При пустом списке перезапустить и tunnel тоже")

    status_parser = subparsers.add_parser("status", help="Показать статус компонентов")
    status_parser.add_argument("components", nargs="*", choices=component_choices)

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


def _handle_status(args: argparse.Namespace) -> int:
    targets = _resolve_targets(args.components, default=list(COMPONENT_ORDER))
    _print_statuses(status_for_components(targets))
    return 0


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


def _print_statuses(statuses) -> None:
    for item in statuses:
        marker = "RUNNING" if item.running else "STOPPED"
        pid = "-" if item.pid is None else str(item.pid)
        print(f"{item.label:<12} {marker:<8} pid={pid:<8} {item.detail}")