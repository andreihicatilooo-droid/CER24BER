from __future__ import annotations

import argparse
import time

from cerber_launcher.runtime import LauncherRuntimeError, SpawnedComponent, default_start_targets, expand_component_names, spawn_component
from cerber_launcher.shared import launcher_log, remove_pid_file, write_pid_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CERBER server runner")
    parser.add_argument("components", nargs="*", choices=["shop", "admin", "ceer", "tunnel", "all", "bot"])
    parser.add_argument("--with-tunnel", action="store_true", help="Добавить cloudflared к стандартному набору")
    args = parser.parse_args(argv)

    default = default_start_targets()
    if args.with_tunnel and "tunnel" not in default:
        default.append("tunnel")

    try:
        targets = expand_component_names(args.components, default=default)
        return run_server(targets)
    except LauncherRuntimeError as error:
        print(f"[server] {error}")
        return 1


def run_server(targets: list[str]) -> int:
    started: list[SpawnedComponent] = []
    try:
        for component in targets:
            spawned = spawn_component(component, detached=False)
            write_pid_file(component, spawned.process.pid, spawned.command)
            started.append(spawned)
            print(f"[server] started {component} pid={spawned.process.pid}")
            launcher_log(f"server started {component} pid={spawned.process.pid}")

        while True:
            for spawned in started:
                return_code = spawned.process.poll()
                if return_code is not None:
                    print(f"[server] {spawned.key} exited with code {return_code}")
                    launcher_log(f"server detected {spawned.key} exit={return_code}")
                    return return_code or 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("[server] stopping")
        launcher_log("server interrupted")
        return 0
    finally:
        for spawned in reversed(started):
            if spawned.process.poll() is None:
                try:
                    spawned.process.terminate()
                    spawned.process.wait(timeout=5)
                except Exception:
                    spawned.process.kill()
            remove_pid_file(spawned.key)
            if hasattr(spawned.stdout_handle, "close"):
                spawned.stdout_handle.close()
            if spawned.stderr_handle is not None:
                spawned.stderr_handle.close()