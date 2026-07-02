from __future__ import annotations

from pathlib import Path

import pytest

from cerber_launcher import cli
from cerber_launcher import supervisor as launcher_supervisor
from cerber_launcher.runtime import ComponentStatus, LauncherRuntimeError, expand_component_names


def _patch_component_basics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher_supervisor,
        "component_status",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, False, None, "not started"),
    )
    monkeypatch.setattr(launcher_supervisor, "ensure_component_ready", lambda component: None)
    monkeypatch.setattr(launcher_supervisor, "build_component_command", lambda component: ["python", "-m", component])


def test_parser_includes_management_commands() -> None:
    help_text = cli._build_parser().format_help()

    assert "serve" in help_text
    assert "ui" in help_text
    assert "menu" in help_text
    assert "bots" in help_text
    assert "tunnels" in help_text
    assert "doctor" in help_text
    assert "logs" in help_text


def test_main_without_args_opens_menu_in_new_terminal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class _Stdin:
        def isatty(self) -> bool:
            return True

    opened: list[bool] = []
    monkeypatch.setattr(cli.sys, "stdin", _Stdin())
    monkeypatch.setattr(cli, "_launch_menu_terminal", lambda: opened.append(True) or True)

    exit_code = cli.main([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert opened == [True]
    assert "dashboard открыт в отдельном терминале" in output


def test_expand_component_names_supports_group_aliases() -> None:
    assert expand_component_names(["bots"]) == ["shop", "admin", "ceer", "crp"]
    assert expand_component_names(["tunnels"]) == ["tunnel"]


def test_doctor_returns_error_for_blocked_component(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        launcher_supervisor,
        "component_status",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, False, None, "not started"),
    )

    def _blocked(component: str) -> None:
        raise LauncherRuntimeError(f"{component} blocked")

    monkeypatch.setattr(launcher_supervisor, "ensure_component_ready", _blocked)

    exit_code = cli.main(["doctor", "shop"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "BLOCKED" in output
    assert "shop blocked" in output


def test_status_prints_component_table_with_indicators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_component_basics(monkeypatch)
    log_path = tmp_path / "shop.log"
    error_path = tmp_path / "shop.err"
    log_path.write_text("started\n", encoding="utf-8")
    error_path.write_text("OSError: port busy\n", encoding="utf-8")

    monkeypatch.setitem(cli.LOGS, "shop", log_path)
    monkeypatch.setitem(cli.LOGS, "shop_err", error_path)

    exit_code = cli.main(["status", "shop"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Компонент" in output
    assert "Логи" in output
    assert "Ошибки" in output
    assert "cerber_bot" in output
    assert "YES" in output
    assert "OSError: port busy" in output


def test_bots_command_lists_only_bots(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _patch_component_basics(monkeypatch)

    exit_code = cli.main(["bots"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "cerber_bot" in output
    assert "cerber_admin" in output
    assert "ceer_bot" in output
    assert "CRP" in output
    assert "cloudflared" not in output


def test_status_does_not_mark_warning_as_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_component_basics(monkeypatch)
    error_path = tmp_path / "admin.err"
    error_path.write_text("WARNING: sleep and retry\n", encoding="utf-8")

    monkeypatch.setitem(cli.LOGS, "admin_err", error_path)

    exit_code = cli.main(["status", "admin"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "cerber_admin" in output
    assert "NO" in output


def test_logs_prints_tail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_path = tmp_path / "launcher.log"
    log_path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")
    monkeypatch.setitem(cli.LOGS, "launcher", log_path)

    exit_code = cli.main(["logs", "launcher", "--lines", "2"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "line-1" not in output
    assert "line-2" in output
    assert "line-3" in output


def test_ui_command_runs_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    monkeypatch.setattr(cli, "_run_dashboard", lambda: called.append(True) or 0)

    exit_code = cli.main(["ui"])

    assert exit_code == 0
    assert called == [True]


def test_menu_can_open_component_and_show_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_component_basics(monkeypatch)
    log_path = tmp_path / "shop.log"
    error_path = tmp_path / "shop.err"
    log_path.write_text("boot ok\n", encoding="utf-8")
    error_path.write_text("", encoding="utf-8")

    monkeypatch.setitem(cli.LOGS, "shop", log_path)
    monkeypatch.setitem(cli.LOGS, "shop_err", error_path)
    responses = iter(["1", "log", "back", "quit"])
    monkeypatch.setattr(cli, "_read_menu_input", lambda prompt: next(responses))
    monkeypatch.setattr(cli, "_pause", lambda: None)
    monkeypatch.setattr(cli, "_clear_terminal", lambda: None)

    exit_code = cli.main(["menu", "--inline"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Главная панель" in output
    assert "Компонент: cerber_bot" in output
    assert "boot ok" in output


def test_serve_runs_server_with_default_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli._SUPERVISOR, "default_targets", lambda with_tunnel=False: ["shop", "admin"])
    captured: list[list[str]] = []

    def _run_server(targets: list[str]) -> int:
        captured.append(targets)
        return 7

    monkeypatch.setattr(cli, "run_server", _run_server)

    exit_code = cli.main(["serve"])

    assert exit_code == 7
    assert captured == [["shop", "admin"]]


def test_supervisor_start_tunnel_updates_web_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_url = "https://fresh-url.trycloudflare.com"
    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(
        launcher_supervisor,
        "start_component",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, True, 12345, "running"),
    )
    monkeypatch.setattr(launcher_supervisor.LauncherSupervisor, "wait_for_tunnel_url", lambda self: expected_url)
    monkeypatch.setattr(launcher_supervisor, "set_env", lambda key, value: captured.append((key, value)))

    supervisor = launcher_supervisor.LauncherSupervisor()
    statuses = supervisor.start_components(["tunnel"])

    assert statuses[0].running is True
    assert captured == [("WEB_BASE_URL", expected_url)]


def test_supervisor_start_tunnel_clears_stale_trycloudflare_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(
        launcher_supervisor,
        "start_component",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, True, 12345, "running"),
    )
    monkeypatch.setattr(launcher_supervisor.LauncherSupervisor, "wait_for_tunnel_url", lambda self: None)
    monkeypatch.setattr(launcher_supervisor, "get_env", lambda key, default="": "https://old.trycloudflare.com")
    monkeypatch.setattr(launcher_supervisor, "set_env", lambda key, value: captured.append((key, value)))

    supervisor = launcher_supervisor.LauncherSupervisor()
    statuses = supervisor.start_components(["tunnel"])

    assert statuses[0].running is True
    assert captured == [("WEB_BASE_URL", "")]


def test_supervisor_restart_tunnel_clears_stale_trycloudflare_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(
        launcher_supervisor,
        "start_component",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, True, 54321, "running"),
    )
    monkeypatch.setattr(launcher_supervisor, "terminate_component", lambda component: None)
    monkeypatch.setattr(launcher_supervisor.LauncherSupervisor, "wait_for_tunnel_url", lambda self: None)
    monkeypatch.setattr(launcher_supervisor, "get_env", lambda key, default="": "https://old.trycloudflare.com")
    monkeypatch.setattr(launcher_supervisor, "set_env", lambda key, value: captured.append((key, value)))

    supervisor = launcher_supervisor.LauncherSupervisor()
    statuses = supervisor.restart_components(["tunnel"])

    assert statuses[0].running is True
    assert captured == [("WEB_BASE_URL", "")]