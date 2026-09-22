"""The stop vocabulary — every type M2 speaks in, defined once, at L1 (T1).

`engines/`, `signals/`, `store/`, `logs/` and `toolsurface/` all import
**downward** into this module and none of them defines a second copy — the
F9 / BLOCKER-T7b-1 lesson: two structurally identical types are a type split
`mypy` only catches at the one call site that mixes them.

Types, enums, frozen dataclasses and constant tables only. The bucket *map*
and the `next_actions[]` *default table* are T7's; this module holds the
vocabulary they have to be total over. D34 forbids a classifier protocol here
by name — an interface with zero implementations is D9's mistake in its purest
form. Two invariants are enforced rather than hoped for (E-M2-28):
`NextAction.text` caps at 80 and `Verdict.why` at 120, both with an ellipsis,
so a column can never silently exceed the width §7 documents for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

#: §7's documented widths and D21's cap, as constants rather than as magic
#: numbers spread over five modules.
WHY_MAX = 120
ACTION_TEXT_MAX = 80
MAX_ACTIONS = 3

#: §8's "*(empty when confidence >= 0.8)*". ONE named constant: it is the only
#: number between a quiet fleet and a noisy one (ADR-M2-5).
CONFIDENT_ENOUGH = 0.8

#: Deliberately below the threshold, so a clean heuristic stop still carries
#: `Review the diff` rather than claiming certainty it has not earned.
HEURISTIC_COMPLETED_CONFIDENCE = 0.5

#: ADR-M2-6 — the stop-log record is versioned, and a reader tolerates an
#: older one rather than parsing a newer one optimistically (E-M2-21).
STOP_RECORD_VERSION = 1

_ELLIPSIS = "…"


def _capped(text: str, limit: int) -> str:
    """Truncate at the documented boundary. The untruncated text is in the log."""
    return text if len(text) <= limit else text[: limit - 1] + _ELLIPSIS


class StopReason(StrEnum):
    """Why a session stopped. Values are §8's spellings verbatim, because
    migration 002's `CHECK` lists exactly these twenty.

    **`StopReason.CLEARED` is not `core.fold_types.CLEARED`** — the latter is
    the fold's empty-string clear sentinel. Different namespaces; a module that
    needs both imports the module, not the name.
    """

    # the sixteen mechanical reasons
    RATE_LIMITED = "rate_limited"
    QUOTA_PAUSED = "quota_paused"
    AUTH_FAILED = "auth_failed"
    ACCOUNT_BLOCKED = "account_blocked"
    BAD_REQUEST = "bad_request"
    SERVER_ERROR = "server_error"
    TRUNCATED = "truncated"
    STALLED_PENDING_TOOL = "stalled_pending_tool"
    CRASHED = "crashed"
    """Unreachable at M2 (G-M2-2 / C13): an attached session gives an exit
    *time* and never an exit *code*. P-M2-12 asserts no path produces it."""
    KILLED = "killed"
    """Unreachable at M2 (G-M2-4): it needs M4's `action_log`."""
    CONTEXT_EXHAUSTED = "context_exhausted"
    USER_EXITED = "user_exited"
    CLEARED = "cleared"
    LOGGED_OUT = "logged_out"
    RESUMED_ELSEWHERE = "resumed_elsewhere"
    """§8's name misleads: the same pane continues as a *different* session id,
    and the `why` text says so (E-M2-9)."""
    UNKNOWN = "unknown"

    # the four completeness reasons
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    DERAILED = "derailed"
    """Unreachable at M2 (G-M2-6): no mechanical detector exists."""
    BLOCKED_EXTERNAL = "blocked_external"


class Bucket(StrEnum):
    """§4's seven palette buckets plus `UNCLASSIFIED` (D-4) — a stopped row
    with **no verdict**, never green and never red. It is what E-M2-4 leaves
    behind when a `StopFailure` is lost at `-p` shutdown; counting it is
    principle 5."""

    RUNNING = "running"
    NEEDS_YOU = "needs_you"
    FINISHED = "finished"
    UNFINISHED = "unfinished"
    BLOCKED = "blocked"
    PAUSED = "paused"
    ERROR = "error"
    UNCLASSIFIED = "unclassified"


class TurnEnding(StrEnum):
    """ADR-M2-3 — a **narrowing** of the transcript's turn-ending field, not a
    rename of it. Two engine spellings collapse into `OTHER` and three distinct
    *absences* into `ABSENT`, each still emitting its own anomaly kind. A sixth
    engine spelling becomes `OTHER` and is counted, and the count is what tells
    you to add a member, rather than a sixth behaviour nobody verified.
    """

    ENDED_TURN = "ended_turn"
    HELD_TOOL_CALL = "held_tool_call"
    HIT_TOKEN_CAP = "hit_token_cap"
    OTHER = "other"
    ABSENT = "absent"


class DecidedBy(StrEnum):
    """DP1. `MODEL` and `MANUAL` exist and nothing at M2 writes them."""

    MECHANICAL = "mechanical"
    HEURISTIC = "heuristic"
    MODEL = "model"
    DECLARED = "declared"
    MANUAL = "manual"


class NextActionKind(StrEnum):
    """DP5 — D21's list, which is the one the default table uses."""

    RETRY = "retry"
    RESUME = "resume"
    RESPAWN = "respawn"
    INSPECT = "inspect"
    EXTERNAL = "external"
    REAUTH = "reauth"
    ESCALATE = "escalate"
    REQUEUE = "requeue"
    NONE = "none"


class ActionSource(StrEnum):
    """The ordering guarantee's rank: `DECLARED` > `LLM` > `HEURISTIC` (§8)."""

    DECLARED = "declared"
    LLM = "llm"
    HEURISTIC = "heuristic"


@dataclass(frozen=True)
class BucketStyle:
    """§4's row. Colour **and** glyph for all eight, so amber/red survive
    colourblindness and greyscale."""

    colour: str
    glyph: str
    label: str
    who_acts: str


@dataclass(frozen=True)
class NextAction:
    """One of at most three things a human could do about this stop (D21)."""

    text: str
    kind: NextActionKind
    target: str | None
    source: ActionSource

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _capped(self.text, ACTION_TEXT_MAX))


@dataclass(frozen=True)
class ToolUseRef:
    """A `tool_use` block from the tail. `name` is the tool's own name (`Bash`,
    `Write`) — API vocabulary, not hook vocabulary."""

    tool_use_id: str
    name: str
    entry_index: int


@dataclass(frozen=True)
class ToolFailure:
    """An `is_error` tool result, paired back to its call where possible
    (E-M2-17). An unpairable one keeps `name=None` and is counted, never
    attributed to a tool it may not have come from."""

    tool_use_id: str | None
    name: str | None
    entry_index: int


@dataclass(frozen=True)
class TranscriptTail:
    """The neutral projection of the engine's on-disk transcript (T3).

    No mapping field (P-M2-6). `promise_followed_by_tool_use` is `None` when
    there was no promise to judge, and `truncated` is A4's bounded-window flag:
    a short tail is honest about being short, because the observer may not harm
    the observed (principle 4).
    """

    ending: TurnEnding
    last_assistant_text: str | None
    entry_count: int
    tool_uses: tuple[ToolUseRef, ...]
    failures: tuple[ToolFailure, ...]
    promise_followed_by_tool_use: bool | None
    skipped_lines: int
    truncated: bool


@dataclass(frozen=True)
class StopEvidence:
    """The classifier's **whole** input, assembled once, at the stop (ADR-M2-1).

    Written to the stop log verbatim and read back by `replay`, so the
    transcript is read exactly once and `replay` still works months later on a
    machine where `~/.claude` has been cleared. A field a rule wants later is
    added here *and* to `record_version` — a visible change, not a silent new
    read. `mechanical is None` means the adapter **deferred** to the tail.
    """

    record_version: int
    session_id: str
    engine_session_id: str | None
    received_at: str
    mechanical: StopReason | None
    mechanical_detail: str | None
    tail: TranscriptTail
    tasks_total: int
    tasks_done: int
    brief: str | None
    auto_compact_pending: bool
    quota_notice: bool
    process_exit_observed: bool
    exit_code: int | None


@dataclass(frozen=True)
class Verdict:
    """What `classify()` returns and what the eight stop columns hold.

    `waiting_on` is `None` at M2 (G-M2-7): `blocked_external`'s two sources are
    M4's `report_blocked()` and M5's `work_item.status_class`, so nothing at M2
    can name what a session is waiting on without guessing.
    """

    stop_reason: StopReason
    bucket: Bucket
    why: str
    confidence: float
    decided_by: DecidedBy
    next_actions: tuple[NextAction, ...]
    waiting_on: str | None
    missing: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "why", _capped(self.why, WHY_MAX))


#: §4's table (`orchestrator-platform.md:202-208`) plus `UNCLASSIFIED`, grey because
#: nobody could classify it. **U5's three `label` renames land here, not in a UI copy.**
PALETTE: Mapping[Bucket, BucketStyle] = MappingProxyType(
    {
        Bucket.RUNNING: BucketStyle("#3B82F6", "●", "running", "nobody"),
        Bucket.NEEDS_YOU: BucketStyle("#F59E0B", "⏸", "needs you", "you, now"),
        Bucket.FINISHED: BucketStyle("#10B981", "✓", "finished", "nobody"),
        Bucket.UNFINISHED: BucketStyle("#8B5CF6", "◑", "stranded", "you, when ready"),
        Bucket.BLOCKED: BucketStyle("#64748B", "⏳", "blocked", "someone else"),
        Bucket.PAUSED: BucketStyle("#06B6D4", "⏱", "limit exceeded", "nobody, wait"),
        Bucket.ERROR: BucketStyle("#EF4444", "✕", "error", "you, fix it"),
        Bucket.UNCLASSIFIED: BucketStyle("#9CA3AF", "?", "unknown", "nobody yet"),
    }
)

#: §12's order for its first seven entries, then ours.
#:
#: §12's eighth entry is `idle`, which is **not** a `Bucket`: M1's D-2 resolved
#: `idle` as a *workspace-level* rendering (a workspace all of whose sessions
#: are stopped), never a session state. `unclassified` takes the last slot
#: because a row we could not classify should never outrank one we could.
#:
#: **`blocked` below `running` is deliberate** and *is* verbatim from §12 — it
#: is real, it is visible, and it is not yours to act on.
BUCKET_ORDER: tuple[Bucket, ...] = (
    Bucket.NEEDS_YOU,
    Bucket.ERROR,
    Bucket.UNFINISHED,
    Bucket.RUNNING,
    Bucket.PAUSED,
    Bucket.BLOCKED,
    Bucket.FINISHED,
    Bucket.UNCLASSIFIED,
)
