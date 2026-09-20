"""Table A — the normaliser's map (T11).

Every engine event name and every engine field name in the product lives in
`engines/claude_code/normalise.py`; these tests are the only other place they
are written down, and they are written against **captured payloads**
(`docs/probes/2026-09-14-schemas/…`), never against an invented shape.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from shepherd.core.signals import SIGNAL_FIELD_KEYS, MalformedPayload, Signal, SignalKind
from shepherd.engines.claude_code.events import ALL_HOOK_EVENT_NAMES
from shepherd.engines.claude_code.normalise import parse_hook_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "shepherd"
DOCTOR_CAPTURE = (
    REPO_ROOT
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "hooks"
    / "live"
    / "R03_config_unknown_event_name"
    / "doctor.txt"
)

RECEIVED_AT = "2026-09-14T10:00:00Z"

#: The four fields C8 proves are on **every** event, and nothing else.
COMMON: Mapping[str, str] = {
    "session_id": "s-1",
    "transcript_path": "/root/.claude/projects/p/s-1.jsonl",
    "cwd": "/tmp/work",
}


def doctor_event_names() -> tuple[str, ...]:
    """The 33 names, parsed from the capture that lists them (G13)."""
    text = DOCTOR_CAPTURE.read_text(encoding="utf-8")
    listed = text[text.index("Valid events:") + len("Valid events:") :]
    return tuple(name.strip() for name in listed.strip().splitlines()[0].split(",") if name.strip())


def payload(event: str, **extra: object) -> bytes:
    body: dict[str, object] = {**COMMON, "hook_event_name": event}
    body.update(extra)
    return json.dumps(body).encode("utf-8")


def parsed(event: str, **extra: object) -> Signal:
    signal = parse_hook_payload(payload(event, **extra), RECEIVED_AT)
    assert isinstance(signal, Signal), signal
    return signal


# ----- totality (Table A is total over the 33 names) -----------------------


def test_normalise_all_33_event_names() -> None:
    names = doctor_event_names()
    assert len(names) == 33
    assert names == ALL_HOOK_EVENT_NAMES
    for name in names:
        signal = parse_hook_payload(payload(name), RECEIVED_AT)
        assert isinstance(signal, Signal), f"{name} did not normalise"
        assert signal.raw_kind == name


def test_every_engine_event_maps_to_a_kind() -> None:
    """Total over the 33 names **plus** the unrecognised case (r5)."""
    kinds = {name: parsed(name).kind for name in doctor_event_names()}
    assert set(kinds.values()) <= set(SignalKind)
    assert SignalKind.UNKNOWN not in set(kinds.values())
    assert parsed("NoSuchEventName").kind is SignalKind.UNKNOWN


def test_fields_only_ever_carry_neutral_keys() -> None:
    samples = [
        parsed("SessionStart", source="startup"),
        parsed("UserPromptSubmit", prompt="hello"),
        parsed("PreToolUse", tool_name="Bash", tool_input={"command": "ls"}),
        parsed("PostToolUse", tool_name="Write", tool_input={"file_path": "/tmp/work/a.txt"}),
        parsed("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf /"}),
        parsed("Notification", notification_type="idle_prompt", message="waiting"),
        parsed("SubagentStart", agent_id="a1", agent_type="general-purpose"),
        parsed("TaskCreated", task_id="1"),
        parsed("CwdChanged", old_cwd="/tmp/work", new_cwd="/tmp/work/sub"),
        parsed("PreModelSwitch", to_model="claude-sonnet-5"),
        parsed("StopFailure", error="model_not_found"),
        parsed("FileChanged", file_path="/tmp/work/watched.txt"),
    ]
    for signal in samples:
        for key in signal.fields:
            assert key in SIGNAL_FIELD_KEYS, f"{signal.raw_kind} projected {key!r}"


# ----- C8: the receiver stamps the time, the payload never does ------------


def test_normalise_stamps_nothing() -> None:
    signal = parsed("Stop")
    assert signal.received_at == RECEIVED_AT
    other = parse_hook_payload(payload("Stop"), "2031-01-01T00:00:00Z")
    assert isinstance(other, Signal)
    assert other.received_at == "2031-01-01T00:00:00Z"


def test_the_four_common_fields_are_carried_and_the_rest_degrade() -> None:
    signal = parsed("Stop")
    assert signal.engine_session_id == "s-1"
    assert signal.cwd == "/tmp/work"
    assert signal.transcript_path == COMMON["transcript_path"]
    # every other field is optional; absence degrades, it is never an error (C8)
    thin = parse_hook_payload(
        json.dumps({"session_id": "s-2", "hook_event_name": "Stop"}).encode("utf-8"), RECEIVED_AT
    )
    assert isinstance(thin, Signal)
    assert thin.cwd == ""
    assert thin.transcript_path == ""


# ----- the per-event projections -------------------------------------------


def test_session_start_projects_its_source() -> None:
    assert parsed("SessionStart", source="resume").fields.get("start_source") == "resume"
    assert parsed("SessionStart").fields.get("start_source") is None


def test_prompt_is_projected_verbatim() -> None:
    assert parsed("UserPromptSubmit", prompt="Say hi.").fields.get("prompt") == "Say hi."


def test_posttooluse_projects_edit_and_write_paths_only() -> None:
    """C9: `repos_touched` comes from the agent's own edits, not from watches."""
    written = parsed("PostToolUse", tool_name="Write", tool_input={"file_path": "/tmp/work/a.txt"})
    assert written.fields.get("changed_paths") == ("/tmp/work/a.txt",)
    edited = parsed("PostToolUse", tool_name="Edit", tool_input={"file_path": "/tmp/work/b.txt"})
    assert edited.fields.get("changed_paths") == ("/tmp/work/b.txt",)
    ran = parsed("PostToolUse", tool_name="Bash", tool_input={"command": "echo hi"})
    assert ran.fields.get("changed_paths") is None
    assert ran.kind is SignalKind.TOOL_FINISHED


def test_filechanged_projects_the_declared_watch_path() -> None:
    signal = parsed("FileChanged", file_path="/tmp/work/watched.txt")
    assert signal.kind is SignalKind.FILES_CHANGED
    assert signal.fields.get("changed_paths") == ("/tmp/work/watched.txt",)


def test_cwd_changed_projects_the_neutral_key_not_the_engine_spelling() -> None:
    signal = parsed("CwdChanged", old_cwd="/tmp/work", new_cwd="/tmp/work/sub")
    assert signal.kind is SignalKind.CWD_CHANGED
    assert signal.fields.get("next_cwd") == "/tmp/work/sub"
    assert "new_cwd" not in dict(signal.fields)


def test_model_switch_projects_the_destination_model() -> None:
    for event in ("PreModelSwitch", "PostModelSwitch"):
        signal = parsed(event, from_model="claude-haiku-4-5", to_model="claude-sonnet-5")
        assert signal.kind is SignalKind.MODEL_CHANGED
        assert signal.fields.get("model") == "claude-sonnet-5"


def test_stop_failure_projects_the_error_as_a_failure_note() -> None:
    signal = parsed("StopFailure", error="model_not_found")
    assert signal.kind is SignalKind.STOP_FAILED
    assert signal.fields.get("failure_note") == "model_not_found"


def test_stop_and_session_end_both_stop_the_session() -> None:
    """Two kinds since r3 BLOCKING 1, and both still stop the session — the
    split is one cell wide (the compaction mark), which is why the golden
    table cannot move."""
    assert parsed("Stop", stop_hook_active=False).kind is SignalKind.TURN_STOPPED
    assert parsed("SessionEnd", reason="clear").kind is SignalKind.SESSION_STOPPED
    from shepherd.core.states import SessionState
    from shepherd.signals.fold import fold

    for signal in (parsed("Stop"), parsed("SessionEnd", reason="clear")):
        assert fold(signal, None, RECEIVED_AT).delta.state is SessionState.STOPPED


def test_no_rule_keys_on_a_stop_reason_field() -> None:
    """D46/E9: `Stop.stop_reason` does not exist. Inventing it is the bug."""
    with_invention = parsed("Stop", stop_reason="completed")
    without = parsed("Stop")
    assert with_invention.kind is without.kind
    assert dict(with_invention.fields) == dict(without.fields)


# ----- the two asks (Decision pressure 3, C21) -----------------------------


def test_permission_request_ask_names_the_tool() -> None:
    signal = parsed("PermissionRequest", tool_name="Bash", tool_input={"command": "git push"})
    assert signal.kind is SignalKind.NEEDS_INPUT
    ask = signal.fields.get("ask")
    assert isinstance(ask, str)
    assert ask.startswith("permission: Bash(")
    assert "git push" in ask


def test_idle_prompt_and_permission_prompt_are_different_asks() -> None:
    idle = parsed("Notification", notification_type="idle_prompt", message="Claude is waiting")
    permission = parsed(
        "Notification",
        notification_type="permission_prompt",
        message="Claude needs your permission",
    )
    assert idle.kind is SignalKind.NEEDS_INPUT
    assert permission.kind is SignalKind.NEEDS_INPUT
    assert idle.fields.get("ask") == "idle — waiting for your next instruction"
    assert permission.fields.get("ask") == "Claude needs your permission"
    assert idle.fields.get("ask") != permission.fields.get("ask")


def test_unmapped_notification_types_are_a_counted_unknown() -> None:
    signal = parsed("Notification", notification_type="auth_success", message="ok")
    assert signal.kind is SignalKind.NOTICE_UNMAPPED
    assert signal.fields.get("ask") is None


def test_elicitation_asks_and_its_result_resolves() -> None:
    ask = parsed("Elicitation", message="What name should the probe use?", mode="form")
    assert ask.kind is SignalKind.NEEDS_INPUT
    assert ask.fields.get("ask") == "What name should the probe use?"
    assert parsed("ElicitationResult", action="cancel").kind is SignalKind.INPUT_RESOLVED
    denied = parsed("PermissionDenied", reason="[Data Exfiltration]")
    assert denied.kind is SignalKind.INPUT_RESOLVED


# ----- C10: the internal subagent -----------------------------------------


def test_subagent_start_and_stop_pair_on_the_neutral_id() -> None:
    started = parsed("SubagentStart", agent_id="a7154de3fc719065c", agent_type="general-purpose")
    stopped = parsed("SubagentStop", agent_id="a7154de3fc719065c", agent_type="general-purpose")
    assert started.kind is SignalKind.SUBAGENT_STARTED
    assert stopped.kind is SignalKind.SUBAGENT_FINISHED
    assert started.fields.get("subagent_id") == stopped.fields.get("subagent_id")


def test_internal_subagent_stops_carry_no_id_to_pair_on() -> None:
    """C10: `agent_type: ""` internal stops have no `SubagentStart` (2 of 4)."""
    internal = parsed("SubagentStop", agent_id="ace5bce6e251be370", agent_type="")
    assert internal.kind is SignalKind.SUBAGENT_FINISHED
    assert internal.fields.get("subagent_id") is None


# ----- malformed input is a value, never a raise (principle 5) -------------


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json at all",
        b"[1, 2, 3]",
        b'"a string"',
        b"{}",
        json.dumps({"hook_event_name": "Stop"}).encode("utf-8"),
        json.dumps({"session_id": "s-1"}).encode("utf-8"),
        json.dumps({"session_id": 7, "hook_event_name": "Stop"}).encode("utf-8"),
        b"\xff\xfe\x00",
    ],
)
def test_unparseable_payloads_are_counted_not_raised(raw: bytes) -> None:
    result = parse_hook_payload(raw, RECEIVED_AT)
    assert isinstance(result, MalformedPayload)
    assert result.received_at == RECEIVED_AT
    assert result.raw_len == len(raw)
    assert result.reason


# ----- the boundary this task exists to hold -------------------------------


def _string_literals(path: Path) -> set[str]:
    return {
        node.value
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_normaliser_owns_every_engine_field_name() -> None:
    """r4: the asks and every engine field name are composed in `engines/`."""
    composed = _string_literals(SRC_ROOT / "engines" / "claude_code" / "normalise.py")
    for literal in ("tool_input", "file_path", "to_model", "agent_id", "agent_type", "new_cwd"):
        assert literal in composed, literal

    in_signals: set[str] = set()
    for module in sorted((SRC_ROOT / "signals").rglob("*.py")):
        in_signals |= _string_literals(module)
    for literal in (
        "tool_input",
        "file_path",
        "to_model",
        "agent_id",
        "agent_type",
        "new_cwd",
        "notification_type",
    ):
        # NB: the *ask sentences* are not engine field names — `signals/
        # discovery_loop.py` (T7b) composes the same idle sentence from the
        # registry's observed status, which is the sidecar lane, not this one.
        assert literal not in in_signals, f"{literal!r} leaked into signals/"


def test_idle_prompt_sets_needs_you_with_idle_reason() -> None:
    """Decision pressure 3, end to end: the capture, the fold, the reason.

    The payload is `§Notification payload (TUI: idle_prompt, permission_prompt)`
    — the one captured idle notification, which arrives 60 s after a stop and is
    the only signal that says a session is waiting on you with nothing to answer.
    """
    from shepherd.core.states import SessionState
    from shepherd.signals.fold import fold

    signal = parsed(
        "Notification",
        notification_type="idle_prompt",
        message="Claude is waiting for your input",
    )
    result = fold(signal, None, RECEIVED_AT)
    assert result.delta.state is SessionState.NEEDS_YOU
    assert result.delta.needs_you_reason == "idle — waiting for your next instruction"


# ----- BLOCKER T11-2: the refusal `PostToolBatch` uniquely records ----------

LIVE_CAPTURES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "hooks" / "live"


def captured_post_tool_batches() -> list[Mapping[str, object]]:
    """Every real `PostToolBatch` payload in the corpus, envelopes unwrapped."""
    found: list[Mapping[str, object]] = []
    for path in sorted(LIVE_CAPTURES.glob("*/events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            envelope = json.loads(line)
            if envelope.get("_event") != "PostToolBatch":
                continue
            body = envelope["payload"]
            assert isinstance(body, dict)
            found.append(body)
    return found


def test_post_tool_batch_projects_the_refusal_it_uniquely_records() -> None:
    """`PostToolBatch` is the only event that records a refusal, and Table A
    projected nothing saying one happened — so the fold's Table B row could not
    count it (BLOCKER T11-2).

    Classification is by the engine's own **literal** refusal sentences, read
    out of the 40 captures. It is not a reading of prose for meaning: that is
    M2's heuristic territory, and a wording we have not captured projects
    nothing, so the counter under-counts rather than inventing.

    The expected counts come from the corpus itself, not from the classifier:
    40 batches, of which exactly one carries the `PreToolUse:Bash hook error:
    … exit 2` response (R01_exit_codes) and seven carry a permission sentence.
    """
    batches = captured_post_tool_batches()
    assert len(batches) == 40

    kinds: list[object] = []
    for body in batches:
        signal = parse_hook_payload(json.dumps(body).encode("utf-8"), RECEIVED_AT)
        assert isinstance(signal, Signal)
        assert signal.kind is SignalKind.TOOL_BATCH_FINISHED
        for key in signal.fields:
            assert key in SIGNAL_FIELD_KEYS, f"projected {key!r}"
        kinds.append(signal.fields.get("refusal"))

    assert kinds.count("hook_block") == 1
    assert kinds.count("permission") == 7
    assert kinds.count(None) == 32


def test_the_fold_counts_a_refused_batch_as_its_own_anomaly() -> None:
    """Principle 5: an anomaly that cannot be named cannot be counted, and
    `doctor` must tell a hook block from a permission refusal (BLOCKER T11-2)."""
    from shepherd.core.anomalies import AnomalyKind
    from shepherd.signals.fold import fold

    ordinary = parse_hook_payload(
        json.dumps(
            {
                **COMMON,
                "hook_event_name": "PostToolBatch",
                "tool_calls": [
                    {"tool_name": "Bash", "tool_response": "hello"},
                ],
            }
        ).encode("utf-8"),
        RECEIVED_AT,
    )
    assert isinstance(ordinary, Signal)
    assert fold(ordinary, None, RECEIVED_AT).anomalies == ()

    blocked = next(
        body
        for body in captured_post_tool_batches()
        if any(
            "hook error:" in str(call.get("tool_response", ""))
            for call in body.get("tool_calls", [])  # type: ignore[union-attr]
        )
    )
    signal = parse_hook_payload(json.dumps(blocked).encode("utf-8"), RECEIVED_AT)
    assert isinstance(signal, Signal)
    anomalies = fold(signal, None, RECEIVED_AT).anomalies
    assert [anomaly.kind for anomaly in anomalies] == [AnomalyKind.TOOL_BLOCKED_BY_HOOK]

    denied = parse_hook_payload(
        json.dumps(
            {
                **COMMON,
                "hook_event_name": "PostToolBatch",
                "tool_calls": [
                    {
                        "tool_name": "Bash",
                        "tool_response": (
                            "Permission to use Bash with command rm -f ./nofile.txt"
                            " has been denied."
                        ),
                    }
                ],
            }
        ).encode("utf-8"),
        RECEIVED_AT,
    )
    assert isinstance(denied, Signal)
    denied_anomalies = fold(denied, None, RECEIVED_AT).anomalies
    assert [a.kind for a in denied_anomalies] == [AnomalyKind.TOOL_PERMISSION_REFUSED]


# ----- T10: the three new rows, and the Stop/SessionEnd split --------------


def test_stop_and_session_end_are_different_kinds() -> None:
    """r3 BLOCKING 1: a turn ending and a session ending have different column
    effects now (one clears the compaction mark, the other does not), so
    ADR-6's rule — one `SignalKind` per distinct column effect — gives them
    two members rather than one."""
    turn = parsed("Stop")
    session = parsed("SessionEnd", reason="other")
    assert turn.kind is not session.kind
    assert turn.kind is SignalKind.TURN_STOPPED
    assert session.kind is SignalKind.SESSION_STOPPED


def test_manual_compact_does_not_set_the_mark() -> None:
    """§PreCompact / PostCompact: `trigger` is what separates exhaustion from a
    human typing `/compact`, and only `auto` means the engine ran out of room.

    The `manual` payload is the captured one (`docs/probes/2026-09-14-schemas/`
    `hooks/live/S05_compact/events.jsonl`); `auto` is in the binary enum and
    has never been provoked live, which is why the row reads the value and not
    the event name."""
    auto = parsed("PreCompact", trigger="auto", custom_instructions=None)
    manual = parsed("PreCompact", trigger="manual", custom_instructions=None)
    assert auto.kind is SignalKind.COMPACT_STARTED
    assert manual.kind is SignalKind.COMPACT_FINISHED
    assert parsed("PostCompact", trigger="manual").kind is SignalKind.COMPACT_FINISHED
    assert auto.fields == {} and manual.fields == {}


def test_an_uncaptured_compact_trigger_decides_no_column() -> None:
    """Principle 5: a value nobody has captured may not be allowed to set a
    mark or to clear one. It stays the liveness-only kind M1 gave it."""
    assert parsed("PreCompact", trigger="scheduled").kind is SignalKind.TURN_PROGRESS
    assert parsed("PreCompact").kind is SignalKind.TURN_PROGRESS


def test_quota_notice_reads_only_the_type() -> None:
    """G-M2-1: the three quota values of `notification_type` decide the kind,
    and **no payload field is read** — nothing about the notice's message has
    ever been captured."""
    for value in (
        "quota_auto_resume_fired",
        "quota_auto_resume_stale",
        "quota_auto_resume_disabled",
    ):
        signal = parsed("Notification", notification_type=value, message="anything at all")
        assert signal.kind is SignalKind.QUOTA_NOTICE, value
        assert dict(signal.fields) == {}, value


def test_quota_notice_is_no_longer_an_unmapped_notice() -> None:
    """It was `NOTICE_UNMAPPED`, so the anomaly counter must stop moving for it
    — while every other unmapped type still counts (principle 5 intact)."""
    from shepherd.core.anomalies import AnomalyKind
    from shepherd.signals.fold import fold

    quota = parsed("Notification", notification_type="quota_auto_resume_fired")
    assert fold(quota, None, RECEIVED_AT).anomalies == ()

    other = parsed("Notification", notification_type="auth_success")
    assert other.kind is SignalKind.NOTICE_UNMAPPED
    assert [a.kind for a in fold(other, None, RECEIVED_AT).anomalies] == [
        AnomalyKind.UNMAPPED_NOTICE
    ]


def test_the_session_ending_reason_reaches_the_stop_lane() -> None:
    """BLOCKER T6-1: without a neutral projection the four mechanical endings
    are a tested seam that never runs. The field is `reason` (the spec's
    `end_reason` does not exist on the payload), and the value stays the
    engine's own word — only the adapter's stop map interprets it."""
    for value in ("other", "clear", "prompt_input_exit", "logout", "resume"):
        signal = parsed("SessionEnd", reason=value)
        assert signal.fields.get("end_reason") == value, value
        assert "end_reason" in SIGNAL_FIELD_KEYS
    assert dict(parsed("SessionEnd").fields) == {}, "an absent reason projects nothing"
