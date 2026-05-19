from __future__ import annotations

import base64
import os
from dataclasses import dataclass
import shutil
import signal
import subprocess
import time

from cerber_launcher.shared import (
    ENV_FILE,
    LOGS,
    PROJECT_ROOT,
    get_env,
    launcher_log,
    python_executable,
    read_pid_file,
    remove_pid_file,
    write_pid_file,
)


class LauncherRuntimeError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class ComponentSpec:
    key: str
    label: str
    log_key: str
    error_log_key: str | None


@dataclass(slots=True)
class SpawnedComponent:
    key: str
    process: subprocess.Popen[bytes]
    stdout_handle: object
    stderr_handle: object | None
    command: list[str]


@dataclass(slots=True, frozen=True)
class ComponentStatus:
    key: str
    label: str
    running: bool
    pid: int | None
    detail: str


COMPONENT_SPECS: dict[str, ComponentSpec] = {
    "shop": ComponentSpec("shop", "cerber_bot", "shop", "shop_err"),
    "admin": ComponentSpec("admin", "cerber_admin", "admin", "admin_err"),
    "ceer": ComponentSpec("ceer", "ceer_bot", "ceer", "ceer_err"),
    "tunnel": ComponentSpec("tunnel", "cloudflared", "tunnel", None),
}

COMPONENT_ORDER = ("shop", "admin", "ceer", "tunnel")
BOT_COMPONENTS = ("shop", "admin", "ceer")
TUNNEL_COMPONENTS = ("tunnel",)


def default_start_targets() -> list[str]:
    targets = ["shop"]
    if get_env("ADMIN_BOT_TOKEN"):
        targets.append("admin")
    if get_env("CEER_BOT_TOKEN"):
        targets.append("ceer")
    return targets


def expand_component_names(components: list[str] | None, *, default: list[str] | None = None) -> list[str]:
    if not components:
        return list(default or [])
    normalized = [item.lower() for item in components]
    result: list[str] = []
    aliases = {
        "bot": "shop",
        "shop": "shop",
        "admin": "admin",
        "ceer": "ceer",
        "tunnel": "tunnel",
    }
    groups = {
        "all": COMPONENT_ORDER,
        "bots": BOT_COMPONENTS,
        "tunnels": TUNNEL_COMPONENTS,
    }
    for item in normalized:
        members = groups.get(item)
        if members is not None:
            for member in members:
                if member not in result:
                    result.append(member)
            continue

        mapped = aliases.get(item)
        if mapped is None:
            raise LauncherRuntimeError(f"Неизвестный компонент: {item}")
        if mapped not in result:
            result.append(mapped)
    return result


def build_component_command(component: str) -> list[str]:
    python_bin = str(python_executable())
    if component == "shop":
        return [python_bin, "-u", "-m", "cerber_bot"]
    if component == "admin":
        return [python_bin, "-u", "-m", "cerber_admin"]
    if component == "ceer":
        return [python_bin, "-u", "-m", "ceer_bot"]
    if component == "tunnel":
        cloudflared = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
        if not cloudflared:
            raise LauncherRuntimeError("cloudflared не найден в PATH.")
        port = get_env("WEB_PORT", "8088")
        return [cloudflared, "tunnel", "--url", f"http://localhost:{port}"]
    raise LauncherRuntimeError(f"Неизвестный компонент: {component}")


def ensure_component_ready(component: str) -> None:
    if component != "tunnel" and not python_executable().exists():
        raise LauncherRuntimeError("Python из .venv не найден. Создайте окружение или запустите из активного venv.")
    if component != "tunnel" and not ENV_FILE.exists():
        raise LauncherRuntimeError("Файл .env не найден. Используйте `launcher.py env init`.")

    if component == "shop" and not get_env("BOT_TOKEN"):
        raise LauncherRuntimeError("BOT_TOKEN не задан в .env.")
    if component == "admin" and not get_env("ADMIN_BOT_TOKEN"):
        raise LauncherRuntimeError("ADMIN_BOT_TOKEN не задан в .env.")
    if component == "ceer" and not get_env("CEER_BOT_TOKEN"):
        raise LauncherRuntimeError("CEER_BOT_TOKEN не задан в .env.")
    if component == "tunnel" and get_env("WEB_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        raise LauncherRuntimeError("WEB_ENABLED=false, туннель не требуется.")


def spawn_component(component: str, *, detached: bool) -> SpawnedComponent:
    ensure_component_ready(component)
    spec = COMPONENT_SPECS[component]
    command = build_component_command(component)

    if os.name == "nt" and detached:
        return _spawn_component_windows_live_console(component, spec, command)

    stdout_handle = LOGS[spec.log_key].open("a", encoding="utf-8")
    stderr_handle = stdout_handle if spec.error_log_key is None else LOGS[spec.error_log_key].open("a", encoding="utf-8")

    kwargs: dict[str, object] = {
        "cwd": str(PROJECT_ROOT),
        "stdout": stdout_handle,
        "stderr": stderr_handle,
    }
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if detached:
            creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **kwargs)
    except Exception:
        stdout_handle.close()
        if stderr_handle is not stdout_handle:
            stderr_handle.close()
        raise

    return SpawnedComponent(
        key=component,
        process=process,
        stdout_handle=stdout_handle,
        stderr_handle=None if stderr_handle is stdout_handle else stderr_handle,
        command=command,
    )


def _spawn_component_windows_live_console(component: str, spec: ComponentSpec, command: list[str]) -> SpawnedComponent:
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    stdout_path = str(LOGS[spec.log_key])
    stderr_path = stdout_path if spec.error_log_key is None else str(LOGS[spec.error_log_key])
    encoded_script = _encode_powershell_command(
        _build_live_log_powershell_script(
            command=command,
            working_dir=str(PROJECT_ROOT),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
    )

    wrapped_command = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded_script,
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    process = subprocess.Popen(
        wrapped_command,
        cwd=str(PROJECT_ROOT),
        creationflags=creationflags,
    )
    return SpawnedComponent(
        key=component,
        process=process,
        stdout_handle=subprocess.DEVNULL,
        stderr_handle=None,
        command=command,
    )


def _build_live_log_powershell_script(*, command: list[str], working_dir: str, stdout_path: str, stderr_path: str) -> str:
    command_lines = [
        "$psi.FileName = " + _quote_ps_literal(command[0]),
    ]
    for argument in command[1:]:
        command_lines.append("[void]$psi.ArgumentList.Add(" + _quote_ps_literal(argument) + ")")

    python_cmd = str(python_executable())
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$psi = New-Object System.Diagnostics.ProcessStartInfo",
            *command_lines,
            "$psi.WorkingDirectory = " + _quote_ps_literal(working_dir),
            "$psi.UseShellExecute = $false",
            "$psi.RedirectStandardOutput = $true",
            "$psi.RedirectStandardError = $true",
            "$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8",
            "$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8",
            "$stdoutPath = " + _quote_ps_literal(stdout_path),
            "$stderrPath = " + _quote_ps_literal(stderr_path),
            "$stdoutWriter = [System.IO.StreamWriter]::new($stdoutPath, $true, [System.Text.UTF8Encoding]::new($false))",
            "$stderrWriter = [System.IO.StreamWriter]::new($stderrPath, $true, [System.Text.UTF8Encoding]::new($false))",
            f"if ($psi.FileName -eq {_quote_ps_literal(python_cmd)}) {{ $psi.Environment['PYTHONUNBUFFERED'] = '1' }}",
            "$process = New-Object System.Diagnostics.Process",
            "$process.StartInfo = $psi",
            "$onOut = [System.Diagnostics.DataReceivedEventHandler]{",
            "    param($sender, $eventArgs)",
            "    if ($null -eq $eventArgs.Data) { return }",
            "    Write-Host $eventArgs.Data",
            "    $script:stdoutWriter.WriteLine($eventArgs.Data)",
            "    $script:stdoutWriter.Flush()",
            "}",
            "$onErr = [System.Diagnostics.DataReceivedEventHandler]{",
            "    param($sender, $eventArgs)",
            "    if ($null -eq $eventArgs.Data) { return }",
            "    Write-Host $eventArgs.Data -ForegroundColor Red",
            "    $script:stderrWriter.WriteLine($eventArgs.Data)",
            "    $script:stderrWriter.Flush()",
            "}",
            "$process.add_OutputDataReceived($onOut)",
            "$process.add_ErrorDataReceived($onErr)",
            "$null = $process.Start()",
            "$process.BeginOutputReadLine()",
            "$process.BeginErrorReadLine()",
            "$process.WaitForExit()",
            "$process.remove_OutputDataReceived($onOut)",
            "$process.remove_ErrorDataReceived($onErr)",
            "$stdoutWriter.Dispose()",
            "$stderrWriter.Dispose()",
            "exit $process.ExitCode",
        ]
    )


def _quote_ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _encode_powershell_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def start_component(component: str) -> ComponentStatus:
    current = component_status(component)
    if current.running:
        return current

    spawned = spawn_component(component, detached=True)
    try:
        write_pid_file(component, spawned.process.pid, spawned.command)
    finally:
        if hasattr(spawned.stdout_handle, "close"):
            spawned.stdout_handle.close()
        if spawned.stderr_handle is not None:
            spawned.stderr_handle.close()

    launcher_log(f"{component} started pid={spawned.process.pid}")
    spec = COMPONENT_SPECS[component]
    if os.name == "nt":
        return ComponentStatus(component, spec.label, True, spawned.process.pid, "запущен (логи в отдельной консоли)")
    return ComponentStatus(component, spec.label, True, spawned.process.pid, "started")


def _pid_from_file(component: str) -> int | None:
    payload = read_pid_file(component)
    if not payload:
        return None
    pid = payload.get("pid")
    return int(pid) if isinstance(pid, int) or isinstance(pid, float) else None


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return str(pid) in result.stdout
        return False
    return True


def terminate_component(component: str) -> ComponentStatus:
    spec = COMPONENT_SPECS[component]
    pid = _pid_from_file(component)
    if pid is None:
        return ComponentStatus(component, spec.label, False, None, "pid file missing")

    if not is_process_running(pid):
        remove_pid_file(component)
        return ComponentStatus(component, spec.label, False, pid, "already stopped")

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    else:
        os.killpg(pid, signal.SIGTERM)
        deadline = time.time() + 5
        while time.time() < deadline and is_process_running(pid):
            time.sleep(0.2)
        if is_process_running(pid):
            os.killpg(pid, signal.SIGKILL)

    remove_pid_file(component)
    launcher_log(f"{component} stopped pid={pid}")
    return ComponentStatus(component, spec.label, False, pid, "stopped")


def component_status(component: str) -> ComponentStatus:
    spec = COMPONENT_SPECS[component]
    pid = _pid_from_file(component)
    if pid is None:
        return ComponentStatus(component, spec.label, False, None, "not started")
    if is_process_running(pid):
        return ComponentStatus(component, spec.label, True, pid, "running")
    remove_pid_file(component)
    return ComponentStatus(component, spec.label, False, pid, "stale pid removed")


def status_for_components(components: list[str]) -> list[ComponentStatus]:
    return [component_status(component) for component in components]