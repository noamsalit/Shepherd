"""T11 — may this spawn happen, and at what depth? §13's roots, D-5, §11's caps.

A **sibling** of `spawn.py`, not a section of it. Task 11's expected artifact is one
module of ≤ 300 lines and the sequence plus its admission came to 367; this repo has
answered that collision with a split five times (`rows.py`, `stops.py`,
`signals/fields.py`, `reads.py`, `writes.py`) and once more here. The two jobs are
different: this module answers a question and touches nothing, `spawn.py` creates the
row and drives the pane.

Everything here is a **refusal or a value**. No session row is written, no process is
started, and the only runner member touched is `list_owned_panes()` — which serves
twice over, because "can a pane be opened at all" (D-5) and "how many are open"
(§11's total cap) are the same observation.

**One write arrived with M4**, named rather than left to be found: D31's retry cap bumps
`WAKE_RETRY_CAP_REACHED` on the refusal it returns (T10), so *"no row is written"* is now
true of the `session` table alone. The answer to the caller is still a value."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.runner import (
    MAX_CHILDREN_PER_SESSION,
    MAX_SESSION_DEPTH,
    MAX_TOTAL_OWNED_SESSIONS,
    RunnerRefusal,
)
from shepherd.engines.claude_code.spawn import capabilities
from shepherd.core.states import Origin
from shepherd.runner.base import Runner
from shepherd.store.db import Store

__all__ = ["CAP_CHILDREN", "CAP_DEPTH", "CAP_RETRY", "CAP_TOTAL", "MASTER_ORIGIN",
           "MAX_MASTER_ATTEMPTS", "Admitted", "Retry", "SpawnRefused", "admit"]  # fmt: skip

#: §11's three caps and D31's fourth, named. Each refusal carries **its own** name and
#: number: "cap exceeded" tells an agent nothing it can act on, while a depth refusal
#: means start from a shallower parent and a total one means wait for a pane.
CAP_DEPTH = "depth"
CAP_CHILDREN = "children_per_session"
CAP_TOTAL = "total_owned_panes"
CAP_RETRY = "retry_cap_reached"

MAX_MASTER_ATTEMPTS = 2  #: D31, verbatim: *"Capped at 2 master-initiated per lineage"*.
#: The origin the master spawns under, and the one `reads.WAKE_ORIGIN` selects the wake
#: set on — two spellings would let the wake set hand back a session this cap then treats
#: as a human's, so the pair is asserted equal rather than assumed equal.
MASTER_ORIGIN = Origin.ORCHESTRATOR


@dataclass(frozen=True)
class Retry:
    """*Another attempt at `of`, asked for by `initiated_by`.* One parameter, both facts:
    as two defaulted keywords the lineage can be passed without the audience, which has
    no safe default — one value caps a human, the other uncaps the master."""

    of: str
    initiated_by: Origin


@dataclass(frozen=True)
class SpawnRefused:
    """A spawn that did not happen, and why. `cap` names which cap refused it."""

    reason: str
    cap: str | None


@dataclass(frozen=True)
class Admitted:
    """A spawn that may proceed: where it really is, which root let it, how deep.

    `root` is the **innermost** registered root that admitted `cwd` (D22). It is
    carried rather than discarded because a yes/no answer cannot tell "some root
    matched" from "the innermost root matched", and a longest-prefix rule whose
    choice nothing can observe is a rule asserted by reading the source.
    """

    cwd: Path
    depth: int
    root: Path


def _canonical(path: str) -> Path | None:
    """`Path.resolve()` as a **value**: the string that will not resolve is `None`.

    `Path("/tmp/a\\x00b").resolve()` raises `ValueError: embedded null byte`, and
    the string reaches this module from outside — `POST /api/sessions` hands the
    caller's `cwd` to `spawn_session` unaltered, and `upsert_repo` stores a
    `root_path` containing a NUL without complaint. A raise here is flattened by
    `invoke()` into `Failure.FAILED` + `"ValueError"`: a page that cannot tell a
    refusal from a crash, which is the outcome principle 5 forbids and the whole
    reason `SpawnRefused` exists (P-M3-9: every degradation returns a value and
    **none raises**; T23's handoff).

    `OSError` is caught beside it because `realpath` is the one call in this pure
    module that touches the filesystem, and a path this process may not walk is
    an unresolvable path by the same argument. Neither is repaired: a cwd this
    rule cannot canonicalize is a cwd it cannot place inside an allowlist, and
    guessing which directory was meant is the mistake `check_tmux_argv` refuses
    to make one layer down.
    """
    try:
        return Path(path).resolve()
    except (OSError, ValueError):
        return None


def _registered_roots(store: Store, workspace_id: str) -> list[Path] | SpawnRefused:
    """§13's allowlist: the project's **registered repo paths**, and nothing else.

    D22: *"`add_repo` is `local_destructive` because §13 validates every spawn
    against the registered allowlist — adding a repo **widens that
    allowlist**"*. After D57 that is the whole population. The workspace root
    was the other half until migration 004 dropped the column: it was where a
    scanner started, never a statement about where repos are, and reading it
    refused a spawn into any repo not nested under it (blocker T11-1).

    Existence is asked of `get_workspace` rather than inferred from an empty
    list: "there is no such project" and "this project registered nothing" are
    different facts and are fixed differently. Every repo is included —
    nothing in `store/` ever clears `repo.active` (tripwire in `test_verbs`).
    """
    if store.get_workspace(workspace_id) is None:
        return SpawnRefused(
            f"there is no project {workspace_id!r}, so it has no allowlist to evaluate a "
            f"spawn against — a missing project and an empty one are different facts and "
            f"are fixed differently",
            None,
        )
    registered = [repo.root_path for repo in store.list_repos(workspace_id)]
    roots: list[Path] = []
    for stored in registered:
        resolved = _canonical(stored)
        if resolved is None:
            # Named, never dropped. A root this rule cannot evaluate makes the
            # allowlist unevaluable, and silently omitting it would narrow §13's
            # allowlist and then report "no registered repo" — false of the
            # database, and the same silent-shrink failure this module closed in
            # the other direction (T11-1).
            return SpawnRefused(
                f"project {workspace_id!r} has a registered repo path that does not "
                f"canonicalize, so its allowlist cannot be evaluated at all: {stored!r} — fix "
                f"that row before anything can be admitted here",
                None,
            )
        roots.append(resolved)
    return roots


def _canonical_cwd(store: Store, workspace_id: str, cwd: str) -> tuple[Path, Path] | SpawnRefused:
    """§13: canonicalize, then longest-prefix match against the registered roots.

    Both sides are **resolved**, so `../` traversal, a symlink pointing out of a
    root and a sibling whose name merely starts with a root's all refuse — the
    comparison is over path components (`Path.parents`), never over strings. A
    workspace with no registered root and no registered repo is not an allowlist
    of everything.

    Returns the canonical cwd **and** the innermost root that admitted it — or a
    `SpawnRefused`, including for the inputs `resolve()` itself will not accept
    (`_canonical`).
    """
    roots = _registered_roots(store, workspace_id)
    if isinstance(roots, SpawnRefused):
        return roots
    if not roots:
        return SpawnRefused(
            f"project {workspace_id!r} has no registered repo, so no directory is inside "
            f"its allowlist: {cwd!r}",
            None,
        )
    candidate = _canonical(cwd)
    if candidate is None:
        return SpawnRefused(
            f"{cwd!r} does not canonicalize to any directory, so it cannot be placed inside "
            f"project {workspace_id!r}'s allowlist: a cwd carrying a NUL byte or a path this "
            f"process may not walk is refused, never guessed at",
            None,
        )
    matched = [root for root in roots if candidate == root or root in candidate.parents]
    if matched:
        # Innermost wins (D22): the deepest root, by component count, is the one
        # git itself would resolve a nested repo to.
        return candidate, max(matched, key=lambda root: len(root.parts))
    return SpawnRefused(
        f"{cwd!r} canonicalizes to {str(candidate)!r}, outside every registered root of "
        f"project {workspace_id!r} ({sorted(str(root) for root in roots)}): §13 permits no "
        f"path traversal into an unregistered directory",
        None,
    )


def _retry_cap(store: Store, retry: Retry) -> SpawnRefused | None:
    """D31's fourth cap, **walked and never read off `attempt`** — a column a caller writes
    and nothing in this tree writes, so a cap resting on it could never fire at all.
    `retry_chain_depth` walks `retry_of`, whose only writer is `store.link_retry`, which is
    what makes this cap reachable. Two readings are conservative on purpose and written out
    in the M4 blockers file (T10-2, T10-3) rather than decided here: the chain is the
    **whole** lineage (T8), and a human retry is not capped (D31 caps *master-initiated*)."""
    if Origin(retry.initiated_by) is not MASTER_ORIGIN:
        return None
    attempts = store.retry_chain_depth(retry.of)
    if attempts < MAX_MASTER_ATTEMPTS:
        return None
    store.bump_anomaly(str(AnomalyKind.WAKE_RETRY_CAP_REACHED.value))
    return SpawnRefused(
        f"D31 caps a lineage at {MAX_MASTER_ATTEMPTS} master-initiated attempts and "
        f"{retry.of!r} already stands in a lineage of {attempts}, so this one is not "
        f"started: the earlier attempts' conclusions and next actions are already "
        f"written — read those, or ask the human to re-run it.",
        CAP_RETRY,
    )


def _caps(store: Store, panes: int, parent_session_id: str | None) -> int | SpawnRefused:
    """§11's three caps, in order, each in its own words; returns the new depth.

    `panes` is `len(runner.list_owned_panes())` — panes on the socket, never rows.
    A handle-less row can never be terminated, so a row-counting cap lets orphans
    accumulate across every restart while each one holds a live `claude`.
    """
    depth = 0
    if parent_session_id is not None:
        parent = store.get_owned_session(parent_session_id)
        if parent is None:
            return SpawnRefused(
                f"no owned session {parent_session_id!r} to be the parent of this spawn", None
            )
        depth = parent.depth + 1
        if depth >= MAX_SESSION_DEPTH:
            return SpawnRefused(
                f"the {CAP_DEPTH} cap is {MAX_SESSION_DEPTH} and this spawn would sit at "
                f"{depth}: start it from a shallower parent than {parent_session_id!r}",
                CAP_DEPTH,
            )
        children = store.children_of(parent_session_id)
        if children >= MAX_CHILDREN_PER_SESSION:
            return SpawnRefused(
                f"the {CAP_CHILDREN} cap is {MAX_CHILDREN_PER_SESSION} and "
                f"{parent_session_id!r} already has {children} live children: one must end "
                f"before it can start another",
                CAP_CHILDREN,
            )
    if panes >= MAX_TOTAL_OWNED_SESSIONS:
        return SpawnRefused(
            f"the {CAP_TOTAL} cap is {MAX_TOTAL_OWNED_SESSIONS} and {panes} owned panes are "
            f"open on this socket: the cap counts panes, not rows, because a row whose pane is "
            f"gone holds no slot",
            CAP_TOTAL,
        )
    return depth


def admit(
    *,
    store: Store,
    runner: Runner,
    workspace_id: str,
    cwd: str,
    parent_session_id: str | None,
    retry: Retry | None = None,
) -> Admitted | SpawnRefused:
    """Steps 1 and 2 of the sequence, plus D-5. Writes nothing, starts nothing.

    **`can_spawn` comes from `capabilities(pane_driver_available=...)`, never from
    the engine's capability record (T10-R2, D-5)**, which carries
    `can_spawn=True` unconditionally — a caller reading it gets `True` on a host
    with no pane driver and the degrade never fires. The runner's own answer to
    `list_owned_panes` is the caller's fact. Held by a check rather than a
    convention: `tests/boundaries/test_capability_degrade.py`.
    """
    canonical = _canonical_cwd(store, workspace_id, cwd)
    if isinstance(canonical, SpawnRefused):
        return canonical
    here, root = canonical
    try:
        panes, unreachable = len(runner.list_owned_panes()), ""
    except RunnerRefusal as refusal:
        panes, unreachable = 0, refusal.reason
    if not capabilities(pane_driver_available=not unreachable).can_spawn:
        return SpawnRefused(
            f"can_spawn is False on this host: no pane driver answered, so D-5's degrade "
            f"applies and nothing can be started for you — {unreachable}",
            None,
        )
    depth = _caps(store, panes, parent_session_id)
    if isinstance(depth, SpawnRefused):
        return depth
    if retry is not None:
        # Last, so no §11 refusal is displaced: a spawn that is both a third
        # attempt and over the pane cap reports the pane cap, which is the one an
        # operator can act on now.
        capped = _retry_cap(store, retry)
        if capped is not None:
            return capped
    return Admitted(cwd=here, depth=depth, root=root)
