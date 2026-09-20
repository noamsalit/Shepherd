"""P24 (D46): nothing reads `stop_reason` out of an engine payload or a `Signal`.

**Why this rule replaced a three-file list.** M2's milestone acceptance clause 2
claims D46 is proven "over `src/shepherd/`". It was not: enforcement was a
substring scan of three hand-named files (`rules.py`, `fold.py`, `ordering.py`)
plus one in `stop_map.py` — **4 of 79 source files**. The M2 verification pass
proved the hole by appending `PLANTED = "stop_reason"` to `signals/stop_lane.py`,
a signals module of exactly the kind the clause governs, and watching all 864
tests pass. A check whose stated scope exceeds its real scope is the M1 tautology
shape again: no amount of green tells you about it.

**Why the tree-wide version could not be a substring scan.** `stop_reason` is a
legitimate name in thirteen places. It is our own `session` column
(`store/stops.py`, `store/rows.py`), our own stop-record key (`logs/stops.py`),
our own rendered payload key (`signals/stop_lane.py`), and — the subtle one —
`entry.message.get("stop_reason")` in `engines/claude_code/transcript_tail.py`,
which reads the **transcript's** `message.stop_reason` (`end_turn`, `tool_use`,
`stop_sequence`; data-schemas §Transcript entry). That field is real, captured,
and load-bearing.

D46 is about a different field with the same name: **`Stop.stop_reason`, on the
hook payload**, which does not exist — absent from all 78 captured `Stop` events
and from the CLI's own zod schema. A rule keyed on it would never fire, and
would never say so.

So the property is not *the word*, it is *the object being read*: a lookup of
`"stop_reason"` against a **payload**, a **fields** mapping, or a **signal**. Our
own rows, records and transcript entries are read through differently-named
receivers and stay legal, which is why this rule needs no exemption list — and
ADR-1 calls an exemption how boundaries die.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import MISSING_MODULE, fixture, iter_modules
from _parse import parsed

#: The field D46 forbids. Matched exactly, so a longer SQL string that merely
#: contains the word (`REPLAY_SQL`) is not a hit.
FORBIDDEN_KEY = "stop_reason"

#: An identifier anywhere in the receiver expression marks it as engine-side.
#: `payload` and `fields` are the two neutral mappings a signal carries; `signal`
#: covers `signal.fields[...]` and any attribute path off it. Our own containers
#: are spelled `row`, `record`, `entry.message`, `verdict` — none of them here.
ENGINE_RECEIVERS: frozenset[str] = frozenset({"payload", "fields", "signal"})


def _receiver_names(node: ast.expr) -> set[str]:
    """Every identifier in a receiver expression, however deep the attribute path."""
    return {inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)}


def _is_forbidden_key(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == FORBIDDEN_KEY


def stop_reason_reads(path: Path, package: str) -> list[str]:
    """Lookups of `stop_reason` against a payload, a fields mapping or a signal.

    The file is read **before** anything else is decided (B1): a scan that
    returns early cannot have its own negative self-check trusted.
    """
    tree = parsed(path)
    found: list[str] = []
    for node in ast.walk(tree):
        receiver: ast.expr | None = None
        if isinstance(node, ast.Subscript) and _is_forbidden_key(node.slice):
            receiver = node.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and _is_forbidden_key(node.args[0])
        ):
            receiver = node.func.value
        if receiver is not None and _receiver_names(receiver) & ENGINE_RECEIVERS:
            found.append(f"{package}:{node.lineno}: reads {FORBIDDEN_KEY!r} off an engine payload")
    return found


def test_no_module_reads_stop_reason_off_a_payload() -> None:
    """D46, over the whole tree — the scope clause 2 always claimed."""
    offenders = [
        violation
        for module in iter_modules()
        for violation in stop_reason_reads(module.path, module.package)
    ]
    assert offenders == [], (
        "`Stop.stop_reason` does not exist: it is absent from all 78 captured Stop "
        "events and from the CLI's own schema (D46). A rule keyed on it never fires "
        "and never says so — which is the whole reason principle 5 counts unknowns:\n  "
        + "\n  ".join(offenders)
    )


def test_the_rule_bites_on_the_shape_the_planted_violation_had() -> None:
    """The negative control, in all three spellings a reader would reach for."""
    rogue = fixture("engine_reads_stop_reason_off_a_payload.py")
    assert len(stop_reason_reads(rogue, "shepherd.engines")) == 3


def test_our_own_column_and_the_transcript_field_stay_legal() -> None:
    """The rule must not fire on the thirteen real uses of the same word.

    Named individually rather than counted, because a scan that fired on these
    would be "fixed" with an exemption, and the exemption is what would then let
    the real defect back in.
    """
    legal = (
        "src/shepherd/store/stops.py",           # our `session` column
        "src/shepherd/store/rows.py",            # decoding that column
        "src/shepherd/logs/stops.py",            # our stop-record key
        "src/shepherd/signals/stop_lane.py",     # our rendered payload key
        "src/shepherd/signals/replay.py",        # our column, again
        "src/shepherd/toolsurface/tools_m1.py",  # our column on the way out
        # The subtle one: the transcript's own `message.stop_reason`, which is a
        # real captured field and a *different* field from `Stop.stop_reason`.
        "src/shepherd/engines/claude_code/transcript_tail.py",
    )
    for relative in legal:
        path = Path(relative).resolve()
        assert stop_reason_reads(path, "shepherd") == [], relative


def test_the_scan_reads_the_file_before_deciding_anything() -> None:
    """B1: a missing file raises rather than returning an empty, passing list."""
    with pytest.raises(FileNotFoundError):
        stop_reason_reads(MISSING_MODULE, "shepherd.signals")
