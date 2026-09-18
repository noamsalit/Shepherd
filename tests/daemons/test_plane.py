"""T25 — `daemons/plane.py`: the two things only the root can build.

**Why this module exists at L6 rather than inside `compose_tool_surface`.** Two
of M4's wiring facts cannot be spelled at L4:

* the master runtime is `shepherd.master` (L5), and `toolsurface/` (L4) may not
  import upward — `test_compose_does_not_import_the_master_package` is the rule;
* the audit **sink** is built over a `RotatingJsonlLog`, and DP3 (P-M4-6) pins
  `toolsurface/audit.py` as the *single* L4 importer of `shepherd.logs`. A
  second one — `compose.py` constructing the log the plan's prose describes —
  is a failing build in `tests/boundaries/test_l4_import_rules.py`, which is
  how this task found out. The construction moved to where the lines and the
  imports are, exactly as T23 and T25's predecessors moved the registration.

Seam: this module's two public functions, driven against a real `Store` in
`tmp_path`. The runtime's own construction is observed by substituting
`plane.AgentSDKMaster` — the technique `tests/daemons/test_controld.py` already
uses for `compose.build_runner` — because the shipped runtime has no public
reader for the tool set or the prompt it was configured with, and reaching into
`_tools` would be a check that breaks on a rename while the behaviour holds.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.master import ExportedTool, MasterRuntime
from shepherd.daemons import plane
from shepherd.host.base import HostDirs, HostPlatform
from shepherd.logs.stops import date_of
from shepherd.master.prompt import orchestrator_prompt
from shepherd.store.db import Store, open_store
from shepherd.toolsurface.audit import read_audit_records
from shepherd.toolsurface.client import bind_master_client, reset_master_client
from shepherd.toolsurface.compose import log_root
from shepherd.toolsurface.types import ActorKind, AuditRecord, BlastClass

from scripted_hosts import build_scripted_host

TURN = "01TURNIDTHATTHEDRIVERMINTED"
AT = "2026-09-17T10:00:00.000Z"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def host(tmp_path: Path) -> HostPlatform:
    return build_scripted_host(tmp_path)


@pytest.fixture(autouse=True)
def unbound_client() -> Iterator[None]:
    """The client is a module global (ADR-7): every check starts unbound."""
    reset_master_client()
    yield
    reset_master_client()


@dataclass
class RecordedRuntime:
    """A `MasterRuntime` that records what the plane built it with."""

    kwargs: Mapping[str, object]
    configured: list[tuple[tuple[ExportedTool, ...], str]] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)

    def configure(self, tools: tuple[ExportedTool, ...], system_prompt: str) -> None:
        self.configured.append((tools, system_prompt))

    def send(self, text: str) -> object:  # pragma: no cover - never driven here
        raise AssertionError("no turn is run in this file")

    def resume(self, master_session_id: str) -> None:
        self.resumed.append(master_session_id)

    def interrupt(self) -> None:  # pragma: no cover
        raise AssertionError("no turn is run in this file")

    def capabilities(self) -> object:  # pragma: no cover
        raise AssertionError("no capability is read here")

    def close(self) -> None:
        pass


def record_runtime(monkeypatch: pytest.MonkeyPatch) -> list[RecordedRuntime]:
    """Substitute the runtime class in the plane's own namespace."""
    built: list[RecordedRuntime] = []

    def fake(**kwargs: object) -> RecordedRuntime:
        runtime = RecordedRuntime(kwargs=kwargs)
        built.append(runtime)
        return runtime

    monkeypatch.setattr(plane, "AgentSDKMaster", fake)
    return built


def a_record(tool: str) -> AuditRecord:
    return AuditRecord(
        at=AT,
        correlation_id=TURN,
        actor_kind=ActorKind.MASTER,
        actor_id="master",
        tool=tool,
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        args={},
        autonomy_level=2,
        decision="allow",
        approved_by="user",
        approval_id="ap-1",
        result="ok",
        failure=None,
        duration_ms=1,
    )


# ----- build_master -----------------------------------------------------------


def test_the_runtime_is_keyed_on_the_turn_it_was_built_for(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RD-T4-2, the closing line: `turn_id()` answers the driver's own id.

    §T20-1 and §T21-1 both stop here — the supplier had a holder and no
    producer. A key that merely *looks* plausible fails silently: every blocked
    tool handler rides its full 600 s while every test stays green, and P2
    measured that `interrupt()` frees none of them. So the assertion is
    identity against the id the plane was handed, never a shape.
    """
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)

    assert len(built) == 1
    supplier = built[0].kwargs["turn_id"]
    assert callable(supplier)
    assert supplier() == TURN


def test_the_runtime_withdraws_through_the_client_the_root_bound(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§T16-7's row: `bind_master_client` had no caller, and this is the
    consumer that makes the binding load-bearing.

    The runtime is handed the **client's own function**, not a private path
    (T21 §T21-10 row 5) — so this drives the callable the plane passed and
    asserts it reached the bound wiring. Unbound, the client raises
    `MasterClientUnbound`, which is what makes this an arrival and not a shape.
    """
    withdrawn: list[str] = []
    bind_master_client(
        withdraw_approval=lambda approval_id: False,
        withdraw_turn_approvals=lambda turn_id: (withdrawn.append(turn_id), 1)[1],
        autonomy_level=lambda: 2,
    )
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)

    withdraw = built[0].kwargs["withdraw_turn_approvals"]
    assert callable(withdraw)
    assert withdraw(TURN) == 1
    assert withdrawn == [TURN]


def test_the_counter_the_runtime_was_handed_reaches_this_stores_anomalies(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K24: `master/` may not reach a store, so the plane closes over one.

    Driven rather than inspected — a `bump` that named the member and wrote it
    nowhere is the counter-with-no-writer this milestone has already paid for.
    """
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)

    bump = built[0].kwargs["bump"]
    assert callable(bump)
    assert store.list_anomaly_counts().get(AnomalyKind.MASTER_TOOL_UNEXPECTED.value, 0) == 0
    bump(AnomalyKind.MASTER_TOOL_UNEXPECTED)
    assert store.list_anomaly_counts()[AnomalyKind.MASTER_TOOL_UNEXPECTED.value] == 1


def test_the_runtime_is_configured_with_the_prompt_for_the_stored_level(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D8: the prompt's autonomy section is the level the store holds.

    Compared against `orchestrator_prompt(3)` — the shipped renderer at the
    level this check stored — rather than against a substring of it, and
    against `orchestrator_prompt(2)` as the negative, so a plane that ignored
    the store and rendered the default cannot pass.
    """
    store.set_app_state("autonomy_level", 3)
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)

    assert len(built[0].configured) == 1
    _tools, prompt = built[0].configured[0]
    assert prompt == orchestrator_prompt(3)
    assert prompt != orchestrator_prompt(2)


def test_the_model_comes_from_app_state_and_never_from_a_literal(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§17: *"so M4 does not hard-code the runtime choice somewhere a settings
    page cannot reach"*. The row `app_state` holds is the settings page's.

    Both halves: the stored value wins, and with nothing stored the build still
    names a model — a `None` here would be an option block with no model at all
    rather than a default anybody chose.
    """
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)
    default = built[0].kwargs["model"]

    store.set_app_state(plane.MASTER_MODEL_KEY, "a-model-the-operator-picked")
    plane.build_master(store, TURN)

    assert built[1].kwargs["model"] == "a-model-the-operator-picked"
    assert isinstance(default, str) and default != ""
    assert default != "a-model-the-operator-picked"


def test_a_persisted_conversation_is_resumed_and_a_missing_one_is_not(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§T27-6 / RD-T27-6: `master_session_id` is written by the turn driver and
    was **never read back** — D10's continuity half-built, and the fifth row on
    the "no caller" register. This is the read-back.

    Both directions, because only the pair is the rule: a stored id is resumed,
    and an empty store resumes **nothing** — a `resume("")` would start every
    cold boot by asking the engine for a transcript that does not exist.
    """
    built = record_runtime(monkeypatch)

    plane.build_master(store, TURN)
    assert built[0].resumed == []

    store.set_app_state(plane.MASTER_SESSION_KEY, "conv-from-the-last-daemon")
    plane.build_master(store, TURN)

    assert built[1].resumed == ["conv-from-the-last-daemon"]


def test_the_shipped_runtime_satisfies_the_seam(store: Store) -> None:
    """Arrival: the substitutions above are substitutions *for something*.

    Built with no double at all, so the class the plane really names is the one
    that has to satisfy `MasterRuntime` — and nothing is started by building
    one (RD6: the master is lazy, and M4 starts no thread at boot).
    """
    bind_master_client(
        withdraw_approval=lambda approval_id: False,
        withdraw_turn_approvals=lambda turn_id: 0,
        autonomy_level=lambda: 2,
    )

    runtime: MasterRuntime = plane.build_master(store, TURN)

    assert runtime is not None
    runtime.close()


# ----- audit_sink -------------------------------------------------------------


def test_the_sink_writes_into_the_log_root_the_composition_resolves(
    store: Store, host: HostPlatform, tmp_path: Path
) -> None:
    """P-M4-4's other half: the **sink itself** is shipped code.

    The record is read back through `read_audit_records`, the one reader, from
    `log_root(host)` — the same resolver `compose.py` uses — so a sink writing
    somewhere else reads as no record at all rather than as a passing test.
    """
    sink = plane.audit_sink(store, host)

    sink(a_record("kill_session"))

    records = read_audit_records(log_root(host), 10)
    assert [record["tool"] for record in records] == ["kill_session"]
    assert records[0]["correlation_id"] == TURN
    # …and it really is a file under this host's own root, not a happy reader.
    written = sorted((log_root(host) / "audit").glob("*.jsonl"))
    assert [path.name for path in written] == [f"{date_of(AT)}.jsonl"]


def test_the_sink_counts_a_lost_line_against_this_stores_anomalies(
    store: Store, host: HostPlatform
) -> None:
    """E-M4-6: the call has already run, so a write that fails is **counted**,
    never raised — and the counter is the plane's, for K24's reason.

    The failure is made by the filesystem rather than by a patch: a plain file
    sits where the log's own directory has to be, so `append` cannot write and
    says so. Nothing is monkeypatched, which is what makes this a property of
    the shipped sink rather than of a substitution.
    """
    sink = plane.audit_sink(store, host)
    blocked = log_root(host) / "audit"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("not a directory", encoding="utf-8")

    sink(a_record("kill_session"))

    assert store.list_anomaly_counts()[AnomalyKind.AUDIT_LINE_LOST.value] == 1


def test_the_host_decides_where_the_log_goes(store: Store, tmp_path: Path) -> None:
    """ADR-2: no environment variable, no `Path.home()`, no cwd. A check
    relocates the log by handing in a host, which is the property that keeps
    this file from ever writing beside a real one."""
    elsewhere = build_scripted_host(tmp_path / "elsewhere")

    plane.audit_sink(store, elsewhere)(a_record("kill_session"))

    assert read_audit_records(log_root(elsewhere), 10) != ()
    assert read_audit_records(log_root(build_scripted_host(tmp_path)), 10) == ()


# ----- the re-export (ADR-M4-6) ----------------------------------------------


def test_the_plane_re_exports_shutdown_so_the_root_keeps_one_import() -> None:
    """ADR-M4-6's first edit: `controld.py:32` imports `ShutdownOutcome`,
    `build_master` and `shut_down` from **one** module, because a second import
    line is a line the root does not have (it is at 140 of 140).

    Identity, not a re-declaration: the re-export is the same object.
    """
    from shepherd.daemons import shutdown

    assert plane.shut_down is shutdown.shut_down
    assert plane.ShutdownOutcome is shutdown.ShutdownOutcome


def test_every_name_the_root_imports_from_the_plane_is_there() -> None:
    """The root's import line is text until something resolves it. Read off
    `controld.py`'s own AST, so a rename on either side is red here."""
    import ast

    from shepherd.daemons import controld

    source = Path(controld.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "shepherd.daemons.plane":
            imported.update(alias.name for alias in node.names)

    assert imported, "controld.py imports nothing from the plane"
    assert [name for name in sorted(imported) if not hasattr(plane, name)] == []
