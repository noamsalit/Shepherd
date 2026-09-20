"""T14: the one chokepoint every consumer crosses (D32, D35, D38, D53).

Integration seam: `invoke()`. Nothing here reaches past it into a handler.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from shepherd.toolsurface.registry import (
    SchemaInvalid,
    freeze_registry,
    install_chokepoint,
    invoke,
    register,
    registered_tools,
    resolve_failure,
)
from shepherd.toolsurface.types import (
    Audience,
    AuditRecord,
    AuthzOutcome,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="test", correlation_id="cid-1")
MASTER = CallerContext(audience=Audience.MASTER, caller_id="test", correlation_id="cid-2")

OBJECT_SCHEMA: dict[str, object] = {"type": "object", "properties": {}}


def echo_tool(
    name: str = "echo",
    audiences: frozenset[Audience] = frozenset({Audience.HUMAN}),
    schema: dict[str, object] | None = None,
) -> ToolDef:
    return ToolDef(
        name=name,
        description="echo its argument back",
        input_schema=OBJECT_SCHEMA if schema is None else schema,
        blast_class=BlastClass.LOCAL_READ,
        handler=lambda args, ctx: dict(args),
        audiences=audiences,
    )


def gated(allowed: bool = True) -> list[AuditRecord]:
    """Install a chokepoint and return the list the sink writes into.

    **Why an M1 test needed this at T6.** Two tests below drive a
    `local_write` tool, and `invoke()` now **fails closed** for every class
    outside `GATE_FREE_CLASSES` when no chokepoint is installed (DP13). That is
    the hole T6 closes, so the fix is to install one — never to relax the rule
    or to re-class the fixture tool as a read. The plan's *"existing M1 tests
    must still pass unchanged"* and DP13 cannot both hold; recorded in
    `docs/plans/m4-blockers/t6.md` §T6-2.
    """
    records: list[AuditRecord] = []
    install_chokepoint(
        lambda tool, args, ctx: AuthzOutcome(
            allowed=allowed, approved_by="policy", approval_id=None, reason=None
        ),
        records.append,
    )
    return records


def test_registration_rejects_schema_without_type() -> None:
    """D53: `create_sdk_mcp_server` mangles a schema with no string `type`."""
    with pytest.raises(SchemaInvalid):
        register(echo_tool(schema={"properties": {}}))
    assert registered_tools() == {}


def test_registration_rejects_schema_without_properties() -> None:
    """D53: without `properties` the SDK reads the dict as `{param: python_type}`."""
    with pytest.raises(SchemaInvalid):
        register(echo_tool(schema={"type": "object"}))
    assert registered_tools() == {}


def test_registration_is_startup_failure_not_runtime() -> None:
    """P10: the malformed schema fails at `register()`, not at the first call."""
    bad = echo_tool(name="bad", schema={"type": 7, "properties": {}})
    with pytest.raises(SchemaInvalid):
        register(bad)
    # The refusal happened at registration, so at runtime there is simply no such
    # tool — never a registered one that misbehaves in one binding.
    assert "bad" not in registered_tools()
    result = invoke("bad", {}, HUMAN)
    assert result.ok is False
    assert result.error is not None
    assert "bad" not in result.error


def test_invoke_validates_arguments_before_handler() -> None:
    """spec l.1464-1472: one binding validated, the other forwarded a short payload."""
    calls: list[object] = []

    def handler(args: ToolArgs, ctx: CallerContext) -> object:
        calls.append(args["session_id"])
        return args["session_id"]

    register(
        ToolDef(
            name="needs_arg",
            description="",
            input_schema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            blast_class=BlastClass.LOCAL_READ,
            handler=handler,
            audiences=frozenset({Audience.HUMAN}),
        )
    )
    result = invoke("needs_arg", {}, HUMAN)
    assert result.ok is False
    assert calls == []
    assert invoke("needs_arg", {"session_id": "s1"}, HUMAN).data == "s1"


def test_invoke_denies_wrong_audience() -> None:
    register(echo_tool(audiences=frozenset({Audience.MASTER})))
    denied = invoke("echo", {}, HUMAN)
    assert denied.ok is False
    assert denied.data is None
    assert invoke("echo", {}, MASTER).ok is True


def test_invoke_returns_generic_error_for_unknown_tool() -> None:
    """§13 Errors: a generic literal plus the correlation id, never a stack trace."""
    result = invoke("no_such_tool", {}, HUMAN)
    assert result.ok is False
    assert result.error is not None
    assert "cid-1" in result.error
    assert "no_such_tool" not in result.error
    assert "Traceback" not in result.error


def test_a_handler_that_raised_is_not_a_capability_that_is_absent() -> None:
    """The two failures need different advice, so they need different values.

    Both used to produce the one literal `request failed`, so a consumer whose
    database had just been half-rewritten was told *the tool surface this
    process sees has no such capability registered — start the control daemon*.
    The generic **text** is right (§13: a caller may not probe the surface by
    reading error strings); one shared *value* is what made the advice false.
    """

    def explode(args: ToolArgs, ctx: CallerContext) -> object:
        raise RuntimeError("the handler fell over")

    register(
        ToolDef(
            name="explodes",
            description="",
            input_schema=OBJECT_SCHEMA,
            blast_class=BlastClass.LOCAL_WRITE,
            handler=explode,
            audiences=frozenset({Audience.HUMAN}),
        )
    )

    gated()
    raised = invoke("explodes", {}, HUMAN)
    absent = invoke("no_such_tool", {}, HUMAN)

    assert (raised.ok, absent.ok) == (False, False)
    assert raised.failure is Failure.FAILED
    assert absent.failure is Failure.UNAVAILABLE
    # …and the text stays the same for both, so nothing can be probed by it.
    assert raised.error == absent.error
    assert raised.error is not None and "RuntimeError" not in raised.error


def test_an_argument_the_handler_refuses_is_its_own_failure() -> None:
    """A value a JSON schema cannot express is a usage error, not a crash.

    `{"type": "string"}` cannot say *a date*, so the handler is the only place
    that can refuse `--since 30d` — and a refusal indistinguishable from a
    crash is a refusal no consumer can render as usage advice.
    """

    def refuse(args: ToolArgs, ctx: CallerContext) -> object:
        raise ToolArgumentRefused("since must be a date spelled YYYY-MM-DD")

    register(
        ToolDef(
            name="refuses",
            description="",
            input_schema=OBJECT_SCHEMA,
            blast_class=BlastClass.LOCAL_READ,
            handler=refuse,
            audiences=frozenset({Audience.HUMAN}),
        )
    )

    result = invoke("refuses", {}, HUMAN)

    assert result.ok is False
    assert result.failure is Failure.REFUSED
    assert result.error is not None
    assert "YYYY-MM-DD" in result.error, "the caller's own value is the caller's to know"


def test_a_correlation_id_that_is_printed_can_be_resolved() -> None:
    """§13 prints an id; something has to be able to answer it.

    Before this, `correlation_id` was only ever formatted into a string — no
    file, no buffer, nothing. An id that resolves to nothing is an id that
    should not be printed.
    """

    def explode(args: ToolArgs, ctx: CallerContext) -> object:
        raise RuntimeError("the handler fell over")

    register(
        ToolDef(
            name="explodes",
            description="",
            input_schema=OBJECT_SCHEMA,
            blast_class=BlastClass.LOCAL_WRITE,
            handler=explode,
            audiences=frozenset({Audience.HUMAN}),
        )
    )
    gated()
    invoke("explodes", {}, HUMAN)

    recorded = resolve_failure("cid-1")

    assert recorded is not None
    assert recorded.tool == "explodes"
    assert recorded.failure is Failure.FAILED
    assert recorded.detail == "RuntimeError"
    assert resolve_failure("cid-never-issued") is None


def test_every_tooldef_has_a_blast_class() -> None:
    register(echo_tool())
    assert all(
        isinstance(tool.blast_class, BlastClass) for tool in registered_tools().values()
    )
    with pytest.raises(TypeError):
        ToolDef(  # type: ignore[call-arg]
            name="no_blast",
            description="",
            input_schema=OBJECT_SCHEMA,
            handler=lambda args, ctx: None,
            audiences=frozenset({Audience.HUMAN}),
        )


def test_registry_is_frozen_after_startup() -> None:
    """ADR-7: written by one thread at startup, read-only once the server binds."""
    register(echo_tool())
    freeze_registry()
    with pytest.raises(RuntimeError):
        register(echo_tool(name="late"))
    assert invoke("echo", {}, HUMAN).ok is True


# `test_no_authorize_call_exists_yet` was **retired here by T6**, deliberately and
# with its reason recorded (RD-T4-4, `docs/plans/m4-blockers/t6.md` §T6-1).
#
# It was M1's tripwire: *"M1 has no gate, so M4 adding one is visible in the
# diff"* — it walked every identifier under `toolsurface/` and asserted that
# `authorize` and `audit_log` were absent. **The event it was watching for has
# happened**: T6 put the gate and the audit write inside `invoke()`. T6's own
# Files/Surfaces says *"existing M1 tests must still pass unchanged"*, and that
# sentence and this tripwire cannot both be honoured; the plan sentence is the
# one that is wrong (T4 recorded the collision as §T4-4 rather than dodging it,
# and proved the tripwire was still armed with a mutation instead of leaving the
# dodge unverified).
#
# **It is retired, not weakened.** Narrowing it to a spelling that still passes —
# and it *would* still have passed, because `invoke()` holds an `Authorizer` and
# calls it through a local named `authorizer` — is worse than deleting it: a
# tripwire green after the event it watches for reads as evidence that the event
# did not happen.
#
# **What guards the property now**, and it is a stronger statement than an absent
# symbol, because it is positive rather than negative:
# `tests/toolsurface/test_registry_gate.py::test_no_handler_runs_before_the_gate_
# answers` asserts the gate is **consulted inside `invoke()`** and consulted
# before any handler; `test_invoke_fails_closed_without_a_gate` asserts what
# happens when it is absent; `test_every_blast_class_audits_exactly_once` asserts
# the audit write. The diff is no longer *visible* — it is *required*.


def test_no_transport_or_vendor_symbol_in_toolsurface() -> None:
    """D38: MCP is an output format, never an input type — exporters arrive at M4.

    Identifiers and string values, never docstrings: a docstring recording *why*
    D53 exists is prose, and it cannot export anything (the repo's own boundary
    rules draw the same line).
    """
    forbidden = ("mcp", "stdio", "anthropic", "openai", "http", "sse")
    # Word-bounded, never a substring: `missed_from` is not `sse` (the repo's own
    # boundary rules learned this from `/procedure` matching `/proc`).
    offenders: list[str] = []
    for path in sorted((SRC_ROOT / "toolsurface").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(holder.body[0].value)
            for holder in ast.walk(tree)
            if isinstance(holder, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and holder.body
            and isinstance(holder.body[0], ast.Expr)
            and isinstance(holder.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            spelling: str | None = None
            if isinstance(node, ast.Name):
                spelling = node.id
            elif isinstance(node, ast.Attribute):
                spelling = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                spelling = node.name
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                spelling = node.value
            if spelling is None:
                continue
            offenders += [
                f"{path.name}:{word}"
                for word in forbidden
                if re.search(rf"(?<![a-z]){word}(?![a-z])", spelling.lower())
            ]
    assert offenders == []
