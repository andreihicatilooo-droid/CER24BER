from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class LogRecord:
    source: str
    path: Path
    line: str


class LogStreamCursor:
    def __init__(self, entries: list[tuple[str, Path]]) -> None:
        self._entries = list(entries)
        self._positions: dict[Path, int] = {}

    def snapshot(self, *, tail_lines: int = 80) -> list[LogRecord]:
        records: list[LogRecord] = []
        for source, path in self._entries:
            for line in _tail_lines(path, tail_lines):
                records.append(LogRecord(source=source, path=path, line=line))
            self._positions[path] = path.stat().st_size if path.exists() else 0
        return records

    def poll(self) -> list[LogRecord]:
        records: list[LogRecord] = []
        for source, path in self._entries:
            if not path.exists():
                self._positions[path] = 0
                continue

            previous = self._positions.get(path, 0)
            size = path.stat().st_size
            if size < previous:
                previous = 0

            with path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(previous)
                for line in stream:
                    records.append(LogRecord(source=source, path=path, line=line.rstrip("\n")))
                self._positions[path] = stream.tell()
        return records


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    buffer: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            buffer.append(line.rstrip("\n"))
    return list(buffer)
