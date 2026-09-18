"""ADR-M4-5's projection — the engine's stream in our words, and nothing else.

**Pure, and deliberately so.** Nothing here holds a client, a connection or a
turn: it takes one object the vendor's parser produced and answers with the
`MasterEvent`s it means. That is what lets it be driven over the *recorded*
stream of every probe capture on disk
(`tests/master/test_sdk_master.py::test_every_captured_stream_object_projects`),
which is a stronger test than any live turn could be — a live turn shows the
shapes that happened to occur in it.

**It is separate from `sdk_master.py` because the file rule said so**, and the
seam it fell on is the right one: one module knows the engine's *shapes*, the
other knows its *lifecycle*. Recorded in `docs/plans/m4-blockers/t21.md`.

**No vendor word leaves here.** `MasterEvent.tool_name` carries our own
registered name, the `mcp__shepherd__` prefix is stripped at the one place it
arrives, and the engine's classes are named in this module and in `sdk_tools.py`
and nowhere else in `src/` (D32, K13).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, MutableMapping

from claude_agent_sdk import (
    AssistantMessage,
    RateLimitEvent,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import utc_now
from shepherd.core.master import MasterEvent, MasterEventKind
from shepherd.master.sdk_tools import TOOL_PREFIX


#: §7's `app_state` key the turn driver reads the conversation id off
#: (`orchestration/master_turn.py`'s `MASTER_SESSION_KEY`). Spelled here rather
#: than imported: `orchestration/` is L3 and `master/` is L5, so the import would
#: be upward (§5.0). Two spellings of one fact is a fact two components can
#: disagree about, so `test_the_session_key_has_one_spelling` compares them.
MASTER_SESSION_KEY = "master_session_id"

#: Where the terminal event records what the turn's end *was*. One key, because
#: a page that has to know seven payload shapes to render an ending is a page
#: that renders six of them wrong.
OUTCOME_KEY = "outcome"

#: An ending we have never seen. G-M4-5: it is counted and rendered, never
#: raised — a turn that ended in a way we do not recognise still ended.
UNKNOWN_OUTCOME = "unknown"

#: The ending this runtime writes itself when the turn was cut short. Not the
#: engine's word: the engine's own result for an interrupted turn arrives after
#: we have stopped reading it (P2).
INTERRUPTED_OUTCOME = "interrupted"

#: `ResultMessage.subtype` → our terminal kind. `error` is *"a turn that ended
#: badly and is still a turn"* (`core/master.py`), which is why every failed
#: ending is still one terminal event. The four subtypes are the vocabulary
#: `data-schemas.md` §ResultMessage records; anything else is `UNKNOWN_OUTCOME`
#: and is counted, which is what G-M4-5 asks for and what makes the two
#: unprovoked subtypes (P5, deliberately not run) safe to meet in production.
RESULT_KINDS: Mapping[str, MasterEventKind] = {
    "success": "turn_ended",
    "error_during_execution": "error",
    "error_max_turns": "error",
    "error_max_budget_usd": "error",
}

#: The `terminal_reason`s the captures show beside those subtypes. A new one is
#: not an error — it is a fact about the engine we have not met — so it takes the
#: same counted `unknown` path rather than a branch of its own.
KNOWN_TERMINAL_REASONS: frozenset[str] = frozenset(
    {"completed", "aborted_streaming", "aborted_tools"}
)


def master_event(
    kind: MasterEventKind,
    *,
    text: str | None = None,
    tool_name: str | None = None,
    payload: Mapping[str, object],
) -> MasterEvent:
    return MasterEvent(
        kind=kind,
        text=text,
        tool_name=tool_name,
        payload=payload,
        occurred_at=utc_now(),
    )


def session_payload(session_id: str | None) -> dict[str, object]:
    """The conversation id, under the spelling the turn driver reads (D10).

    It rides on the event rather than on a member of the seam because the driver
    persists it *"from the first event of the turn that carries one"* — a runtime
    reports its session the way it reports everything else.
    """
    return {MASTER_SESSION_KEY: session_id} if session_id else {}


def _mapping(record: object) -> Mapping[str, object]:
    """One vendor record as plain data. Nothing below the seam sees its class."""
    if dataclasses.is_dataclass(record) and not isinstance(record, type):
        return dataclasses.asdict(record)
    return {}


def _result_text(content: object) -> str | None:
    """A tool result's text, whichever of the two shapes the block carries."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(block["text"])
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(parts) if parts else None
    return None


def result_ending(
    subtype: str, terminal_reason: str | None
) -> tuple[MasterEventKind, str, bool]:
    """`(kind, outcome, unmapped)` for one `ResultMessage` (ADR-M4-5, G-M4-5).

    An ending we do not have a word for becomes `turn_ended` carrying
    `outcome="unknown"` and is **counted**. It is deliberately not an exception:
    the turn is over either way, and a runtime that raised here would turn an
    unrecognised ending into a chat page that never sees its turn end.
    """
    if subtype not in RESULT_KINDS:
        return "turn_ended", UNKNOWN_OUTCOME, True
    if terminal_reason is not None and terminal_reason not in KNOWN_TERMINAL_REASONS:
        return "turn_ended", UNKNOWN_OUTCOME, True
    return RESULT_KINDS[subtype], subtype, False


def project_events(
    obj: object,
    *,
    bump: Callable[[AnomalyKind], None],
    tool_names: MutableMapping[str, str],
) -> tuple[MasterEvent, ...]:
    """One object off the engine's stream, in our words (ADR-M4-5).

    **A tuple, not `MasterEvent | None`** — a deviation from the plan's pinned
    `project_event`, recorded in `docs/plans/m4-blockers/t21.md`. The vendor's
    `AssistantMessage.content` is a *list* of blocks, so one message can be
    thinking **and** text **and** a tool call; a signature that can answer with
    at most one event drops the rest silently. Every assistant message in the
    probe captures happens to carry exactly one block, which is precisely why
    the narrower signature would have looked correct.

    `tool_names` is the turn's `tool_use_id` → **our** name map. The vendor sends
    a result back with the id and no name, and `MasterEvent.tool_name` carries
    our own registered name and never a prefixed one (D32, K13) — so the name is
    remembered when the call goes out and resolved when the result comes back.
    Anything the map has not seen is `None` rather than a guess.
    """
    if isinstance(obj, AssistantMessage):
        events: list[MasterEvent] = []
        for block in obj.content:
            session = session_payload(obj.session_id)
            if isinstance(block, TextBlock):
                events.append(master_event("text", text=block.text, payload=session))
            elif isinstance(block, ThinkingBlock):
                events.append(master_event("thinking", text=block.thinking, payload=session))
            elif isinstance(block, ToolUseBlock):
                name = block.name.removeprefix(TOOL_PREFIX)
                tool_names[block.id] = name
                events.append(
                    master_event(
                        "tool_call",
                        tool_name=name,
                        payload={**session, "tool_use_id": block.id, "input": dict(block.input)},
                    )
                )
        return tuple(events)

    if isinstance(obj, UserMessage):
        results: list[MasterEvent] = []
        content = obj.content
        if isinstance(content, str):
            return ()
        for block in content:
            if isinstance(block, ToolResultBlock):
                results.append(
                    master_event(
                        "tool_result",
                        text=_result_text(block.content),
                        tool_name=tool_names.get(block.tool_use_id),
                        payload={
                            "tool_use_id": block.tool_use_id,
                            "is_error": bool(block.is_error),
                        },
                    )
                )
        return tuple(results)

    if isinstance(obj, ResultMessage):
        kind, outcome, unmapped = result_ending(obj.subtype, obj.terminal_reason)
        if unmapped:
            bump(AnomalyKind.MASTER_RESULT_UNMAPPED)
        return (
            master_event(
                kind,
                text=obj.result,
                payload={
                    **session_payload(obj.session_id),
                    OUTCOME_KEY: outcome,
                    "subtype": obj.subtype,
                    "terminal_reason": obj.terminal_reason,
                    "is_error": obj.is_error,
                },
            ),
        )

    if isinstance(obj, RateLimitEvent):
        return (
            master_event(
                "rate_limit",
                payload={
                    **session_payload(obj.session_id),
                    "rate_limit": _mapping(obj.rate_limit_info),
                },
            ),
        )

    # Everything else the engine sends is the client's business, not a turn's:
    # `system/init` is read for the isolation assertion (T22) and the hook and
    # control traffic is never ours. Silence here is the design, and
    # `test_every_captured_stream_object_projects` is what holds it to exactly
    # the shapes the captures contain.
    return ()


#: Every kind a `ResultMessage` can become, which is exactly the set of kinds
#: that **end a turn**. Derived rather than restated: a second hand-written set
#: is the drift that lets a runtime end a turn on a kind nobody treats as an
#: ending, and then a chat page waits forever.
TERMINAL_KINDS: frozenset[str] = frozenset(RESULT_KINDS.values())
