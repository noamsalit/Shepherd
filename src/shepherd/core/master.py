"""The orchestrator vocabulary — L1, vendor-free, shared by four packages.

`master/`, `toolsurface/`, `orchestration/` and `web/` all talk about the same
seam, so the words live here once rather than four times. Nothing in this
module runs: it is types, a Protocol, and one curated table of facts.

**Why no vendor name appears below (D32, K13).** A seam that carries a vendor's
shape is the D9 mistake committed inside the fix for it. Every engine word —
the SDK's message classes, its option block, its permission callback, its tool
prefix — lives under `master/` and nowhere else, so a second runtime is one
class rather than a rewrite. `core/` is L1: a vendor import here would put a
208 MB package under every module in the build, including `shepherd status`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, get_args


@dataclass(frozen=True)
class ExportedTool:
    """One tool, described to a model and to nothing else (DP4, DP12).

    Name, description, schema — exactly what a runtime needs to tell a model a
    capability exists. It deliberately carries **no** handler, no audience set
    and no blast class: that is gate vocabulary, and a runtime holding it could
    reason about its own permissions. `toolsurface/export.py` imports this
    downward and projects one per audience.
    """

    name: str
    description: str
    input_schema: Mapping[str, object]


@dataclass(frozen=True)
class MasterCapabilities:
    """§6's record, unchanged — no field added, none removed (DP8).

    Two of these five are values no probe could fill on the first call, which
    is why `CURATED_MASTER_FACTS` exists below instead of a sixth field.
    """

    billing_mode: Literal["seat", "api"]
    owns_history: bool
    owns_compaction: bool
    supports_parallel_tool_calls: bool
    context_window: int


#: One thing a runtime emitted, in our words (ADR-M4-5). `turn_ended` is the
#: terminal kind; `error` is a turn that ended badly and is still a turn.
MasterEventKind = Literal[
    "text",
    "thinking",
    "tool_call",
    "tool_result",
    "turn_ended",
    "rate_limit",
    "error",
]

#: The kinds, enumerated from the domain above rather than restated beside it
#: (K19) — the chat page and the contract suite both iterate this set, and a
#: kind that exists in one place and not the other is a class of output a
#: surface silently drops.
MASTER_EVENT_KINDS: frozenset[str] = frozenset(get_args(MasterEventKind))


@dataclass(frozen=True)
class MasterEvent:
    """Our projection of one runtime event. Both implementations emit these.

    `tool_name` is **our** registered name, never a transport-prefixed one:
    the prefix is a vendor detail and it is stripped in `master/`.
    """

    kind: MasterEventKind
    text: str | None
    tool_name: str | None
    payload: Mapping[str, object]
    occurred_at: str


class MasterRefusal(Exception):
    """The one refusal a master raises upward (RD-T17-2).

    The same shape as `RunnerRefusal` one layer down, and for the same reason: a
    caller of the seam gets **two** cases to handle — a stream of events, or this
    — rather than an open set of builtins. `ScriptedMaster` raised a bare
    `RuntimeError` until T18, which meant the contract suite could only assert on
    the *spelling* of a message, and `pytest.raises(RuntimeError)` is satisfied by
    almost any bug a half-built runtime can produce, including an `AttributeError`
    that is not a refusal at all.

    `reason` is the actionable half and is carried as an attribute rather than
    only inside `args`, exactly as `RunnerRefusal.reason` is.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MasterRuntime(Protocol):
    """The sixth seam. Six members, and the sixth is the flagged one (DP9).

    §6 writes five. `MasterRuntime` as specified **cannot be shut down**: the
    runtime owns a subprocess and a connection, `daemons/shutdown.py` has to
    end both, and without a verb here it would have to reach past the seam into
    an implementation — which is the private path D19 exists to prevent. So
    `close()` is a sixth member, flagged as a difference from §6 rather than
    slipped in.
    """

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        """Mount the tool set and the frozen prompt.

        **The one genuine widening of a §6 signature (DP12).** §6 writes the
        gate's own tool record here, and that is impossible under D19: the
        record lives at L4, which a master may not import. The seam therefore
        gets *less* of our shape, which is the direction D32 pushes.
        """

    def send(self, text: str) -> AsyncIterator[MasterEvent]:
        """One turn: everything it streams, until a terminal event.

        **Async, exactly as §6:472 writes it** (DP12). A synchronous iterator
        here would need a hidden loop thread and a queue behind it; instead the
        turn driver owns one loop per turn, on a worker thread it tears down
        with the turn, so this build starts no loop and no thread at boot.
        """

    def resume(self, master_session_id: str) -> None:
        """Continue a conversation. The id is opaque and the runtime owns what
        it means."""

    def interrupt(self) -> None:
        """End the turn in flight."""

    def capabilities(self) -> MasterCapabilities: ...

    def close(self) -> None:
        """Release the runtime's process and connection (DP9). Idempotent:
        shutdown must be able to call it after an already-failed turn."""


@dataclass(frozen=True)
class CuratedFact:
    """A value, and where it was measured. The source is not decoration.

    DP8: a capability record that invents a field on the first call is worse
    than one that says it does not know, so every value here names the capture
    or the spec line it came from, and `test_every_curated_fact_names_its_source`
    goes red on an empty one. That assertion is what stops this table quietly
    growing a guess.
    """

    value: bool | int | str
    source: str


#: The five facts a runtime cannot answer before its first turn, curated from
#: the 2026-09-14 probe captures. Keyed by `MasterCapabilities` field name; the
#: test compares the key set to the dataclass's own fields, enumerated.
#:
#: **Pinned three versions back (G-M4-1).** These captures are SDK 0.2.152 /
#: bundled CLI 2.1.259; this host runs 0.2.153 / 2.1.273. T1/P1 re-runs them.
CURATED_MASTER_FACTS: Mapping[str, CuratedFact] = {
    "billing_mode": CuratedFact(
        value="seat",
        source=(
            "docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/auth-context.txt"
            " (no ANTHROPIC_* in the calling shell) with the handshake in"
            " docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl"
            " — account.subscriptionType='Claude Max', apiProvider='firstParty' (D30)."
            " Per-turn cost is still reported at list price, so a surface that"
            " shows it on a seat shows a notional number."
        ),
    ),
    "owns_history": CuratedFact(
        value=True,
        source=(
            "docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/"
            " — the engine wrote the conversation to disk itself"
            " (two transcript-*.jsonl files) and resumed from it; spec §6 D30."
        ),
    ),
    "owns_compaction": CuratedFact(
        value=True,
        source=(
            "orchestrator-platform.md §6 (the paragraph under MasterCapabilities):"
            " the engine trims its own context, which is why the second"
            " implementation would have to and this one does not."
            " Asserted by the spec, not by a capture — no probe ran long enough"
            " to watch a compaction."
        ),
    ),
    "supports_parallel_tool_calls": CuratedFact(
        value=False,
        source=(
            "never observed: data-schemas.md §Not verified — 'the model never"
            " emitted parallel tool_use blocks' across"
            " docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/."
            " False is the honest reading of an unobserved capability; a True"
            " here would be a guess the first turn could contradict."
        ),
    ),
    "context_window": CuratedFact(
        value=200000,
        source=(
            "docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl"
            " — modelUsage[<model>].contextWindow = 200000,"
            " available only **after** the first turn, which is why it is"
            " curated here rather than asked of a fresh runtime."
        ),
    ),
}
