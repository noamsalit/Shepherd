"""P23: `fold.advance` carries **every** field of `FoldDelta`, not the ones someone remembered.

**Why this file exists.** `advance()` listed thirteen of `FoldDelta`'s twenty-two
fields and silently dropped seven — `title`, `title_source`, `auto_compact_at`,
`quota_notice_at`, `pid`, `proc_start`, `observed_at`. Every pure in-memory
replay therefore lost them after the first fold, and `context_exhausted` was
unreachable in any lane with no store (BLOCKER T17-1, found while T17 built the
golden classifier fixtures).

Nothing went red, for two compounding reasons, and both are the shape this repo
keeps finding:

1. **A hand-maintained list beside a dataclass is not checked by anything that
   knows the dataclass.** `store.DELTA_COLUMNS` has the same shape but is
   guarded; the pure lane was not.
2. **The suite reimplemented the function under test.** `test_fold_rules.py`
   defines its own `advanced()` helper that carries every field generically —
   the *correct* behaviour — so the fold-rule tests proved the helper right and
   never touched production's `advance()` at all. A test double that
   reimplements its subject cannot observe its subject being wrong.

So this rule is a **property over the dataclass**, not a list: adding a field to
`FoldDelta` fails here until `advance` carries it, and adding a field of an
unfamiliar *type* fails at `probe_value` rather than being skipped silently.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from dataclasses import replace

import pytest
from shepherd.core.fold_types import CLEARED, EMPTY_SETS, FoldDelta, FoldResult, IdentitySets
from shepherd.core.states import SessionState
from shepherd.signals.fold import SET_FIELDS, advance

from signals.test_fold_rules import snapshot

#: **Derived here, from the dataclass — never imported from `fold`.** The first
#: draft of this file parametrised over `fold.DELTA_FIELDS`, so shrinking that
#: constant shrank the test's own case list and the totality checks passed by
#: vanishing. A test that takes its cases from its subject cannot watch its
#: subject shrink; `test_the_module_constant_is_still_total` below is what
#: compares the two.
ALL_DELTA_FIELDS: frozenset[str] = frozenset(field.name for field in dataclass_fields(FoldDelta))

#: A distinguishable value per field *type*, so a new field is covered the day
#: it is added. An unrecognised type raises rather than returning a default:
#: a probe that silently yields `None` would assert that `None` was carried,
#: which is true of every broken implementation.
PROBES: dict[str, object] = {
    "str | None": "probe-value",
    "int | None": 4041880,
    "SessionState | None": SessionState.STOPPED,
    "TitleSource | None": "user",
    "tuple[str, ...] | None": ("01REPO-probe",),
    "frozenset[str] | None": frozenset({"probe-id"}),
}


def probe_value(annotation: str) -> object:
    """A value unlike anything in `snapshot()`'s baseline, chosen by type."""
    if annotation not in PROBES:
        raise AssertionError(
            f"`FoldDelta` has a field annotated {annotation!r} and this test does not know "
            "how to probe it. Add a probe value — do not widen the test to skip it, because "
            "a skipped field is exactly how seven of them went missing from `advance`."
        )
    return PROBES[annotation]


def result_with(**delta_fields: object) -> FoldResult:
    """A `FoldResult` carrying only the named delta fields.

    `**object` rather than `**Any`: the repo forbids an explicit `Any`
    (`disallow_any_explicit`), and a test helper is not the place to make the
    first exception.
    """
    delta = FoldDelta()
    for name, value in delta_fields.items():
        delta = replace(delta, **{name: value})
    return FoldResult(delta=delta, events=(), anomalies=(), sets=EMPTY_SETS)


def test_the_module_constant_is_still_total() -> None:
    """`fold.DELTA_FIELDS` equals the dataclass, compared from outside it.

    The parametrised tests above derive their cases independently, so this is
    the assertion that actually notices the constant losing a member — the
    failure mode the first draft of this file could not see.
    """
    from shepherd.signals.fold import DELTA_FIELDS

    assert DELTA_FIELDS == ALL_DELTA_FIELDS, (
        "`fold.DELTA_FIELDS` no longer equals `FoldDelta`'s fields: "
        f"missing {sorted(ALL_DELTA_FIELDS - DELTA_FIELDS)}, "
        f"extra {sorted(DELTA_FIELDS - ALL_DELTA_FIELDS)}"
    )


def test_every_delta_field_is_also_a_snapshot_field() -> None:
    """`advance` can only carry a field the snapshot has a place for."""
    snapshot_fields = {field.name for field in dataclass_fields(snapshot())}
    missing = ALL_DELTA_FIELDS - snapshot_fields
    assert missing == set(), (
        f"`FoldDelta` carries {sorted(missing)}, which `SessionSnapshot` cannot hold. "
        "One of the two is wrong; `advance` cannot be the place that decides."
    )


@pytest.mark.parametrize(
    "field_name",
    sorted(ALL_DELTA_FIELDS - SET_FIELDS),
)
def test_advance_carries_every_delta_field(field_name: str) -> None:
    """One field set on the delta, and only that field, arrives on the snapshot.

    Parametrised over the dataclass rather than over a list, so the failure
    names the field that was dropped.
    """
    annotation = next(
        field.type for field in dataclass_fields(FoldDelta) if field.name == field_name
    )
    value = probe_value(str(annotation))
    prior = snapshot()
    assert getattr(prior, field_name) != value, (
        f"the probe for {field_name} equals the baseline, so this test would pass "
        "against an `advance` that carried nothing at all"
    )

    carried = getattr(advance(prior, result_with(**{field_name: value})), field_name)

    assert carried == value, (
        f"`advance` dropped {field_name!r}: the delta set it to {value!r} and the "
        f"snapshot still reads {carried!r}. A field `FoldDelta` carries and `advance` "
        "does not is a field every store-less replay loses after the first fold."
    )


@pytest.mark.parametrize("field_name", sorted(SET_FIELDS))
def test_the_identity_sets_come_from_result_sets_not_the_delta(field_name: str) -> None:
    """The three set fields have a second source, and `advance` reads that one.

    They are on the delta so they survive a restart through the store; the pure
    lane already holds the authoritative value in `result.sets`. This pins which
    of the two `advance` trusts, so the split cannot quietly invert.
    """
    from_sets = frozenset({"from-result-sets"})
    from_delta = frozenset({"from-the-delta"})
    result = FoldResult(
        delta=FoldDelta(**{field_name: from_delta}),
        events=(),
        anomalies=(),
        sets=replace(IdentitySets(frozenset(), frozenset(), frozenset()), **{field_name: from_sets}),
    )
    assert getattr(advance(snapshot(), result), field_name) == from_sets


def test_an_untouched_field_keeps_the_prior_value() -> None:
    """`None` means *untouched*, never *cleared* — `FoldDelta`'s own first line."""
    prior = snapshot(brief="the prior brief", model="claude-opus-5", pid=4041880)
    carried = advance(prior, result_with(state=SessionState.STOPPED))
    assert (carried.brief, carried.model, carried.pid) == ("the prior brief", "claude-opus-5", 4041880)


def test_a_cleared_reason_becomes_none_and_a_cleared_stamp_does_not() -> None:
    """The one asymmetry, pinned so the generic carry cannot flatten it.

    An empty *reason* renders as a stale reason, so `CLEARED` becomes `None`.
    The stamps keep `CLEARED_STAMP` verbatim: `SessionSnapshot` documents that
    `""` and `None` both mean "no mark" there, and every reader tests them for
    truth rather than for `is None`.
    """
    prior = snapshot(needs_you_reason="permission", auto_compact_at="2026-09-17T01:04:18.671Z")
    carried = advance(prior, result_with(needs_you_reason=CLEARED, auto_compact_at=CLEARED))
    assert carried.needs_you_reason is None
    assert carried.auto_compact_at == CLEARED and not carried.auto_compact_at


def test_the_probe_table_refuses_an_unknown_annotation() -> None:
    """The negative control: `probe_value` raises rather than returning a default.

    Without this, a future field of an unfamiliar type would be probed with
    `None`, and asserting `None` was carried is true of every broken
    implementation — the tautology this repo has now shipped five times.
    """
    with pytest.raises(AssertionError, match="does not know how to probe it"):
        probe_value("SomeFutureType | None")
