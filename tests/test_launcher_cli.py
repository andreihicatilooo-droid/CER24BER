from __future__ import annotations

from pathlib import Path

import pytest

from cerber_launcher import cli
from cerber_launcher.runtime import ComponentStatus, LauncherRuntimeError


def test_parser_includes_management_commands() -> None:
    help_text = cli._build_parser().format_help()

    assert "serve" in help_text
    assert "doctor" in help_text
    assert "logs" in help_text


def test_doctor_returns_error_for_blocked_component(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        cli,
        "component_status",
        lambda component: ComponentStatus(component, cli.COMPONENT_SPECS[component].label, False, None, "not started"),
    )

    def _blocked(component: str) -> None:
        raise LauncherRuntimeError(f"{component} blocked")

    monkeypatch.setattr(cli, "ensure_component_ready", _blocked)

    exit_code = cli.main(["doctor", "shop"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "BLOCKED" in output
    assert "shop blocked" in output


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


def test_serve_runs_server_with_default_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "default_start_targets", lambda: ["shop", "admin"])
    captured: list[list[str]] = []

    def _run_server(targets: list[str]) -> int:
        captured.append(targets)
        return 7

    monkeypatch.setattr(cli, "run_server", _run_server)

    exit_code = cli.main(["serve"])

    assert exit_code == 7
    assert captured == [["shop", "admin"]]