"""The engine-neutral signal vocabulary (ADR-6, r4 BLOCKING 2).

Nothing in this module knows an engine event name exists. The adapter
(`engines/claude_code/normalise.py`) is the only place an engine's own spelling
is read; it projects what it needs into `Signal.fields` under a key from
`SIGNAL_FIELD_KEYS`, and `signals/` reads only those keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class SignalKind(StrEnum):
    """One member per **distinct column effect** — never one per engine event.

    That is what lets `FoldRule.kind` type the rule table and select by dict
    lookup, so no rule ever needs a `raw_kind` predicate.
    """

    SESSION_REGISTERED = "session_registered"
    PROMPT_SUBMITTED = "prompt_submitted"
    TURN_PROGRESS = "turn_progress"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    TOOL_BATCH_FINISHED = "tool_batch_finished"
    NEEDS_INPUT = "needs_input"
    INPUT_RESOLVED = "input_resolved"
    NOTICE_UNMAPPED = "notice_unmapped"
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_FINISHED = "subagent_finished"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    TURN_STOPPED = "turn_stopped"
    """A turn ended. Separate from `SESSION_STOPPED` because their column
    effects are no longer identical: a turn ending clears the auto-compaction
    mark and a session ending — the *death* §8's rule is bounded by — does not
    (r3 BLOCKING 1). Writing that difference any other way would mean naming an
    engine event inside `signals/`."""
    SESSION_STOPPED = "session_stopped"
    STOP_FAILED = "stop_failed"
    COMPACT_STARTED = "compact_started"
    COMPACT_FINISHED = "compact_finished"
    QUOTA_NOTICE = "quota_notice"
    CWD_CHANGED = "cwd_changed"
    FILES_CHANGED = "files_changed"
    MODEL_CHANGED = "model_changed"
    UNKNOWN = "unknown"


#: The CLOSED set of neutral keys `Signal.fields` may carry. A key here is never
#: the engine's own spelling: `new_cwd` is literally Claude Code's `CwdChanged`
#: field, so the neutral key is `next_cwd` (r5).
SIGNAL_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "ask",
        "changed_paths",
        "model",
        "subagent_id",
        "task_id",
        "prompt",
        "next_cwd",
        "start_source",
        "tool_label",
        "failure_note",
        "refusal",
        # BLOCKER T6-1: *how* a session ended. The value is still the engine's
        # own word, which is why the table that interprets it lives in the
        # adapter (`engines/claude_code/stop_map.py`) and never in `signals/`,
        # exactly as `failure_note` already works. Without a neutral key here
        # the stop lane has no route to the reason at all, and four mechanical
        # rows plus `context_exhausted` become a tested seam that never runs.
        "end_reason",
    }
)


#: The CLOSED set of values the neutral `refusal` key may carry. Two conditions,
#: because they mean different things to a human reading `doctor`: a hook the
#: user installed refused the call, or the permission system did (BLOCKER T11-2).
HOOK_BLOCK_REFUSAL = "hook_block"
PERMISSION_REFUSAL = "permission"
REFUSAL_VALUES: frozenset[str] = frozenset({HOOK_BLOCK_REFUSAL, PERMISSION_REFUSAL})


@dataclass(frozen=True)
class Signal:
    kind: SignalKind
    engine_session_id: str
    cwd: str
    transcript_path: str
    received_at: str
    fields: Mapping[str, object]
    raw_kind: str
    """The engine's own event name — for anomaly detail and `doctor` ONLY.

    `signals/` may pass it through; it may never compare it against a literal.
    """

    def __post_init__(self) -> None:
        """Deep-freeze `fields` — `frozen=True` alone is a *shallow* freeze.

        It stops the attribute being rebound; it does nothing about the dict the
        adapter still holds a reference to, and `Signal` is the fold's input,
        read by the rule table long after the adapter has moved on. Every other
        core type uses `tuple`/`frozenset`; this was the one outlier.
        """
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True)
class SubagentRef:
    """A live subagent, paired on the neutral `subagent_id` key (C10, E4)."""

    subagent_id: str
    label: str | None


@dataclass(frozen=True)
class TaskRef:
    task_id: str
    label: str | None


@dataclass(frozen=True)
class MalformedPayload:
    """A payload the adapter could not parse. Counted, never raised (§8)."""

    raw_len: int
    reason: str
    received_at: str
