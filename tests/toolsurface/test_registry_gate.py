"""T6: the gate and the audit log behind `invoke()` (D8, D38, DP13, C-M4-1, C-M4-2).

Integration seam: `invoke()`. Nothing here reaches past it into a handler, and
nothing here calls `authorize()` directly — a gate proved through anything but
the chokepoint is a gate a second path can skip, which is D42's whole subject.

**Never a literal count and never a literal class list.** Every test that spans
the blast classes enumerates `BlastClass` at test time, so a fifth member is a
failing build rather than a row nobody wrote.
"""

from __future__ import annotations

import ast
import inspect
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from shepherd.core.clock import parse_stamp, utc_now
from shepherd.toolsurface.approvals import ApprovalOutcome, ApprovalStore, build_authorizer
from shepherd.toolsurface.audit import actor_kind_of
from shepherd.toolsurface.export import DENIED_TEXT
from shepherd.toolsurface.policy import AutonomyLevel
from shepherd.toolsurface.registry import (
    UNREPORTED_AUTONOMY_LEVEL,
    chokepoint,
    install_chokepoint,
    invoke,
    register,
    reset_registry,
)

# One module internal, read on purpose. `_RESULT_OF` is **not** part of the
# surface the plan pins and it stays private; what is asserted about it is
# structural — a map's totality over an enum — which is exactly the kind of
# property a test may reach for and a caller may not.
from shepherd.toolsurface.registry import _RESULT_OF as RESULT_OF
from shepherd.toolsurface.registry import actor_kind_of as registry_actor_kind
from shepherd.toolsurface.types import actor_kind_of as types_actor_kind_of
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    AuditRecord,
    Authorizer,
    AuthzOutcome,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
    ToolResult,
)

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="cli", correlation_id="cid-human")
MASTER = CallerContext(audience=Audience.MASTER, caller_id="mst_01", correlation_id="cid-master")

OBJECT_SCHEMA: Mapping[str, object] = {"type": "object", "properties": {}}

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd"

#: The classes `test_every_blast_class_audits_exactly_once` drives, enumerated
#: from the enum at test time — never a literal list and never a count.
#: `test_the_shipped_blast_classes_are_covered` is the other half: what ships is
#: inside this cover.
AUDITED_CLASSES = set(BlastClass)


ID_SCHEMA: Mapping[str, object] = {"type": "object", "properties": {"id": {"type": "string"}}}


def tool_for(
    blast_class: BlastClass,
    *,
    name: str | None = None,
    handler: object = None,
    schema: Mapping[str, object] = OBJECT_SCHEMA,
    audiences: frozenset[Audience] = frozenset({Audience.HUMAN, Audience.MASTER}),
) -> ToolDef:
    """One registered capability of the given class. The name carries the class
    so a record can be traced back to the row that produced it."""

    def echo(args: ToolArgs, ctx: CallerContext) -> object:
        return dict(args)

    return ToolDef(
        name=name or f"tool_{blast_class.value}",
        description=f"a {blast_class.value} capability",
        input_schema=schema,
        blast_class=blast_class,
        handler=echo if handler is None else handler,  # type: ignore[arg-type]
        audiences=audiences,
    )


def test_invoke_fails_closed_without_a_gate() -> None:
    """P-M4-19 / DP13: with no chokepoint installed, only `local_read` runs.

    Enumerated over `set(BlastClass)` at test time. **Goes red** if the absent
    state becomes permissive, and **goes red** if `local_read` is refused too,
    which would break `cli/` and take Gate A with it.
    """
    ran: list[str] = []

    for blast_class in set(BlastClass):
        tool = tool_for(blast_class, handler=lambda args, ctx, seen=ran: seen.append("ran"))
        register(tool)

    for blast_class in set(BlastClass):
        result = invoke(f"tool_{blast_class.value}", {}, HUMAN)
        if blast_class is BlastClass.LOCAL_READ:
            assert result.ok is True, f"{blast_class.value} must still run: cli/ depends on it"
            assert result.failure is None
        else:
            assert result.ok is False, f"{blast_class.value} ran with no gate installed"
            assert result.failure is Failure.UNAVAILABLE
            assert "request failed" in (result.error or "")

    assert ran == ["ran"], f"exactly the local_read handler ran, not {len(ran)}"


def test_no_handler_runs_before_the_gate_answers() -> None:
    """P-M4-3 / C-M4-1: the gate is consulted, and it is consulted **first**.

    **Arrival before absence** (K20): a handler count of zero is also what a
    test that never invoked anything sees, so the gate's own arrival is asserted
    first and the count second. **Goes red** if the gate call is moved below the
    handler, which is the single most damaging mutation in this milestone.
    """
    consulted: list[str] = []
    handled: list[str] = []

    def deny(tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> AuthzOutcome:
        consulted.append(tool.name)
        return AuthzOutcome(
            allowed=False, approved_by=None, approval_id=None, reason="you declined this"
        )

    def handler(args: ToolArgs, ctx: CallerContext) -> object:
        handled.append("ran")
        return None

    records: list[AuditRecord] = []
    install_chokepoint(deny, records.append)
    register(tool_for(BlastClass.LOCAL_DESTRUCTIVE, handler=handler))

    result = invoke("tool_local_destructive", {}, MASTER)

    assert consulted == ["tool_local_destructive"], "the gate was never consulted"
    assert handled == [], "a handler ran before the gate answered"
    assert result.ok is False
    assert "you declined this" in (result.error or ""), "the gate's reason reaches the caller"


def allow_all(approved_by: str = "policy") -> Authorizer:
    def allow(tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> AuthzOutcome:
        return AuthzOutcome(
            allowed=True, approved_by=approved_by, approval_id=None, reason=None
        )

    return allow


def test_every_blast_class_audits_exactly_once() -> None:
    """P-M4-2a / C-M4-2: one record per decided call, whatever the class.

    The tools are built from `set(BlastClass)` **enumerated at test time**, so a
    member added to the enum with no path through `invoke()` is a failing build
    rather than a class nobody audits. **Goes red** if a branch returns before
    the audit.
    """
    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)

    classes = AUDITED_CLASSES
    for blast_class in classes:
        register(tool_for(blast_class))
    for blast_class in classes:
        assert invoke(f"tool_{blast_class.value}", {}, MASTER).ok is True

    assert [record.tool for record in records] == [
        f"tool_{blast_class.value}" for blast_class in classes
    ], "one record per call, naming the tool that produced it"
    assert {record.blast_class for record in records} == classes
    assert {record.result for record in records} == {"ok"}
    assert {record.decision for record in records} == {"allow"}


def test_an_allowed_call_is_recorded_with_what_the_process_knows() -> None:
    """ADR-M4-1's fields, from the one writer. `approved_by` and `approval_id`
    are the gate's own answer, carried and never translated (K23)."""
    records: list[AuditRecord] = []
    install_chokepoint(
        lambda tool, args, ctx: AuthzOutcome(
            allowed=True, approved_by="user", approval_id="apr_3k9", reason=None
        ),
        records.append,
    )
    register(tool_for(BlastClass.LOCAL_DESTRUCTIVE, schema=ID_SCHEMA))

    invoke("tool_local_destructive", {"id": "ses_7f3k"}, MASTER)

    assert len(records) == 1
    record = records[0]
    assert record.correlation_id == MASTER.correlation_id
    assert record.actor_id == MASTER.caller_id
    assert record.actor_kind is ActorKind.MASTER
    assert record.approved_by == "user"
    assert record.approval_id == "apr_3k9"
    assert dict(record.args) == {"id": "ses_7f3k"}
    assert record.failure is None
    assert record.duration_ms >= 0
    assert parse_stamp(record.at) is not None, f"`at` is not a readable stamp: {record.at!r}"


def test_an_undecided_call_writes_no_record() -> None:
    """C-M4-2's other half: no decision, no record — asserted three ways.

    An unknown name, a wrong audience and a malformed payload are all
    `UNAVAILABLE` and all happen before there is anything to authorise.
    Auditing them turns the audit log into a request log an agent can fill with
    10 000 lines by guessing names, and D25's 90-day retention then holds mostly
    noise. **Arrival first**: each call is asserted to have produced the
    `UNAVAILABLE` it claims, before the sink is asserted empty.
    """
    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)
    register(
        tool_for(
            BlastClass.LOCAL_DESTRUCTIVE,
            name="human_only",
            audiences=frozenset({Audience.HUMAN}),
        )
    )
    register(
        ToolDef(
            name="needs_an_id",
            description="",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: None,
            audiences=frozenset({Audience.MASTER}),
        )
    )

    undecided = [
        invoke("no_such_tool", {}, MASTER),
        invoke("human_only", {}, MASTER),
        invoke("needs_an_id", {}, MASTER),
    ]

    assert [result.failure for result in undecided] == [Failure.UNAVAILABLE] * len(undecided)
    assert records == [], f"an undecided call was audited: {[r.tool for r in records]}"


def test_a_refused_argument_is_audited_as_refused() -> None:
    """The handler read the arguments and refused one: a decided call, audited,
    and the `Failure` is carried into the record (ADR-M4-1)."""

    def refuse(args: ToolArgs, ctx: CallerContext) -> object:
        raise ToolArgumentRefused("since must be a date spelled YYYY-MM-DD")

    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)
    register(tool_for(BlastClass.LOCAL_WRITE, handler=refuse))

    result = invoke("tool_local_write", {}, MASTER)

    assert result.failure is Failure.REFUSED
    assert [(record.result, record.failure) for record in records] == [
        ("refused", Failure.REFUSED)
    ]


def test_a_failed_handler_is_audited_as_failed() -> None:
    """The call reached the capability and it fell over half way. An audit log
    that cannot tell that from *the tool never ran* is the exact defect
    `Failure` was added to fix."""

    def explode(args: ToolArgs, ctx: CallerContext) -> object:
        raise RuntimeError("the handler fell over")

    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)
    register(tool_for(BlastClass.LOCAL_DESTRUCTIVE, handler=explode))

    result = invoke("tool_local_destructive", {}, MASTER)

    assert result.failure is Failure.FAILED
    assert [(record.result, record.failure) for record in records] == [("failed", Failure.FAILED)]
    assert "RuntimeError" not in (result.error or ""), "§13: no traceback reaches the caller"


def test_a_denied_call_is_audited_as_denied_and_the_handler_never_ran() -> None:
    """A denial **is** a decision, so it is one record — and it is the record
    the incident is reconstructed from, so `decision` says `deny`."""
    handled: list[str] = []
    records: list[AuditRecord] = []
    install_chokepoint(
        lambda tool, args, ctx: AuthzOutcome(
            allowed=False, approved_by="timeout", approval_id="apr_1", reason="nobody answered"
        ),
        records.append,
    )
    register(
        tool_for(BlastClass.EXTERNAL, handler=lambda args, ctx: handled.append("ran"))
    )

    result = invoke("tool_external", {}, MASTER)

    assert handled == []
    assert result.ok is False
    assert [(record.decision, record.result, record.approved_by) for record in records] == [
        ("deny", "denied", "timeout")
    ]
    assert records[0].approval_id == "apr_1"


def test_the_shipped_blast_classes_are_covered() -> None:
    """P-M4-2b: every class a **shipped** tool carries is one the audit test drives.

    Discovery is by property — a scan of `toolsurface/` for `blast_class=`
    keywords — never a hand-written list, and the scan asserts it found
    something before it asserts anything about what it found: *a scan of nothing
    finds nothing*, and a subset check against an empty left-hand side is the
    check that reports success without checking.

    **Why a subset and not an equality, and why the shipped tools are not
    driven.** P-M4-2 read "every tool in the registry" in one place and "one per
    blast class" in another. Driving every shipped tool for real is not
    implementable — `install_hooks` writes a settings file Claude Code owns — so
    the pair is: one synthetic tool per class, plus this check that the shipped
    classes are inside that cover. **Goes red** if a tool ships with a class no
    audit test exercises.
    """
    shipped = shipped_blast_classes()

    assert shipped, "the scan found no shipped blast class at all — it is pointing at nothing"
    assert BlastClass.LOCAL_DESTRUCTIVE in shipped, (
        "D38.1's install-hooks tools are local_destructive; a scan that misses them "
        "is reading the wrong tree"
    )
    assert shipped <= AUDITED_CLASSES, (
        f"a shipped tool carries a class no audit test drives: {sorted(shipped - AUDITED_CLASSES)}"
    )


def shipped_blast_classes() -> set[BlastClass]:
    """Every `blast_class=BlastClass.X` in the shipped tool modules, by AST.

    The registry itself cannot be walked here: registering the real tools means
    composing them, and composition is T25's. The declaration site is the next
    truest thing and it is discovered rather than listed.
    """
    found: set[BlastClass] = set()
    for path in sorted((SRC_ROOT / "toolsurface").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.keyword) or node.arg != "blast_class":
                continue
            value = node.value
            if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                if value.value.id == BlastClass.__name__:
                    found.add(BlastClass[value.attr])
    return found


def test_the_chokepoint_cannot_be_half_installed() -> None:
    """DP13 / ADR-M4-9: a gate with no audit log is not a representable state.

    Three statements, none of them a spelling:

    1. the slot is discovered as the module global annotated with **both**
       `Authorizer` and `AuditSink` — so it holds one value, not two;
    2. every function that writes that slot either clears it to `None` or takes
       parameters annotated with both — **goes red** if a setter for one half is
       added;
    3. the installer has no defaulted parameter, so neither half can be omitted
       at the call site (T5 gives `build_audit_sink` the same property one layer
       down).
    """
    module = ast.parse((SRC_ROOT / "toolsurface" / "registry.py").read_text(encoding="utf-8"))

    slots = [
        node.target.id
        for node in module.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and {"Authorizer", "AuditSink"} <= set(_names_in(node.annotation))
    ]
    assert len(slots) == 1, f"the gate and the sink are not one value: {slots}"
    slot = slots[0]

    writers = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(inner, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == slot for t in inner.targets)
            for inner in ast.walk(node)
        )
    ]
    assert writers, f"nothing writes {slot}; this check is reading the wrong module"
    for writer in writers:
        clears_only = all(
            isinstance(inner.value, ast.Constant) and inner.value.value is None
            for inner in ast.walk(writer)
            if isinstance(inner, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == slot for t in inner.targets)
        )
        annotated = {
            name
            for argument in writer.args.args
            if argument.annotation is not None
            for name in _names_in(argument.annotation)
        }
        assert clears_only or {"Authorizer", "AuditSink"} <= annotated, (
            f"{writer.name}() writes {slot} without being handed both halves"
        )

    for parameter in inspect.signature(install_chokepoint).parameters.values():
        assert parameter.default is inspect.Parameter.empty, (
            f"{parameter.name} is defaulted: one half could be omitted at the call site"
        )


def _names_in(node: ast.expr) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def test_the_installed_chokepoint_is_always_a_pair() -> None:
    """`chokepoint()` answers `None` or two callables — never one and a hole."""
    assert chokepoint() is None

    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)
    installed = chokepoint()

    assert installed is not None
    assert len(installed) == 2
    assert all(callable(half) for half in installed)


def test_reset_registry_returns_invoke_to_failing_closed() -> None:
    """A module global that survives a test is a module global that decides the
    next one — and the cleared state is the **safe** one.

    **Arrival first**: the destructive call is proved to run *with* the
    chokepoint installed, so the refusal after the reset is the reset's doing
    and not a tool that was never reachable. **Goes red** on a leaked global,
    and **goes red** if the cleared state permits a destructive call.
    """
    records: list[AuditRecord] = []
    install_chokepoint(allow_all(), records.append)
    register(tool_for(BlastClass.LOCAL_DESTRUCTIVE))

    assert invoke("tool_local_destructive", {}, MASTER).ok is True
    assert len(records) == 1

    reset_registry()
    register(tool_for(BlastClass.LOCAL_DESTRUCTIVE))
    after = invoke("tool_local_destructive", {}, MASTER)

    assert chokepoint() is None, "the chokepoint leaked past reset_registry()"
    assert after.ok is False
    assert after.failure is Failure.UNAVAILABLE
    assert len(records) == 1, "a record was written with no chokepoint installed"


def test_the_result_vocabulary_is_total_over_failure() -> None:
    """K19: every `Failure` the audit can see has a `result` word.

    Enumerated from the enum at test time. **Goes red** if a member is added to
    `Failure` without one — which would otherwise be a `KeyError` raised while
    auditing a call that has **already run**.
    """
    assert set(RESULT_OF) == set(Failure) | {None}
    assert set(RESULT_OF.values()) >= {"ok", "refused", "failed"}


def test_the_unreported_autonomy_level_is_not_a_real_level() -> None:
    """K23: the record must not say *this ran at level 2* when nothing asked.

    `AuthzOutcome` does not carry the level the gate read and
    `install_chokepoint` is pinned at two parameters, so `invoke()` cannot know
    it. The sentinel is asserted **outside** `AutonomyLevel` enumerated at test
    time, so a reader can tell unreported from reported. Owed fix: one field on
    `AuthzOutcome` (t6.md §T6-3).
    """
    assert UNREPORTED_AUTONOMY_LEVEL not in {int(level) for level in AutonomyLevel}


def test_the_actor_kind_derivation_is_one_object_and_is_total() -> None:
    """§T6-4, closed: the derivation had two definitions and now has one.

    `registry.py` said `audit.actor_kind_of` a second time because importing
    `audit` would have dragged `shepherd.logs` into `shepherd status` through
    `cli/`'s import of `registry` — and the shipped DP3 rule checks only *direct*
    importers, so it would have passed while being defeated. Both now import it
    from `types.py`, which is stdlib-only.

    **This is an identity assertion, not a comparison.** The drift guard it
    replaces compared two functions over every `Audience`; two functions that
    agree today can disagree tomorrow, and `is` cannot. The property that keeps a
    *third* one from appearing is structural and lives in
    `tests/boundaries/test_one_definition_site.py::
    test_the_actor_kind_derivation_has_one_definition_site`.

    The behaviour is asserted here too, over `Audience` enumerated at test time
    rather than listed, so a fourth member is a failing lookup rather than a
    record that invents a kind.
    """
    assert registry_actor_kind is actor_kind_of is types_actor_kind_of

    for audience in set(Audience):
        ctx = CallerContext(audience=audience, caller_id="x", correlation_id="c")
        assert isinstance(actor_kind_of(ctx), ActorKind)

    # …and the explicit field wins over the audience, which is what made
    # `ActorKind.WORKER` reachable at all (DP2).
    worker = CallerContext(
        audience=Audience.MASTER,
        caller_id="w",
        correlation_id="c",
        actor_kind=ActorKind.WORKER,
    )
    assert actor_kind_of(worker) is ActorKind.WORKER


#: Every wait in this file is bounded. A mutant that **hangs** is not a red: it
#: is a builder waiting for a test that never returns, which T4 and T20 both hit.
WAIT_S = 5.0


def until(predicate: object, what: str) -> None:
    """Block until `predicate()` is true, or fail the test. Never forever."""
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out after {WAIT_S}s waiting for {what}")


def test_an_ask_verdict_blocks_until_a_decision() -> None:
    """The approval wait is **behind the gate**, and the handler is behind the wait.

    Driven through the shipped `build_authorizer` over a real `ApprovalStore`,
    because the thing under test is the composition: a stub that returns `ASK`
    and then returns `allowed=True` would prove nothing about blocking.

    **Arrival first**: the card is asserted to exist and the invoking thread to
    be alive and handler-less *before* the release. **Goes red** if `ASK` falls
    through to allow — the handler would have run before anyone clicked.
    """
    store = ApprovalStore()
    handled: list[str] = []
    records: list[AuditRecord] = []
    install_chokepoint(
        build_authorizer(
            store=store,
            level=lambda: AutonomyLevel.LEVEL_2,
            publish=lambda event: 0,
            bump=lambda kind: None,
            now=utc_now,
        ),
        records.append,
    )
    register(
        tool_for(BlastClass.LOCAL_DESTRUCTIVE, handler=lambda args, ctx: handled.append("ran"))
    )

    answered: list[object] = []
    caller = threading.Thread(
        target=lambda: answered.append(invoke("tool_local_destructive", {}, MASTER)),
        daemon=True,
    )
    caller.start()

    until(lambda: store.pending(), "the approval card to be raised")
    card = store.pending()[0]
    assert caller.is_alive(), "the caller did not block on the card"
    assert handled == [], "the handler ran while a person was still being asked"
    assert answered == []
    assert records == [], "a decided call was audited before the decision"

    assert store.decide(card.id, ApprovalOutcome.APPROVED) is True

    caller.join(WAIT_S)
    assert caller.is_alive() is False, "the caller was not released by the decision"
    assert handled == ["ran"]
    assert [(r.decision, r.result, r.approved_by, r.approval_id) for r in records] == [
        ("allow", "ok", "user", card.id)
    ]


def test_a_rejected_card_denies_the_call_and_the_handler_never_ran() -> None:
    """The other terminal outcome of the same wait: a person declined, so the
    call is denied, the denial text is the one `export.py` declares, and the
    record says `deny` (ADR-M4-1)."""
    store = ApprovalStore()
    handled: list[str] = []
    records: list[AuditRecord] = []
    install_chokepoint(
        build_authorizer(
            store=store,
            level=lambda: AutonomyLevel.LEVEL_2,
            publish=lambda event: 0,
            bump=lambda kind: None,
            now=utc_now,
        ),
        records.append,
    )
    register(
        tool_for(BlastClass.LOCAL_DESTRUCTIVE, handler=lambda args, ctx: handled.append("ran"))
    )

    answered: list[object] = []
    caller = threading.Thread(
        target=lambda: answered.append(invoke("tool_local_destructive", {}, MASTER)),
        daemon=True,
    )
    caller.start()
    until(lambda: store.pending(), "the approval card to be raised")
    card = store.pending()[0]
    assert store.decide(card.id, ApprovalOutcome.REJECTED) is True
    caller.join(WAIT_S)

    assert caller.is_alive() is False
    assert handled == []
    result = answered[0]
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert DENIED_TEXT in (result.error or ""), "the denial text is export.py's, never respelled"
    assert [(r.decision, r.result) for r in records] == [("deny", "denied")]
