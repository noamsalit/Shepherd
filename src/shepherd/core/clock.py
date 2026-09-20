"""The one stamp format this system writes, and the one reader of it.

Every stamp Shepherd persists — `last_event_at`, `observed_at`, `started_at`,
`ended_at`, `created_at` — is written by `utc_now()` (or `stamp(moment)` when
the moment comes from somewhere else, such as the engine's epoch-millisecond
sidecar). There is one spelling:

    2026-09-17T01:04:18.671Z    UTC, millisecond precision, `Z`.

**Why this module exists.** Before it, three writers spelled the same instant
three ways — `…Z`, `….671Z`, `…+00:00` — and `signals/ordering.parse_stamp`
accepted exactly one of them: the one no writer used. The parse failure was
swallowed into a `None`, `None` collapsed into `is_live() == False`, and §16's
whole `running` bucket became unreachable without a single test going red,
because every fixture hand-wrote the parser's own format. A format is a contract
between a writer and a reader; it belongs in one place that both import.

Millisecond precision rather than seconds because RD8 breaks ties on recency
between the two lanes, and two events inside one second are ordinary. `Z` rather
than `+00:00` because it is what the engine's own sidecars use, so a converted
engine stamp and one of ours are the same string shape.

`parse_stamp` reads ISO-8601 rather than only the canonical spelling: a row
written by an older build, or read back from a database this build did not
create, is still a readable instant. That tolerance is a *reader* property; it
buys nothing for a writer, and there is exactly one writer here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

__all__ = ["DATE_EXAMPLE", "STAMP_EXAMPLE", "parse_date", "parse_stamp", "stamp", "utc_now"]

#: A real stamp, for documentation and for a test that wants a shape to compare.
STAMP_EXAMPLE = "2026-09-17T01:04:18.671Z"

#: The one **date** spelling — a log partition, `--since`, the diff's file name.
DATE_EXAMPLE = "2026-09-17"


def stamp(moment: datetime) -> str:
    """`moment` in the one format. Naive input is read as UTC, never as local."""
    in_utc = moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return in_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{in_utc.microsecond // 1000:03d}Z"


def utc_now() -> str:
    """Now, in the one format. The only clock any writer in this system calls."""
    return stamp(datetime.now(UTC))


def parse_date(text: str) -> tuple[int, int, int] | None:
    """`YYYY-MM-DD` as its three numbers, or `None`. Never raises.

    A date is not a stamp — it is a *partition*: the log's daily file, the
    diff's file name, and the value `--since` narrows by. It belongs here for
    the same reason the stamp does. Before this function, `--since` was
    unvalidated at all four layers that touch it, so `shepherd replay --since
    30d` — the plan's own §8 example — compared `"2026-09-17" < "30d"`, got
    `True`, read zero records, wrote a diff saying so and exited 0.

    Strict, deliberately: `2026-9-17` is a typo and reading it as the 17th
    would be a reader inventing a spelling no writer of ours produces. The
    calendar is checked too — `2026-02-30` is three numbers that are not a day.
    """
    parts = text.split("-")
    if len(parts) != 3 or [len(part) for part in parts] != [4, 2, 2]:
        return None
    if not all(part.isdigit() and part.isascii() for part in parts):
        return None
    year, month, day = (int(part) for part in parts)
    try:
        date(year, month, day)
    except ValueError:
        return None
    return year, month, day


def parse_stamp(text: str) -> datetime | None:
    """An ISO-8601 stamp as an aware UTC datetime, or `None`. Never raises.

    `None` is *unreadable*, a first-class unknown (principle 5) — not "old" and
    not "not live". Every caller must decide what an unknown age means rather
    than inheriting a `False`; `ordering.is_live` says so at its own seam.
    """
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
