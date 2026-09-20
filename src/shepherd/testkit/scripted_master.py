"""`ScriptedMaster` — the `MasterRuntime` seam's `Scripted*` double (§14.2, T17).

A **concrete peer** of `AgentSDKMaster`, never a base class: nothing inherits
from it, nothing here grows toward the real thing, and every answer comes from
the `Turn` script it was constructed with. It replays that script in
milliseconds with no process spawned, no socket opened, no clock read and no
tokens spent — which is what lets the `MasterRuntime` contract suite exist and
bite *before* the vendor implementation is written (§14.2's second reason,
which is the important one: a `ScriptedMaster` is the cheapest second caller of
the interface, and `mount_tools(mcp_servers)` is the shape it would have caught
in an afternoon).

**It is not a mock, not a stub, and not "the simple version to start from."**
Nothing here records call expectations and nothing here can fail a test by
itself: `sent`, `resumed`, `configured_tools`, `interrupts` and `closed` are a
**record a test may read**, exactly as `ScriptedRunner.writes` is. No member
returns a bare `None` to get past a caller — the two that answer nothing useful
(`resume`, `interrupt`) both change what the next event is.

**Six members, and the sixth has teeth (DP9).** §6 writes five; `close()` is
the flagged addition, and after it `send()` refuses. That refusal is what makes
the contract suite able to ask both implementations the same shutdown question
and get a comparable answer, rather than "the scripted one shrugs."

**`send()` is async exactly as §6:472 writes it (DP12)** — an async generator,
so this module starts no loop and no thread: the caller owns the loop.

Ships with the package, in `testkit/`, which is deliberately not a layer in
ADR-1's map.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from shepherd.core.master import (
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterEventKind,
    MasterRefusal,
)

#: Every scripted event carries this stamp. A fixture is not an observation, so
#: the double does not read a clock to invent one (P22 keeps the wall clock in
#: `core/clock.py`; a second speller is a second format). `ScriptedHost` names
#: its `observed_at` default for the same reason.
SCRIPTED_OCCURRED_AT = "1970-01-01T00:00:00+00:00"

#: The capability record a script honestly has. Not a copy of
#: `CURATED_MASTER_FACTS`: those are measurements of the *vendor* runtime, and a
#: double that claimed them would let a caller pass this suite while relying on
#: a shape only the SDK has. A script owns no history — `resume()` restores
#: nothing — compacts nothing, and calls no tools in parallel. `billing_mode`
#: has no third spelling in §6's `Literal`, and `"api"` is the closer of the two
#: to "no seat is being consumed here"; a test that needs a seat hands its own
#: record to the constructor.
SCRIPTED_CAPABILITIES = MasterCapabilities(
    billing_mode="api",
    owns_history=False,
    owns_compaction=False,
    supports_parallel_tool_calls=False,
    context_window=200000,
)


@dataclass(frozen=True)
class Turn:
    """One scripted turn: what the master says, and what it asks to call.

    §14.2's example, in its own words::

        ScriptedMaster([
            Turn(says="Two sessions need you.",
                 calls=[("fleet_summary", {}),
                        ("kill_session", {"id": "ses_7f3k"})]),
        ])

    The arguments are carried **as handed over** and emitted on the
    `tool_call` event's payload. There is deliberately no `results` field: the
    double says a call was asked for and stops there, and the **suite** decides
    what the call did. That division is what lets one suite drive both
    implementations — a double that ran tools would be answering the question
    the gate exists to answer.
    """

    says: str
    calls: Sequence[tuple[str, Mapping[str, object]]] = field(default_factory=tuple)
    #: The kind the turn's terminal event carries (RD-T17-3). **Defaulted, so
    #: every construction written before this field existed is unchanged.**
    #:
    #: T17 measured that a `Turn` of `says` + `calls` can script only three of
    #: ADR-M4-5's seven kinds, which left `error` — *"a turn that ended badly and
    #: is still a turn"* — unscriptable, and a contract suite that cannot ask
    #: either implementation what happens on a failed turn proves the happy path
    #: and calls it a contract. One field makes the terminal kind the script's to
    #: choose.
    #:
    #: It is not validated here. A script that ends on a kind that does not end a
    #: turn is a **negative control** the contract suite drives its own terminal
    #: row with, and a double that refused the arrangement would take that proof
    #: away.
    ends: MasterEventKind = "turn_ended"


def _event(
    kind: MasterEventKind,
    *,
    text: str | None = None,
    tool_name: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> MasterEvent:
    return MasterEvent(
        kind=kind,
        text=text,
        tool_name=tool_name,
        payload={} if payload is None else payload,
        occurred_at=SCRIPTED_OCCURRED_AT,
    )


class ScriptedMaster:
    """The six `MasterRuntime` members, answered from a list of `Turn`s.

    `turns` is walked once: the first `send()` replays the first turn, the
    second the second, and a send past the end is **refused**. A double that
    repeated its last turn forever would answer a question it was never given,
    and a caller could pass a contract suite having sent twice as many turns as
    it was scripted for.
    """

    def __init__(
        self, turns: Sequence[Turn], capabilities: MasterCapabilities | None = None
    ) -> None:
        self._turns: tuple[Turn, ...] = tuple(turns)
        self._capabilities = SCRIPTED_CAPABILITIES if capabilities is None else capabilities
        self._interrupted = False
        #: The observation channel — read by a test, never asserted by this class.
        self.configured_tools: tuple[ExportedTool, ...] = ()
        self.system_prompt: str | None = None
        self.sent: list[str] = []
        self.resumed: list[str] = []
        self.interrupts = 0
        self.closed = False

    # ----- the six members ---------------------------------------------------

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        """Recorded **exactly** as handed over: no normalising of the prompt.

        A double that stripped or re-wrapped here would let a real runtime that
        mangles the frozen prompt pass the suite this member exists to make
        meaningful.
        """
        self.configured_tools = tools
        self.system_prompt = system_prompt

    async def send(self, text: str) -> AsyncIterator[MasterEvent]:
        """One turn's events, in script order, ending on a terminal event.

        `text`, then one `tool_call` per scripted call, then the terminal event
        the turn's `ends` names — `turn_ended` unless the script said otherwise
        (RD-T17-3). The prompt is recorded rather than consulted: a script does
        not read what it was asked.

        **Refuses with `MasterRefusal`** (RD-T17-2), never a builtin: a contract
        suite that asserted `pytest.raises(RuntimeError)` here would be asserting
        on a spelling, and would stay green against a half-built runtime raising
        something that is not a refusal at all.
        """
        if self.closed:
            raise MasterRefusal(
                "this ScriptedMaster is closed; close() releases the runtime and"
                " send() after it is refused (DP9)"
            )
        index = len(self.sent)
        if index >= len(self._turns):
            raise MasterRefusal(
                f"this fixture was given {len(self._turns)} turn(s) and this is"
                f" send #{index + 1}; a script does not repeat its last turn"
            )
        self.sent.append(text)
        turn = self._turns[index]
        self._interrupted = False

        yield _event("text", text=turn.says)
        for name, args in turn.calls:
            if self._interrupted:
                break
            yield _event("tool_call", tool_name=name, payload=args)
        yield _event(turn.ends, payload={"interrupted": self._interrupted})

    def resume(self, master_session_id: str) -> None:
        """The opaque id, recorded. A script owns no history to restore
        (`SCRIPTED_CAPABILITIES.owns_history is False`), so resuming moves the
        cursor nowhere — and the record is how a suite proves the id reached
        the runtime at all."""
        self.resumed.append(master_session_id)

    def interrupt(self) -> None:
        """Ends the turn in flight: the remaining scripted calls are not
        emitted and the terminal event says `interrupted: True`.

        Between events, not mid-event — the same granularity a real runtime has,
        which streams whole blocks. An interrupt with no turn in flight ends
        nothing: the flag is cleared when the next `send()` starts, because a
        turn that was never running cannot have been interrupted.
        """
        self.interrupts += 1
        self._interrupted = True

    def capabilities(self) -> MasterCapabilities:
        return self._capabilities

    def close(self) -> None:
        """Idempotent (DP9): shutdown must be able to call it after an
        already-failed turn."""
        self.closed = True
