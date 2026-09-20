"""D21's bucket map and the default `next_actions[]` table (T7).

Two **total** tables over the twenty `StopReason` values, and one derivation
that reads them. Both are computed free in the same pass that sets the bucket,
which is D21's whole argument: *"it stopped"* is a fact nobody can act on, and
*"it stopped and here is the one thing to do"* is the product.

Pure. No clock, no mapping read, no engine word — a reason is a `StopReason`
before it reaches this module, and the table that turns an engine value into
one lives in the adapter (ADR-M2-2).

**Two rows are reconciliations of §8, not §8 verbatim**, and they are named
rather than absorbed (A7, r3):

* **N14.** §8's `incomplete`/`derailed` row reads *"one item per `missing[]`
  entry, truncated to 3 · `Requeue with what's missing`"* — which is four
  items, against D21's hard maximum of three. The cap is the half stated as a
  decision, so the **truncation** yields: two findings, then the requeue.
* **N15.** §8 writes `Re-authenticate <provider>`. **No captured field supplies
  a provider at M2** — `session.provider` is null on every attached session —
  so the text is `Re-authenticate` with no slot. A blank or a guess inside an
  action button is worse than a shorter true sentence (principle 5). When M3
  spawns sessions with a known provider the text takes it.

A third degradation is not a deviation but a gap: `waiting_on` is `None` at M2
(G-M2-7), so `blocked_external` says *what it is waiting on is not recorded*
rather than naming something nobody captured.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from shepherd.core.stops import (
    CONFIDENT_ENOUGH,
    MAX_ACTIONS,
    ActionSource,
    Bucket,
    NextAction,
    NextActionKind,
    StopReason,
)

__all__ = ["BUCKET_OF", "DEFAULT_ACTIONS", "default_actions"]


#: §8's `outcome_class` column, total over `StopReason` (P-M2-3). A `Mapping`
#: rather than a function because totality over an enum is provable by
#: iteration, and a function's `else` branch is not.
BUCKET_OF: Mapping[StopReason, Bucket] = MappingProxyType(
    {
        StopReason.RATE_LIMITED: Bucket.PAUSED,
        StopReason.QUOTA_PAUSED: Bucket.PAUSED,
        StopReason.AUTH_FAILED: Bucket.ERROR,
        StopReason.ACCOUNT_BLOCKED: Bucket.ERROR,
        StopReason.BAD_REQUEST: Bucket.ERROR,
        StopReason.SERVER_ERROR: Bucket.ERROR,
        StopReason.STALLED_PENDING_TOOL: Bucket.ERROR,
        StopReason.CRASHED: Bucket.ERROR,
        StopReason.LOGGED_OUT: Bucket.ERROR,
        StopReason.UNKNOWN: Bucket.ERROR,
        StopReason.TRUNCATED: Bucket.UNFINISHED,
        StopReason.KILLED: Bucket.UNFINISHED,
        StopReason.CONTEXT_EXHAUSTED: Bucket.UNFINISHED,
        StopReason.USER_EXITED: Bucket.UNFINISHED,
        StopReason.CLEARED: Bucket.UNFINISHED,
        StopReason.RESUMED_ELSEWHERE: Bucket.UNFINISHED,
        StopReason.INCOMPLETE: Bucket.UNFINISHED,
        StopReason.DERAILED: Bucket.UNFINISHED,
        StopReason.COMPLETED: Bucket.FINISHED,
        StopReason.BLOCKED_EXTERNAL: Bucket.BLOCKED,
    }
)


def _action(text: str, kind: NextActionKind, target: str | None = None) -> NextAction:
    """One default item. `source` is always `HEURISTIC` — it is the floor of
    §8's ordering guarantee (`declared` > `llm` > `heuristic`), and nothing at
    M2 writes either of the other two."""
    return NextAction(text=text, kind=kind, target=target, source=ActionSource.HEURISTIC)


#: §8's default table, total over the twenty reasons. The rows that depend on
#: a *parameter* — `completed` on its confidence, `incomplete` on `missing[]`,
#: `blocked_external` on `waiting_on` — carry their **fixed** part here and are
#: completed by `default_actions`. `completed` is the one empty row, and
#: P-M2-3 asserts that it is the only one.
DEFAULT_ACTIONS: Mapping[StopReason, tuple[NextAction, ...]] = MappingProxyType(
    {
        StopReason.COMPLETED: (),
        StopReason.INCOMPLETE: (
            _action("Requeue with what's missing", NextActionKind.REQUEUE),
        ),
        StopReason.DERAILED: (
            _action("Requeue with what's missing", NextActionKind.REQUEUE),
        ),
        StopReason.BLOCKED_EXTERNAL: (
            _action(
                "Chase — what it is waiting on is not recorded", NextActionKind.EXTERNAL
            ),
        ),
        StopReason.RATE_LIMITED: (
            _action("Resumes by itself — nothing to do", NextActionKind.NONE),
            _action("Retry now", NextActionKind.RETRY),
        ),
        StopReason.QUOTA_PAUSED: (
            _action("Resumes by itself — nothing to do", NextActionKind.NONE),
            _action("Retry now", NextActionKind.RETRY),
        ),
        StopReason.TRUNCATED: (
            _action("Resume — output hit the token cap", NextActionKind.RESUME),
        ),
        StopReason.CONTEXT_EXHAUSTED: (
            _action("Re-spawn with a compacted brief", NextActionKind.RESPAWN),
        ),
        StopReason.CRASHED: (
            _action("Read the last 50 lines", NextActionKind.INSPECT),
            _action("Re-spawn from the last good commit", NextActionKind.RESPAWN),
        ),
        StopReason.STALLED_PENDING_TOOL: (
            _action(
                "Open logs — a tool call never executed; likely a bug",
                NextActionKind.INSPECT,
            ),
            _action("Escalate", NextActionKind.ESCALATE),
        ),
        StopReason.KILLED: (
            _action("Re-spawn with the remaining brief", NextActionKind.RESPAWN),
        ),
        StopReason.USER_EXITED: (_action("Resume the session", NextActionKind.RESUME),),
        StopReason.CLEARED: (_action("Resume the session", NextActionKind.RESUME),),
        StopReason.RESUMED_ELSEWHERE: (
            _action("Resume the session", NextActionKind.RESUME),
        ),
        # N15: no `<provider>` slot — nothing at M2 captures one.
        StopReason.AUTH_FAILED: (_action("Re-authenticate", NextActionKind.REAUTH),),
        StopReason.LOGGED_OUT: (_action("Re-authenticate", NextActionKind.REAUTH),),
        StopReason.ACCOUNT_BLOCKED: (
            _action("Check billing", NextActionKind.EXTERNAL),
        ),
        StopReason.BAD_REQUEST: (
            _action("Inspect the request — model or args rejected", NextActionKind.INSPECT),
        ),
        StopReason.SERVER_ERROR: (_action("Retry", NextActionKind.RETRY),),
        StopReason.UNKNOWN: (
            _action("Open logs", NextActionKind.INSPECT),
            _action("Run shepherd replay after fixing the rule", NextActionKind.INSPECT),
        ),
    }
)

#: N14's truncation: `MAX_ACTIONS` minus the one `Requeue with what's missing`
#: item §8's own row appends after the findings.
MISSING_ITEMS = MAX_ACTIONS - 1


def default_actions(
    reason: StopReason,
    *,
    confidence: float,
    missing: tuple[str, ...],
    waiting_on: str | None,
) -> tuple[NextAction, ...]:
    """The at-most-three things a human could do about this stop (D21).

    Computed in the same pass that sets the bucket, from values the verdict
    already holds — no lookup, no second read, nothing to wire.
    """
    if reason is StopReason.COMPLETED:
        # DP10 / ADR-M2-5: a clean stop the heuristics were not confident about
        # is `completed` at 0.5, and 0.5 is below the one threshold that stands
        # between a quiet fleet and a noisy one. It gets an action, so the row
        # is never a dead end claiming verification it has not earned.
        if confidence >= CONFIDENT_ENOUGH:
            return ()
        return (_action("Review the diff", NextActionKind.INSPECT),)

    if reason in (StopReason.INCOMPLETE, StopReason.DERAILED):
        findings = tuple(
            _action(f"Requeue: {item}", NextActionKind.REQUEUE)
            for item in missing[:MISSING_ITEMS]
        )
        return (findings + DEFAULT_ACTIONS[reason])[:MAX_ACTIONS]

    if reason is StopReason.BLOCKED_EXTERNAL and waiting_on:
        return (_action(f"Chase {waiting_on}", NextActionKind.EXTERNAL, waiting_on),)

    return DEFAULT_ACTIONS[reason][:MAX_ACTIONS]
