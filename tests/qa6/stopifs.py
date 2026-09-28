"""The build order's lanes and stop-ifs (test-plan §3), as data the runner applies.

Every wave's rows are here — including waves 4-9, which STAGE B builds — so a
later builder adds test modules and never edits this file. A stop-if never
turns a scenario into FAIL: it writes `BLOCKED` with the stop-if as the reason
(§3: "a skipped scenario is recorded BLOCKED with the stop-if that skipped it").

Lanes are directories under `tests/qa6/`; the runner runs one pytest process
per (wave, lane) over `tests/qa6/<lane>/test_wave<N>_*.py`, in the order below.
`inproc_long` is launched in the background at its wave's start and joined
before wave 9 (M17's 630 s, env-plan §4 step 10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from .catalog import SCENARIOS, wave_ids

WAVE_LANES: Final[dict[int, tuple[str, ...]]] = {
    1: ("sub", "unit", "live"),
    2: ("unit", "cli", "sub"),
    3: ("sub",),
    4: ("sub",),
    5: ("inproc_long", "inproc", "unit"),
    6: ("sub",),
    7: ("sub", "inproc"),
    8: ("live",),
    9: ("host",),
}
BACKGROUND_LANES: Final[frozenset[str]] = frozenset({"inproc_long"})

#: test-plan §3 "SHIM-DEPENDENTS" (r3): the one list both the wave-1 and the
#: wave-4 stop-if cite. P7(a), U19(b-d) are clause-level in the plan; at
#: scenario granularity the whole scenario is blocked.
SHIM_DEPENDENTS: Final[tuple[str, ...]] = (
    "O1", *(f"O{i}" for i in range(3, 13)), "T1", "T2", "T3", "T4", "P7", "P8",
    "U10", "U11", "U14", "U19", *(f"M{i}" for i in range(3, 15)), "M16", "M17", "M18", "M19",
    "P10", *(f"U{i}" for i in range(27, 33)), "U46",
)

Records = Mapping[str, Mapping[str, object]]


def verdict(records: Records, sid: str) -> str | None:
    record = records.get(sid)
    value = record.get("verdict") if record is not None else None
    return str(value) if value is not None else None


def failed_clauses(records: Records, sid: str, prefix: str = "") -> list[str]:
    record = records.get(sid)
    clauses = record.get("clauses") if record is not None else None
    if not isinstance(clauses, list):
        return []
    return [
        str(clause.get("name")) for clause in clauses
        if isinstance(clause, dict) and clause.get("result") == "fail"
        and str(clause.get("name", "")).startswith(prefix)
    ]


def later_waves(after: int, upto: int = 9) -> list[str]:
    return [sid for wave in range(after + 1, upto + 1) for sid in wave_ids(wave)]


def waves(*numbers: int) -> list[str]:
    return [sid for wave in numbers for sid in wave_ids(wave)]


def ids(prefix: str, low: int, high: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(low, high + 1)]


@dataclass(frozen=True)
class StopIf:
    after_wave: int
    description: str
    fires: Callable[[Records], bool]
    blocks: Callable[[Records], Sequence[str]]
    stops_run: bool = False


def _not_pass(sid: str) -> Callable[[Records], bool]:
    return lambda records: verdict(records, sid) != "PASS"


def _a1_or_e1_framing(records: Records) -> bool:
    route_failures = failed_clauses(records, "A1", "route.")
    framing_failures = failed_clauses(records, "E1", "framing.")
    return len(route_failures) >= 3 or bool(framing_failures) or verdict(records, "A1") is None or verdict(records, "E1") is None


def _live_unavailable(records: Records) -> bool:
    record = records.get("S0")
    if record is None:
        return True
    evidence = record.get("evidence")
    return not (isinstance(evidence, list) and any(
        isinstance(line, str) and (line.startswith("LIVE_AUTH_MODE=sandbox_ok") or line.startswith("LIVE_AUTH_MODE=needs_real_home"))
        for line in evidence
    ))


def _settings_changed_in_s0(records: Records) -> bool:
    return bool(failed_clauses(records, "S0", "files.settings_sha"))


STOP_IFS: Final[tuple[StopIf, ...]] = (
    StopIf(1, "W1 or W2 did not PASS: every later verdict would be an environment artifact",
           lambda r: verdict(r, "W1") != "PASS" or verdict(r, "W2") != "PASS",
           lambda r: later_waves(1, 8), stops_run=True),
    StopIf(1, "a settings-sha change during S0 stops the run (U2)",
           _settings_changed_in_s0, lambda r: later_waves(1, 8), stops_run=True),
    StopIf(1, "W3 did not PASS: the UI is uninterpretable (waves 6-7 skipped)",
           _not_pass("W3"), lambda r: waves(6, 7)),
    StopIf(1, "W5(a): the fake engine's pane did not classify PROMPT_READY (SHIM-DEPENDENTS)",
           _not_pass("W5"), lambda r: SHIM_DEPENDENTS),
    StopIf(1, "S0 bound LIVE_AUTH_MODE=unavailable (or no S0 record): wave 8 BLOCKED",
           _live_unavailable, lambda r: waves(8)),
    StopIf(2, "A1 failed on >= 3 session-free routes, or E1's framing clauses failed: waves 3-7 stopped",
           _a1_or_e1_framing, lambda r: waves(3, 4, 5, 6, 7)),
    StopIf(3, "D1 did not PASS (no session registers): U7-U13, U41-U45 skipped",
           _not_pass("D1"), lambda r: [*ids("U", 7, 13), *ids("U", 41, 45)]),
    StopIf(3, "P1 did not PASS: U15-U21 skipped", _not_pass("P1"), lambda r: ids("U", 15, 21)),
    StopIf(4, "O1 did not PASS: every other SHIM-DEPENDENT BLOCKED",
           _not_pass("O1"), lambda r: [sid for sid in SHIM_DEPENDENTS if sid != "O1"]),
    StopIf(5, "M1 did not PASS (no streamed events): U25-U32, U46 skipped",
           _not_pass("M1"), lambda r: [*ids("U", 25, 32), "U46"]),
    StopIf(5, "M3 did not raise a card: U27-U30, U46 skipped",
           _not_pass("M3"), lambda r: [*ids("U", 27, 30), "U46"]),
    StopIf(6, "U1 did not PASS: nav is the premise of every UI scenario (waves 6-7 stopped)",
           _not_pass("U1"), lambda r: [sid for sid in waves(6, 7) if sid != "U1"]),
)

#: Clause-name conventions the stop-ifs above read (so STAGE B names them so):
#: A1 per-route clauses start `route.`; E1's framing clauses start `framing.`;
#: S0's sha clauses start `files.settings_sha`; S0 records `LIVE_AUTH_MODE=<v>`
#: as its first evidence line; O-/Z2 argv violations are clauses `tmux.argv`.
CLAUSE_CONVENTIONS: Final[str] = "route., framing., files.settings_sha, LIVE_AUTH_MODE=, tmux.argv"

ALL_IDS: Final[tuple[str, ...]] = tuple(scenario.id for scenario in SCENARIOS)
