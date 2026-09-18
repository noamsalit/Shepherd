"""The vendor-free projection (T11, D32, D53, DP4).

Every expected value here comes from a declared table or from a capture in
`docs/specs/data-schemas.md`, never from re-running the projection's own rule.
The audience table below is the independent source of truth for
`test_the_projection_is_exactly_the_audience_subset`: the tools are declared
with their audiences in one place and the expected name sets are written out in
another, so a filter that is dropped or inverted disagrees with a literal.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.core.master import ExportedTool
from shepherd.toolsurface.export import (
    DENIED_TEXT,
    SCHEMA_WIRE_KEY,
    call_exported,
    exported_tools,
    result_payload,
)
from shepherd.toolsurface.registry import register, registered_tools
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgumentRefused,
    ToolArgs,
    ToolDef,
    ToolResult,
)

MASTER = Audience.MASTER
SESSION = Audience.SESSION
HUMAN = Audience.HUMAN

#: The declared surface for this module's fixtures: name -> (schema, audiences).
#: Read by `_register_fixture_tools`; the expected projections below are written
#: out separately rather than derived from it.
_FIXTURE_TOOLS: Mapping[str, tuple[Mapping[str, object], frozenset[Audience]]] = {
    "fleet_summary": (
        {"type": "object", "properties": {}},
        frozenset({MASTER, SESSION, HUMAN}),
    ),
    "spawn_session": (
        {
            "type": "object",
            "properties": {"project_id": {"type": "string"}, "count": {"type": "integer"}},
            "required": ["project_id"],
        },
        frozenset({MASTER, SESSION}),
    ),
    "kill_session": (
        {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        frozenset({MASTER, HUMAN}),
    ),
    "open_settings": (
        {"type": "object", "properties": {}},
        frozenset({HUMAN}),
    ),
}

#: What each audience must see, written out. **Not a count** (K19): a count of
#: three cannot tell "the master lost `kill_session`" from "the master gained
#: `open_settings`", and both are the mutation this check exists to catch.
_EXPECTED_BY_AUDIENCE: Mapping[Audience, frozenset[str]] = {
    MASTER: frozenset({"fleet_summary", "spawn_session", "kill_session"}),
    SESSION: frozenset({"fleet_summary", "spawn_session"}),
    HUMAN: frozenset({"fleet_summary", "kill_session", "open_settings"}),
}


def _register_fixture_tools() -> None:
    def echo(args: ToolArgs, ctx: CallerContext) -> object:
        return dict(args)

    for name, (schema, audiences) in _FIXTURE_TOOLS.items():
        register(
            ToolDef(
                name=name,
                description=f"{name} for the export tests.",
                input_schema=schema,
                blast_class=BlastClass.LOCAL_READ,
                handler=echo,
                audiences=audiences,
            )
        )


def _ctx(audience: Audience = MASTER) -> CallerContext:
    return CallerContext(audience=audience, caller_id="test", correlation_id="corr_1")


def _text_of(payload: Mapping[str, object]) -> str:
    content = payload["content"]
    assert isinstance(content, list), payload
    assert len(content) == 1, content
    block = content[0]
    assert isinstance(block, dict), block
    assert block["type"] == "text", block
    text = block["text"]
    assert isinstance(text, str), block
    return text


# ----- the audience filter ----------------------------------------------------


def test_the_projection_is_exactly_the_audience_subset() -> None:
    _register_fixture_tools()
    # Arrival: the registry really holds the declared tools, so every emptiness
    # below is an emptiness the projection could have broken.
    assert set(registered_tools()) == set(_FIXTURE_TOOLS)

    # The enumeration rule, written into the test: every member of `Audience`
    # has a row, enumerated from the enum at test time. A new audience with no
    # expectation is a projection nobody checked.
    assert set(Audience) == set(_EXPECTED_BY_AUDIENCE)

    for audience, expected in _EXPECTED_BY_AUDIENCE.items():
        projected = exported_tools(audience)
        assert projected, f"{audience} projected nothing at all"
        assert {tool.name for tool in projected} == expected, audience
        assert all(isinstance(tool, ExportedTool) for tool in projected), audience

    # The projection carries the model's three fields and nothing else — no
    # handler, no audience set, no blast class (DP4: a runtime holding gate
    # vocabulary could reason about its own permissions).
    one = exported_tools(MASTER)[0]
    assert {field for field in vars(one)} == {"name", "description", "input_schema"}


def test_the_captured_wire_key_is_the_camel_spelling() -> None:
    """`inputSchema`, camel-cased, per the capture — not our own spelling.

    data-schemas.md §In-process MCP `tools/list`:
    `{"description": …, "inputSchema": {"properties": {}, "type": "object"},
      "name": "fleet_summary"}`.

    **Narrowed by the router after T20 (RD-T11-1).** This test used to drive
    `tools_list_payload()`, which is retired: T20 measured that
    `create_sdk_mcp_server` builds the `tools/list` entry itself and has no
    parameter a pre-built payload could fill, so the function had no consumer.
    What survives is the constant the wire shape actually turns on, still checked
    against the capture. The *emitted* entry is asserted one layer up, against the
    vendor's own answer, by `tests/master/test_sdk_tools.py::
    test_the_schema_and_description_reach_the_wire_unchanged`.
    """
    assert SCHEMA_WIRE_KEY == "inputSchema"


# ----- D53: the schema a binding would not mangle ------------------------------


def _survives_the_sdk_rule(schema: object) -> bool:
    """`_build_input_schema`'s branch, written out here rather than imported.

    claude-agent-sdk 0.2.153 passes a dict through **only** when it has a string
    `type` and a `properties` key; anything else it reads as a
    `{param: python_type}` map with every key required, producing a different
    tool (docs/probes/2026-09-17-m4-sdk/FINDINGS.md P1; data-schemas.md
    §In-process MCP tool declaration).
    """
    return (
        isinstance(schema, Mapping)
        and isinstance(schema.get("type"), str)
        and "properties" in schema
    )


def test_every_exported_schema_survives_the_sdk_rule() -> None:
    # The predicate bites before it is used to pass anything: the two shapes the
    # SDK would mangle, as literals.
    assert not _survives_the_sdk_rule({"type": "object"})
    assert not _survives_the_sdk_rule({"properties": {}})
    assert _survives_the_sdk_rule({"type": "object", "properties": {}})

    _register_fixture_tools()
    for audience in Audience:
        projected = exported_tools(audience)
        assert projected, audience  # arrival, before the property over the set
        for tool in projected:
            assert _survives_the_sdk_rule(tool.input_schema), (audience, tool.name)
        # …and the schema is the registered one, unaltered by the projection.
        registered = registered_tools()
        for tool in projected:
            assert tool.input_schema == registered[tool.name].input_schema


# ----- D53: validation happens before the handler ------------------------------

#: Each row is (label, arguments). The four classes the plan names.
_MALFORMED: tuple[tuple[str, Mapping[str, object]], ...] = (
    ("missing required", {}),
    ("wrong type", {"project_id": 7}),
    ("unknown key", {"project_id": "p1", "nope": "x"}),
    ("boolean where a number is declared", {"project_id": "p1", "count": True}),
)


def test_invoke_refuses_bad_arguments_before_the_handler() -> None:
    # T6/DP13: `spawn_session` is `local_write`, so `invoke()` fails closed here
    # unless this test composes a chokepoint the way a root does.
    install_test_chokepoint()
    calls: list[Mapping[str, object]] = []

    def counting(args: ToolArgs, ctx: CallerContext) -> object:
        calls.append(dict(args))
        return "spawned"

    schema, audiences = _FIXTURE_TOOLS["spawn_session"]
    register(
        ToolDef(
            name="spawn_session",
            description="Spawn a session in a project.",
            input_schema=schema,
            blast_class=BlastClass.LOCAL_WRITE,
            handler=counting,
            audiences=audiences,
        )
    )

    # Arrival first, as an assertion: a well-formed call reaches the handler, so
    # "the handler was not called" below is a fact about the gate and not about
    # a handler that was never reachable.
    good = call_exported("spawn_session", {"project_id": "p1"}, _ctx())
    assert good["is_error"] is False, good
    assert _text_of(good) == "spawned"
    assert calls == [{"project_id": "p1"}]

    for label, args in _MALFORMED:
        result = call_exported("spawn_session", args, _ctx())
        # Arrival: a *result* arrived, before anything is asserted about it.
        assert set(result) == {"content", "is_error"}, label
        assert _text_of(result), label
        assert result["is_error"] is True, label

    # The handler's count is unmoved — asserted after the reachable call above
    # was asserted to have moved it.
    assert calls == [{"project_id": "p1"}]


# ----- the error the model reads ----------------------------------------------


def test_an_error_result_is_readable_by_the_model() -> None:
    def refusing(args: ToolArgs, ctx: CallerContext) -> object:
        raise ToolArgumentRefused("'30d' is not a date spelled YYYY-MM-DD")

    def exploding(args: ToolArgs, ctx: CallerContext) -> object:
        raise RuntimeError("handler exploded on purpose")

    for name, handler in (("refuse_tool", refusing), ("raise_tool", exploding)):
        register(
            ToolDef(
                name=name,
                description=f"{name}.",
                input_schema={"type": "object", "properties": {}},
                blast_class=BlastClass.LOCAL_READ,
                handler=handler,
                audiences=frozenset({MASTER}),
            )
        )

    # A denial. §11's `authorize()` returns `Deny("you declined this")` and the
    # capture shows the model reading that text verbatim (data-schemas.md
    # §can_use_tool; §Agent SDK `tool_result` `"content": "you declined this"`).
    assert DENIED_TEXT == "you declined this"
    denial = result_payload(
        ToolResult(ok=False, data=None, error=DENIED_TEXT, failure=Failure.REFUSED)
    )
    assert denial["is_error"] is True
    assert _text_of(denial) == "you declined this"

    # A refusal: the caller's own value described back to them.
    refusal = call_exported("refuse_tool", {}, _ctx())
    assert refusal["is_error"] is True
    assert "'30d' is not a date spelled YYYY-MM-DD" in _text_of(refusal)

    # A failure: generic text plus the correlation id, never a traceback.
    failure = call_exported("raise_tool", {}, _ctx())
    assert failure["is_error"] is True
    text = _text_of(failure)
    assert "corr_1" in text
    assert "RuntimeError" not in text and "Traceback" not in text

    # An error with no text at all is a tool the model retries forever, so the
    # encoder never emits one. `ToolResult(ok=False, error=None)` typechecks, so
    # this is a shape the encoder can actually be handed.
    empty = result_payload(ToolResult(ok=False, data=None, error=None, failure=Failure.FAILED))
    assert empty["is_error"] is True
    assert _text_of(empty).strip() != ""


def test_a_success_is_encoded_as_one_text_block() -> None:
    """The captured handler return shape: `content[]` of text, `is_error`.

    data-schemas.md §In-process MCP `tools/call`, `handler-calls.jsonl`:
    `{"content": [{"type": "text", "text": "ses_new42"}]}` for a string, and
    `"{\\"running\\": 2, …}"` — JSON text — for a mapping.
    """
    register(
        ToolDef(
            name="counts",
            description="counts.",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: {"running": 2, "needs_you": ["ses_a1"]},
            audiences=frozenset({MASTER}),
        )
    )
    register(
        ToolDef(
            name="spawn",
            description="spawn.",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: "ses_new42",
            audiences=frozenset({MASTER}),
        )
    )

    install_test_chokepoint()  # T6/DP13: `spawn` below is `local_write`.
    mapping = call_exported("counts", {}, _ctx())
    assert mapping["is_error"] is False
    assert _text_of(mapping) == '{"running": 2, "needs_you": ["ses_a1"]}'

    plain = call_exported("spawn", {}, _ctx())
    assert plain["is_error"] is False
    assert _text_of(plain) == "ses_new42"


def test_an_unexported_tool_is_refused_through_the_bound_call() -> None:
    """The audience filter is total: the projection and the call agree."""
    _register_fixture_tools()
    assert "open_settings" not in {tool.name for tool in exported_tools(MASTER)}
    result = call_exported("open_settings", {}, _ctx(MASTER))
    assert result["is_error"] is True
    assert _text_of(result)
    # …and the same tool, called by the audience that has it, succeeds.
    allowed = call_exported("open_settings", {}, _ctx(HUMAN))
    assert allowed["is_error"] is False


#: The two inert fixtures Task 7 shipped for DP4. They are **read as text and
#: parsed as an AST**, never imported (CLAUDE.md: a planted violation is a
#: fixture nothing imports). The second is the call-shaped spelling that
#: `module_imports` alone is blind to (BLOCKERS §T7-3).
_VENDOR_FIXTURES: Mapping[str, frozenset[str]] = {
    "toolsurface_imports_the_vendor_sdk.py": frozenset({"claude_agent_sdk", "mcp"}),
    "toolsurface_imports_the_vendor_sdk_dynamically.py": frozenset({"claude_agent_sdk", "mcp"}),
}


def _import_roots(source: str) -> set[str]:
    """Top-level package names imported by `source`, in all four spellings.

    Statement, alias, from-import and submodule are import nodes;
    `importlib.import_module("x")` and `__import__("x")` are `ast.Call` nodes and
    are resolved by their string argument, because a rule keyed on one spelling
    passes on the idiomatic spelling of the same violation (§T7-3).
    """
    import ast

    tree = ast.parse(source)
    # Module-level string constants, because the idiomatic spelling of the
    # dynamic form names the package through one (`VENDOR = "claude_agent_sdk"`).
    constants: dict[str, str] = {
        target.id: statement.value.value
        for statement in tree.body
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant)
        for target in statement.targets
        if isinstance(target, ast.Name) and isinstance(statement.value.value, str)
    }
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            callee = node.func
            named = getattr(callee, "attr", None) or getattr(callee, "id", None)
            if named in {"import_module", "__import__"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        roots.add(arg.value.split(".")[0])
                    elif isinstance(arg, ast.Name) and arg.id in constants:
                        roots.add(constants[arg.id].split(".")[0])
    return roots


def test_export_imports_no_vendor_package() -> None:
    """DP4 at the one file this task owns.

    `tests/boundaries/test_l4_import_rules.py::test_no_vendor_sdk_below_l5` is
    the rule over the whole tree; this is the same claim asserted where a reader
    of `export.py` will look for it, and it fails for a reason naming this file.
    """
    from pathlib import Path

    import shepherd.toolsurface.export as module

    fixtures = Path(__file__).resolve().parent.parent / "boundaries" / "fixtures"
    # The detector bites **before** it is used to report an absence: both
    # spellings of the violation, over the inert fixtures Task 7 froze, with the
    # found set written out rather than merely asserted non-empty.
    for name, expected in _VENDOR_FIXTURES.items():
        found = _import_roots((fixtures / name).read_text(encoding="utf-8"))
        assert expected <= found, (name, found)

    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    roots = _import_roots(source)
    # Arrival: the scan really read this module's own imports.
    assert {"shepherd", "json"} <= roots, roots
    assert {"claude_agent_sdk", "mcp"} & roots == set(), roots


def test_the_module_docstring_keeps_the_measured_validation_fact() -> None:
    """T11: the fact the next binding's author must read before moving validation.

    Claude Code 2.1.270 forwarded `{"count": 5}` — missing a required `text` —
    to a stdio server **unvalidated**, while `create_sdk_mcp_server` validates
    with `jsonschema` first. Two bindings that validate differently is why
    `invoke()` is the only validator.
    """
    import shepherd.toolsurface.export as module

    doc = module.__doc__ or ""
    assert "unvalidated" in doc
    assert "invoke()" in doc


@pytest.mark.parametrize("audience", list(Audience))
def test_an_empty_registry_projects_nothing_for_every_audience(audience: Audience) -> None:
    assert registered_tools() == {}
    assert exported_tools(audience) == ()
