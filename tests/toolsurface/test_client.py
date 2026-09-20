"""T16 — the one door `master/` has into the tool surface (D19, D32, D54).

**Every expected value here is a literal or a written-out set.** Nothing in this
file rebuilds an answer the way `client.py` builds it: the fixture tools declare
their audiences in one table and the expected projections are typed out in
another, so a filter that is dropped or inverted disagrees with a literal rather
than with a second copy of itself.

**Populations are enumerated at test time and compared as sets, never as
counts** (K19). A bare count cannot tell *the client lost a member* from
*the client gained `registered_tools`*, and the second one is the whole reason
D19 names a single module. The enumeration rules live in `public_names()`,
`imported_names()` and `shepherd_imports_under()` below, so the rule a check
relies on is readable next to the check.

**Arrival before absence, as an assertion.** Every check that asserts something
is *missing* first asserts the scan found something: the module's name set is
asserted non-empty, the master package's file set is asserted to contain
`prompt.py`, and the refusal checks call a tool that works before they call one
that must not.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType

import pytest

from _imports import (
    MASTER_PACKAGE,
    master_import_violations,
    permitted_master_import,
)
from shepherd.toolsurface import client
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import Audience, BlastClass, ToolArgs, ToolDef

MASTER = Audience.MASTER
SESSION = Audience.SESSION
HUMAN = Audience.HUMAN

CLIENT_SOURCE = Path(client.__file__)
REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_PACKAGE_ROOT = REPO_ROOT / "src" / "shepherd" / "master"


# --------------------------------------------------------------------------- #
# the enumeration rules, written out so a check's population is readable
# --------------------------------------------------------------------------- #


def public_names(module: ModuleType) -> frozenset[str]:
    """Every name the module offers a caller, read from `vars()` at test time.

    **Imported names are deliberately included.** `from shepherd.store.db import
    Store` binds `Store` in this module's namespace and hands it to anything
    that imports the client — so a surface check that filtered imports out would
    be blind to the exact widening D19 forbids. Underscore-prefixed names are
    excluded because this repo already spells "not the surface" that way
    (`registry._TOOLS`, `stream._RING`).
    """
    return frozenset(name for name in vars(module) if not name.startswith("_"))


def imported_names(source: Path) -> frozenset[str]:
    """Every module path and every bound symbol `source` imports, by AST.

    AST and not a grep: a textual scan for `import` also matches a docstring
    that discusses one, which is a rule answering a different question than the
    one asked (T19-1's reasoning, applied here).
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                found.add(node.module)
            found.update(alias.name for alias in node.names)
    return frozenset(found)


def shepherd_imports_under(root: Path) -> tuple[frozenset[str], frozenset[str]]:
    """`(shepherd module paths imported, file names scanned)` under `root`.

    Returns the scanned population alongside the answer so a caller can assert
    the scan found something before it asserts the answer is small — a scan of
    nothing finds nothing, and would report perfect isolation for a deleted
    package.
    """
    imported: set[str] = set()
    scanned: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned.add(path.name)
        for name in imported_names(path):
            if name == "shepherd" or name.startswith("shepherd."):
                imported.add(name)
    return frozenset(imported), frozenset(scanned)


# --------------------------------------------------------------------------- #
# the declared fixture surface — the independent source of truth
# --------------------------------------------------------------------------- #

#: name -> (schema, audiences). Read by `_register_fixture_tools`; the expected
#: projections below are typed out separately rather than derived from this.
_FIXTURE_TOOLS: Mapping[str, tuple[Mapping[str, object], frozenset[Audience]]] = {
    "fleet_summary": ({"type": "object", "properties": {}}, frozenset({MASTER, SESSION, HUMAN})),
    "kill_session": (
        {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        frozenset({MASTER, HUMAN}),
    ),
    "open_settings": ({"type": "object", "properties": {}}, frozenset({HUMAN})),
    "report_blocked": ({"type": "object", "properties": {}}, frozenset({SESSION})),
}

#: What the master must see through the client. Written out, not filtered: this
#: is the second, independent statement of the audience rule.
_EXPECTED_MASTER_TOOLS = frozenset({"fleet_summary", "kill_session"})

#: The client's whole surface, typed out. Every entry is a capability granted to
#: `master/`, which is why this is an **equality**: a member added without a
#: line here is a failing build, and that is the D19 budget made mechanical.
_EXPECTED_PUBLIC_NAMES = frozenset(
    {
        # bound by `from __future__ import annotations`
        "annotations",
        # vocabulary the signatures are written in
        "Callable",
        "Mapping",
        "dataclass",
        "ExportedTool",
        "Audience",
        "CallerContext",
        # the L4 seam the client sits on
        "call_exported",
        "exported_tools",
        # the plan's Produces block for Task 16
        "MASTER_AUDIENCE",
        "master_tools",
        "call",
        "withdraw_approval",
        "withdraw_turn_approvals",
        "autonomy_level",
        # the composition root's side of the seam (§T16-1)
        "MasterClientUnbound",
        "bind_master_client",
        "reset_master_client",
    }
)

#: Everything `client.py` may import, typed out. Equality, for the same reason.
_EXPECTED_IMPORTS = frozenset(
    {
        "__future__",
        "annotations",
        "collections.abc",
        "Callable",
        "Mapping",
        "dataclasses",
        "dataclass",
        "shepherd.core.master",
        "ExportedTool",
        "shepherd.toolsurface.export",
        "call_exported",
        "exported_tools",
        "shepherd.toolsurface.types",
        "Audience",
        "CallerContext",
    }
)

#: The three the plan names by name. Subsumed by the equality above and written
#: out anyway, because the failure message is what a reviewer reads first.
_FORBIDDEN = frozenset({"Store", "ToolDef", "registered_tools"})


def _register_fixture_tools(calls: dict[str, int]) -> None:
    def counted(name: str) -> object:
        def handler(args: ToolArgs, ctx: CallerContext) -> object:
            calls[name] = calls.get(name, 0) + 1
            return {"tool": name, "args": dict(args)}

        return handler

    for name, (schema, audiences) in _FIXTURE_TOOLS.items():
        register(
            ToolDef(
                name=name,
                description=f"{name} for the client tests.",
                input_schema=schema,
                blast_class=BlastClass.LOCAL_READ,
                handler=counted(name),  # type: ignore[arg-type]
                audiences=audiences,
            )
        )


@pytest.fixture
def calls() -> dict[str, int]:
    counted: dict[str, int] = {}
    _register_fixture_tools(counted)
    return counted


#: What a bound client answers. Literals, so a member that returns the wrong
#: neighbour's value disagrees with one of them.
_BOUND_AUTONOMY = 2
_WITHDRAWN_APPROVAL_IDS = ("apr_live",)


@pytest.fixture(autouse=True)
def unbound_client() -> Iterator[None]:
    """The wiring is a module global (ADR-7), so each test starts unbound."""
    client.reset_master_client()
    yield
    client.reset_master_client()


@pytest.fixture
def seen() -> dict[str, list[str]]:
    """What the root's callables were handed. A client that ignored its own
    argument and withdrew everything is D54's bug, and this is what sees it."""
    return {"approval": [], "turn": []}


@pytest.fixture
def bound(seen: dict[str, list[str]]) -> None:
    def withdraw_approval(approval_id: str) -> bool:
        seen["approval"].append(approval_id)
        return approval_id in _WITHDRAWN_APPROVAL_IDS

    def withdraw_turn_approvals(turn_id: str) -> int:
        seen["turn"].append(turn_id)
        return len(turn_id)

    client.bind_master_client(
        withdraw_approval=withdraw_approval,
        withdraw_turn_approvals=withdraw_turn_approvals,
        autonomy_level=lambda: _BOUND_AUTONOMY,
    )


# --------------------------------------------------------------------------- #
# the plan's three Required Checks
# --------------------------------------------------------------------------- #


def test_the_client_exposes_no_store_and_no_registry() -> None:
    """D19's budget, as an equality over two enumerated populations.

    Goes red if `Store`, `ToolDef` or `registered_tools` appears in either the
    module's names or its import set — and equally red on any *other* member,
    which is the half a deny-list of three names would miss.
    """
    names = public_names(client)
    imports = imported_names(CLIENT_SOURCE)

    # arrival: the scans found a module and a file with imports in it
    assert "call" in names, "the client has no `call`; the name scan points at nothing"
    assert "shepherd.toolsurface.export" in imports, "the import scan points at nothing"

    assert names == _EXPECTED_PUBLIC_NAMES
    assert imports == _EXPECTED_IMPORTS
    assert names & _FORBIDDEN == frozenset()
    assert imports & _FORBIDDEN == frozenset()


def test_calling_an_unexported_tool_is_refused(calls: dict[str, int]) -> None:
    """The audience is pinned inside the client, so the caller cannot choose it.

    Arrival first: a tool the master *may* call is driven through `call()` and
    asserted to have reached its handler, so the refusal below is a refusal and
    not a client that cannot call anything.
    """
    allowed = client.call("fleet_summary", {}, "master", "cor_allowed")
    assert allowed["is_error"] is False
    assert calls["fleet_summary"] == 1

    refused = client.call("open_settings", {}, "master", "cor_refused")
    assert refused["is_error"] is True
    content = refused["content"]
    assert isinstance(content, list)
    text = content[0]["text"]
    assert "cor_refused" in text, "the correlation id the caller passed never reached the result"
    assert calls.get("open_settings", 0) == 0, "a HUMAN-only tool reached its handler"


def test_the_client_is_the_only_shepherd_import_the_master_needs() -> None:
    """The structural half of D19, as `master/` stands today.

    **T22 ships the allow-list that enforces this**; what is asserted here is
    the property itself, over the real package. Recorded honestly in `t16.md`:
    `master/` imports nothing from `shepherd` at all right now (T19-3 measured
    the same), so the subset assertion is satisfied by an empty left side. The
    arrival assertion is what keeps that from being vacuous — the scan is proved
    to be looking at the package before it reports it clean.
    """
    imported, scanned = shepherd_imports_under(MASTER_PACKAGE_ROOT)

    assert {"__init__.py", "prompt.py"} <= scanned, f"the master scan found only {scanned}"

    # **D19's master predicate has ONE definition site** (RD-T5-5, §T22-6).
    # T21 widened this check to `{client} ∪ core.* ∪ master.*` with a floor of six
    # packages and flagged that T22 would otherwise land red; T22 shipped the same
    # predicate as a named function and recorded that *"the duplication is the
    # problem"* — a rule copied into a second file can be widened in one place and
    # keep biting from another, and neither copy is the wrong one. The convergence
    # T22 named is this line: the rule is imported from the shared walker rather
    # than restated here, so the allow-list, the floor and the spellings the scan
    # resolves are all decided in exactly one place.
    #
    # `master_import_violations` reads `all_imports`, so it also sees the two
    # call-shaped spellings this file's own `imported_names` never could —
    # `importlib.import_module(...)` and `__import__(...)` are `ast.Call` nodes.
    # That is a strengthening of this check, not a restatement of it.
    for path in sorted(MASTER_PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        assert master_import_violations(path, MASTER_PACKAGE) == [], path.name

    # Arrival, because the loop above is satisfied by a package that imports
    # nothing: the predicate is shown to say **no** to the things D19 names, over
    # the same objects the scan would hand it.
    assert not permitted_master_import("shepherd.store.db")
    assert not permitted_master_import("shepherd.toolsurface.registry")
    assert permitted_master_import("shepherd.toolsurface.client")

    core_root = MASTER_PACKAGE_ROOT.parent / "core"
    core_imports, core_scanned = shepherd_imports_under(core_root)
    assert core_scanned, "the core scan found nothing — it is not proving purity"
    assert core_imports <= {
        name for name in core_imports if name.startswith("shepherd.core.")
    }, f"core/ is no longer pure vocabulary: {sorted(core_imports)}"


# --------------------------------------------------------------------------- #
# the members, and the wiring T16 added to make them satisfiable (§T16-1)
# --------------------------------------------------------------------------- #


def test_master_tools_is_the_master_subset_and_the_client_picks_the_audience(
    calls: dict[str, int],
) -> None:
    """Compared as a set of names against a literal, never a count."""
    assert frozenset(tool.name for tool in client.master_tools()) == _EXPECTED_MASTER_TOOLS
    assert client.MASTER_AUDIENCE is Audience.MASTER


def test_an_unbound_client_refuses_readably_and_says_which_member(bound: None) -> None:
    """Arrival first: the bound client answers, and only then is it reset.

    The refusing set is **written out**: a non-emptiness assertion over four
    members cannot tell "all four refuse" from "the first one does".
    """
    assert client.autonomy_level() == _BOUND_AUTONOMY  # arrival

    client.reset_master_client()

    members = {
        "autonomy_level": client.autonomy_level,
        "withdraw_approval": lambda: client.withdraw_approval("apr_live"),
        "withdraw_turn_approvals": lambda: client.withdraw_turn_approvals("tur_1"),
    }
    refused = set()
    for name, member in members.items():
        try:
            member()
        except client.MasterClientUnbound:
            refused.add(name)
    assert refused == set(members)


def test_each_member_answers_with_what_the_root_installed(
    bound: None, seen: dict[str, list[str]]
) -> None:
    """Each answer is a distinct literal, so a member wired to its neighbour's
    callable disagrees with one of them; and each argument is asserted to have
    arrived, because a withdrawal that ignores its id withdraws everything."""
    assert client.autonomy_level() == _BOUND_AUTONOMY

    assert client.withdraw_approval("apr_live") is True
    assert client.withdraw_approval("apr_gone") is False
    assert seen["approval"] == ["apr_live", "apr_gone"]

    assert client.withdraw_turn_approvals("tur_17") == len("tur_17")
    assert seen["turn"] == ["tur_17"]


def test_a_root_that_answers_the_other_level_is_passed_on_unchanged() -> None:
    """The root's value, not a client default.

    This used to be `test_a_root_that_has_no_wake_text_is_a_value_the_client_
    passes_on`, asserting `wake_text() -> str | None` distinguished *nothing to
    say* from *an empty summary*. `wake_text` was retired from this surface by
    RD-T16-7a — it drained the wake set, and so does the turn driver, which is
    D31's lost stop. What the check was really worth keeping for is the
    pass-through property, so that is what it asserts now, over the member that
    remains.
    """
    client.bind_master_client(
        withdraw_approval=lambda approval_id: False,
        withdraw_turn_approvals=lambda turn_id: 0,
        autonomy_level=lambda: 3,
    )
    assert client.autonomy_level() == 3
