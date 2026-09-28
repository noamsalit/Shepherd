"""What a declared retry may name, and when it joins the lineage (§3 D70).

Split out of `spawn.py` for the reason `admission.py` was: the sequence module
is capped at 300 lines, and "is this a retry of something retryable" is a job of
its own, answered **before** admission and before any row is written.

**Only a stopped attempt in the same project is retried.** A live session is
still its own attempt, and a lineage that crossed projects would be capped by
one project's history and woken into another's.

**RD-2 at a full lineage is the cap, said once.** A second retry of X names the
retry that exists. For a human, "retry that one instead" is advice that can
succeed, since D31 caps only the master. For the master, X and its retry already
fill D31's two attempts (whoever started them: the cap counts the lineage), so
that advice would only reach `retry_cap_reached`: the refusal names the human as
the next step instead, carries the cap, and bumps the cap's anomaly, so the
fleet sees it as the cap it is.

**Only a started attempt joins the lineage.** `link` runs after `runner.start`
succeeded. A start the runner refused is not an attempt at the work, so it
consumes nothing: the next retry of X is still X's first.
"""

from __future__ import annotations

from collections.abc import Callable

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.states import Origin, SessionState
from shepherd.orchestration.admission import (
    CAP_RETRY,
    MASTER_ORIGIN,
    MAX_MASTER_ATTEMPTS,
    SpawnRefused,
)
from shepherd.orchestration.declared_verdicts import refused_verdict
from shepherd.store.db import Store
from shepherd.store.models import StoreError

__all__ = ["link", "refuse_target"]


def _sibling(store: Store, retry_of: str, existing: str, origin: Origin) -> SpawnRefused:
    """RD-2: `retry_of` already has the retry `existing`."""
    already = f"{retry_of!r} was already retried as {existing!r}"
    depth = store.retry_chain_depth(existing)
    if Origin(origin) is not MASTER_ORIGIN or depth < MAX_MASTER_ATTEMPTS:
        return SpawnRefused(f"{already}; retry that one instead", None)
    store.bump_anomaly(str(AnomalyKind.WAKE_RETRY_CAP_REACHED.value))
    return SpawnRefused(
        f"{already}, and that lineage already holds {depth} attempts; D31 lets the master start "
        f"at most {MAX_MASTER_ATTEMPTS}: read their conclusions, and ask the human to re-run it.",
        CAP_RETRY,
    )


def refuse_target(
    store: Store, retry_of: str, workspace_id: str, origin: Origin
) -> SpawnRefused | None:
    """Why `retry_of` cannot be retried by this spawn, or `None` when it can.
    Writes nothing except RD-2's cap count at a full master lineage."""
    target = store.get_session(retry_of)
    if target is None:
        return SpawnRefused(f"no session {retry_of!r} to retry: start it afresh instead", None)
    if target.state is not SessionState.STOPPED:
        return SpawnRefused(
            f"{retry_of!r} is {target.state.value}, not stopped: only an attempt that has "
            f"ended can be retried",
            None,
        )
    if target.workspace_id != workspace_id:
        return SpawnRefused(
            f"{retry_of!r} ran in another project ({target.workspace_id!r}): a retry starts "
            f"in the project its attempt ran in",
            None,
        )
    existing = store.retried_by(retry_of)
    return None if existing is None else _sibling(store, retry_of, existing, origin)


def link(
    store: Store, session_id: str, retry_of: str, now: Callable[[], str]
) -> SpawnRefused | None:
    """Join the started `session_id` to `retry_of`'s lineage. A link the store
    refuses ends the row `refused` (§3 D73) and is answered, never raised."""
    try:
        store.link_retry(session_id, retry_of)
    except StoreError as refusal:
        why = f"{session_id!r} could not be recorded as a retry of {retry_of!r}: {refusal}"
        try:
            store.end_refused(session_id, refused_verdict(why), now())
        except StoreError:
            pass  # the link's refusal is the answer; a failed ending does not replace it
        return SpawnRefused(why, None)
    return None
