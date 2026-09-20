"""D25's rotating JSONL log — the generic writer and reader (T5).

Five rules, each straight from D25:

1. **Daily files**, `<prefix>/<YYYY-MM-DD>.jsonl`, named from a **date the
   caller passes** and never from a clock read. That is what makes the tests
   deterministic and the golden lane byte-identical — and it is why
   `core/clock.py` stays the only module in this system that reads a wall
   clock or spells an instant;
2. **gzip on close.** When the day rolls over, or the writer is closed, the
   finished file becomes `<name>.jsonl.gz` and the plain file is removed
   **after** the gzip is fsynced. In that order, so a crash mid-rotation
   leaves a readable copy rather than none;
3. **a size cap as a second trigger** (`MAX_BYTES`): the file rolls to
   `<date>.<n>.jsonl` and the finished part is gzipped;
4. **90-day retention**, applied **on rotation only** — the writer rotates on
   write, which is when it can, and a sweeper thread would be a second clock —
   and **by filename date, never by mtime**, which lies: a file restored or
   rsynced yesterday is not a file *from* yesterday;
5. **the reader skips malformed lines and counts them**, reads `.jsonl` and
   `.jsonl.gz`, and tolerates a truncated gzip tail the same way (E-M2-22).

**This module receives its paths** (ADR-M2-6, ADR-2's rule for `store/`): it
reads no environment variable, asks no host and resolves no XDG directory. A
module that resolves its own path is a module a test cannot put in `tmp_path`.

**It is written to have three callers and has one.** M4's audit log and M3's
pty ring are the second and third; neither is built here, and nothing in this
file knows what a stop is.

**Nothing it does may raise into a caller.** The log is the *second* consumer
of a verdict, and losing a line may never stop the column write (C-M2-6). A
failed write is counted in `lost` and reported as `False`.
"""

from __future__ import annotations

import gzip
import json
import os
import zlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import IO

from shepherd.core.clock import parse_date

__all__ = [
    "MAX_BYTES",
    "RETENTION_DAYS",
    "ReadStats",
    "RotatingJsonlLog",
    "ScanStats",
    "read_records",
    "scan_records",
]

#: The damage forms a read of a compressed file can take. `zlib.error` is the
#: one that is **not** an `OSError`: a *truncated* deflate stream raises
#: `EOFError` and a *corrupt* one raises `zlib.error`, so a tuple that named
#: only the first let one bad day-file out of ninety escape every handler in
#: this module and surface three layers up as a generic failure.
UNREADABLE = (OSError, EOFError, gzip.BadGzipFile, UnicodeError, zlib.error)

#: D25's second rotation trigger.
MAX_BYTES = 32 * 1024 * 1024

#: D25's retention horizon.
RETENTION_DAYS = 90

#: ADR-2's mode. E-M2-23: the data directory may not exist when the first stop
#: arrives, and a stop log is session content.
DIRECTORY_MODE = 0o700

SUFFIX = ".jsonl"
GZ_SUFFIX = ".jsonl.gz"


@dataclass(frozen=True)
class ScanStats:
    """What one scan had to skip, at line level and at **file** level.

    The file-level numbers exist because a read that is abandoned half way
    through an archive loses every record after the tear, and before they were
    counted it lost them *with every counter at zero* — a report saying "read 6
    records (0 malformed)" that a reader cannot tell from a log which only ever
    held six.
    """

    skipped_malformed: int
    unreadable_files: int
    """Files whose read was abandoned: a torn archive, a corrupt deflate stream,
    a `.gz` whose magic number is wrong. The records after the tear are gone and
    this is the number that says so."""

    skipped_undated: int
    """Files left unread because `since` narrows by date and their partition has
    no readable one. A date nobody can read is not evidence of being in range."""


@dataclass(frozen=True)
class ReadStats:
    """What a read had to skip. Five numbers rather than one, because a torn
    write, a record from a newer build, a file the reader had to abandon, a
    partition `since` cannot place, and a record read whole are five different
    work items, and `doctor` acts on each differently."""

    records: int
    skipped_malformed: int
    skipped_version: int
    unreadable_files: int
    skipped_undated: int


class RotatingJsonlLog:
    """One append-only JSONL log under `directory/prefix/`.

    Not thread-safe by itself: ADR-7 gives the stop path a single writer
    thread, and E-M2-24 (two stops in one millisecond) is answered by that one
    lock rather than by a second one here.
    """

    def __init__(
        self,
        directory: Path,
        prefix: str,
        max_bytes: int = MAX_BYTES,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self._root = directory / prefix
        self._max_bytes = max_bytes
        self._retention_days = retention_days
        self._date: str | None = None
        self._part = 0
        self._handle: IO[str] | None = None
        self._bytes = 0
        #: Lines this writer could not persist. Counted, never raised — and
        #: read by `doctor`, because a log that silently stopped writing is
        #: the failure D25 exists to prevent.
        self.lost = 0

    def append(self, record: Mapping[str, object], date: str) -> bool:
        """Write one record to `date`'s file. `False` means the line was lost."""
        try:
            line = json.dumps(record, separators=(",", ":"), sort_keys=False) + "\n"
        except (TypeError, ValueError):
            self.lost += 1
            return False

        try:
            if date != self._date:
                self._finish()
                self._date = date
                self._part = 0
                self._sweep(date)
            elif self._handle is not None and self._bytes + len(line) > self._max_bytes:
                self._finish()
                self._part += 1
            if self._handle is None:
                self._open()
            handle = self._handle
            if handle is None:  # pragma: no cover - _open either sets it or raises
                self.lost += 1
                return False
            handle.write(line)
            handle.flush()
            self._bytes += len(line)
        except OSError:
            self.lost += 1
            return False
        return True

    def close(self) -> None:
        """Finish the open file: gzip it, fsync, then remove the plain copy."""
        try:
            self._finish()
        except OSError:
            self.lost += 1
        self._date = None

    # ----- the parts that touch the filesystem --------------------------------

    def _path(self, date: str, part: int) -> Path:
        stem = date if part == 0 else f"{date}.{part}"
        return self._root / (stem + SUFFIX)

    def _open(self) -> None:
        if self._date is None:  # pragma: no cover - append always sets it first
            return
        self._root.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        path = self._path(self._date, self._part)
        self._bytes = path.stat().st_size if path.exists() else 0
        self._handle = open(path, "a", encoding="utf-8")

    def _finish(self) -> None:
        """Rule 2's order, and the order is the whole point.

        gzip → fsync → unlink. A crash between the fsync and the unlink leaves
        **both** files, which the reader resolves in favour of the plain one:
        it is the file the rotation never finished with, it is always whole,
        and preferring it is what makes each record appear exactly once.
        """
        if self._handle is None or self._date is None:
            return
        self._handle.close()
        self._handle = None
        self._bytes = 0
        plain = self._path(self._date, self._part)
        if not plain.exists():
            return
        archive = plain.parent / (plain.name + ".gz")
        with open(archive, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                compressed.write(plain.read_bytes())
            raw.flush()
            os.fsync(raw.fileno())
        plain.unlink()

    def _sweep(self, today: str) -> None:
        """Rule 4 — by **filename** date, on rotation only."""
        cutoff = _minus_days(today, self._retention_days)
        if cutoff is None or not self._root.is_dir():
            return
        for path in sorted(self._root.iterdir()):
            stamped = _date_part(path.name)
            if stamped is not None and stamped < cutoff:
                try:
                    path.unlink()
                except OSError:
                    pass


# ----- the reader -------------------------------------------------------------


def read_records(
    directory: Path, prefix: str, since: str | None = None
) -> Iterator[tuple[Mapping[str, object], int]]:
    """Every readable record under `directory/prefix`, in write order.

    The second element is the **1-based line number** the record was read from,
    within its own file — enough for a human chasing one bad line, and the only
    thing a streaming reader can say about where a record came from. (The plan
    left this `int` unnamed; see the blocker file, T5-1.)

    Malformed lines are skipped here and **counted** by `scan_records`, which
    is the same read with its bookkeeping visible.
    """
    for record, line in _iter_lines(directory, prefix, since, _Ledger()):
        if record is not None:
            yield record, line


def scan_records(
    directory: Path, prefix: str, since: str | None = None
) -> tuple[list[tuple[Mapping[str, object], int]], ScanStats]:
    """The same read, materialised, plus everything it had to skip.

    Two views of one parser rather than two parsers: a streaming reader cannot
    return a total, and a caller that must *report* what it skipped — which is
    every caller of a versioned log — needs one.
    """
    found: list[tuple[Mapping[str, object], int]] = []
    ledger = _Ledger()
    skipped = 0
    for record, line in _iter_lines(directory, prefix, since, ledger):
        if record is None:
            skipped += 1
        else:
            found.append((record, line))
    return found, ScanStats(
        skipped_malformed=skipped,
        unreadable_files=ledger.unreadable_files,
        skipped_undated=ledger.skipped_undated,
    )


@dataclass
class _Ledger:
    """The file-level facts one scan accumulates.

    A generator that `return`s on a damaged file cannot report it: the
    abandoned lines never reach the caller, so they are never yielded and never
    counted. Handing the read a ledger is what turns "I could not read the rest
    of this file" from silence into a number.
    """

    unreadable_files: int = 0
    skipped_undated: int = 0


def _iter_lines(
    directory: Path, prefix: str, since: str | None, ledger: _Ledger
) -> Iterator[tuple[Mapping[str, object] | None, int]]:
    """One tuple per **line**: the record, or `None` for a line nobody can read.

    `None` rather than a second channel, so one parse serves both views — and
    so a trailing torn line, which has no record to ride on, is still counted.
    Whole files the read abandons are counted in `ledger`, which is the only
    place they can be: they have no line to ride on either.
    """
    root = directory / prefix
    if not root.is_dir():
        return
    for path in _ordered_files(root, since, ledger):
        for line_number, raw in enumerate(_lines(path, ledger), start=1):
            yield _decode(raw), line_number


def _lines(path: Path, ledger: _Ledger) -> Iterator[str]:
    """Every line of a plain or gzipped file. A damaged one yields what it had,
    stops, and is **counted** — E-M2-22: the machine died while the file was
    compressing, the records before the tear are still true, and the ones after
    it are lost, which is a fact the report has to be able to state."""
    opener = gzip.open if path.name.endswith(GZ_SUFFIX) else open
    try:
        with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
            while True:
                try:
                    line = handle.readline()
                except UNREADABLE:
                    ledger.unreadable_files += 1
                    return
                if not line:
                    return
                yield line
    except UNREADABLE:
        ledger.unreadable_files += 1
        return


def _decode(raw: str) -> Mapping[str, object] | None:
    """One line → one record, or `None`.

    `null`, `3` and `[1, 2]` are all valid JSON and none of them is a record;
    a reader that accepted them would hand its caller a shape it cannot read.
    """
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    decoded: Mapping[str, object] = parsed
    return decoded


def _ordered_files(root: Path, since: str | None, ledger: _Ledger) -> list[Path]:
    """In write order: by date, then by part — **not** by filename.

    `2026-09-17.1.jsonl.gz` sorts before `2026-09-17.jsonl.gz` as a string, and
    a replay that read the second part first would re-classify a session out of
    order. When a date-part has both a plain file and a `.gz` twin, the plain
    one wins: it is the file a crash between the fsync and the unlink left
    behind, it is always whole, and taking one of the two is what makes each
    record appear exactly once.

    A stem that is not a date (`unknown-date`) is read when nothing narrows the
    read and **left out, counted, when `since` does**. It sorts after every date
    as a string, so a plain `key[0] < since` compare included it for every value
    of `since` — and with `replay --apply` that overwrote verdicts derived from
    records of arbitrary age. A date nobody can read is not evidence of being
    inside the window; it is an unknown, and principle 5 says so out loud.
    """
    by_key: dict[tuple[str, int], Path] = {}
    undated: set[tuple[str, int]] = set()
    for path in root.iterdir():
        key = _key(path.name)
        if key is None:
            continue
        if since is not None and parse_date(key[0]) is None:
            # one partition, not one file: a `.gz` and the plain twin a crash
            # left beside it are the same lost partition counted once.
            undated.add(key)
            continue
        if since is not None and key[0] < since:
            continue
        if key not in by_key or not path.name.endswith(GZ_SUFFIX):
            by_key[key] = path
    ledger.skipped_undated += len(undated)
    return [by_key[key] for key in sorted(by_key)]


def _key(name: str) -> tuple[str, int] | None:
    """`2026-09-17.3.jsonl.gz` → `("2026-09-17", 3)`; a foreign name → `None`.

    The stem is **not** required to be a date. A caller with no readable date
    for a record still has to put it somewhere (`logs/stops.py` writes it under
    `unknown-date`), and a file this reader refused to open would be a line
    lost at read time instead of at write time — the same loss, later and
    quieter. Such a stem sorts after every date, because it is not one.
    """
    if name.endswith(GZ_SUFFIX):
        stem = name[: -len(GZ_SUFFIX)]
    elif name.endswith(SUFFIX):
        stem = name[: -len(SUFFIX)]
    else:
        return None
    head, _, tail = stem.partition(".")
    if not head:
        return None
    if not tail:
        return head, 0
    return (head, int(tail)) if tail.isdigit() else None


def _date_part(name: str) -> str | None:
    key = _key(name)
    return None if key is None else key[0]


def _minus_days(text: str, days: int) -> str | None:
    """`days` before `text`, in the same spelling. `None` if unreadable."""
    fields = parse_date(text)
    if fields is None:
        return None
    try:
        moved = date(*fields) - timedelta(days=days)
    except ValueError:
        return None
    return f"{moved.year:04d}-{moved.month:02d}-{moved.day:02d}"
