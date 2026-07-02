from __future__ import annotations

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
    crp = runtime.build_component_command("crp")

    assert Path(shop[0]).name == "python.exe"
    assert Path(admin[0]).name == "python.exe"
    assert Path(ceer[0]).name == "python.exe"
    assert Path(crp[0]).name == "python.exe"
    assert shop[1:3] == ["-u", "-m"]
    assert admin[1:3] == ["-u", "-m"]
    assert ceer[1:3] == ["-u", "-m"]
    assert crp[1:3] == ["-u", "-m"]


def test_spawn_component_windows_detached_starts_python_directly(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime, "ensure_component_ready", lambda component: None)
    monkeypatch.setattr(runtime, "build_component_command", lambda component: ["C:/venv/python.exe", "-u", "-m", "cerber_bot"])
    monkeypatch.setattr(runtime, "python_executable", lambda: Path("C:/venv/python.exe"), raising=False)
    monkeypatch.setattr(runtime.os, "name", "nt", raising=False)

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
    kwargs = captured["kwargs"]
    assert captured["command"] == ["C:/venv/python.exe", "-u", "-m", "cerber_bot"]
    assert kwargs.get("creationflags") == (512 | 16)
    assert kwargs.get("cwd") is not None
    env = kwargs.get("env")
    assert isinstance(env, dict)
    assert env["CERBER_LOG_FILE"] == str(tmp_path / "shop.log")
    assert env["CERBER_ERROR_LOG_FILE"] == str(tmp_path / "shop.err")
    assert "stdout" not in kwargs
    assert "stderr" not in kwargs


def test_build_component_command_for_tunnel(monkeypatch) -> None:
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "C:/tools/cloudflared.exe")
    monkeypatch.setattr(runtime, "get_env", lambda key, default="": "9099" if key == "WEB_PORT" else default)

    command = runtime.build_component_command("tunnel")

    assert command == ["C:/tools/cloudflared.exe", "tunnel", "--url", "http://localhost:9099"]


def test_default_start_targets_include_crp_when_token_exists(monkeypatch) -> None:
    def _get_env(key: str, default: str = "") -> str:
        if key == "BOT_TOKEN":
            return "bot-token"
        if key == "CRP_BOT_TOKEN":
            return "crp-token"
        return default

    monkeypatch.setattr(runtime, "get_env", _get_env)

    assert runtime.default_start_targets() == ["shop", "crp"]


def test_spawn_tunnel_truncates_previous_log(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime, "ensure_component_ready", lambda component: None)
    monkeypatch.setattr(runtime, "build_component_command", lambda component: ["cloudflared", "tunnel", "--url", "http://localhost:8088"])
    monkeypatch.setattr(runtime.os, "name", "posix", raising=False)

    tunnel_log = tmp_path / "tunnel.log"
    tunnel_log.write_text("stale line\n", encoding="utf-8")
    monkeypatch.setitem(runtime.LOGS, "tunnel", tunnel_log)

    captured: dict[str, object] = {}

    def _fake_popen(command, **kwargs):
        captured["kwargs"] = kwargs
        return _DummyProcess(5555)

    monkeypatch.setattr(runtime.subprocess, "Popen", _fake_popen)

    spawned = runtime.spawn_component("tunnel", detached=False)

    assert spawned.process.pid == 5555
    assert tunnel_log.read_text(encoding="utf-8") == ""

    stdout_handle = captured["kwargs"]["stdout"]
    stderr_handle = captured["kwargs"]["stderr"]
    stdout_handle.close()
    if stderr_handle is not stdout_handle:
        stderr_handle.close()
