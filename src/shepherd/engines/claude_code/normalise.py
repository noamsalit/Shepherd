"""Table A (T11) — the engine's vocabulary, and the last place it is spoken.

One hook payload in, one engine-neutral `Signal` out. **Every** Claude Code
event name and **every** Claude Code field name the product reads appears in
this module and nowhere else: `signals/` sees a `SignalKind` and a `fields`
mapping whose keys all come from `SIGNAL_FIELD_KEYS` (r5, BLOCKING 1/3).

Three probed facts shape the projection:

* **C8** — only `session_id`, `transcript_path`, `cwd` and the event name are on
  every payload, and **no payload carries a timestamp**. `received_at` is a
  parameter: the receiver stamps it. Every other field is optional, and its
  absence degrades a neutral key to *missing*, never to an error.
* **C9** — the watch-path event fires only for declared watch paths, never for
  files the agent edits, so the agent's own edits are read from the tool input
  of an `Edit`/`Write` completion instead.
* **C10** — an internal subagent stops with `agent_type: ""` and never started,
  so that stop carries **no** `subagent_id`: there is nothing to pair it with,
  and the fold counts it as the anomaly it is.

Nothing here reads a clock, a file or the store. `parse_hook_payload` never
raises: an unreadable payload is a `MalformedPayload` value (principle 5), and
an unrecognised event name is `SignalKind.UNKNOWN`, counted downstream.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from shepherd.core.signals import (
    HOOK_BLOCK_REFUSAL,
    PERMISSION_REFUSAL,
    MalformedPayload,
    Signal,
    SignalKind,
)

#: §Common input fields: the event's own name, and the session it belongs to.
EVENT_NAME_FIELD = "hook_event_name"
SESSION_ID_FIELD = "session_id"

#: §Notification and §Notification payload (TUI). These five types are an ask a
#: human has to answer; every other type is an unmapped notice (principle 5).
NEEDS_INPUT_NOTIFICATION_TYPES: frozenset[str] = frozenset(
    {
        "permission_prompt",
        "idle_prompt",
        "elicitation_dialog",
        "agent_needs_input",
        "elicitation_url_dialog",
    }
)

#: Decision pressure 3: the idle ask is a different sentence from the permission
#: ask, and the UI has to be able to say which. Composed here, never in `signals/`.
IDLE_ASK = "idle — waiting for your next instruction"

#: C9: the two tools whose completion means the agent wrote to a path.
EDITING_TOOLS: frozenset[str] = frozenset({"Edit", "Write"})

#: The tool-input keys worth putting in an ask, most specific first.
_ASK_SUMMARY_KEYS: tuple[str, ...] = ("command", "file_path", "description", "pattern", "path")
_ASK_SUMMARY_LIMIT = 80

#: The engine's own refusal sentences, as **literal** prefixes and markers read
#: off the 40 captured `PostToolBatch` payloads. This is deliberately not a
#: reading of prose for meaning — that is M2's heuristic territory and it would
#: make the counter guess. A wording we have not captured projects nothing, so
#: the counter under-counts and never invents a refusal that did not happen.
_HOOK_BLOCK_MARKER = " hook error: "
_PERMISSION_REFUSAL_PREFIXES: tuple[str, ...] = (
    "Permission for this action was denied",
    "Permission for this tool use was denied",
    "Permission to use ",
    "Claude requested permissions to ",
)

#: Events that carry no neutral field at all and mean exactly one kind.
_PLAIN_KINDS: Mapping[str, SignalKind] = {
    "PostToolUseFailure": SignalKind.TOOL_FAILED,
    "MessageDisplay": SignalKind.TURN_PROGRESS,
    "PermissionDenied": SignalKind.INPUT_RESOLVED,
    "ElicitationResult": SignalKind.INPUT_RESOLVED,
    # r3 BLOCKING 1: a turn ending and a session ending are two kinds now,
    # because their column effects differ by exactly one cell (the compaction
    # mark). `Stop` carries no `stop_reason` — 26 captures and the binary
    # schema agree — so it projects nothing at all.
    "Stop": SignalKind.TURN_STOPPED,
    # §Hook event names: real events M1 observes but folds as liveness only.
    "InstructionsLoaded": SignalKind.TURN_PROGRESS,
    "ConfigChange": SignalKind.TURN_PROGRESS,
    "Setup": SignalKind.TURN_PROGRESS,
    "DirectoryAdded": SignalKind.TURN_PROGRESS,
    "UserPromptExpansion": SignalKind.TURN_PROGRESS,
    "WorktreeCreate": SignalKind.TURN_PROGRESS,
    "WorktreeRemove": SignalKind.TURN_PROGRESS,
    "PostCompact": SignalKind.COMPACT_FINISHED,
    "TeammateIdle": SignalKind.TURN_PROGRESS,
}

#: §PreCompact / PostCompact: the field is `trigger`, and `auto` is the one
#: value that means the engine ran out of context rather than a human asking.
#: A manual compact is not exhaustion, so it finishes the mark instead of
#: setting one.
COMPACT_TRIGGER_FIELD = "trigger"
AUTO_COMPACT_TRIGGER = "auto"
MANUAL_COMPACT_TRIGGER = "manual"

#: §Enumerations: the three quota values of `notification_type`. **The type
#: only** — no payload field is read (G-M2-1), because nothing about the quota
#: notice's message has been captured.
QUOTA_NOTIFICATION_TYPES: frozenset[str] = frozenset(
    {
        "quota_auto_resume_fired",
        "quota_auto_resume_stale",
        "quota_auto_resume_disabled",
    }
)

#: §SessionEnd: the field is `reason` (the spec's `end_reason` does not exist).
#: Its value is the engine's own word and is projected under the neutral
#: `end_reason` key for the adapter's own stop map to read back — the same
#: shape `failure_note` already uses, and the only route the stop lane has to
#: the four mechanical endings (BLOCKER T6-1).
SESSION_END_REASON_FIELD = "reason"


def _text(payload: Mapping[str, object], key: str) -> str | None:
    """A payload field as a non-empty string, or `None`. Never raises (C8)."""
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _summary(tool_input: Mapping[str, object]) -> str:
    """The shortest honest description of what a tool was asked to do."""
    for key in _ASK_SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            trimmed = " ".join(value.split())
            return trimmed if len(trimmed) <= _ASK_SUMMARY_LIMIT else trimmed[:_ASK_SUMMARY_LIMIT]
    return ""


def _permission_ask(payload: Mapping[str, object]) -> str:
    tool = _text(payload, "tool_name") or "a tool"
    return f"permission: {tool}({_summary(_mapping(payload, 'tool_input'))})"


def _notification(payload: Mapping[str, object]) -> tuple[SignalKind, dict[str, object]]:
    notification_type = _text(payload, "notification_type")
    if notification_type in QUOTA_NOTIFICATION_TYPES:
        return SignalKind.QUOTA_NOTICE, {}
    if notification_type not in NEEDS_INPUT_NOTIFICATION_TYPES:
        return SignalKind.NOTICE_UNMAPPED, {}
    if notification_type == "idle_prompt":
        return SignalKind.NEEDS_INPUT, {"ask": IDLE_ASK}
    ask = _text(payload, "message") or f"needs your input: {notification_type}"
    return SignalKind.NEEDS_INPUT, {"ask": ask}


def _post_tool_use(payload: Mapping[str, object]) -> tuple[SignalKind, dict[str, object]]:
    """C9: the agent's own edits, read from the tool input of Edit/Write."""
    fields: dict[str, object] = {}
    if _text(payload, "tool_name") in EDITING_TOOLS:
        path = _text(_mapping(payload, "tool_input"), "file_path")
        if path is not None:
            fields["changed_paths"] = (path,)
    return SignalKind.TOOL_FINISHED, fields


def _post_tool_batch(payload: Mapping[str, object]) -> tuple[SignalKind, dict[str, object]]:
    """The batch's refusal, if the engine named one in a `tool_response`.

    A hook block outranks a permission refusal when a batch carries both: the
    marker is the engine's own mechanical string, where the permission
    sentences are prose that varies per refusal path.
    """
    calls = payload.get("tool_calls")
    responses = [
        response
        for call in (calls if isinstance(calls, list) else [])
        if isinstance(call, Mapping)
        for response in [call.get("tool_response")]
        if isinstance(response, str)
    ]
    if any(_HOOK_BLOCK_MARKER in response for response in responses):
        return SignalKind.TOOL_BATCH_FINISHED, {"refusal": HOOK_BLOCK_REFUSAL}
    if any(response.startswith(_PERMISSION_REFUSAL_PREFIXES) for response in responses):
        return SignalKind.TOOL_BATCH_FINISHED, {"refusal": PERMISSION_REFUSAL}
    return SignalKind.TOOL_BATCH_FINISHED, {}


def _subagent_stop(payload: Mapping[str, object]) -> tuple[SignalKind, dict[str, object]]:
    """C10: `agent_type: ""` is an internal agent that never started.

    Its id is dropped here, so the fold sees a finish with nothing to pair on
    and counts it rather than driving the live count negative.
    """
    fields: dict[str, object] = {}
    if _text(payload, "agent_type") is not None:
        agent_id = _text(payload, "agent_id")
        if agent_id is not None:
            fields["subagent_id"] = agent_id
    return SignalKind.SUBAGENT_FINISHED, fields


def _pre_compact(payload: Mapping[str, object]) -> SignalKind:
    """§PreCompact: `trigger` is what separates exhaustion from a human's
    `/compact`. A trigger nobody has captured decides **no** column — it stays
    the liveness-only kind M1 gave it, because a value we cannot read may not
    be allowed to clear a mark or to claim the session ran out of context
    (principle 5: under-fire rather than invent).
    """
    trigger = _text(payload, COMPACT_TRIGGER_FIELD)
    if trigger == AUTO_COMPACT_TRIGGER:
        return SignalKind.COMPACT_STARTED
    if trigger == MANUAL_COMPACT_TRIGGER:
        return SignalKind.COMPACT_FINISHED
    return SignalKind.TURN_PROGRESS


def _optional(key: str, value: str | None) -> dict[str, object]:
    return {} if value is None else {key: value}


def _project(event: str, payload: Mapping[str, object]) -> tuple[SignalKind, dict[str, object]]:
    """Table A itself: one engine event name in, one kind and its fields out."""
    plain = _PLAIN_KINDS.get(event)
    if plain is not None:
        return plain, {}
    if event == "SessionStart":
        return SignalKind.SESSION_REGISTERED, _optional("start_source", _text(payload, "source"))
    if event == "UserPromptSubmit":
        return SignalKind.PROMPT_SUBMITTED, _optional("prompt", _text(payload, "prompt"))
    if event == "PreToolUse":
        return SignalKind.TOOL_STARTED, _optional("tool_label", _text(payload, "tool_name"))
    if event == "PostToolUse":
        return _post_tool_use(payload)
    if event == "PostToolBatch":
        return _post_tool_batch(payload)
    if event == "PermissionRequest":
        return SignalKind.NEEDS_INPUT, {"ask": _permission_ask(payload)}
    if event == "Notification":
        return _notification(payload)
    if event == "Elicitation":
        ask = _text(payload, "message") or "a tool is asking for input"
        return SignalKind.NEEDS_INPUT, {"ask": ask}
    if event == "SubagentStart":
        return SignalKind.SUBAGENT_STARTED, _optional("subagent_id", _text(payload, "agent_id"))
    if event == "SubagentStop":
        return _subagent_stop(payload)
    if event == "TaskCreated":
        return SignalKind.TASK_CREATED, _optional("task_id", _text(payload, "task_id"))
    if event == "TaskCompleted":
        return SignalKind.TASK_COMPLETED, _optional("task_id", _text(payload, "task_id"))
    if event == "FileChanged":
        path = _text(payload, "file_path")
        paths: dict[str, object] = {} if path is None else {"changed_paths": (path,)}
        return SignalKind.FILES_CHANGED, paths
    if event == "CwdChanged":
        return SignalKind.CWD_CHANGED, _optional("next_cwd", _text(payload, "new_cwd"))
    if event in ("PreModelSwitch", "PostModelSwitch"):
        return SignalKind.MODEL_CHANGED, _optional("model", _text(payload, "to_model"))
    if event == "PreCompact":
        return _pre_compact(payload), {}
    if event == "SessionEnd":
        return SignalKind.SESSION_STOPPED, _optional(
            "end_reason", _text(payload, SESSION_END_REASON_FIELD)
        )
    if event == "StopFailure":
        return SignalKind.STOP_FAILED, _optional("failure_note", _text(payload, "error"))
    return SignalKind.UNKNOWN, {}


def parse_hook_payload(raw: bytes, received_at: str) -> Signal | MalformedPayload:
    """One hook's stdin bytes → an engine-neutral `Signal`. Never raises.

    `received_at` is the receiver's stamp: no payload carries a timestamp (C8),
    so the caller's clock is the only honest one — and passing it in is what
    makes T12's replay of the captured corpus byte-deterministic.
    """
    try:
        decoded: object = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        return MalformedPayload(raw_len=len(raw), reason=str(error), received_at=received_at)
    if not isinstance(decoded, dict):
        return MalformedPayload(
            raw_len=len(raw), reason="payload is not a JSON object", received_at=received_at
        )
    payload: Mapping[str, object] = decoded
    event = _text(payload, EVENT_NAME_FIELD)
    if event is None:
        return MalformedPayload(
            raw_len=len(raw), reason="no hook event name", received_at=received_at
        )
    session_id = _text(payload, SESSION_ID_FIELD)
    if session_id is None:
        return MalformedPayload(
            raw_len=len(raw), reason="no session id", received_at=received_at
        )
    kind, fields = _project(event, payload)
    return Signal(
        kind=kind,
        engine_session_id=session_id,
        cwd=_text(payload, "cwd") or "",
        transcript_path=_text(payload, "transcript_path") or "",
        received_at=received_at,
        fields=fields,
        raw_kind=event,
    )
