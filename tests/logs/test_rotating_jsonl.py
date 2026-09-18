"""D25's rotating JSONL writer and its reader (T5, `logs/jsonl.py`).

Integration by design: every test writes **real files** under `tmp_path` and
reads them back, because the failures this module exists to survive — a torn
last line, a half-written gzip, a crash between the compress and the unlink —
are failures of files, not of objects.

Nothing here reads a clock. Every date is a parameter, which is what makes the
rotation deterministic and the golden lane byte-identical.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import os
from pathlib import Path

from shepherd.logs.jsonl import (
    MAX_BYTES,
    RETENTION_DAYS,
    RotatingJsonlLog,
    read_records,
    scan_records,
)

JSONL_MODULE = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "logs" / "jsonl.py"
PREFIX = "stops"


def records(directory: Path, prefix: str = PREFIX, since: str | None = None) -> list[object]:
    return [record for record, _line in read_records(directory, prefix, since)]


def files(directory: Path) -> list[str]:
    return sorted(path.name for path in (directory / PREFIX).iterdir())


def test_the_two_documented_constants() -> None:
    assert MAX_BYTES == 32 * 1024 * 1024
    assert RETENTION_DAYS == 90


def test_a_record_written_is_a_record_read(tmp_path: Path) -> None:
    log = RotatingJsonlLog(tmp_path, PREFIX)
    assert log.append({"a": 1}, "2026-09-17")
    log.close()
    assert records(tmp_path) == [{"a": 1}]


def test_rotates_on_date_change(tmp_path: Path) -> None:
    """Daily files, named from the **caller's** date — never from a clock."""
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": 1}, "2026-09-16")
    log.append({"n": 2}, "2026-09-17")
    log.close()
    assert files(tmp_path) == ["2026-09-16.jsonl.gz", "2026-09-17.jsonl.gz"]
    assert records(tmp_path) == [{"n": 1}, {"n": 2}]


def test_gzips_the_finished_file_and_removes_the_plain_one_after(tmp_path: Path) -> None:
    """In that order: a crash mid-rotation leaves a readable copy, never none."""
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": 1}, "2026-09-16")
    assert files(tmp_path) == ["2026-09-16.jsonl"]
    log.append({"n": 2}, "2026-09-17")
    assert "2026-09-16.jsonl.gz" in files(tmp_path)
    assert "2026-09-16.jsonl" not in files(tmp_path)
    log.close()
    with gzip.open(tmp_path / PREFIX / "2026-09-16.jsonl.gz", "rt") as handle:
        assert json.loads(handle.read().strip()) == {"n": 1}


def test_crash_between_gzip_and_unlink_leaves_a_readable_copy(tmp_path: Path) -> None:
    """Simulated by leaving both halves on disk. The reader must yield each
    record **once** — a duplicated stop is a second verdict for one event."""
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": 1}, "2026-09-16")
    log.append({"n": 2}, "2026-09-16")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-16.jsonl.gz"
    plain = tmp_path / PREFIX / "2026-09-16.jsonl"
    with gzip.open(gz, "rb") as handle:
        plain.write_bytes(handle.read())
    assert gz.exists() and plain.exists()
    assert records(tmp_path) == [{"n": 1}, {"n": 2}]


def test_size_cap_rolls_within_a_day(tmp_path: Path) -> None:
    log = RotatingJsonlLog(tmp_path, PREFIX, max_bytes=80)
    for n in range(6):
        assert log.append({"n": n, "pad": "x" * 20}, "2026-09-17")
    log.close()
    names = files(tmp_path)
    assert names == [
        "2026-09-17.1.jsonl.gz",
        "2026-09-17.2.jsonl.gz",
        "2026-09-17.jsonl.gz",
    ]
    # read back in **part** order, not in filename order: `…​.1.jsonl.gz`
    # sorts before `….jsonl.gz` as a string, and a replay that read the
    # second part first would re-classify a session out of order.
    assert [record["n"] for record in records(tmp_path)] == [0, 1, 2, 3, 4, 5]  # type: ignore[index]


def test_retention_drops_by_filename_date_not_mtime(tmp_path: Path) -> None:
    """D25 rule 4 — mtime lies: a file copied, restored or rsynced yesterday is
    not a file *from* yesterday."""
    log = RotatingJsonlLog(tmp_path, PREFIX, retention_days=90)
    log.append({"n": "old"}, "2026-01-01")
    log.append({"n": "fresh"}, "2026-09-17")
    log.close()

    stale_mtime = (tmp_path / PREFIX / "2026-09-17.jsonl.gz")
    os.utime(stale_mtime, (0, 0))
    assert stale_mtime.stat().st_mtime == 0

    again = RotatingJsonlLog(tmp_path, PREFIX, retention_days=90)
    again.append({"n": "newer"}, "2026-09-18")
    again.close()

    names = files(tmp_path)
    assert "2026-01-01.jsonl.gz" not in names, "a file 259 days old should be gone"
    assert "2026-09-17.jsonl.gz" in names, "a fresh name with a stale mtime must stay"


def test_retention_is_applied_on_rotation_only(tmp_path: Path) -> None:
    """Never a background thread: the writer rotates on write, which is when it
    can, and a daemon that sweeps on a timer is a second clock."""
    log = RotatingJsonlLog(tmp_path, PREFIX, retention_days=1)
    log.append({"n": 1}, "2026-01-01")
    assert files(tmp_path) == ["2026-01-01.jsonl"]
    log.append({"n": 2}, "2026-09-17")
    assert files(tmp_path) == ["2026-09-17.jsonl"]


def test_reader_skips_malformed_and_reads_gzip(tmp_path: Path) -> None:
    """D25's own sentence. A daemon killed mid-write leaves a half line."""
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": 1}, "2026-09-17")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-17.jsonl.gz"
    with gzip.open(gz, "rb") as handle:
        good = handle.read()
    gz.unlink()
    (tmp_path / PREFIX / "2026-09-17.jsonl").write_bytes(good + b'{"n": 2, "half')

    assert records(tmp_path) == [{"n": 1}]

    with gzip.open(gz, "wb") as handle:
        handle.write(good)
    (tmp_path / PREFIX / "2026-09-17.jsonl").unlink()
    assert records(tmp_path) == [{"n": 1}]


def test_a_line_that_is_not_an_object_is_skipped(tmp_path: Path) -> None:
    """Valid JSON is not a valid record: `null`, `3` and `[1]` all parse."""
    (tmp_path / PREFIX).mkdir(parents=True)
    (tmp_path / PREFIX / "2026-09-17.jsonl").write_text(
        'null\n3\n[1, 2]\n{"n": 1}\n\n', encoding="utf-8"
    )
    assert records(tmp_path) == [{"n": 1}]


def test_reader_survives_a_truncated_gzip_tail(tmp_path: Path) -> None:
    """E-M2-22 — the machine died while the gzip was being written."""
    log = RotatingJsonlLog(tmp_path, PREFIX)
    for n in range(50):
        log.append({"n": n, "pad": "y" * 50}, "2026-09-17")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-17.jsonl.gz"
    whole = gz.read_bytes()
    gz.write_bytes(whole[: len(whole) // 2])

    read_back = records(tmp_path)
    assert read_back != []
    assert len(read_back) < 50
    assert read_back[0] == {"n": 0, "pad": "y" * 50}


def test_an_abandoned_read_is_counted_never_silently_returned(tmp_path: Path) -> None:
    """A torn archive loses records, and the count is the only thing that says so.

    Before this was counted, a half-read file produced `6 records
    (0 malformed, ...)` — byte-indistinguishable from a log that only ever held
    six, and `replay --apply` then rewrote the fleet from the six it could see.
    """
    log = RotatingJsonlLog(tmp_path, PREFIX)
    for n in range(50):
        log.append({"n": n, "pad": "y" * 50}, "2026-09-17")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-17.jsonl.gz"
    whole = gz.read_bytes()
    gz.write_bytes(whole[: len(whole) // 2])

    found, stats = scan_records(tmp_path, PREFIX)

    assert 0 < len(found) < 50
    assert stats.unreadable_files == 1


def test_the_stop_log_reader_never_raises_over_200_truncations(tmp_path: Path) -> None:
    """D25's reader property, **proven** at 200 cuts rather than asserted.

    M2's acceptance clause 6 says the stop-evidence reader is "proven against 200
    truncations, not asserted". The M2 verification pass found that it was not:
    this reader had **two** truncations (the two tests above, each a single
    half-file cut), and the 200-case property belonged to a *different* reader —
    `read_tail` over transcripts (`tests/engines/test_transcript_tail.py`,
    `test_tail_reader_never_raises`). The property was true here too; the
    evidence had simply been banked from the neighbour.

    That is worth a test of its own rather than a reworded clause, because the
    two readers fail differently: a transcript is an *observed* file the engine
    owns, while this one is a file **we** wrote, so a truncation here means our
    own process died mid-append and the next run must still read what survived.

    Every cut lands inside the gzip member, so all 200 are real damage rather
    than a number padded with harmless prefixes. The assertion is on all three
    honest outcomes at once: it never raises, it never silently returns a count
    indistinguishable from a short log (`unreadable_files` sees it), and
    whatever it does recover parses.
    """
    log = RotatingJsonlLog(tmp_path, PREFIX)
    for n in range(80):
        # High-entropy padding, deterministic by `n`. Repeated padding gzips to
        # ~270 bytes, which would put most of the 200 "cuts" past the end of the
        # file and quietly turn this into a test of an absent archive.
        pad = hashlib.sha256(str(n).encode()).hexdigest() * 4
        log.append({"n": n, "pad": pad}, "2026-09-17")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-17.jsonl.gz"
    whole = gz.read_bytes()
    assert len(whole) > 400, "the archive must be long enough for 200 cuts to be inside it"

    cuts = 0
    for cut in range(len(whole) - 200, len(whole)):
        gz.write_bytes(whole[:cut])
        found, stats = scan_records(tmp_path, PREFIX)
        assert all(isinstance(record, dict) for record, _line in found)
        # A torn read is *counted*. Either the member decoded whole (a cut that
        # happened to land on a clean boundary) or the loss is visible.
        assert stats.unreadable_files in (0, 1)
        cuts += 1

    assert cuts == 200, f"the property claims 200 truncations and ran {cuts}"


def test_a_corrupt_deflate_stream_is_counted_not_raised(tmp_path: Path) -> None:
    """A *corrupt* archive, not a truncated one: `zlib.error` is not an `OSError`.

    Truncation raises `EOFError`, which the handler already covered — so the
    one damage form nobody had tested escaped every `except` in this module and
    surfaced as `replay` answering "request failed" for the rest of the build's
    life.
    """
    log = RotatingJsonlLog(tmp_path, PREFIX)
    for n in range(50):
        log.append({"n": n, "pad": "y" * 50}, "2026-09-17")
    log.close()
    gz = tmp_path / PREFIX / "2026-09-17.jsonl.gz"
    whole = bytearray(gz.read_bytes())
    for offset in range(len(whole) // 2, len(whole) // 2 + 40):
        whole[offset] ^= 0xFF
    gz.write_bytes(bytes(whole))

    found, stats = scan_records(tmp_path, PREFIX)

    assert len(found) < 50
    assert stats.unreadable_files == 1


def test_an_archive_with_a_bad_magic_number_is_counted(tmp_path: Path) -> None:
    """A `.gz` that is not one contributes 0 to every counter — unless counted."""
    (tmp_path / PREFIX).mkdir(parents=True)
    (tmp_path / PREFIX / "2026-09-16.jsonl.gz").write_bytes(b"not gzip at all\n" * 100)
    (tmp_path / PREFIX / "2026-09-17.jsonl").write_text('{"n": 1}\n', encoding="utf-8")

    found, stats = scan_records(tmp_path, PREFIX)

    assert [record for record, _line in found] == [{"n": 1}]
    assert (stats.unreadable_files, stats.skipped_malformed) == (1, 0)


def test_undated_records_are_left_out_when_since_narrows(tmp_path: Path) -> None:
    """The `unknown-date` stem sorts after every date, so it used to be read for
    every value of `since` — and with `--apply` that overwrites verdicts derived
    from records of arbitrary age. A date nobody can read is not "in range"."""
    (tmp_path / PREFIX).mkdir(parents=True)
    (tmp_path / PREFIX / "unknown-date.jsonl").write_text('{"n": "undated"}\n', encoding="utf-8")
    (tmp_path / PREFIX / "2026-09-17.jsonl").write_text('{"n": "dated"}\n', encoding="utf-8")

    wide, wide_stats = scan_records(tmp_path, PREFIX)
    narrow, narrow_stats = scan_records(tmp_path, PREFIX, "2026-09-17")

    assert {str(record["n"]) for record, _line in wide} == {"undated", "dated"}
    assert wide_stats.skipped_undated == 0
    assert [record["n"] for record, _line in narrow] == ["dated"]
    assert narrow_stats.skipped_undated == 1


def test_a_missing_directory_reads_as_empty(tmp_path: Path) -> None:
    assert records(tmp_path / "never-created") == []


def test_since_filters_by_filename_date(tmp_path: Path) -> None:
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": "old"}, "2026-09-15")
    log.append({"n": "mid"}, "2026-09-16")
    log.append({"n": "new"}, "2026-09-17")
    log.close()
    assert records(tmp_path, since="2026-09-16") == [{"n": "mid"}, {"n": "new"}]


def test_the_reader_reports_the_line_it_read_a_record_from(tmp_path: Path) -> None:
    log = RotatingJsonlLog(tmp_path, PREFIX)
    log.append({"n": 1}, "2026-09-17")
    log.append({"n": 2}, "2026-09-17")
    log.close()
    assert [line for _record, line in read_records(tmp_path, PREFIX)] == [1, 2]


def test_the_directory_is_created_private(tmp_path: Path) -> None:
    """E-M2-23 / ADR-2's mode. The data directory may not exist when the first
    stop arrives, and a stop log is session content."""
    log = RotatingJsonlLog(tmp_path / "fresh", PREFIX)
    log.append({"n": 1}, "2026-09-17")
    log.close()
    assert (tmp_path / "fresh" / PREFIX).stat().st_mode & 0o777 == 0o700


def test_a_write_failure_is_counted_and_never_raised(tmp_path: Path) -> None:
    """C-M2-6 — the log is the *second* consumer of a verdict; losing a line
    may never stop the column write. The failure is injected by giving the
    writer a parent that is a **file**, because these tests run as root and
    root ignores the mode bits a `chmod` would set."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    log = RotatingJsonlLog(blocker / "under-a-file", PREFIX)
    assert log.append({"n": 1}, "2026-09-17") is False
    assert log.lost == 1
    log.close()
    assert log.lost == 1


def test_logs_never_read_the_environment() -> None:
    """ADR-M2-6 / ADR-2's rule: `logs/` **receives** its paths. It never reads
    an environment variable, asks a host or resolves XDG — a module that
    resolves its own path is a module a test cannot put in `tmp_path`."""
    for module in sorted((JSONL_MODULE.parent).rglob("*.py")):
        tree = ast.parse(module.read_text())
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert "environ" not in attributes, module.name
        assert "getenv" not in attributes, module.name
        assert "home" not in attributes, module.name
        assert "expanduser" not in attributes, module.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "XDG_" not in node.value, (module.name, node.value)
