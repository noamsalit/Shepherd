"""The stop lane (T11) — assemble, classify, write, log, publish.

One impure function with three injected collaborators, called **by** M1's
`HookLane` rather than contained in it (ADR-M2-7). It constructs nothing, opens
nothing and resolves no path: the store, the log and the publisher all arrive
as parameters, which is what lets a test build the whole lane out of a
`tmp_path` and a list with no process at all.

**The order of the five steps is the contract:**

1. `build_stop_evidence(...)` — the transcript is read **exactly once**, here
   (ADR-M2-1). Everything a verdict could ever need is frozen into one record,
   so `replay` still works months later on a machine whose engine project
   directory has been cleared.
2. `classify(evidence)` — pure.
3. `store.apply_stop_verdict(...)` — the eight columns, one verb, one
   transaction (D33).
4. `stop_log.append(evidence, verdict)` — **after** the columns, so a log
   failure never costs a verdict (C-M2-6, E-M2-23). The log counts its own
   losses in `RotatingJsonlLog.lost` and returns `False`; nothing here raises.
5. `publish(...)` — so the page repaints with no polling (§12).

**Two events per stop, deliberately (A3, r3).** The fold already emits
`session_stopped` from three rules, and that one fires *before* the verdict
exists — it is what turns the row grey immediately. This one fires after the
verdict is written and carries the bucket and the first action. They are two
different facts arriving at two different times, which is why this one has its
own name a subscriber can tell apart.

**The three arguments `build_stop_evidence` refuses to default** are supplied
here, and this is the call site those `mypy --strict` errors were waiting for
(BLOCKER T6-1, T8-3):

* the session-ending reason comes off the signal's **neutral** `end_reason`
  key — the engine's own word, projected by the adapter and read back by the
  adapter's own stop map. Nothing in `signals/` interprets it;
* the two fold marks come off the prior snapshot, where T10's two columns put
  them so they survive D24 discarding the events that proved them;
* the promise predicate is this package's vocabulary, injected downwards. The
  adapter owns the *ordering* fact ("did a tool call follow?"); what counts as
  a promise is a rule, and a rule may not live in an adapter (ADR-M2-2, D9).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.fold_types import SessionSnapshot
from shepherd.core.signals import Signal, SignalKind
from shepherd.core.stops import Verdict
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.evidence import build_stop_evidence
from shepherd.logs.stops import StopLog
from shepherd.signals.heuristics import is_promise
from shepherd.signals.verdict import classify
from shepherd.store.db import Store

__all__ = ["CLASSIFIED_EVENT", "STOP_KINDS", "handle_stop"]

Publisher = Callable[[StreamEvent], int]

#: The kinds that trigger a classification. Three rather than one because a
#: turn ending, a session ending and a failed stop are three distinct column
#: effects (ADR-6) and all three end the work a verdict is about.
STOP_KINDS: frozenset[SignalKind] = frozenset(
    {SignalKind.TURN_STOPPED, SignalKind.SESSION_STOPPED, SignalKind.STOP_FAILED}
)

#: Not a second `session_stopped`: the fold's event says *the row went grey*,
#: this one says *here is what it turned out to be*. Revision 2 gave them one
#: name and asserted "exactly one", which was wrong on both counts (A3, r3).
CLASSIFIED_EVENT = "session.classified"


def handle_stop(
    *,
    signal: Signal,
    prior: SessionSnapshot,
    projects_root: Path,
    received_at: str,
    store: Store,
    stop_log: StopLog,
    publish: Publisher,
    process_exit_observed: bool = False,
    exit_code: int | None = None,
) -> Verdict | None:
    """One stop -> one persisted, logged, published verdict. `None` if skipped.

    A second *stop* re-classifies and overwrites (E-M2-5: S18 has two in one
    session), and both records are in the log so `replay` sees the history. An
    observed process **exit** for a session that already has a verdict is
    ignored (E-M2-30): the verdict that saw a transcript beats one that saw a
    dead pid.
    """
    if process_exit_observed and _already_classified(store, prior.session_id):
        return None

    evidence, anomalies = build_stop_evidence(
        signal=signal,
        prior=prior,
        projects_root=projects_root,
        received_at=received_at,
        end_reason=_end_reason(signal),
        auto_compact_pending=bool(prior.auto_compact_at),
        quota_notice=bool(prior.quota_notice_at),
        promise=is_promise,
        process_exit_observed=process_exit_observed,
        exit_code=exit_code,
    )
    verdict = classify(evidence)

    store.apply_stop_verdict(prior.session_id, verdict, received_at, exit_code)
    # The log is the second consumer, and its failure is already counted in
    # `RotatingJsonlLog.lost` where `doctor` reads it. Raising here would cost
    # the verdict the columns already hold.
    stop_log.append(evidence, verdict)
    for anomaly in anomalies:
        store.bump_anomaly(anomaly.kind.value)

    publish(
        StreamEvent(
            kind=CLASSIFIED_EVENT,
            session_id=prior.session_id,
            payload=_payload(verdict),
            occurred_at=received_at,
        )
    )
    return verdict


def _already_classified(store: Store, session_id: str) -> bool:
    session = store.get_session(session_id)
    return session is not None and session.stop_reason is not None


def _end_reason(signal: Signal) -> str | None:
    """The neutral projection of *how* the session ended.

    ONE literal key, read once, spelled inline: a computed key is a key no
    test can check, and the boundary scan fails closed on one (K12) — even
    when the "computation" is a module constant. The value is still the
    engine's own word, which is why the table that interprets it lives in the
    adapter and never here.
    """
    value = signal.fields.get("end_reason")
    return value if isinstance(value, str) and value else None


def _payload(verdict: Verdict) -> dict[str, object]:
    """What a subscriber needs to repaint the row without asking again: the
    bucket it belongs in, the reason, and the first thing to do about it."""
    payload: dict[str, object] = {
        "bucket": verdict.bucket.value,
        "stop_reason": verdict.stop_reason.value,
        "confidence": verdict.confidence,
    }
    if verdict.next_actions:
        payload["next_action"] = verdict.next_actions[0].text
    return payload
