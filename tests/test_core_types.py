"""T1: every dataclass in `core/` is frozen, and `core/` imports nothing but stdlib.

Three defects in the first version of this file, all of the same shape — a check
that reported success without having checked:

* relative imports were skipped outright (`node.level == 0`), so
  `from ..store import open_store` inside `core/` passed (C3);
* the escape hatch was `root == "shepherd"`, which admits **any** `shepherd.*`
  module, and `LAYER_OF` puts `core` and `store` both at layer 1 so the direction
  test cannot catch it either — `core/` importing `store/`, which owns `sqlite3`,
  passed every gate in the batch, against ADR-1's stated reason for L1 purity;
* the scan was `glob("*.py")`, not `rglob`, so `core/_tmpsub/leak.py` with an
  unfrozen `@dataclass` **and** `import requests` passed both halves (C4).

The scans below therefore take **source text**, so every self-check is forced to
read content rather than trusting a path.
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path

import pytest
from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.fold_types import FoldDelta, SessionSnapshot
from shepherd.core.frames import Frame
from shepherd.core.signals import (
    SIGNAL_FIELD_KEYS,
    MalformedPayload,
    Signal,
    SignalKind,
    SubagentRef,
    TaskRef,
)
from shepherd.core.stream import StreamEvent

CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "shepherd" / "core"

DECLARED_TYPES = (
    Signal,
    SubagentRef,
    TaskRef,
    MalformedPayload,
    Anomaly,
    FoldDelta,
    SessionSnapshot,
    StreamEvent,
    Frame,
)


CORE_PACKAGE = "shepherd.core"


def core_sources() -> list[tuple[Path, str]]:
    """Every module under `core/`, **recursively** (C4), with its source text."""
    paths = sorted(CORE_DIR.rglob("*.py"))
    assert paths, f"no modules found under {CORE_DIR}"
    return [(path, path.read_text(encoding="utf-8")) for path in paths]


def package_of(path: Path) -> str:
    """`core/_tmpsub/leak.py` -> `shepherd.core._tmpsub` — the anchor for `from ..x`."""
    relative = path.resolve().relative_to(CORE_DIR.resolve().parents[1])
    return ".".join(relative.parts[:-1])


def _dataclass_decorators(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name == "dataclass":
                found.append((node.name, decorator))
    return found


def imported_modules(source: str, package: str) -> set[str]:
    """Fully qualified imports, **relative ones resolved** against `package` (C3)."""
    found: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                prefix = node.module or ""
            else:
                anchor = package.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)]
                prefix = ".".join([*anchor, node.module] if node.module else anchor)
            if prefix:
                found.add(prefix)
    return found


def purity_violations(source: str, package: str, label: str) -> list[str]:
    """`core/` is pure vocabulary: the stdlib, or another `core` module. Nothing else.

    The escape is `shepherd.core`, not `shepherd` (C3): `store/` owns `sqlite3`
    and sits at the same ADR-1 layer, so the layer-direction test is structurally
    incapable of catching `core` -> `store` and this is the only gate that can.
    """
    violations: list[str] = []
    for module in sorted(imported_modules(source, package)):
        root = module.split(".")[0]
        if root in sys.stdlib_module_names:
            continue
        if module == CORE_PACKAGE or module.startswith(CORE_PACKAGE + "."):
            continue
        violations.append(f"{label} imports {module!r}, which is outside core/ and the stdlib")
    return violations


def unfrozen_dataclasses(source: str, label: str) -> list[str]:
    violations: list[str] = []
    for class_name, decorator in _dataclass_decorators(ast.parse(source)):
        if not isinstance(decorator, ast.Call):
            violations.append(f"{label}:{class_name} bare @dataclass")
            continue
        frozen = [
            kw.value
            for kw in decorator.keywords
            if kw.arg == "frozen" and isinstance(kw.value, ast.Constant)
        ]
        if not frozen or frozen[0].value is not True:
            violations.append(f"{label}:{class_name} not frozen")
    return violations


def test_core_types_are_frozen_and_pure() -> None:
    # 1. Every declared core type is a frozen dataclass at runtime.
    for declared in DECLARED_TYPES:
        assert dataclasses.is_dataclass(declared), declared
        params = getattr(declared, "__dataclass_params__")
        assert params.frozen is True, f"{declared.__name__} is not frozen=True"

    # 2. No @dataclass anywhere in core/ may omit frozen=True — recursively (C4).
    sources = core_sources()
    assert [
        message
        for path, source in sources
        for message in unfrozen_dataclasses(source, path.name)
    ] == []

    # 3. core/ is pure vocabulary: stdlib, or another core module. Nothing else.
    assert [
        message
        for path, source in sources
        for message in purity_violations(source, package_of(path), path.name)
    ] == []

    # self-check: each scan must bite on the exact form that defeated it (C3, C4).
    # A relative import of a sibling L1 package — the form `node.level == 0` skipped.
    assert purity_violations(
        "from ..store import open_store\n", "shepherd.core", "leak"
    ) == ["leak imports 'shepherd.store', which is outside core/ and the stdlib"]
    # Two levels up from a SUBPACKAGE of core/ resolves to the same place.
    assert purity_violations("from ...store import x\n", "shepherd.core.sub", "leak") != []
    # The old `root == "shepherd"` escape admitted every one of these.
    assert purity_violations("import shepherd.store\n", "shepherd.core", "leak") != []
    assert purity_violations("from shepherd.host import HostPlatform\n", "shepherd.core", "l") != []
    assert purity_violations("import requests\n", "shepherd.core", "leak") != []
    # …while core-to-core and stdlib imports stay clean, in both spellings.
    assert purity_violations("from shepherd.core.states import S\n", "shepherd.core", "c") == []
    assert purity_violations("from .states import S\n", "shepherd.core", "c") == []
    assert purity_violations("from dataclasses import dataclass\n", "shepherd.core", "c") == []
    # The frozen scan bites on both the bare and the explicit-false forms.
    assert unfrozen_dataclasses("@dataclass\nclass L:\n    v: int\n", "leak") != []
    assert unfrozen_dataclasses("@dataclass(frozen=False)\nclass L:\n    v: int\n", "leak") != []
    assert unfrozen_dataclasses("@dataclass(frozen=True)\nclass L:\n    v: int\n", "ok") == []
    # The recursive walk is what puts a subpackage on the analysis path at all.
    assert package_of(CORE_DIR / "sub" / "leak.py") == "shepherd.core.sub"
    assert any(path.name == "ids.py" for path, _ in sources)

    # 4. The closed neutral key set (r4 BLOCKING 2, r5): `new_cwd` is the engine's
    #    spelling and must never be a neutral key.
    assert SIGNAL_FIELD_KEYS == frozenset(
        {
            "ask",
            "changed_paths",
            "model",
            "subagent_id",
            "task_id",
            "prompt",
            "next_cwd",
            "start_source",
            "tool_label",
            "failure_note",
            # BLOCKER T6-1: *how* a session ended. The engine's own word,
            # projected under a neutral key so the adapter can read its own
            # projection back at the stop — the same shape `failure_note`
            # uses, and the only route the stop lane has to the four
            # mechanical endings. `signals/` never interprets it.
            "end_reason",
            # BLOCKER T11-2: the fact that a tool batch was refused. The engine's
            # refusal *sentence* stays in the adapter; only the neutral verdict
            # crosses.
            "refusal",
        }
    )
    assert "new_cwd" not in SIGNAL_FIELD_KEYS

    # 5. One SignalKind per distinct column effect (ADR-6 / r4 BLOCKING 2).
    assert {kind.name for kind in SignalKind} == {
        "SESSION_REGISTERED",
        "PROMPT_SUBMITTED",
        "TURN_PROGRESS",
        "TOOL_STARTED",
        "TOOL_FINISHED",
        "TOOL_FAILED",
        "TOOL_BATCH_FINISHED",
        "NEEDS_INPUT",
        "INPUT_RESOLVED",
        "NOTICE_UNMAPPED",
        "SUBAGENT_STARTED",
        "SUBAGENT_FINISHED",
        "TASK_CREATED",
        "TASK_COMPLETED",
        # r3 BLOCKING 1: a turn ending clears the compaction mark and a session
        # ending does not, so ADR-6's rule gives them two members.
        "TURN_STOPPED",
        "SESSION_STOPPED",
        "STOP_FAILED",
        "COMPACT_STARTED",
        "COMPACT_FINISHED",
        "QUOTA_NOTICE",
        "CWD_CHANGED",
        "FILES_CHANGED",
        "MODEL_CHANGED",
        "UNKNOWN",
    }
    assert AnomalyKind.MALFORMED_PAYLOAD in set(AnomalyKind)


def test_signal_fields_cannot_be_mutated_after_construction() -> None:
    """C7: `Mapping[str, object]` on a frozen dataclass is a *shallow* freeze.

    `frozen=True` stops rebinding the attribute; it does nothing about the dict
    the caller still holds a reference to. `fold_types.py` uses `tuple` and
    `frozenset` throughout, so `Signal.fields` was the one outlier — and it is
    the fold's input, read by the rule table after the adapter has moved on.
    """
    source: dict[str, object] = {"ask": "permission?"}
    signal = Signal(
        kind=SignalKind.NEEDS_INPUT,
        engine_session_id="s",
        cwd="/tmp",
        transcript_path="/tmp/t.jsonl",
        received_at="2026-09-16T00:00:00Z",
        fields=source,
        raw_kind="an engine name",
    )

    # The caller's later mutation must not reach a signal already constructed.
    source["ask"] = "something else"
    source["tool_input"] = "an engine field"
    assert dict(signal.fields) == {"ask": "permission?"}

    # …and the mapping the signal exposes is itself read-only.
    with pytest.raises(TypeError):
        signal.fields["ask"] = "mutated"  # type: ignore[index]


def test_both_fold_lanes_return_the_same_type_and_the_same_clear() -> None:
    """BLOCKER T7b-1 / T11-6, closed. The hook lane and the registry lane were
    built in parallel and each defined its own structurally identical
    `FoldResult` and its own `""` clear sentinel. D37's "one writer, one rule
    set" only means something if the two lanes are literally the same type and
    the same constant — otherwise T18's composition root has one
    `on_result` callback that can name only one of them, and a reader that
    tests `reason is None` sees two conventions that merely happen to agree.
    """
    from shepherd.core.fold_types import CLEARED, FoldResult
    from shepherd.signals import discovery_loop, fold

    assert fold.FoldResult is FoldResult
    assert discovery_loop.FoldResult is FoldResult
    assert fold.CLEARED is CLEARED
    assert discovery_loop.CLEARED_REASON is CLEARED


def test_m3_anomaly_members_are_appended_at_the_end() -> None:
    """`AnomalyKind` is closed and **append-only** (its own docstring).

    `toolsurface/tools_m1.py` pre-seeds the zero rows *from the enum*, so a kind
    that is not a member is never displayed as `0` and principle 5 is quietly
    unmet — which is why M3's own kinds are members rather than bare `str`
    constants. They go at the **end**: M2's ordering blocker (T3-2/T4-1) stays
    deferred, and this test is what makes reopening it visible.
    """
    shipped = [
        "MALFORMED_PAYLOAD",
        "UNKNOWN_EVENT_NAME",
        "UNMAPPED_NOTICE",
        "SUBAGENT_UNDERFLOW",
        "MISSING_SUBAGENT_TRANSCRIPT",
        "SUBAGENT_STATE_UNKNOWN",
        "TOOL_BLOCKED_BY_HOOK",
        "TOOL_PERMISSION_REFUSED",
        "UNKNOWN_REGISTRY_STATUS",
        "STOP_FAILED",
        "GIT_NO_REMOTE",
        "GIT_AMBIGUOUS_REMOTE",
        "GIT_DUBIOUS_OWNERSHIP",
        "GIT_BARE_REPO",
        "GIT_NOT_A_REPO",
        "STOP_UNMAPPED_VALUE",
        "STOP_DEFERRED_VALUE",
        "EXIT_CODE_UNOBSERVABLE",
        "TRANSCRIPT_TAIL_ABSENT",
        "TRANSCRIPT_TAIL_TRUNCATED",
        "TOOL_RESULT_UNPAIRED",
    ]
    m3 = [
        "KILL_WITHOUT_SESSION_END",
        "MAILBOX_INPUT_NOT_EMPTY",
        "ASK_FORK_RESIDUE",
        "ORPHANED_PANE",
        "PANE_UNREADABLE",
        "SIDECAR_ABSENT",
        # BLOCKER-T1-3, appended by T14: the router decided the attached-client
        # race is a caller-side precondition with a counted deferral, rather
        # than a fifth field of the 96-key write-policy table.
        "MAILBOX_CLIENT_ATTACHED",
        "TMUX_UNAVAILABLE",
        # T16-1, authorised by the router: T16 refuses an amended or otherwise
        # unrecognised permission dialog — the safety property P4 was run to
        # establish — and could not count the refusal, because a refusal visible
        # only in a returned `reason` never reaches the counter `doctor` renders.
        # Appended, nothing reordered: acceptance clause 14's rule holds, and its
        # literal "seven" is now **ten** (T-ACC-14 records why, and says not to
        # quietly edit the clause).
        "DIALOG_TEXT_UNRECOGNISED",
    ]
    order = [member.name for member in AnomalyKind]

    # 1. Every member shipped before M3 keeps its position, exactly.
    assert order[: len(shipped)] == shipped
    # 2. M3's members follow, in the plan's order — and are no longer the last
    #    ones, because M4 appended its own section behind them (T2). The rule
    #    the test enforces is unchanged: **nothing already shipped moved**.
    assert order[len(shipped) : len(shipped) + len(m3)] == m3
    # 3. Nothing was slipped in between — M2's and M3's halves are a prefix.
    assert order[: len(shipped) + len(m3)] == shipped + m3

    # 4. The wire values are the member names lowercased; `doctor`'s zero rows
    #    are keyed by them, so a mismatch would be a count nobody can find.
    assert [member.value for member in AnomalyKind] == [name.lower() for name in order]

    # 5. The degraded conditions P-M3-9 names each map to a member — including
    #    the one that is deliberately NOT an anomaly.
    assert AnomalyKind("sidecar_absent") is AnomalyKind.SIDECAR_ABSENT
    assert AnomalyKind("pane_unreadable") is AnomalyKind.PANE_UNREADABLE  # empty capture
    assert AnomalyKind("tmux_unavailable") is AnomalyKind.TMUX_UNAVAILABLE  # no server / no binary
    # A dead pane carries a real `pane_dead_status` (E-M3-16), so it is a real
    # classification, not an unknown. Counting a knowable outcome as an unknown
    # is the opposite of principle 5.
    assert "DEAD_PANE" not in order
    assert not any("dead" in member.value for member in AnomalyKind)


# --------------------------------------------------------------------------
# T2 (M4): the orchestrator's own members, and the file order that proves it
# --------------------------------------------------------------------------

#: The marker `core/anomalies.py` writes above M4's members. The reachability
#: check (`tests/test_core_master.py`) enumerates the section from this same
#: string, so the two cannot disagree about which members are M4's.
M4_SECTION_MARKER = "M4's orchestrator"


def anomaly_source() -> str:
    return (CORE_DIR / "anomalies.py").read_text(encoding="utf-8")


def members_after_marker(source: str, marker: str) -> list[str]:
    """Member names declared below `marker` in the file, in file order.

    Line-based on purpose: a section marker is a **comment**, so it is not in
    the AST at all, and the members are read from the AST so that a name in a
    docstring cannot be mistaken for a declaration.
    """
    lines = source.splitlines()
    at = [index for index, line in enumerate(lines, start=1) if marker in line]
    assert len(at) == 1, f"{marker!r} appears {len(at)} times, expected once"
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or node.name != "AnomalyKind":
            continue
        for statement in node.body:
            if isinstance(statement, ast.Assign) and statement.lineno > at[0]:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    names.append(target.id)
    return names


def test_every_anomaly_member_is_unique_and_appended() -> None:
    """T2 / K24's companion: M4's members come **after** the M3 marker, nothing
    earlier moved, and no name or wire value is used twice.

    M2's ordering blocker (T3-2/T4-1) stays deferred, so append-only is still
    the whole discipline: `toolsurface/tools_m1.py` seeds a zero row per member
    from the enum, and a member that changes position changes nothing the
    operator sees — but a member that is *replaced* silently re-points a
    counter that has been accumulating under the old meaning.
    """
    source = anomaly_source()
    m4 = members_after_marker(source, M4_SECTION_MARKER)

    # Written out from the plan's own table — an independent source of truth,
    # in the plan's order. A name set, never a count (K19).
    assert m4 == [
        "APPROVAL_TIMED_OUT",
        "APPROVAL_WITHDRAWN",
        "AUDIT_LINE_LOST",
        "MASTER_TOOL_UNEXPECTED",
        "MASTER_TOOL_RESULT_ORPHANED",
        "MASTER_RESULT_UNMAPPED",
        "MASTER_RESUME_LOST",
        "WAKE_RETRY_CAP_REACHED",
    ]

    order = [member.name for member in AnomalyKind]
    # 1. M4's members are the last ones, and they are last in **file** order
    #    too — the enum's order is the file's order, so a member appended to
    #    the source in the wrong place moves a member in the enum.
    assert order[-len(m4) :] == m4
    # 2. Nothing already shipped moved: everything before M4's section keeps
    #    its position, compared as a sequence rather than as a set.
    before = order[: -len(m4)]
    assert before == [name for name in order if name not in set(m4)]
    # 3. No name and no wire value is used twice.
    assert len(set(order)) == len(order)
    values = [member.value for member in AnomalyKind]
    assert len(set(values)) == len(values)
    assert values == [name.lower() for name in order]

    # 4. Named as deliberately NOT anomalies (principle 5, the DEAD-pane
    #    precedent): a decision is not an unknown.
    for knowable in ("APPROVAL_DENIED", "APPROVAL_REJECTED", "TOOL_ASKED", "TURN_ABORTED"):
        assert knowable not in order
    # 5. Track C's member was cut with its transport: a counter for a socket
    #    that does not exist could only ever read zero (K24).
    assert "TIER2_RPC_REFUSED" not in order

    # self-check: the section reader is not vacuous and really is line-bounded.
    sample = (
        "class AnomalyKind(StrEnum):\n"
        "    EARLY = \"early\"\n"
        "    # ----- M4's orchestrator -----\n"
        "    LATE = \"late\"\n"
    )
    assert members_after_marker(sample, M4_SECTION_MARKER) == ["LATE"]
