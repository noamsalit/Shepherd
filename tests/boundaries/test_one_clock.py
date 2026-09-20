"""P22: `core/clock.py` is the only module that reads a wall clock.

**Why this rule exists, and why a list was not enough.** M1's verification failed
on a format owned by a reader and written by nobody: `signals/ordering.parse_stamp`
accepted `"%Y-%m-%dT%H:%M:%SZ"` while five production writers spelled the same
instant five other ways. The parse failed, the failure was swallowed into a
`None`, `None` collapsed into `is_live() == False`, and §16's whole `running`
bucket became unreachable — with 444 tests green, because every fixture
hand-wrote the parser's own format.

The remediation collapsed every writer into `core/clock.py` and added
`tests/signals/test_liveness_stamp_contract.py`, which drives liveness from the
real writers. That contract is good and it stays: it catches **drift in a writer
it knows about**.

It cannot catch a writer it does not know about, because it enumerates them by
hand. The M1 closure check proved exactly that — a new module dropped into
`signals/` stamping with `datetime.now(UTC).isoformat()`, defect 1's own
spelling, passed the full suite *and* `mypy --strict`, both exit 0. A
hand-maintained list guards the past; a rule guards the future, and M2 is adding
writers now.

So: the clock is a boundary, enforced the way this repo enforces boundaries —
AST over the shipped tree, a property rather than a spelling, with a paired
fixture proving the check bites.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import MISSING_MODULE, fixture, in_package, iter_modules
from _parse import parsed

#: The one FILE allowed to read a wall clock or spell an instant. A file, not a
#: package: `package_of` resolves `core/clock.py` to `shepherd.core`, which would
#: have exempted `core/ids.py` too.
CLOCK_MODULE = "clock.py"

#: Reading "now" as a `datetime` — the thing that becomes a stored stamp.
CLOCK_READERS: frozenset[str] = frozenset({"now", "utcnow", "today"})

#: Spelling an instant as text, or reading text back. A second speller is a
#: second format, and a format owned by one side of a seam is the whole defect.
STAMP_FORMATTERS: frozenset[str] = frozenset(
    {"isoformat", "strftime", "strptime", "fromisoformat"}
)

#: Deliberately NOT in the rule, each for a stated reason — a boundary that
#: fires on correct code gets an exemption bolted onto it, and ADR-1 calls that
#: how boundaries die:
#:
#: * `time.monotonic()` is not a wall clock. It cannot produce a stamp, and it
#:   is the *correct* primitive for the deadlines in `daemons/controld.py`.
#: * `time.time()` yields a float, not a spelling. `core/ids.py` uses it for a
#:   ULID's time component, whose determinism is guarded by its own injected
#:   lane and by `tests/test_core_ids.py`.
#: * `.timestamp()` reads an instant someone else already parsed, to compare
#:   recency (`signals/discovery_loop.py`). It spells nothing.


def clock_violations(path: Path, package: str) -> list[str]:
    """Wall-clock reads and stamp formatting outside `core/clock.py`.

    The file is read **before** the package exemption is consulted (B1): a
    detector that returns early on its exempt package never opens the file, so
    its own negative self-check passes for a path that does not exist. Five such
    tautologies shipped in M1 before that was caught.
    """
    tree = parsed(path)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr in CLOCK_READERS and _names_a_time_module(func.value):
            found.append(f"{package}: reads a wall clock via .{func.attr}()")
        elif func.attr in STAMP_FORMATTERS:
            found.append(f"{package}: formats or parses a stamp via .{func.attr}()")
    return [] if path.name == CLOCK_MODULE and in_package(package, "shepherd.core") else found


def _names_a_time_module(node: ast.expr) -> bool:
    """`datetime.now`, `datetime.datetime.now`, `dt.now`, `time.time`, …

    Matched on the attribute chain rather than on one spelling, because an alias
    is how the platform rule was defeated: `import sys as s; s.platform` slipped
    a scan pinned to the literal `sys.platform`.
    """
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in {"datetime", "dt", "time", "clock"}


def test_only_core_clock_reads_the_wall_clock() -> None:
    """No module but `core/clock.py` may read a clock or spell a stamp."""
    offenders = [
        violation
        for module in iter_modules()
        for violation in clock_violations(module.path, module.package)
    ]
    assert offenders == [], (
        "A second clock reader is a second format, and a format owned by one side "
        "of a seam is what made every `running` session unreachable in M1. "
        "Call shepherd.core.clock.utc_now()/stamp()/parse_stamp() instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_rule_bites_on_a_rogue_writer() -> None:
    """The exact spelling that passed the whole suite before this rule existed."""
    rogue = fixture("signals_reads_the_wall_clock.py")
    assert clock_violations(rogue, "shepherd.signals") != []


def test_core_clock_itself_is_allowed() -> None:
    """The exemption is real, and it is exactly one file wide."""
    real_clock = Path("src/shepherd/core/clock.py").resolve()
    assert clock_violations(real_clock, "shepherd.core") == []


def test_the_exemption_is_a_file_not_a_package() -> None:
    """`core/ids.py` sits in the exempt package and is NOT exempt.

    `package_of` resolves every file under `core/` to `shepherd.core`, so a
    package-wide exemption would have covered `ids.py`, `states.py` and the rest
    of L1 — a hole wide enough to put the next second-format through.
    """
    rogue = fixture("signals_reads_the_wall_clock.py")
    assert clock_violations(rogue, "shepherd.core") != []


def test_the_scan_reads_the_file_before_consulting_the_package() -> None:
    """B1: a missing file raises, even for the exempt package.

    Without this, `clock_violations(MISSING, CLOCK_PACKAGE)` would return `[]`
    and the negative self-check above would assert nothing at all.
    """
    with pytest.raises(FileNotFoundError):
        clock_violations(MISSING_MODULE, "shepherd.core")
