"""Clause 14's residue — every `SESSION` audience in the tree is a named entry.

**What the shipped checks actually bind.** Clause 14's assertion is

    session_tools & MASTER_TOOL_NAMES == set(UNREACHABLE_SESSION_TOOLS)

— an **intersection with the master tools**, so a `SESSION` audience anywhere
else is invisible to it. The M4 remediation measured the residue one tool per
row, whole default suite each time: a third `SESSION` audience planted on
`rename_session` or on destructive `interrupt_session` goes red **by rule**, and
on a tool whose audiences some test pins with an equality it goes red **by
name** — but on `list_subagents`, on `engine_version`, on `terminal_snapshot`,
and on **any new tool in a new module**, the whole default suite stayed green at
1779 passed with one planted. So the tree caught a `SESSION` audience on the tool
the verification happened to pick, and on nothing else.

**Why that is a product problem and not tidiness, which is the part worth
keeping.** `invoke()` checks `ctx.audience` against the tool's audiences and then
**discards the caller** — `caller_id` reaches the audit record and never the
handler (`registry.py`) — so *no handler can scope a request to its caller*. That
is why Track C was cut, and six `SESSION`-audience tools already take an
arbitrary session id. A new tool acquiring that audience unnoticed is the same
hole re-opening, one tool wider.

**Why this rule is structural rather than an enumeration of the composed
registry.** A registry enumeration can only see what some composition
*registered*; the sentence to enforce is about **any new tool in a new module**,
including one nothing composes yet. So the scan reads `ToolDef(...)`
constructions out of `src/` by AST, resolves the `audiences` expression through
module-level constants, and **refuses what it cannot resolve** — an audience set
spelled in a way this rule cannot read is a violation, not a silent pass, which
is the only way "every" survives a new spelling.

**Arrival before absence, as an assertion, and the arrival is mutated.** The scan
is shown to have found the real tools and read real audiences out of them before
its answer is allowed to mean anything, and the reported set is compared by
**equality** against a table with a reason per member — never a count.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest
from _imports import MISSING_MODULE, SRC_ROOT, fixture, iter_modules, parsed

#: The tool constructor every capability in this build goes through. A capability
#: absent from the registry has no surface that can reach it (D32), and nothing
#: reaches the registry except as a `ToolDef`.
TOOL_DEF = "ToolDef"

#: The audience whose every holder must be a reviewed entry.
SESSION = "SESSION"

#: The `SESSION`-audience tools, **whole**, each with the reason it holds the
#: audience and what that audience can reach. Adding a tool to this set is a
#: review, not an edit: the equality below fails until the entry is written, and
#: the entry is what a reviewer reads.
#:
#: Six of the eight take a session id they cannot scope — `invoke()` discards the
#: caller — so each of those reasons says so. That is not a defect of the tool;
#: it is the shape of the seam, recorded at every site it applies to so the next
#: person adding a `SESSION` tool meets it.
SESSION_AUDIENCE_TOOLS: Mapping[str, str] = {
    "list_sessions": (
        "LOCAL_READ, tools_m1.py. A session lists the fleet it is part of. "
        "Unscoped: the list is the whole fleet, not the caller's neighbours, "
        "because `invoke()` discards the caller."
    ),
    "get_session": (
        "LOCAL_READ, tools_m1.py. A session reads a session record by id, and "
        "**any** id. Unscoped: no handler can scope a request to its caller, "
        "which is the reason Track C was cut."
    ),
    "spawn_session": (
        "LOCAL_WRITE, tools_m3.py. A session starts a session. Unscoped, and "
        "gated: LOCAL_WRITE at autonomy level 1 asks, so §12's rail is what "
        "bounds it rather than the audience."
    ),
    "send_to_session": (
        "LOCAL_WRITE, tools_messaging.py. A session writes into **any** session "
        "by id, including the one that asked and including the master's. "
        "Unscoped for the same structural reason."
    ),
    "ask_session": (
        "LOCAL_WRITE, tools_messaging.py. The blocking twin of `send_to_session`, "
        "with the same unscoped id."
    ),
    "get_session_output": (
        "LOCAL_READ, tools_terminal.py. A session reads **any** session's "
        "terminal output by id. The widest read on this list, and unscoped."
    ),
    "report_blocked": (
        "LOCAL_WRITE, tools_master.py. G-M4-15: registered and reachable by "
        "nothing after the Track C cut — no session-audience caller exists to "
        "invoke it. Named in `tools_master.UNREACHABLE_SESSION_TOOLS`."
    ),
    "request_help": (
        "LOCAL_WRITE, tools_master.py. G-M4-15, with `report_blocked`: "
        "registered, unreachable, and kept so the capability exists the day a "
        "session-audience caller does."
    ),
}


def _audience_members(node: ast.expr) -> frozenset[str] | None:
    """The `Audience.X` members a set/frozenset expression names, or `None`.

    `None` means *this rule cannot read this spelling* and is never confused with
    *this set is empty*: the caller turns it into a violation. A rule that read an
    unknown spelling as "no audiences" would pass on the first tool written a new
    way, which is the failure mode this whole file is about.
    """
    inner: ast.expr | None = None
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        inner = node
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in {"frozenset", "set"} or len(node.args) != 1:
            return None
        inner = node.args[0]
    if inner is None or not isinstance(inner, (ast.Set, ast.Tuple, ast.List)):
        return None
    found: set[str] = set()
    for element in inner.elts:
        if (
            isinstance(element, ast.Attribute)
            and isinstance(element.value, ast.Name)
            and element.value.id == "Audience"
        ):
            found.add(element.attr)
        else:
            return None
    return frozenset(found)


def _module_bindings(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level `NAME = <expr>` bindings — how an audience set is spelled."""
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = value
    return found


def tool_audiences(path: Path) -> tuple[dict[str, frozenset[str]], list[str]]:
    """`({tool name: audience members}, [unreadable spellings])` for one module.

    Both halves are returned because they are different failures. A tool whose
    audiences this rule cannot resolve is not clean — it is unread — and the two
    must never collapse into one empty list (B1's lesson, one level up).

    Names and audience sets are both resolved through module-level bindings,
    because that is how this tree spells them: `RENAME_TOOL_NAME`,
    `_EVERY_AUDIENCE`, `EVERY_AUDIENCE`, `_SESSION_ONLY`.
    """
    tree = parsed(path)
    bindings = _module_bindings(tree)
    found: dict[str, frozenset[str]] = {}
    unreadable: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == TOOL_DEF):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        name_node = keywords.get("name")
        audiences_node = keywords.get("audiences")
        name: str | None = None
        if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
            name = name_node.value
        elif isinstance(name_node, ast.Name):
            bound = bindings.get(name_node.id)
            if isinstance(bound, ast.Constant) and isinstance(bound.value, str):
                name = bound.value
        if name is None:
            unreadable.append(f"{path.name}: a ToolDef whose name this rule cannot read")
            continue
        if audiences_node is None:
            unreadable.append(f"{path.name}: {name} declares no audiences")
            continue
        members = _audience_members(audiences_node)
        if members is None and isinstance(audiences_node, ast.Name):
            bound = bindings.get(audiences_node.id)
            members = _audience_members(bound) if bound is not None else None
        if members is None:
            unreadable.append(
                f"{path.name}: {name}'s audiences are spelled in a way this rule "
                f"cannot read ({ast.unparse(audiences_node)})"
            )
            continue
        found[name] = members
    return found, unreadable


def registry_audiences() -> tuple[dict[str, frozenset[str]], list[str]]:
    """The same, over every product module. Every tool in the build, not every
    tool some composition happened to register."""
    found: dict[str, frozenset[str]] = {}
    unreadable: list[str] = []
    for module in iter_modules():
        declared, problems = tool_audiences(module.path)
        found.update(declared)
        unreadable.extend(problems)
    return found, unreadable


def session_audience_tools(declared: Mapping[str, frozenset[str]]) -> frozenset[str]:
    return frozenset(name for name, audiences in declared.items() if SESSION in audiences)


def test_every_session_audience_tool_is_a_named_reviewed_entry() -> None:
    """Clause 14's residue, closed registry-wide.

    The equality is over the **whole tree**, not over the master tools, not over
    `local_destructive` M3 tools, and not over the tools some test pins with an
    equality of its own. A `SESSION` audience on a tool in a module no current
    rule covers is a failing build here.
    """
    declared, unreadable = registry_audiences()

    # Arrival, as an assertion: the scan found the real tools and read real
    # audiences out of them. A scan pointed at nothing reports no `SESSION`.
    assert {"fleet_summary", "kill_session", "rename_session", "replay"} <= set(declared), (
        f"the tool scan found only {sorted(declared)}"
    )
    assert declared["kill_session"] == frozenset({"MASTER", "HUMAN"}), declared["kill_session"]
    assert declared["get_session_output"] == frozenset({"MASTER", "SESSION", "HUMAN"})
    assert unreadable == [], unreadable

    assert session_audience_tools(declared) == frozenset(SESSION_AUDIENCE_TOOLS), {
        "unreviewed": sorted(session_audience_tools(declared) - set(SESSION_AUDIENCE_TOOLS)),
        "reviewed but gone": sorted(set(SESSION_AUDIENCE_TOOLS) - session_audience_tools(declared)),
    }


def test_every_reviewed_entry_says_what_the_audience_can_reach() -> None:
    """An enumerated set without reasons is a list of names somebody allowed.

    Six of the eight take a session id the seam cannot scope, and each says so —
    which is the fact a reviewer of the *next* entry needs and the one a bare
    name would lose.
    """
    assert SESSION_AUDIENCE_TOOLS
    for name, reason in SESSION_AUDIENCE_TOOLS.items():
        assert ".py" in reason, name
        assert len(reason.split()) >= 12, name
    # The six that take a session id the seam cannot scope, as a **set** and not
    # a count: a count cannot tell *one entry stopped saying it* from *one entry
    # started*. The two that are left are G-M4-15's pair, which take no id
    # because nothing can call them at all.
    unscoped = {
        name for name, reason in SESSION_AUDIENCE_TOOLS.items() if "nscoped" in reason
    }
    assert unscoped == {
        "list_sessions",
        "get_session",
        "spawn_session",
        "send_to_session",
        "ask_session",
        "get_session_output",
    }, sorted(unscoped)
    assert set(SESSION_AUDIENCE_TOOLS) - unscoped == {"report_blocked", "request_help"}
    for name in sorted(set(SESSION_AUDIENCE_TOOLS) - unscoped):
        assert "G-M4-15" in SESSION_AUDIENCE_TOOLS[name], name


def test_the_rule_reads_the_file_and_refuses_what_it_cannot_resolve() -> None:
    """B1, and the *unreadable* branch, which is the half that keeps "every" true.

    Driven on planted text rather than on the tree, because the tree resolves
    cleanly — so without this the branch would be a rule half of which is a
    comment (the reason `core_grows_io.py` exists, one rule over).
    """
    with pytest.raises(FileNotFoundError):
        tool_audiences(MISSING_MODULE)

    def read(source: str) -> tuple[dict[str, frozenset[str]], list[str]]:
        path = SRC_ROOT / "core" / "ids.py"  # a real path, so `parsed` has one
        tree = ast.parse(source)
        bindings = _module_bindings(tree)
        found: dict[str, frozenset[str]] = {}
        unreadable: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id != TOOL_DEF:
                    continue
                keywords = {k.arg: k.value for k in node.keywords}
                name_node, audiences_node = keywords.get("name"), keywords.get("audiences")
                name = name_node.value if isinstance(name_node, ast.Constant) else None
                if not isinstance(name, str):
                    unreadable.append("unnamed")
                    continue
                members = (
                    _audience_members(audiences_node) if audiences_node is not None else None
                )
                if members is None and isinstance(audiences_node, ast.Name):
                    bound = bindings.get(audiences_node.id)
                    members = _audience_members(bound) if bound is not None else None
                if members is None:
                    unreadable.append(name)
                else:
                    found[name] = members
        assert path.exists()
        return found, unreadable

    inline = 'ToolDef(name="t", audiences=frozenset({Audience.SESSION, Audience.HUMAN}))'
    assert read(inline) == ({"t": frozenset({"SESSION", "HUMAN"})}, [])

    named = 'A = frozenset({Audience.SESSION})\nToolDef(name="t", audiences=A)\n'
    assert read(named) == ({"t": frozenset({"SESSION"})}, [])

    # …and every spelling this rule cannot read is a **violation**, never a clean
    # answer: a computed set, a set arithmetic expression, a name bound to
    # something it cannot follow, and a missing keyword.
    assert read('ToolDef(name="t", audiences=audiences_for("t"))') == ({}, ["t"])
    assert read('ToolDef(name="t", audiences=EVERY - {Audience.HUMAN})') == ({}, ["t"])
    assert read('ToolDef(name="t", audiences=SOMETHING_ELSE)') == ({}, ["t"])
    assert read('ToolDef(name="t", blast_class=1)') == ({}, ["t"])
    assert read("ToolDef(name=compute(), audiences=A)") == ({}, ["unnamed"])


def test_the_rule_bites_on_a_planted_session_audience() -> None:
    """The positive control, on an **inert fixture** — never on live source.

    A tool in a module none of the shipped rules covers: not a master tool, not a
    destructive M3 tool, not a tool whose audiences any test pins. That is
    precisely the tool the remediation planted on and watched the whole default
    suite stay green (1779 passed). This rule reports it by name.
    """
    declared, unreadable = tool_audiences(fixture("a_new_module_grows_a_session_tool.py"))
    assert unreadable == []
    assert declared == {
        "snapshot_everything": frozenset({"MASTER", "SESSION", "HUMAN"}),
        "quiet_reader": frozenset({"HUMAN"}),
    }
    assert session_audience_tools(declared) == frozenset({"snapshot_everything"})
    assert session_audience_tools(declared) - set(SESSION_AUDIENCE_TOOLS) == {
        "snapshot_everything"
    }
