"""T18's terminal half: the four capabilities that touch a pane, and the handle.

Split out of `tools_m3.py` rather than raising its size cap — the eighth time
this repo has taken that trade, and the halves are two jobs: *drive a session*
(spawn, send, ask, interrupt, kill, answer) versus *drive its terminal* (the
bytes, the keystrokes, the geometry, the stream). Both halves are size-asserted
so the split cannot hide growth.

Three rules are load-bearing here:

* **Nothing is reimplemented.** `toolsurface/` is L4: it composes the `Runner`
  seam and the store's verbs, and it owns no pane vocabulary. There is no tmux
  word in this file and no argv is built here.
* **Bytes are bytes.** `snapshot()` returns what the capture returned, escapes
  and all; the only transform on the way out is base64, because JSON has no
  byte type. It is never decoded, escaped and re-encoded — that is exactly the
  round trip T19's first-frame test goes red on.
* **A projection, never a row.** Every handler returns an explicit dict of
  named fields. A store dataclass is never returned and never spread (§13).

**D40, and why `terminal_write` is `local_write` rather than destructive.** These
are a *human's* keystrokes at a terminal they are looking at, which §13 allows at
both ownership levels; the audience is `HUMAN` alone, so no master and no tier-2
session can reach a pane this way. The write **policy** — whose question is
"should anything be typed here at all" — is `orchestration/write_policy.py`'s and
is not consulted here, because a human typing is not a programmatic write.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from shepherd.core.runner import RunnerHandle
from shepherd.core.states import Ownership
from shepherd.engines.claude_code.transcript import locate_transcript
from shepherd.engines.claude_code.transcript_tail import read_tail
from shepherd.runner.base import ByteStream, Runner
from pathlib import Path

from shepherd.store.db import Store
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolArgumentRefused,
    ToolArgs,
    ToolDef,
    arg_str,
)

__all__ = [
    "EVERY_AUDIENCE",
    "HUMAN_ONLY",
    "SNAPSHOT_SCROLLBACK",
    "TerminalStream",
    "build_terminal_tools",
    "handle_for",
    "kill_landed",
    "no_pane",
    "session_output",
]

#: `get_session_output` is the one capability here every audience may call:
#: reading what a session said is not typing at it (Task 18's table).
EVERY_AUDIENCE = frozenset({Audience.MASTER, Audience.SESSION, Audience.HUMAN})

#: D40: a human's keystrokes at a terminal. `web/` and `cli/` are `HUMAN`
#: (ADR-3), and nothing else may reach a pane through these four.
HUMAN_ONLY = frozenset({Audience.HUMAN})

#: The depth `terminal_snapshot` reaches back by default. **A depth, not a row
#: count** (T9-1): no caller here derives a number of lines from it, and the
#: answer always carries the whole visible pane as well.
SNAPSHOT_SCROLLBACK = 2000


def handle_for(store: Store, session_id: str) -> RunnerHandle | None:
    """Where this session's pane lives, or `None` — a value, never a raise.

    `None` covers three different worlds a caller cannot act on differently: no
    such row, an **attached** row (which has no pane of ours by definition), and
    an owned row whose handle is missing, which is T12's orphan. The projections
    say which by naming the session rather than by inventing a third state.
    """
    row = store.get_owned_session(session_id)
    return None if row is None else row.runner_handle


def no_pane(session_id: str) -> dict[str, object]:
    """The one shape every terminal tool answers with when there is no pane.

    A value a page can render — principle 5 — rather than an exception that
    `invoke()` would flatten into the generic literal, where a human would be
    told "request failed" for a session that simply is not ours to type into.
    """
    return {
        "session_id": session_id,
        "ok": False,
        "reason": (
            f"{session_id}: no owned pane — the session is unknown, attached, or its"
            " handle is gone (an orphan)"
        ),
    }


def kill_landed(answer: Mapping[str, object]) -> bool:
    """Did that `kill(...)` answer say the session stopped?

    **One reader, spelled beside the answers it reads.** This was a closure in
    the composition root reading `answer.get("killed")` — a string key spelled
    in two files, in a function no test could reach. Renaming the key on the
    producer's side would have left the adapter answering `False` **forever and
    silently**: every `kill_sessions` project delete would refuse, and the suite
    would have had nothing to say about it.

    `False` for `no_pane(...)` above, which carries no `"killed"` key at all and
    is what the kill path answers for any session it has no runner handle for —
    which is every *attached* one. That `False` is the truth, and
    `commit_project_delete` refuses on it rather than deleting a live session's
    rows.

    **Here rather than in `tools_m3.py`, beside `kill` itself**, for one
    measured reason: that module is at 445 of the 450-line cap and this
    docstring does not fit under it. `no_pane` — the answer with no key, and the
    branch this predicate exists for — is the thing it is now beside.
    """
    return answer.get("killed") is True


@dataclass(frozen=True)
class TerminalStream:
    """ADR-M3-3's handle: the first frame, then the live ones, then the stop.

    **`snapshot` is carried here rather than fetched again by the transport.**
    The stream and the screen it continues have to be taken as one act, or the
    first live chunk can describe a screen the snapshot never showed; and a
    transport that re-derived the snapshot would be the second place that
    decides what "the screen" is. It is the bytes `capture-pane` returned, not
    decoded and not re-encoded (T19's `test_the_first_frame_is_the_snapshot_
    byte_for_byte` is what holds that).
    """

    session_id: str
    snapshot: bytes
    stream: ByteStream

    def chunks(self) -> Iterator[bytes]:
        """The live frames, in order, until the stream closes."""
        return self.stream.chunks()

    def close(self) -> None:
        """Stop reading. Idempotent, because `ByteStream.close` is."""
        self.stream.close()


def _decode_base64(value: str, field: str) -> bytes:
    """JSON has no byte type, so the wire carries base64 and this is the seam.

    A refusal rather than a crash: `ToolArgumentRefused` is the one failure mode
    whose message is the caller's **own** value described back to them, which is
    what lets `cli/` render usage advice instead of "request failed".
    """
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ToolArgumentRefused(
            f"{field} is not base64; a terminal payload is bytes and the wire carries"
            " them base64-encoded"
        ) from None


def _arg_int(args: ToolArgs, key: str) -> int:
    value = args[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"argument {key!r} is not an integer")
    return value


def _arg_optional_int(args: ToolArgs, key: str, default: int) -> int:
    return default if args.get(key) is None else _arg_int(args, key)


# ----- the four handlers ------------------------------------------------------


def terminal_snapshot(
    store: Store, runner: Runner, session_id: str, scrollback: int
) -> dict[str, object]:
    """The pane's bytes, base64 in JSON and raw over the WebSocket."""
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    raw = runner.snapshot(handle, scrollback)
    return {
        "session_id": session_id,
        "ok": True,
        "encoding": "base64",
        "bytes": base64.b64encode(raw).decode("ascii"),
        "byte_count": len(raw),
    }


def terminal_write(
    store: Store, runner: Runner, session_id: str, data: bytes
) -> dict[str, object]:
    """D40: a human's keystrokes, allowed at both ownership levels."""
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    runner.write(handle, data)
    return {"session_id": session_id, "ok": True, "written": len(data)}


def terminal_resize(
    store: Store, runner: Runner, session_id: str, cols: int, rows: int
) -> dict[str, object]:
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    runner.resize(handle, cols, rows)
    return {"session_id": session_id, "ok": True, "cols": cols, "rows": rows}


def terminal_stream(
    store: Store, runner: Runner, session_id: str, scrollback: int
) -> TerminalStream | dict[str, object]:
    """The handle. The snapshot is taken **before** the attach, so no byte the
    live stream will deliver can already have been in the screen it continues."""
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    raw = runner.snapshot(handle, scrollback)
    return TerminalStream(session_id=session_id, snapshot=raw, stream=runner.attach(handle))


def session_output(
    *, store: Store, runner: Runner, projects_root: Path, session_id: str, scrollback: int
) -> dict[str, object]:
    """N12: the **screen** for an owned session, the transcript tail otherwise.

    §11 called this "pty tail (owned)", and N12 corrected it: a tail of ANSI
    diff-render bytes is not readable text. For a pane we own the answer is what
    a human means by "what does it say" — the capture. An **attached** session
    has no pane of ours at all, so the answer comes from M2's transcript reader,
    and the `source` field says which of the two a caller got rather than
    leaving them to infer it from the shape (principle 5).

    K14: the transcript is the engine's own file, not one of Shepherd's logs.
    Nothing here can reach `shepherd.logs` — `tests/boundaries/
    test_consumer_boundary.py` scans `toolsurface/` for exactly that.
    """
    row = store.get_owned_session(session_id)
    if row is None:
        return {"session_id": session_id, "source": "unknown", "found": False, "text": None}
    handle = row.runner_handle
    if row.ownership is Ownership.OWNED and handle is not None:
        return {
            "session_id": session_id,
            "source": "pane",
            "found": True,
            "text": runner.snapshot(handle, scrollback).decode("utf-8", errors="replace"),
        }
    transcript = (
        None
        if row.engine_session_id is None
        else locate_transcript(projects_root, row.engine_session_id)
    )
    if transcript is None:
        return {"session_id": session_id, "source": "transcript", "found": False, "text": None}
    tail, _ = read_tail(transcript)
    return {
        "session_id": session_id,
        "source": "transcript",
        "found": True,
        "text": tail.last_assistant_text,
    }


# ----- the tools --------------------------------------------------------------

_SESSION_AND_SCROLLBACK: dict[str, object] = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "scrollback": {"type": "integer"},
    },
    "required": ["session_id"],
}


def build_terminal_tools(
    store: Store, runner: Runner, projects_root: Path
) -> tuple[ToolDef, ...]:
    """The five, with their dependencies closed over (D32)."""
    return (
        ToolDef(
            name="get_session_output",
            description="The pane's screen for an owned session, the transcript tail otherwise.",
            input_schema=_SESSION_AND_SCROLLBACK,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: session_output(
                store=store,
                runner=runner,
                projects_root=projects_root,
                session_id=arg_str(args, "session_id"),
                scrollback=_arg_optional_int(args, "scrollback", SNAPSHOT_SCROLLBACK),
            ),
            audiences=EVERY_AUDIENCE,
        ),
        ToolDef(
            name="terminal_snapshot",
            description="The pane's current bytes, base64-encoded for JSON.",
            input_schema=_SESSION_AND_SCROLLBACK,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: terminal_snapshot(
                store,
                runner,
                arg_str(args, "session_id"),
                _arg_optional_int(args, "scrollback", SNAPSHOT_SCROLLBACK),
            ),
            audiences=HUMAN_ONLY,
        ),
        ToolDef(
            name="terminal_write",
            description="Send a human's keystrokes to the pane (D40).",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "data": {"type": "string"},
                },
                "required": ["session_id", "data"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: terminal_write(
                store,
                runner,
                arg_str(args, "session_id"),
                _decode_base64(arg_str(args, "data"), "data"),
            ),
            audiences=HUMAN_ONLY,
        ),
        ToolDef(
            name="terminal_resize",
            description="Set the pane's geometry.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "cols": {"type": "integer"},
                    "rows": {"type": "integer"},
                },
                "required": ["session_id", "cols", "rows"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: terminal_resize(
                store,
                runner,
                arg_str(args, "session_id"),
                _arg_int(args, "cols"),
                _arg_int(args, "rows"),
            ),
            audiences=HUMAN_ONLY,
        ),
        ToolDef(
            name="terminal_stream",
            description="A live terminal handle: the snapshot, then the frames (ADR-M3-3).",
            input_schema=_SESSION_AND_SCROLLBACK,
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: terminal_stream(
                store,
                runner,
                arg_str(args, "session_id"),
                _arg_optional_int(args, "scrollback", SNAPSHOT_SCROLLBACK),
            ),
            audiences=HUMAN_ONLY,
        ),
    )
