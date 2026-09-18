"""Anomalies — principle 5: unknown is a first-class value, counted and shown.

Every member is a condition some probe actually observed and the plan names.
The set is append-only: a new observed condition adds a member, it never
reuses one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AnomalyKind(StrEnum):
    MALFORMED_PAYLOAD = "malformed_payload"
    UNKNOWN_EVENT_NAME = "unknown_event_name"
    UNMAPPED_NOTICE = "unmapped_notice"
    SUBAGENT_UNDERFLOW = "subagent_underflow"
    MISSING_SUBAGENT_TRANSCRIPT = "missing_subagent_transcript"
    """E26 — a subagent whose transcript path was announced and never written.
    Distinct from `MALFORMED_PAYLOAD`: nothing is torn, the file is not there."""
    SUBAGENT_STATE_UNKNOWN = "subagent_state_unknown"
    """C20/E28 — a subagent whose state is written down nowhere at all. Distinct
    from `UNMAPPED_NOTICE`, which is a status word we saw and could not map."""
    TOOL_BLOCKED_BY_HOOK = "tool_blocked_by_hook"
    """A tool call one of the user's own hooks refused."""
    TOOL_PERMISSION_REFUSED = "tool_permission_refused"
    """A tool call the permission system refused. The two are separate members
    because they mean different things to whoever reads the count: one is the
    user's own configuration, the other is the engine's approval surface
    (BLOCKER T11-2, plan gap M7)."""
    UNKNOWN_REGISTRY_STATUS = "unknown_registry_status"
    STOP_FAILED = "stop_failed"
    GIT_NO_REMOTE = "git_no_remote"
    GIT_AMBIGUOUS_REMOTE = "git_ambiguous_remote"
    GIT_DUBIOUS_OWNERSHIP = "git_dubious_ownership"
    GIT_BARE_REPO = "git_bare_repo"
    GIT_NOT_A_REPO = "git_not_a_repo"

    # ----- M2's stop lane (T3, T4) ----------------------------------------
    # Four kinds rather than one, because `doctor` reading "37 unknowns" cannot
    # tell an unmapped API error from a `-p` exit that deferred, and those are
    # different work items.
    STOP_UNMAPPED_VALUE = "stop_unmapped_value"
    """An engine value no row claims. It becomes `unknown` and is counted —
    never converted into a confident reason (principle 5, C-M2-3)."""
    STOP_DEFERRED_VALUE = "stop_deferred_value"
    """A value that decided nothing and handed the question on. The engine's
    catch-all session-ending reason is 47 of 50 corpus captures (DP8), and a
    defer is **not** an unknown: nothing failed, the answer is simply
    elsewhere. The engine's own spelling stays in its adapter (§5.0)."""
    EXIT_CODE_UNOBSERVABLE = "exit_code_unobservable"
    """C13 — an attached session gives an exit *time* and never an exit
    *code*, so `crashed` and `stopped` are not separable. Counted, so the
    limitation is visible rather than inferred from a missing row."""
    TRANSCRIPT_TAIL_ABSENT = "transcript_tail_absent"
    """The tail decided nothing: no file, an empty window, or no `assistant`
    entry that ended a turn (E-M2-12/13). Three absences, one count, each with
    its own detail string."""
    TRANSCRIPT_TAIL_TRUNCATED = "transcript_tail_truncated"
    """A4 — the bounded 256 KiB window was hit, so the tail is shorter than the
    last 20 entries. The observer may not harm the observed (principle 4), and
    a short tail that says so degrades a heuristic instead of inventing one."""
    TOOL_RESULT_UNPAIRED = "tool_result_unpaired"
    """E-M2-17 — an `is_error` result whose `tool_use` fell outside the window,
    so the tool's name is unknown. Counted, never attributed to the nearest
    call: a guess that reads like a fact is the failure principle 5 forbids."""

    # ----- M3's owned sessions (T12, T14, T15, T6, T13/T16, T8) -----------
    # Appended, never reordered: the set is append-only, `doctor` seeds a zero
    # row per member, and M2's ordering blocker (T3-2/T4-1) stays deferred.
    KILL_WITHOUT_SESSION_END = "kill_without_session_end"
    """G-M3-9 — the kill was recorded and no session-ending hook followed. The
    verdict is written from the recorded action, so the hook's absence is a
    count rather than a session with no ending."""
    MAILBOX_INPUT_NOT_EMPTY = "mailbox_input_not_empty"
    """DP10 — delivery deferred because the input line was still non-empty
    **after** the clearing keystroke and the re-read. The message is retried,
    never typed into somebody's half-written prompt."""
    ASK_FORK_RESIDUE = "ask_fork_residue"
    """DP7/K3 — a fork transcript was **found** in the target's project dir.

    Corrected at BLOCKER-T1-2: P2 measured that `--resume --fork-session -p
    --no-session-persistence` leaves **no** transcript at all, so the original
    sentence ("P2 says a fork transcript is left") fired on the normal path and
    was silent on the regression. It fires when residue is found — the flag was
    dropped or ignored — which is the event worth counting (K9). The file is
    named in `ask_fork.<id>` and **never deleted**: Shepherd does not remove a
    file a user may want, and the engine owns every byte of it."""
    ORPHANED_PANE = "orphaned_pane"
    """T12's reconcile — a Shepherd-named pane with no row, or with a
    handle-less row it could not rebind."""
    PANE_UNREADABLE = "pane_unreadable"
    """The capture could not be classified: an empty capture, or bytes that are
    not UTF-8. Two absences, one count, each with its own detail string — the
    shape `TRANSCRIPT_TAIL_ABSENT` already uses.

    A **dead** pane is deliberately not here: it carries a real exit status
    (E-M3-16), so it is a real classification. Counting a knowable outcome as
    an unknown is the opposite of principle 5."""
    SIDECAR_ABSENT = "sidecar_absent"
    """DP8 — the dialog gate wanted the sidecar and it was not there, which is
    the **normal** state during the trust dialog. Counted so that a common,
    expected degrade is still visible rather than assumed."""
    MAILBOX_CLIENT_ATTACHED = "mailbox_client_attached"
    """BLOCKER-T1-3 — delivery deferred because a terminal client is attached to
    the pane, so a human may be typing into it. P3 captured what that costs: a
    writer's submit sent the human's own keystrokes, inside Shepherd's prompt.
    Counted rather than silent, because the deferral is the **safe** direction
    and a queue that never moves has to say why. The check narrows the race; it
    does not close it, and the count is what keeps the residual visible."""
    TMUX_UNAVAILABLE = "tmux_unavailable"
    """Shepherd cannot reach its panes at all: no server on the socket, or the
    binary is not on `PATH`. One member, two detail strings — they mean the
    same thing to whoever reads the count, and `can_spawn` is the capability
    that degrades (D-5)."""
    DIALOG_TEXT_UNRECOGNISED = "dialog_text_unrecognised"
    """BLOCKER-T1-4 / T16-1 — a permission dialog whose option set is **not** the
    one P4 captured: `Tab` re-labelled option 1 (`02a-tab-dialog.txt` ->
    `02b-tab-after.txt`, the dialog staying up), or another tool raised an option
    set nobody has captured. The keys are positional, so Shepherd cannot see an
    amendment it did not make and refuses rather than guessing — and the refusal
    is counted here because T16 could otherwise only return it in a `reason`,
    where the one refusal standing between a positional digit and a tool no human
    approved reaches no surface `doctor` renders. Distinct from `SIDECAR_ABSENT`,
    which is the other source being missing rather than this one disagreeing, and
    from `PANE_UNREADABLE`, whose docstring excludes knowable states: this screen
    was read perfectly well, and what it says is that it is not the screen we
    know."""

    # ----- M4's orchestrator (T4, T5, T10, T20, T21) ----------------------
    # Appended, never reordered. Every member below has a **reachable**
    # increment site: a counter that can only be incremented by a process the
    # import rules forbid from reaching the counter is always zero, which is
    # K9's defect wearing compliance (K24). Four of these are raised inside
    # `master/`, which D19 forbids from importing a store, so the master is
    # handed a `bump: Callable[[AnomalyKind], None]` from L6 — **injected, not
    # imported**, the shape `record_anomaly` in `core/runner.py` already has.
    # `tests/test_core_master.py::test_every_m4_anomaly_member_has_a_reachable
    # _increment_site` enumerates this section and is what stops a ninth member
    # appearing with nowhere to be counted.
    APPROVAL_TIMED_OUT = "approval_timed_out"
    """600 s elapsed and nobody decided. The approval dies, the call is
    refused, and the count is what makes an unattended fleet visible — a
    deadline nobody saw is not the same event as a refusal somebody chose."""
    APPROVAL_WITHDRAWN = "approval_withdrawn"
    """D54 — a pending approval was cancelled before anyone answered it (the
    turn was interrupted, or the caller went away). Distinct from
    `APPROVAL_TIMED_OUT`: the question was retracted, not left unanswered.
    Neither is a **denial**, which is a decision and therefore not an
    anomaly at all."""
    AUDIT_LINE_LOST = "audit_line_lost"
    """E-M4-6 — the rotating log reported a failed write. The sink never
    raises: a swallowed exception that kills a destructive call mid-flight is
    worse than a missing line, so the call proceeds and the gap is counted.
    D8's "always on" is a promise about intent, and this is the counter that
    keeps the difference between intent and outcome readable."""
    MASTER_TOOL_UNEXPECTED = "master_tool_unexpected"
    """DP7 — the belt fired for a tool we never mounted. It denies, always;
    the count is what tells an operator the runtime asked for something this
    build does not export. Raised in `master/` and counted through the
    injected `bump` (K24)."""
    MASTER_TOOL_RESULT_ORPHANED = "master_tool_result_orphaned"
    """DP5's fallback — a cancelled handler's thread finished anyway and its
    result was discarded. The work escaped its turn, which is exactly the
    condition an operator cannot otherwise see. Injected `bump` (K24)."""
    MASTER_RESULT_UNMAPPED = "master_result_unmapped"
    """G-M4-5 — a turn ended with a subtype or terminal reason this build has
    no row for. The turn becomes `outcome="unknown"` rather than being guessed
    into the nearest known ending, and the count is the tuning backlog
    (principle 5). Injected `bump` (K24)."""
    MASTER_RESUME_LOST = "master_resume_lost"
    """E-M4-8 — `resume` named a transcript the engine no longer has. A new
    conversation starts and its id is persisted; it is never a *silent* new
    conversation, because the orchestrator losing its memory is the one thing
    the operator must be told. Injected `bump` (K24)."""
    WAKE_RETRY_CAP_REACHED = "wake_retry_cap_reached"
    """D31 — a master-initiated retry was refused at the cap. Deliberately not
    spelled like the refusal reason the agent reads (`RETRY_CAP_REACHED`):
    they are different things — one is an answer to a caller, one is a counter
    for an operator — and two near-identical names are how a builder bumps one
    and asserts the other."""


@dataclass(frozen=True)
class Anomaly:
    kind: AnomalyKind
    detail: str
    engine_session_id: str | None
