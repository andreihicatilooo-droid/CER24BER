from __future__ import annotations

import json
import sys
from typing import Any

WRITE_TOOLS = {
    "apply_patch",
    "create_file",
    "create_directory",
    "edit_notebook_file",
}

AI_TARGETS = (
    ".github/agents/",
    ".github/skills/",
    ".github/prompts/",
    ".github/hooks/",
    ".github/instructions/",
    ".github/copilot-instructions.md",
)


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))


def allow() -> None:
    emit({"hookSpecificOutput": {"permissionDecision": "allow"}})


def normalize(value: str) -> str:
    return value.lower().replace("\\", "/")


def collect_strings(node: Any) -> list[str]:
    if node is None:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        values: list[str] = []
        for value in node.values():
            values.extend(collect_strings(value))
        return values
    if isinstance(node, list):
        values: list[str] = []
        for item in node:
            values.extend(collect_strings(item))
        return values
    return []


def is_write_tool(values: list[str]) -> bool:
    for value in values:
        normalized = normalize(value)
        for tool in WRITE_TOOLS:
            if normalized == tool or normalized.endswith(f".{tool}") or normalized.endswith(f"/{tool}"):
                return True
    return False


def is_ai_target(values: list[str]) -> bool:
    for value in values:
        normalized = normalize(value)
        if normalized == ".github/hooks" or normalized.endswith("/.github/hooks"):
            return True
        if any(target in normalized for target in AI_TARGETS):
            return True
    return False


def is_failure_key(name: str, value: Any) -> bool:
    normalized_name = normalize(name)

    if normalized_name == "iserror":
        return value is True
    if normalized_name == "error":
        if isinstance(value, bool):
            return value
        return bool(str(value).strip())
    if normalized_name == "errors":
        if value is None:
            return False
        if isinstance(value, list):
            return bool(value)
        return bool(str(value).strip())
    if normalized_name in {"success", "ok"}:
        return value is False
    if normalized_name == "exitcode":
        return isinstance(value, int) and value != 0
    if normalized_name == "status":
        return normalize(str(value)) in {"error", "failed", "failure", "denied", "cancelled"}
    return False


def has_failure_marker(node: Any) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if is_failure_key(str(key), value):
                return True
            if has_failure_marker(value):
                return True
    elif isinstance(node, list):
        for item in node:
            if has_failure_marker(item):
                return True
    return False


def main() -> int:
    if len(sys.argv) < 2:
        allow()
        return 0

    mode = sys.argv[1]
    raw_input = sys.stdin.read().strip()

    if not raw_input:
        if mode == "PreToolUse":
            allow()
        else:
            emit({})
        return 0

    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError:
        if mode == "PreToolUse":
            allow()
        else:
            emit({})
        return 0

    values = collect_strings(payload)
    if not is_write_tool(values) or not is_ai_target(values):
        if mode == "PreToolUse":
            allow()
        else:
            emit({})
        return 0

    if mode == "PreToolUse":
        emit(
            {
                "hookSpecificOutput": {"permissionDecision": "ask"},
                "systemMessage": "AI customization write detected. Keep the change scoped to the targeted .github surfaces and keep hooks limited to guard/reminder behavior.",
            }
        )
        return 0

    if has_failure_marker(payload):
        emit({})
        return 0

    emit(
        {
            "systemMessage": "AI customization edit applied. Sync neighboring discovery surfaces in this change-set and run smoke-ai-customizations before closing the task."
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())