from __future__ import annotations

import base64
from pathlib import Path

from cerber_launcher import runtime


class _DummyProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid


def test_build_component_command_uses_unbuffered_python(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "python_executable", lambda: Path("C:/venv/python.exe"), raising=False)

    shop = runtime.build_component_command("shop")
    admin = runtime.build_component_command("admin")
    ceer = runtime.build_component_command("ceer")

    assert Path(shop[0]).name == "python.exe"
    assert Path(admin[0]).name == "python.exe"
    assert Path(ceer[0]).name == "python.exe"
    assert shop[1:3] == ["-u", "-m"]
    assert admin[1:3] == ["-u", "-m"]
    assert ceer[1:3] == ["-u", "-m"]


def test_spawn_component_windows_detached_uses_live_console_wrapper(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime, "ensure_component_ready", lambda component: None)
    monkeypatch.setattr(runtime, "build_component_command", lambda component: ["C:/venv/python.exe", "-u", "-m", "cerber_bot"])
    monkeypatch.setattr(runtime, "python_executable", lambda: Path("C:/venv/python.exe"), raising=False)
    monkeypatch.setattr(runtime.os, "name", "nt", raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

    monkeypatch.setitem(runtime.LOGS, "shop", tmp_path / "shop.log")
    monkeypatch.setitem(runtime.LOGS, "shop_err", tmp_path / "shop.err")

    monkeypatch.setattr(runtime.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(runtime.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)

    captured: dict[str, object] = {}

    def _fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _DummyProcess()

    monkeypatch.setattr(runtime.subprocess, "Popen", _fake_popen)

    spawned = runtime.spawn_component("shop", detached=True)

    assert spawned.process.pid == 4242
    wrapped = captured["command"]
    kwargs = captured["kwargs"]
    assert isinstance(wrapped, list)
    assert "-EncodedCommand" in wrapped
    assert kwargs.get("creationflags") == (512 | 16)
    assert "stdout" not in kwargs
    assert "stderr" not in kwargs

    encoded_script = wrapped[wrapped.index("-EncodedCommand") + 1]
    script = base64.b64decode(encoded_script).decode("utf-16le")
    assert "RedirectStandardOutput = $true" in script
    assert "RedirectStandardError = $true" in script
    assert "PYTHONUNBUFFERED" in script


def test_build_component_command_for_tunnel(monkeypatch) -> None:
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "C:/tools/cloudflared.exe")
    monkeypatch.setattr(runtime, "get_env", lambda key, default="": "9099" if key == "WEB_PORT" else default)

    command = runtime.build_component_command("tunnel")

    assert command == ["C:/tools/cloudflared.exe", "tunnel", "--url", "http://localhost:9099"]
