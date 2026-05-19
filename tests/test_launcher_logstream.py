from __future__ import annotations

from cerber_launcher.logstream import LogStreamCursor


def test_logstream_snapshot_and_poll_follow_file(tmp_path) -> None:
    log_path = tmp_path / "launcher.log"
    log_path.write_text("line-1\nline-2\n", encoding="utf-8")

    cursor = LogStreamCursor([("launcher", log_path)])

    snapshot = cursor.snapshot(tail_lines=1)
    assert [record.line for record in snapshot] == ["line-2"]

    with log_path.open("a", encoding="utf-8") as stream:
        stream.write("line-3\n")

    updates = cursor.poll()
    assert [record.line for record in updates] == ["line-3"]


def test_logstream_handles_file_truncate(tmp_path) -> None:
    log_path = tmp_path / "service.log"
    log_path.write_text("old-1\nold-2\n", encoding="utf-8")

    cursor = LogStreamCursor([("service", log_path)])
    cursor.snapshot(tail_lines=10)

    log_path.write_text("new-1\n", encoding="utf-8")

    updates = cursor.poll()
    assert [record.line for record in updates] == ["new-1"]
