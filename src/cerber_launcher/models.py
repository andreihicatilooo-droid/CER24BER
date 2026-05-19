from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(slots=True, frozen=True)
class LauncherSummary:
    total_components: int
    enabled_components: int
    running_components: int
    components_with_logs: int
    components_with_errors: int
