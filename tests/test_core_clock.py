"""T1: `core/clock.py` — the one stamp format, and the one **date** reader.

`parse_date` sits beside `parse_stamp` for the reason `parse_stamp` exists at
all: a format owned by one side of a seam is the defect. `--since` is a date,
four layers read it (`cli/`, the tool schema, `replay()`, the SQL), and before
this function not one of them could tell `2026-09-17` from `30d`. The
one-clock boundary rule (`tests/boundaries/test_one_clock.py`) is what keeps
the second speller from appearing somewhere else.
"""

from __future__ import annotations

import pytest

from shepherd.core.clock import DATE_EXAMPLE, parse_date


def test_the_canonical_spelling_reads() -> None:
    assert parse_date("2026-09-17") == (2026, 9, 17)
    assert parse_date(DATE_EXAMPLE) is not None


@pytest.mark.parametrize(
    "text",
    [
        "30d",  # §8's own example — it sorts *above* every date, so it read nothing
        "2026-9-17",  # one missing zero
        "09/17/2026",
        "yesterday",
        "",
        "2026-09-17T01:04:18.671Z",  # a stamp is not a date partition
        "2026-13-01",  # a month that does not exist
        "2026-02-30",  # a day that does not exist
    ],
)
def test_anything_that_is_not_a_date_reads_as_none(text: str) -> None:
    """`None` is the unknown, never a silent "nothing matched" (principle 5)."""
    assert parse_date(text) is None
