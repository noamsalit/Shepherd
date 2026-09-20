"""The chokepoint every consumer crosses (D32, D35, D38, D53, ADR-7).

Five consumers need the same capabilities — the master, a tier-2 session,
`web/`, `cli/` and a queue worker — and every one of them passes through
`invoke()`. A capability absent from this registry has no surface that can
reach it, which is what makes principle 1 structural rather than a discipline.
The watched failure is a prior tool that grew 349 endpoints, each with its own
read logic, until its architecture document no longer described the system.

Three properties, each bought by a measured failure:

* **Every `input_schema` is validated at registration** (D53). `create_sdk_mcp_server`
  passes a schema through unchanged **only** when it has a string `type` *and* a
  `properties` key; any other dict it reads as a `{param: python_type}` map with
  every key required — so a plain, valid `{"type": "object"}` schema is silently
  turned into a different tool. A malformed schema is therefore a startup
  failure, not a tool that misbehaves in one binding and works in another.
* **`invoke()` validates arguments before the handler runs.** One binding
  validated the payload and the other forwarded one missing a required field
  (spec l.1464-1472), so validation that lives in a binding is validation that
  two bindings disagree about.
* **The registry is frozen before the server binds** (ADR-7). It is written by
  exactly one thread at startup and read-only thereafter, which is what makes a
  module-global safe under `ThreadingHTTPServer`.

M1 had **no permission gate and no audit log** (D38). M4 adds them *behind*
`invoke()`, so no file in `web/` or `cli/` changes.

**The order inside `invoke()` is the contract (C-M4-1):** lookup -> audience ->
schema -> **gate** -> (the gate blocks on an approval) -> handler -> audit. The
first three are M1's and produce `Failure.UNAVAILABLE` with **no record**: an
unknown name, a wrong audience and a malformed payload all happen before there
is anything to authorise, and auditing them would turn the log into a request
log an agent can fill with 10 000 lines by guessing names (C-M4-2, D25).

**The gate and the audit sink are installed together or not at all** (DP13,
ADR-M4-9), and with nothing installed `invoke()` **fails closed**: any tool whose
blast class is outside `GATE_FREE_CLASSES` is refused. Revision 1 had two
`None`-defaulted slots meaning *M1's behaviour*, which made D8's "always on" a
property of one composition root instead of a property of this function.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass

from shepherd.core.clock import utc_now

from shepherd.toolsurface.types import (
    AuditRecord,
    AuditSink,
    Authorizer,
    AuthzOutcome,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgumentRefused,
    ToolArgs,
    ToolDef,
    ToolResult,
    actor_kind_of,
)

#: §13 Errors: one generic literal, the same for every failure mode, so a caller
#: cannot use the error text to probe which tools exist or who may call them.
GENERIC_ERROR = "request failed"

#: What the **failure ring** records when the gate denied a call without a
#: reason of its own. Never handed to the caller (`_failure`'s `message` stays
#: generic in that case), and never a second spelling of `export.DENIED_TEXT`:
#: this is `RecordedFailure.detail`, which §13 keeps on our side of the seam.
DENIED = "denied by the gate"

#: ADR-M4-1's `decision` and `result` vocabularies, as values rather than
#: literals spelled at each write site. `decision` is `allow | deny`; `result` is
#: `ok | refused | failed | denied`.
ALLOW = "allow"
DENY = "deny"
DENIED_RESULT = "denied"

#: `Failure` -> the record's `result`. Written out and **total over
#: `set(Failure) | {None}`**, which `test_the_result_vocabulary_is_total_over_
#: failure` asserts by enumerating the enum at test time: a fifth `Failure`
#: member would otherwise be a `KeyError` inside the audit of a call that has
#: already run. `UNAVAILABLE` cannot be reached from here — lookup, audience and
#: schema all return before the gate — and it is written anyway, because a map
#: with a hole in it is a map that decides what happens when the hole is reached.
_RESULT_OF: Mapping[Failure | None, str] = {
    None: "ok",
    Failure.REFUSED: "refused",
    Failure.FAILED: "failed",
    Failure.UNAVAILABLE: "unavailable",
}

#: What the record says about the autonomy level when **this process cannot know
#: it** (K23, and it is the same shape as `ApprovedBy.CLAIMED_HUMAN`).
#:
#: `AuthzOutcome` carries `allowed`, `approved_by`, `approval_id` and `reason`
#: and **not the level the gate read**; `install_chokepoint(authorizer, sink)` is
#: pinned at two parameters; and `invoke()` has no other route to a `Store`. So
#: the level is not available at the one place ADR-M4-1 asks for it. Writing `2`
#: — the default — would be the overclaim K23 is about, in the artefact the next
#: incident is reconstructed from: it would say *this ran at level 2* when the
#: process never asked. `0` is not a member of `AutonomyLevel` ({2, 3}), so a
#: reader can tell *unreported* from *reported*, and
#: `test_the_unreported_autonomy_level_is_not_a_real_level` asserts that against
#: the enum enumerated at test time.
#:
#: **The one-line fix is a field on `AuthzOutcome`** (`types.py`, T3's file, not
#: T6's to change): the authorizer already calls `level()`. Recorded as
#: `docs/plans/m4-blockers/t6.md` §T6-3, owner: router.
UNREPORTED_AUTONOMY_LEVEL = 0

SCHEMA_TYPE_KEY = "type"
SCHEMA_PROPERTIES_KEY = "properties"
SCHEMA_REQUIRED_KEY = "required"
OBJECT_TYPE = "object"

#: JSON Schema `type` -> the Python type `invoke()` accepts for it. `int` is
#: excluded from `number`'s tuple only where `bool` would sneak in: in Python
#: `True` is an `int`, and a boolean forwarded as a count is the exact class of
#: silent mangling D53 exists to stop.
_PRIMITIVES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list, tuple),
}


#: The classes `invoke()` runs with **no chokepoint installed** (DP13, P-M4-19).
#: One member, and it is the whole of the concession: `cli/main.py:188-205`
#: registers exactly `schema_status` and `engine_version` in a process that never
#: composes, both `local_read`, so failing closed refuses nothing that process can
#: do today — and no destructive or external call can run ungated in **any**
#: process. The residue is named rather than hidden: a `local_read` call in a
#: non-composing process is still unaudited (G-M4-17), and D38.1 bars the obvious
#: repair.
GATE_FREE_CLASSES: frozenset[BlastClass] = frozenset({BlastClass.LOCAL_READ})


class SchemaInvalid(Exception):
    """A tool whose `input_schema` would be mangled by a binding (D53)."""


class RegistryFrozen(RuntimeError):
    """`register()` after `freeze_registry()` — ADR-7's one-writer rule."""


_LOCK = threading.Lock()
_TOOLS: dict[str, ToolDef] = {}
_FROZEN = False

#: The gate and the sink, **as one value** (DP13, ADR-M4-9). Two independent
#: slots would make *"a gate with no audit log"* a representable state, and
#: revision 1 had exactly that: two `None`-defaulted slots where `None` meant
#: M1's behaviour. Measured then: `cli/main.py` builds a `CallerContext` and
#: registers tools in a process that **never composes**, so D8's *always on* was
#: a property of one composition root rather than of `invoke()` — and clause 2
#: was self-sealing, because with no gate there is no decision and *no decision,
#: no record* made the silence read as correct.
_CHOKEPOINT: tuple[Authorizer, AuditSink] | None = None


def _as_mapping(value: object) -> Mapping[str, object] | None:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else None


def validate_schema(schema: Mapping[str, object]) -> None:
    """D53's two structural requirements, plus a coherent `required` list."""
    declared = schema.get(SCHEMA_TYPE_KEY)
    if not isinstance(declared, str):
        raise SchemaInvalid(
            f"input_schema needs a string {SCHEMA_TYPE_KEY!r}; a binding would read this dict"
            " as a {param: python_type} map with every key required"
        )
    if declared != OBJECT_TYPE:
        raise SchemaInvalid(f"input_schema {SCHEMA_TYPE_KEY!r} must be {OBJECT_TYPE!r}")
    properties = _as_mapping(schema.get(SCHEMA_PROPERTIES_KEY))
    if properties is None:
        raise SchemaInvalid(
            f"input_schema needs a {SCHEMA_PROPERTIES_KEY!r} object, even when it is empty"
        )
    for name, definition in properties.items():
        entry = _as_mapping(definition)
        if entry is None or not isinstance(entry.get(SCHEMA_TYPE_KEY), str):
            raise SchemaInvalid(f"property {name!r} needs an object with a string type")
    required = schema.get(SCHEMA_REQUIRED_KEY, [])
    if not isinstance(required, (list, tuple)):
        raise SchemaInvalid(f"{SCHEMA_REQUIRED_KEY!r} must be a list of property names")
    for name in required:
        if not isinstance(name, str) or name not in properties:
            raise SchemaInvalid(f"{SCHEMA_REQUIRED_KEY!r} names {name!r}, which is not a property")


def register(tool: ToolDef) -> None:
    """Add one capability. Raises after `freeze_registry()` (ADR-7)."""
    validate_schema(tool.input_schema)
    with _LOCK:
        if _FROZEN:
            raise RegistryFrozen(
                f"the registry was frozen before the server bound; {tool.name!r} is too late"
            )
        if tool.name in _TOOLS:
            raise RegistryFrozen(f"{tool.name!r} is already registered")
        _TOOLS[tool.name] = tool


def freeze_registry() -> None:
    """Called by the composition root before it binds anything (ADR-7)."""
    global _FROZEN
    with _LOCK:
        _FROZEN = True


def reset_registry() -> None:
    """Empty and unfreeze, **and clear the chokepoint**.

    For the same reason it clears the tools: a module global that survives a
    test is a module global that decides the next one. Clearing returns
    `invoke()` to **failing closed**, not to permitting — the cleared state is
    the safe one, which is the property `test_reset_registry_returns_invoke_to_
    failing_closed` asserts.
    """
    global _FROZEN, _CHOKEPOINT
    with _LOCK:
        _TOOLS.clear()
        _FAILURES.clear()
        _FROZEN = False
        _CHOKEPOINT = None


def install_chokepoint(authorizer: Authorizer, sink: AuditSink) -> None:
    """Install the gate and the audit log — **both, in one assignment** (DP13).

    There is no way to set one without the other: this function takes two
    required parameters and it is the only writer of `_CHOKEPOINT`, so *a gate
    with no audit log* is not a value this module can hold. The composition root
    calls it once with `build_authorizer(...)` and `build_audit_sink(...)`;
    until it does, `invoke()` fails closed for everything but
    `GATE_FREE_CLASSES`.
    """
    global _CHOKEPOINT
    with _LOCK:
        _CHOKEPOINT = (authorizer, sink)


def chokepoint() -> tuple[Authorizer, AuditSink] | None:
    """The installed pair, or `None`. Never one half of one."""
    with _LOCK:
        return _CHOKEPOINT


def registered_tools() -> Mapping[str, ToolDef]:
    """A snapshot. The caller never holds the registry's own dict."""
    with _LOCK:
        return dict(_TOOLS)


def _argument_problem(schema: Mapping[str, object], args: Mapping[str, object]) -> str | None:
    """The first reason `args` does not fit `schema`, or `None`."""
    properties = _as_mapping(schema.get(SCHEMA_PROPERTIES_KEY)) or {}
    raw_required = schema.get(SCHEMA_REQUIRED_KEY, [])
    required = list(raw_required) if isinstance(raw_required, (list, tuple)) else []
    for name in required:
        if name not in args:
            return f"missing required argument {name!r}"
    for name, value in args.items():
        definition = _as_mapping(properties.get(name))
        if definition is None:
            return f"unknown argument {name!r}"
        declared = definition.get(SCHEMA_TYPE_KEY)
        accepted = _PRIMITIVES.get(str(declared))
        if accepted is None:
            continue
        if declared != "boolean" and isinstance(value, bool):
            return f"argument {name!r} is a boolean, not {declared!r}"
        if not isinstance(value, accepted):
            return f"argument {name!r} is not {declared!r}"
    return None


@dataclass(frozen=True)
class RecordedFailure:
    """What one printed `correlation_id` resolves to.

    §13 prints an id on every failure; before this, the id was only ever
    formatted into a string — no file, no buffer, nothing that could answer it.
    An id that resolves to nothing is an id that should not be printed. This is
    the smallest thing that makes it resolvable *in this process*; M4's audit
    log (D38) replaces it behind the same reader.
    """

    correlation_id: str
    tool: str
    failure: Failure
    detail: str
    """The exception class name, or the refusal's own message. Never a
    traceback, and never handed to the caller of `invoke()`."""


#: How many failures the ring keeps. Bounded because this is a module global in
#: a long-lived daemon, and an unbounded one is a leak with a nice name.
FAILURE_RING = 64

_FAILURES: dict[str, RecordedFailure] = {}


def _record(ctx: CallerContext, name: str, failure: Failure, detail: str) -> None:
    with _LOCK:
        if len(_FAILURES) >= FAILURE_RING:
            _FAILURES.pop(next(iter(_FAILURES)))
        _FAILURES[ctx.correlation_id] = RecordedFailure(
            correlation_id=ctx.correlation_id, tool=name, failure=failure, detail=detail
        )


def resolve_failure(correlation_id: str) -> RecordedFailure | None:
    """What the id printed to a user means, or `None` if it has aged out."""
    with _LOCK:
        return _FAILURES.get(correlation_id)


def _failure(
    ctx: CallerContext, name: str, kind: Failure, detail: str, message: str = GENERIC_ERROR
) -> ToolResult:
    """§13 Errors: a generic literal and a correlation id. No stack trace, no
    tool name, and the same text whether the tool is missing or forbidden — the
    *kind* is what a consumer branches on, and it is recorded here so the id
    the user is shown resolves to something.

    The one message that is not the literal is `REFUSED`: it describes the
    caller's **own argument** back to them, which reveals nothing about which
    tools exist or who may call them.
    """
    _record(ctx, name, kind, detail)
    return ToolResult(
        ok=False,
        data=None,
        error=f"{message} (correlation_id={ctx.correlation_id})",
        failure=kind,
    )


def invoke(name: str, args: Mapping[str, object], ctx: CallerContext) -> ToolResult:
    """The one path in. M4 adds `authorize()` and the audit log here — behind
    this signature, so no consumer changes (D38's acceptance test)."""
    with _LOCK:
        tool = _TOOLS.get(name)
    if tool is None:
        return _failure(ctx, name, Failure.UNAVAILABLE, "no such tool is registered here")
    if ctx.audience not in tool.audiences:
        return _failure(ctx, name, Failure.UNAVAILABLE, f"not for audience {ctx.audience.value}")
    problem = _argument_problem(tool.input_schema, args)
    if problem is not None:
        return _failure(ctx, name, Failure.UNAVAILABLE, problem)
    installed = chokepoint()
    if installed is None:
        if tool.blast_class not in GATE_FREE_CLASSES:
            # DP13. No gate, so no decision, so no record — and there is no sink
            # to write one to either. §13's generic text: a caller cannot tell
            # this from a tool that does not exist here.
            return _failure(
                ctx, name, Failure.UNAVAILABLE, "no chokepoint is installed in this process"
            )
        return _run(tool, args, ctx)
    authorizer, sink = installed
    started = time.monotonic()
    outcome = authorizer(tool, args, ctx)
    if not outcome.allowed:
        # The gate's own reason — `you declined this`, the timeout text, D54's
        # withdrawal text — reaches the caller, because §11 requires a denial an
        # agent can act on and none of those three texts says anything about
        # which tools exist. The spelling is the authorizer's; this module never
        # writes one.
        denied = _failure(
            ctx,
            tool.name,
            Failure.REFUSED,
            outcome.reason or DENIED,
            message=outcome.reason or GENERIC_ERROR,
        )
        _audit(sink, tool, args, ctx, outcome, DENY, DENIED_RESULT, denied.failure, started)
        return denied
    result = _run(tool, args, ctx)
    _audit(
        sink, tool, args, ctx, outcome, ALLOW, _RESULT_OF[result.failure], result.failure, started
    )
    return result


def _audit(
    sink: AuditSink,
    tool: ToolDef,
    args: ToolArgs,
    ctx: CallerContext,
    outcome: AuthzOutcome,
    decision: str,
    result: str,
    failure: Failure | None,
    started: float,
) -> None:
    """The one record, from the one writer (C-M4-2).

    The sink never raises (E-M4-6) — `build_audit_sink` counts every failure the
    write can produce — so there is no `try` here: one would be a second opinion
    about a contract this module's collaborator already holds, and it would hide
    a sink that started raising.

    **`args` are handed over raw.** §13's redaction is the encoder's, and doing
    it twice would put a second list of secret-shaped keys in the build — the
    defect RD-T4-3 recorded and the QA-prep pass closed: the markers, the
    redaction text and `actor_kind_of` are declared once, in `types.py`, which is
    stdlib-only and so can be imported here without dragging `shepherd.logs` into
    `shepherd status`. This module held the second copy of the actor-kind
    derivation (§T6-4); it now imports it.
    """
    sink(
        AuditRecord(
            at=utc_now(),
            correlation_id=ctx.correlation_id,
            actor_kind=actor_kind_of(ctx),
            actor_id=ctx.caller_id,
            tool=tool.name,
            blast_class=tool.blast_class,
            args=dict(args),
            autonomy_level=UNREPORTED_AUTONOMY_LEVEL,
            decision=decision,
            approved_by=outcome.approved_by,
            approval_id=outcome.approval_id,
            result=result,
            failure=failure,
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )
    )


def _run(tool: ToolDef, args: Mapping[str, object], ctx: CallerContext) -> ToolResult:
    """The handler, and the three ways it ends. Never reached before the gate
    has answered (C-M4-1).

    **The handler is handed `ctx`** (D1 of the M1-M4 QA pass). It used to be
    handed the arguments alone, so a tool registered once but reachable by two
    audiences could not tell which one was calling: `spawn_session` wrote one
    origin for a person clicking the fleet page and for the master alike, and
    D31's wake set — which selects on exactly that origin — could never contain a
    row. The caller is a value this function has already validated against
    `tool.audiences`; handing it on costs nothing and is the only way a handler
    can answer *who asked* without the caller being allowed to say.

    The rejected alternative was an `origin` argument on the call. That puts a
    security-relevant field in the caller's hands, which is what the audience
    check above exists to prevent. `invoke()`'s signature is unchanged either
    way, so no file in `web/` or `cli/` moves (Gate A, DP1, D38).
    """
    name = tool.name
    try:
        data = tool.handler(args, ctx)
    except ToolArgumentRefused as refusal:
        return _failure(ctx, name, Failure.REFUSED, str(refusal), message=str(refusal))
    except Exception as error:  # noqa: BLE001 - a traceback never reaches the caller
        return _failure(ctx, name, Failure.FAILED, type(error).__name__)
    return ToolResult(ok=True, data=data, error=None)
