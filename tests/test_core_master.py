"""T2: the orchestrator vocabulary `master/`, `toolsurface/`, `orchestration/`
and `web/` all speak, and the two package-level facts M4 adds.

Three things are proved here and nowhere else:

* the **seam's shape** — six members (DP9), `send()` async exactly as §6:472
  writes it and `configure()` taking `ExportedTool` rather than `ToolDef`
  (DP12's one flagged widening, because D19 makes `ToolDef` impossible);
* the **curated fact table** — DP8 refused to add a field to
  `MasterCapabilities`, so the two values no probe can fill live in a table
  that must name where each value came from;
* **K24** — every M4 anomaly member has a *reachable* increment site. A counter
  that can only be incremented by code the import rules forbid from reaching
  the counter is always zero, which is K9's defect wearing compliance.
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import get_args, get_type_hints

from shepherd.core import master as core_master

# Resolved through the module rather than by `from … import`, so a missing name
# is a **behavioural** failure inside one test rather than a collection error
# that takes the whole file down and proves nothing about any of them.

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "shepherd"
MANIFEST = REPO_ROOT / "pyproject.toml"


# --------------------------------------------------------------------------
# The seam
# --------------------------------------------------------------------------


def protocol_members(protocol: type) -> set[str]:
    """The names a structural implementation must supply, read off the class."""
    return {
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }


def test_master_runtime_has_six_members() -> None:
    """A **name set**, written out, never a count (K19).

    §6 writes five. The sixth is `close()`: DP9 found that `MasterRuntime` as
    specified cannot be shut down, and `daemons/shutdown.py` needs a verb to
    call. Goes red if a member is added or removed without this plan changing.
    """
    assert protocol_members(core_master.MasterRuntime) == {
        "configure",
        "send",
        "resume",
        "interrupt",
        "capabilities",
        "close",
    }


def module_level_names(source: str) -> set[str]:
    """Every public name this module defines at top level, read off its own AST.

    **The rule:** a top-level `class`, `def`, or assignment target. Imports are
    excluded — they are names this module *borrows*, and pinning them would make
    the set go red on a refactor that changed nothing about what `core/master.py`
    offers its four callers.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return {name for name in names if not name.startswith("_")}


def test_the_modules_public_names_are_the_pinned_set() -> None:
    """§T2-5's pin, **re-pinned** because T18 added a name to this module.

    RD-T17-2: the master seam had no refusal vocabulary, so `ScriptedMaster`
    raised a bare `RuntimeError` and a contract suite asserting on it was
    asserting on a spelling — `pytest.raises(RuntimeError)` is satisfied by
    almost any bug a half-built `AgentSDKMaster` can raise, including an
    `AttributeError` that is not a refusal at all. `MasterRefusal` is the same
    shape as `RunnerRefusal` one layer down, and it is the **only** addition:
    this set is the statement that nothing else came with it.

    A **name set**, written out, never a count (K19). Goes red on the next
    addition too, which is the point of re-pinning rather than widening.
    """
    assert module_level_names(MASTER_SOURCE) == {
        "ExportedTool",
        "MasterCapabilities",
        "MasterEventKind",
        "MASTER_EVENT_KINDS",
        "MasterEvent",
        "MasterRefusal",
        "MasterRuntime",
        "CuratedFact",
        "CURATED_MASTER_FACTS",
    }


def test_the_refusal_is_the_shape_the_runner_seam_already_uses() -> None:
    """RD-T17-2's *"the same shape as `RunnerRefusal`"*, asserted rather than asserted-to.

    Compared **against `RunnerRefusal` itself**, not against a restatement of it:
    a second spelling of "what a refusal looks like" is the drift D32 removed
    three lists to prevent. The base matters — `Exception`, not `RuntimeError`:
    leaving `RuntimeError` in the hierarchy would keep alive exactly the
    `pytest.raises(RuntimeError)` assertion this decision exists to retire.
    """
    from shepherd.core.runner import RunnerRefusal

    assert core_master.MasterRefusal.__bases__ == RunnerRefusal.__bases__ == (Exception,)
    refusal = core_master.MasterRefusal("the runtime is closed")
    assert refusal.reason == RunnerRefusal("the runtime is closed").reason
    assert str(refusal) == "the runtime is closed"
    assert not isinstance(refusal, RuntimeError)
    # …and it is a module-level name, not a seventh member of the Protocol.
    assert "MasterRefusal" not in protocol_members(core_master.MasterRuntime)


def test_the_two_flagged_signature_differences_from_section_6_are_the_ones_dp12_named() -> None:
    """DP12, and it is the assertion revision 1 had no equivalent of.

    `send()` stays **async** (§6:472, as written) — revision 1 wrote a
    synchronous `Iterator` in two places while claiming no §6 change, and a
    sync `send()` wrapping an async SDK needs a loop thread that appears in no
    task. `configure()` takes `ExportedTool`, which **is** a change to a §6
    signature, because `list[ToolDef]` is impossible under D19: `ToolDef`
    carries a handler, audiences and a blast class — gate vocabulary the master
    has no business holding.
    """
    annotations = core_master.MasterRuntime.send.__annotations__
    assert annotations["return"] == "AsyncIterator[MasterEvent]"
    configure = core_master.MasterRuntime.configure.__annotations__
    assert configure["tools"] == "tuple[ExportedTool, ...]"
    assert "ToolDef" not in MASTER_SOURCE
    # …and the exported shape carries nothing a model could reason about its
    # own permissions with: name, description, schema, and nothing else.
    assert [field.name for field in fields(core_master.ExportedTool)] == [
        "name",
        "description",
        "input_schema",
    ]


MASTER_SOURCE = (SRC / "core" / "master.py").read_text(encoding="utf-8")


def test_master_event_kinds_are_exactly_adr_m4_5s_seven() -> None:
    """Our vendor-free projection. Written out from ADR-M4-5 — an independent
    source of truth — and compared to the domain the dataclass field declares,
    so the two cannot drift apart silently.
    """
    assert core_master.MASTER_EVENT_KINDS == frozenset(
        {
            "text",
            "thinking",
            "tool_call",
            "tool_result",
            "turn_ended",
            "rate_limit",
            "error",
        }
    )
    hints = get_type_hints(core_master.MasterEvent)
    assert set(get_args(hints["kind"])) == set(core_master.MASTER_EVENT_KINDS)
    # K13: no vendor word crosses into L1.
    for vendor in (
        "AssistantMessage",
        "ResultMessage",
        "RateLimitEvent",
        "mcp__shepherd__",
        "can_use_tool",
        "ClaudeAgentOptions",
        "claude_agent_sdk",
    ):
        assert vendor not in MASTER_SOURCE, vendor


# --------------------------------------------------------------------------
# The curated facts (DP8)
# --------------------------------------------------------------------------


def test_every_curated_fact_names_its_source() -> None:
    """DP8: `MasterCapabilities` gains no field, so the values no probe could
    fill live here — each beside the capture or spec line it came from.

    Goes red if an entry has an empty source, which is what stops the table
    growing a guess.
    """
    wanted = {field.name for field in fields(core_master.MasterCapabilities)}  # enumerated (K19)
    assert set(core_master.CURATED_MASTER_FACTS) == wanted

    for name, fact in core_master.CURATED_MASTER_FACTS.items():
        assert isinstance(fact, core_master.CuratedFact), name
        assert fact.source.strip() != "", f"{name} has no source"

    # Arrival: the table really does build the record §6 declares.
    record = core_master.MasterCapabilities(
        **{name: fact.value for name, fact in core_master.CURATED_MASTER_FACTS.items()}  # type: ignore[arg-type]
    )
    assert record.billing_mode == "seat"

    # …and every `docs/` path a source names is a file that exists, so a source
    # string cannot be a plausible-looking path nobody captured.
    cited = [
        word.strip("`,;()")
        for fact in core_master.CURATED_MASTER_FACTS.values()
        for word in fact.source.split()
        if word.strip("`,;()").startswith("docs/")
    ]
    assert cited, "no curated fact cites a capture at all"
    missing = [path for path in cited if not (REPO_ROOT / path).exists()]
    assert missing == [], missing


def test_the_fact_that_was_never_observed_says_so() -> None:
    """`supports_parallel_tool_calls` was never observed (`data-schemas.md`
    §Not verified). A capability record that lies on the first call is worse
    than one that says it does not know.
    """
    fact = core_master.CURATED_MASTER_FACTS["supports_parallel_tool_calls"]
    assert fact.value is False
    assert "never observed" in fact.source.lower()


# --------------------------------------------------------------------------
# The dependency declaration
# --------------------------------------------------------------------------


def manifest() -> dict[str, object]:
    with MANIFEST.open("rb") as handle:
        loaded: dict[str, object] = tomllib.load(handle)
    return loaded


def declared_dependencies() -> dict[str, str]:
    project = manifest()["project"]
    assert isinstance(project, dict)
    declared = project["dependencies"]
    assert isinstance(declared, list)
    parsed: dict[str, str] = {}
    for entry in declared:
        text = str(entry)
        name = text.split(">")[0].split("<")[0].split("=")[0].strip()
        parsed[name] = text[len(name) :]
    return parsed


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(".") if part.isdigit())


def test_the_sdk_is_a_declared_dependency() -> None:
    """Goes red if `claude_agent_sdk` is importable and undeclared — the state
    the build was in before M4: the master track reads the SDK's shapes on
    every line and the manifest said the package had no dependencies at all.
    """
    declared = declared_dependencies()
    assert "claude-agent-sdk" in declared, sorted(declared)
    assert "anyio" in declared, sorted(declared)

    for distribution in ("claude-agent-sdk", "anyio"):
        if importlib.util.find_spec(distribution.replace("-", "_")) is None:
            continue
        installed = version_tuple(importlib.metadata.version(distribution))
        specifier = declared[distribution]
        floor = version_tuple(specifier.split(">=")[1].split(",")[0])
        assert floor <= installed, (distribution, floor, installed)
        if "<" in specifier.split(">=")[1]:
            ceiling = version_tuple(specifier.split("<")[-1])
            assert installed < ceiling, (distribution, installed, ceiling)


def test_the_sdk_floor_is_the_version_this_host_measured() -> None:
    """G-M4-1: the honest range is a `<0.3` ceiling over the **measured** floor.

    Pinning exactly would make the manifest a fiction the first time the SDK
    moves; a floor below what was measured would claim a version nobody ran.
    """
    declared = declared_dependencies()["claude-agent-sdk"]
    floor = declared.split(">=")[1].split(",")[0]
    assert version_tuple(floor) == version_tuple(
        importlib.metadata.version("claude-agent-sdk")
    )
    assert declared.endswith("<0.3")


def test_track_c_left_no_console_script_behind() -> None:
    """Revision 1 added `shepherd-mcp` here; it is cut with Track C. A console
    script for a process that does not exist is a `PATH` entry that fails at
    import — written out, never counted (K19).
    """
    project = manifest()["project"]
    assert isinstance(project, dict)
    scripts = project["scripts"]
    assert isinstance(scripts, dict)
    assert set(scripts) == {"shepherd", "shepherd-controld", "shepherd-sessiond"}


# --------------------------------------------------------------------------
# K24 — every M4 anomaly member has a *reachable* increment site
# --------------------------------------------------------------------------
#
# The defect this exists to make impossible: a counter that can only be
# incremented by code the import rules forbid from reaching the counter is
# **always zero**, and a zero row that can never move looks exactly like a
# clean system. Revision 1 of the M4 plan shipped four such members — all
# raised inside `master/`, which D19 forbids from importing a store — so the
# repair is injection rather than import, and this is the check that keeps it
# true when the ninth member arrives.

#: D19: `master/` reaches the system only through the tool-surface client, so a
#: module under it can never call a store. It may still *name* a member, if the
#: member is handed to a `bump` that was injected from a layer that can.
MASTER_PACKAGE = SRC / "master"

#: The call shapes that hand a member to somebody else's counter. `bump` is
#: M4's name for it; `record_anomaly` is the one `core/runner.py` already uses,
#: and naming both is what stops the rule from being about a spelling.
BUMP_CALL_NAMES = ("bump", "record_anomaly", "bump_anomaly")

#: Members whose increment site belongs to a task that has not landed yet, each
#: with the task that owns it and the module it will live in. **Self-expiring**:
#: the entry is only valid while the module does not exist, so the day T4
#: creates `toolsurface/approvals.py` this table has to become a real site or
#: the check goes red. A permanent exemption would be the same defect wearing a
#: different hat.
PENDING_SITES: dict[str, tuple[str, str]] = {
    # **Empty, and that is the milestone's own measure.** Every M4 member now has
    # a site the resolver can find: T4 and T5 took the approval and audit rows,
    # T20 took `MASTER_TOOL_RESULT_ORPHANED`, and T21 took the last three —
    # `MASTER_TOOL_UNEXPECTED` (DP7's belt), `MASTER_RESULT_UNMAPPED` (G-M4-5's
    # counted `unknown` ending) and `MASTER_RESUME_LOST` (E-M4-8). Each removal
    # was asked for by this check's own failure message, quoted in the task's
    # blocker file; none was removed to make a run go green.
    #
    # The table stays, rather than being deleted with its last row: it is the
    # declaration mechanism for the ninth member, and a member arriving with no
    # site and no owner is what `test_every_m4_anomaly_member_has_a_reachable_
    # increment_site` refuses.
}

#: The module that turns an injected `bump` back into a real counter: L6 builds
#: the master and hands it a callable closed over the store (ADR-M4-6). Also
#: self-expiring, and it is the other half of K24 — four members are reachable
#: only if this exists.
PENDING_COUNTER_PROVIDER = ("T25", "daemons/plane.py")


def imports_a_store(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("shepherd.store") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "shepherd.store"
        ):
            return True
    return False


def call_name(node: ast.Call) -> str:
    target = node.func
    if isinstance(target, ast.Attribute):
        return target.attr
    return getattr(target, "id", "")


def module_references(source: str) -> tuple[set[str], set[str], bool]:
    """`(named, handed_to_a_bump, reaches_a_store)` for one module's source.

    `named` is every `AnomalyKind.X` in the module. `handed_to_a_bump` is the
    subset passed as an argument to a bump-shaped call — which is what an
    injected counter looks like from the inside, and the only way a module that
    cannot import a store can still increment one.
    """
    tree = ast.parse(source)
    named: set[str] = set()
    handed: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "AnomalyKind"
        ):
            named.add(node.attr)
        if isinstance(node, ast.Call) and call_name(node).endswith(BUMP_CALL_NAMES):
            for argument in node.args:
                if (
                    isinstance(argument, ast.Attribute)
                    and isinstance(argument.value, ast.Name)
                    and argument.value.id == "AnomalyKind"
                ):
                    handed.add(argument.attr)
    return named, handed, imports_a_store(tree)


def increment_sites(root: Path) -> dict[str, dict[str, list[str]]]:
    """member -> {"reachable": [modules], "unreachable": [modules]}.

    A module is a **reachable** site when it names the member and is allowed to
    reach a counter — i.e. it is not under `master/`, or it is and the member is
    handed to an injected bump rather than to a store the module imported
    itself. Anything else that names a member is an **unreachable** site, which
    is the state K24 forbids: the code that observes the condition is not the
    code that can count it, and nobody finds out.
    """
    found: dict[str, dict[str, list[str]]] = {}
    for path in sorted(root.rglob("*.py")):
        named, handed, store = module_references(path.read_text(encoding="utf-8"))
        if not named:
            continue
        relative = str(path.relative_to(root))
        inside_master = path.is_relative_to(root / "master")
        for member in named:
            bucket = found.setdefault(member, {"reachable": [], "unreachable": []})
            reachable = (not inside_master) or (member in handed and not store)
            bucket["reachable" if reachable else "unreachable"].append(relative)
    return found


def m4_members() -> list[str]:
    """Enumerated from the enum's own section marker — never a written list,
    because a written list is a second place to forget."""
    # Imported from the append-only test rather than restated: the section
    # marker and the reader live in exactly one place, so the two checks can
    # never disagree about which members are M4's.
    from test_core_types import M4_SECTION_MARKER, members_after_marker

    source = (SRC / "core" / "anomalies.py").read_text(encoding="utf-8")
    return members_after_marker(source, M4_SECTION_MARKER)


def test_the_site_resolver_finds_the_sites_that_already_exist() -> None:
    """Arrival, asserted rather than assumed: the resolver really does resolve.

    Every member shipped before M4 is counted somewhere in `src/` today, so if
    the scan returns nothing for them it is broken — and a broken scan is how a
    check reports success without checking. This runs first for that reason.
    """
    from shepherd.core.anomalies import AnomalyKind

    sites = increment_sites(SRC)
    older = [member.name for member in AnomalyKind if member.name not in set(m4_members())]
    assert older, "the pre-M4 population is empty — the enumeration is wrong"

    unsited = [name for name in older if not sites.get(name, {}).get("reachable")]
    assert unsited == [], unsited
    # …and no module already in the tree reaches for a counter it cannot have.
    assert {
        member: bucket["unreachable"]
        for member, bucket in sites.items()
        if bucket["unreachable"]
    } == {}


def test_every_m4_anomaly_member_has_a_reachable_increment_site() -> None:
    """P-M4-20 / K24.

    Goes red three ways, which is the whole point:
    * a member is added with no site and no declared owner;
    * a site sits in `master/` and reaches for a store itself (D19 forbids the
      import, so that site can never run) — or names the member without handing
      it to an injected bump, which is the always-zero counter;
    * a declared-pending entry outlives the site it was waiting for.

    **T2 ships this check with every M4 member declared-pending**, because T2
    is the first task in the milestone and not one of the eight increment sites
    exists yet. That is stated rather than hidden: each entry names the task
    that owes the site, an entry may not survive its site landing, and an entry
    may not exist for a member the enum does not have. The milestone is not
    done while `PENDING_SITES` is non-empty, which is recorded in the M4
    BLOCKERS file rather than left to be noticed.
    """
    members = m4_members()
    assert members, "no M4 section members were enumerated"
    sites = increment_sites(SRC)

    for member in members:
        bucket = sites.get(member, {"reachable": [], "unreachable": []})
        assert bucket["unreachable"] == [], (
            f"{member} is named in {bucket['unreachable']}, which cannot reach a"
            " counter (D19). Inject a bump; do not import a store."
        )
        if bucket["reachable"]:
            # The site landed, so the exemption has expired. A pending entry
            # left behind is a stale exemption that would still be shielding
            # the **next** member someone drops in beside it.
            assert member not in PENDING_SITES, (
                f"{member} is incremented at {bucket['reachable']} — remove its"
                " PENDING_SITES entry."
            )
            continue
        assert member in PENDING_SITES, (
            f"{member} has no increment site and no owner — a counter nothing"
            " can increment is always zero (K24)."
        )
        owner, module = PENDING_SITES[member]
        assert owner.startswith("T") and module.endswith(".py"), (member, owner, module)
        declared = SRC / module
        if declared.exists():
            assert member not in declared.read_text(encoding="utf-8"), (
                f"{member}: {module} names it already — the entry has expired."
            )

    # The table may not outlive the enum either: an entry for a member that no
    # longer exists is a stale exemption nobody would notice.
    assert set(PENDING_SITES) <= set(members), sorted(set(PENDING_SITES) - set(members))


def test_the_injected_counter_provider_is_declared() -> None:
    """K24's other half: the four members raised inside `master/` are reachable
    only if some layer that *can* reach a store builds the `bump` and passes it
    in. Until L6 lands it, that is declared here and expires the same way.
    """
    owner, module = PENDING_COUNTER_PROVIDER
    provider = SRC / module
    if not provider.exists():
        # The provider is T25's and has not landed. Until it does, what can be
        # asserted is that the members it owes a counter to really are raised
        # inside `master/` and really are handed to an injected bump — read off
        # the tree by the resolver rather than off `PENDING_SITES`, which went
        # empty the moment T21's three sites landed. A check that read the table
        # here would have gone quiet at exactly the point it started mattering.
        injected = {
            member
            for member, bucket in increment_sites(SRC).items()
            if any(site.startswith("master/") for site in bucket["reachable"])
        }
        assert injected, "no member is raised inside master/ — the resolver is broken"
        return

    source = provider.read_text(encoding="utf-8")
    assert "bump_anomaly" in source, (
        f"{module} exists ({owner}) but builds no counter for the master to be"
        " handed — the four master-raised members would be always zero."
    )


def test_the_reachability_rule_bites(tmp_path: Path) -> None:
    """The resolver, run over an **inert** tree that nothing imports.

    The fixture is written as text and parsed as an AST — never on an import
    path, never executed. Each case is one classification the rule has to get
    right, and a self-check: a resolver that answered "reachable" to everything
    would pass the two tests above and prove nothing.
    """
    tree = tmp_path / "shepherd"
    (tree / "master").mkdir(parents=True)
    (tree / "toolsurface").mkdir()

    # 1. A site in a layer that may reach a counter.
    (tree / "toolsurface" / "audit.py").write_text(
        "from shepherd.core.anomalies import AnomalyKind\n"
        "def lost(bump):\n    bump(AnomalyKind.AUDIT_LINE_LOST)\n",
        encoding="utf-8",
    )
    # 2. A site in `master/` that imports a store — the D19 violation, and the
    #    one revision 1 shipped four times.
    (tree / "master" / "sdk_master.py").write_text(
        "from shepherd.store.db import Store\n"
        "from shepherd.core.anomalies import AnomalyKind\n"
        "def lost(store):\n"
        "    store.bump_anomaly(AnomalyKind.MASTER_RESUME_LOST.value)\n",
        encoding="utf-8",
    )
    # 3. A site in `master/` that merely names a member and counts nothing —
    #    the always-zero counter, which looks like compliance.
    (tree / "master" / "sdk_tools.py").write_text(
        "from shepherd.core.anomalies import AnomalyKind\n"
        "def belt():\n    return AnomalyKind.MASTER_TOOL_UNEXPECTED\n",
        encoding="utf-8",
    )
    # 4. A site in `master/` done correctly: injected bump, no store import.
    (tree / "master" / "projection.py").write_text(
        "from shepherd.core.anomalies import AnomalyKind\n"
        "class P:\n"
        "    def __init__(self, bump):\n        self._bump = bump\n"
        "    def unmapped(self):\n"
        "        self._bump(AnomalyKind.MASTER_RESULT_UNMAPPED)\n",
        encoding="utf-8",
    )

    resolved = increment_sites(tree)
    assert resolved["AUDIT_LINE_LOST"]["reachable"] == ["toolsurface/audit.py"]
    assert resolved["AUDIT_LINE_LOST"]["unreachable"] == []
    assert resolved["MASTER_RESUME_LOST"]["unreachable"] == ["master/sdk_master.py"]
    assert resolved["MASTER_RESUME_LOST"]["reachable"] == []
    assert resolved["MASTER_TOOL_UNEXPECTED"]["unreachable"] == ["master/sdk_tools.py"]
    assert resolved["MASTER_RESULT_UNMAPPED"]["reachable"] == ["master/projection.py"]
    # A member nobody names anywhere resolves to nothing at all — which is what
    # sends a new member to the "no site and no owner" assertion above.
    assert "APPROVAL_TIMED_OUT" not in resolved
