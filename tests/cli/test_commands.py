"""T17: `status`, `doctor`, `install-hooks`, `uninstall-hooks`, `recompute`.

**Seam: `invoke()`** (the plan's Test Seams for this task). Every assertion drives
`main(argv)` — the process's real entry — and the only capabilities it can reach
are the ones registered on the tool surface, because `cli/` may import nothing
below L4 (D19, D35) and the installer trio arrives through `invoke()` (D38.1).

**No test here names a settings path outside `tmp_path`** (K3). The session-scoped
guard in `tests/conftest.py` asserts the real file's sha256 and its siblings are
unchanged when the suite ends.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from cli.conftest import NOW, register_tools, scripted_host
from project_fixture import the_project

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.cli.main import EXIT_FAILURE, EXIT_OK, EXIT_USAGE, main
from shepherd.store.db import Store
from shepherd.toolsurface.registry import reset_registry
from shepherd.toolsurface.tools_engine import register_engine_tools
from shepherd.store.models import Session

IDLE_ASK = "idle — waiting for your next instruction"


def seed(
    store: Store,
    *,
    engine_session_id: str,
    state: SessionState,
    title: str | None = None,
    needs_you_reason: str | None = None,
    last_event_at: str = NOW,
) -> Session:
    session = store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=the_project(store),
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    return store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=state,
            last_event_at=last_event_at,
            needs_you_reason=needs_you_reason,
            title=title,
            title_source="engine" if title is not None else None,
        ),
    )


def run(argv: list[str], out: io.StringIO, err: io.StringIO, host_dir: Path) -> int:
    return main(
        argv,
        out=out,
        err=err,
        host=scripted_host(runtime_dir=host_dir / "run"),
    )


# --- status -------------------------------------------------------------------


def test_status_goes_through_invoke(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """The fleet is read through the registered tools and nothing else."""
    register_tools(store, projects_root)
    seed(store, engine_session_id="eng-1", state=SessionState.RUNNING, title="build the cli")

    code = run(["status"], out, err, tmp_path)

    assert code == EXIT_OK, err.getvalue()
    assert "build the cli" in out.getvalue()


def test_status_fails_when_no_tool_is_registered(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """A CLI that always exits 0 cannot be scripted. No registry, no fleet."""
    code = run(["status"], out, err, tmp_path)

    assert code == EXIT_FAILURE
    assert "fleet_summary" in err.getvalue()


def test_status_orders_by_state_never_alphabetically(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """§16: needs_you → running → starting → stopped, derived from state.

    The titles are seeded in the reverse alphabetical order of that ranking, so a
    sort by title or by insertion order produces a different sequence.
    """
    register_tools(store, projects_root)
    seed(store, engine_session_id="eng-a", state=SessionState.STOPPED, title="aaa stopped")
    seed(store, engine_session_id="eng-b", state=SessionState.RUNNING, title="mmm running")
    seed(
        store,
        engine_session_id="eng-c",
        state=SessionState.NEEDS_YOU,
        title="zzz waiting",
        needs_you_reason=IDLE_ASK,
    )

    assert run(["status"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    positions = [printed.index(title) for title in ("zzz waiting", "mmm running", "aaa stopped")]
    assert positions == sorted(positions), printed


def test_status_prints_the_actual_ask(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """The reason is the session's own words — never a manufactured placeholder."""
    register_tools(store, projects_root)
    seed(
        store,
        engine_session_id="eng-1",
        state=SessionState.NEEDS_YOU,
        title="waiting one",
        needs_you_reason=IDLE_ASK,
    )

    assert run(["status"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    assert IDLE_ASK in printed
    assert "needs attention" not in printed


def test_status_degrades_honestly_when_a_title_is_missing(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """The title carrier may not have landed. A missing title is a value (principle 5)."""
    register_tools(store, projects_root)
    session = seed(store, engine_session_id="eng-1", state=SessionState.RUNNING, title=None)

    assert run(["status"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    assert "(no title yet)" in printed
    assert session.id in printed


def test_status_counts_every_live_state(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    register_tools(store, projects_root)
    seed(store, engine_session_id="eng-1", state=SessionState.RUNNING, title="one")
    seed(store, engine_session_id="eng-2", state=SessionState.STOPPED, title="two")

    assert run(["status"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    assert "2 sessions" in printed
    assert "running 1" in printed
    assert "stopped 1" in printed


def test_unknown_command_is_a_usage_error(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    code = run(["frobnicate"], out, err, tmp_path)

    assert code == EXIT_USAGE
    assert "frobnicate" in err.getvalue()
    assert "status" in err.getvalue()


def test_recompute_is_now_an_alias_of_replay(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """M1 named `recompute` so its absence was explicit; T12 landed the thing it
    named, so the stub's "nothing in this build replays a session's history"
    became false (review finding A2). It is an alias now — one implementation,
    reached through the same tool, so the two can never drift.

    With no `replay` tool registered in this process the honest failure is the
    same one `status` gives: the capability is not on this tool surface.
    """
    register_tools(store, projects_root)

    code = run(["recompute"], out, err, tmp_path)

    assert code == EXIT_FAILURE
    assert "replay did not answer" in err.getvalue()


# --- doctor -------------------------------------------------------------------

DOCTOR_LABELS: tuple[str, ...] = (
    "host:",
    "directories:",
    "control socket:",
    "hook dispatch:",
    "supervision:",
    "login persistence:",
    "database:",
    "hooks:",
    "discovery:",
    "engine:",
    "anomalies:",
    "fleet:",
)


def doctor(
    argv: list[str],
    out: io.StringIO,
    err: io.StringIO,
    tmp_path: Path,
    *,
    dispatch_available: bool = True,
    dispatch_reason: str = "the dispatcher binaries are present",
    verified: bool = False,
    data_dir: Path | None = None,
) -> int:
    return main(
        argv,
        out=out,
        err=err,
        host=scripted_host(
            runtime_dir=tmp_path / "run",
            dispatch_available=dispatch_available,
            dispatch_reason=dispatch_reason,
            verified=verified,
            data_dir=data_dir,
        ),
    )


def test_doctor_reports_all_twelve_lines(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Every fact `doctor` owes a user is on the page, each on its own line."""
    register_tools(store, projects_root)

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    labels = [
        line.split(":", 1)[0] + ":"
        for line in printed.splitlines()
        if not line.startswith(" ")
    ]
    assert labels == list(DOCTOR_LABELS), printed


def test_doctor_reports_unverified_host(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """G1/D55: a driver that has never been run says so rather than implying support."""
    register_tools(store, projects_root)

    assert doctor(["doctor"], out, err, tmp_path, verified=False) == EXIT_OK
    assert "UNVERIFIED" in out.getvalue()

    verified_out = io.StringIO()
    assert doctor(["doctor"], verified_out, err, tmp_path, verified=True) == EXIT_OK
    assert "UNVERIFIED" not in verified_out.getvalue()
    assert "verified" in verified_out.getvalue()


def test_doctor_reports_missing_dispatch_binary(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """G2: a hook command that cannot run is a finding, and a non-zero exit."""
    register_tools(store, projects_root)

    code = doctor(
        ["doctor"],
        out,
        err,
        tmp_path,
        dispatch_available=False,
        dispatch_reason="the dispatcher binaries are not on PATH",
    )

    assert code == EXIT_FAILURE
    printed = out.getvalue()
    assert "unavailable" in printed
    assert "the dispatcher binaries are not on PATH" in printed


def test_doctor_reports_start_limit_policy(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """C2: the restart policy is a thing a user must know before it bites them."""
    register_tools(store, projects_root)

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    assert "five restarts in ten seconds then the unit is refused" in out.getvalue()


def test_doctor_reports_discovery_sources(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Decision pressure 5: a user never has to guess why a column is null."""
    register_tools(store, projects_root)
    store.set_app_state(
        "discovery_status",
        {
            "hooks": "absent",
            "registry_sessions": 3,
            "sdk_cli_skipped": 1,
            "skipped_other": 0,
            "unknown_status": 2,
            "last_scan_at": NOW,
        },
    )

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    assert "absent" in printed
    assert "3 sessions" in printed
    assert NOW in printed


def test_doctor_reports_skipped_and_unknown_counts(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """RD9 + principle 5: a skipped entry and an unknown one are both counted."""
    register_tools(store, projects_root)
    store.set_app_state(
        "discovery_status",
        {
            "hooks": "absent",
            "registry_sessions": 3,
            "sdk_cli_skipped": 1,
            "skipped_other": 4,
            "unknown_status": 2,
        },
    )

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    discovery = next(
        line for line in out.getvalue().splitlines() if line.startswith("discovery:")
    )
    assert "1 skipped" in discovery
    assert "4 skipped" in discovery
    assert "2 unknown" in discovery


def test_doctor_reports_no_database_yet(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """F16 — the first run: a state, not a traceback, and no reassuring green."""
    code = doctor(["doctor"], out, err, tmp_path, data_dir=tmp_path / "never-created")

    assert code == EXIT_OK, err.getvalue()
    database = next(line for line in out.getvalue().splitlines() if line.startswith("database:"))
    assert "not created yet" in database
    fleet = next(line for line in out.getvalue().splitlines() if line.startswith("fleet:"))
    assert "unknown" in fleet


def test_doctor_reports_the_engine_version_as_unknown_when_no_tool_answers(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """G12/principle 5: with no `engine_version` registered, `doctor` says unknown
    and says why — it does not reach around the consumer boundary to find out."""
    register_tools(store, projects_root)

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    engine = next(line for line in out.getvalue().splitlines() if line.startswith("engine:"))
    assert "unknown" in engine
    assert "no registered tool" in engine


def test_doctor_reports_the_real_engine_version_and_drift_date(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """G12 closed (BLOCKER T17-2): the line the plan specifies, from real values."""
    register_tools(store, projects_root)
    record = tmp_path / "drift.json"
    record.write_text(
        json.dumps(
            {
                "checked_at": "2026-09-17T08:00:00Z",
                "engine_version": "2.1.273",
                "pinned_version": "2.1.270",
                "verdict": "clean",
                "detail": "33 event names + 4 enums unchanged",
            }
        ),
        encoding="utf-8",
    )
    register_engine_tools(
        db_path=tmp_path / "data" / "shepherd.db",
        drift_record_path=record,
        version_reader=lambda: "2.1.273",
    )

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    engine = next(line for line in out.getvalue().splitlines() if line.startswith("engine:"))
    assert "2.1.273" in engine
    assert "pinned 2.1.270" in engine
    assert "2026-09-17T08:00:00Z" in engine
    assert "unknown" not in engine


def test_doctor_reports_a_never_run_drift_check_as_never_run(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """An unrun gate must not read as a passed one."""
    register_tools(store, projects_root)
    register_engine_tools(
        db_path=tmp_path / "data" / "shepherd.db",
        drift_record_path=tmp_path / "absent.json",
        version_reader=lambda: "2.1.273",
    )

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    engine = next(line for line in out.getvalue().splitlines() if line.startswith("engine:"))
    assert "2.1.273" in engine
    assert "never run on this host" in engine
    assert "clean" not in engine


def test_doctor_reports_the_schema_version_when_a_tool_projects_it(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """BLOCKER T17-1: §7's migration rules get their own line, from `store/`."""
    register_tools(store, projects_root)
    register_engine_tools(
        db_path=tmp_path / "data" / "shepherd.db",
        drift_record_path=tmp_path / "absent.json",
        version_reader=lambda: None,
    )

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    database = next(
        line for line in out.getvalue().splitlines() if line.startswith("database:")
    )
    assert "schema version 4" in database
    assert "expects 4" in database
    assert "unknown" not in database


def test_doctor_says_hooks_are_not_inspected_without_a_settings_path(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """K3: there is no default path, so with no `--settings` the answer is unknown."""
    register_tools(store, projects_root)

    assert doctor(["doctor"], out, err, tmp_path) == EXIT_OK
    hooks = next(line for line in out.getvalue().splitlines() if line.startswith("hooks:"))
    assert "not inspected" in hooks
    assert "--settings" in hooks


def test_doctor_reports_hooks_not_installed_in_a_named_file(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    register_tools(store, projects_root)
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    assert doctor(["doctor", "--settings", str(settings)], out, err, tmp_path) == EXIT_OK
    hooks = next(line for line in out.getvalue().splitlines() if line.startswith("hooks:"))
    assert "not installed" in hooks


def test_doctor_refuses_an_over_budget_socket_path(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """E19: a path that cannot bind is a finding, not a traceback."""
    register_tools(store, projects_root)
    long_runtime = tmp_path / ("d" * 120)

    code = main(["doctor"], out=out, err=err, host=scripted_host(runtime_dir=long_runtime))

    assert code == EXIT_FAILURE
    socket_line = next(
        line for line in out.getvalue().splitlines() if line.startswith("control socket:")
    )
    assert "refused" in socket_line
    assert "budget" in socket_line


# --- install-hooks / uninstall-hooks ------------------------------------------

COMMAND_A = "scripted-send /tmp/a.sock"
COMMAND_B = "scripted-send /tmp/b.sock"


def hooks_cli(
    argv: list[str],
    out: io.StringIO,
    err: io.StringIO,
    tmp_path: Path,
    *,
    dispatch_available: bool = True,
) -> int:
    return main(
        argv,
        out=out,
        err=err,
        host=scripted_host(
            runtime_dir=tmp_path / "run",
            dispatch_available=dispatch_available,
            dispatch_command=COMMAND_A,
        ),
    )


def test_install_hooks_requires_an_explicit_settings_path(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """K3: there is no default. A run that names no file changes no file."""
    register_tools(store, projects_root)

    code = hooks_cli(["install-hooks"], out, err, tmp_path)

    assert code == EXIT_USAGE
    assert "--settings" in err.getvalue()


def test_install_hooks_refuses_when_the_dispatcher_is_unavailable(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """G2: a dead hook is worse than no hook, so it is refused before any write."""
    register_tools(store, projects_root)
    settings = tmp_path / "settings.json"

    code = hooks_cli(
        ["install-hooks", "--settings", str(settings), "--yes"],
        out,
        err,
        tmp_path,
        dispatch_available=False,
    )

    assert code == EXIT_FAILURE
    assert not settings.exists()
    assert "dispatcher" in err.getvalue()


def test_install_hooks_defaults_to_a_dry_run(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Anything that writes asks first. Without --yes nothing on disk changes."""
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")

    code = hooks_cli(["install-hooks", "--settings", str(settings)], out, err, tmp_path)

    assert code == EXIT_OK, err.getvalue()
    assert settings.read_text(encoding="utf-8") == "{}"
    printed = out.getvalue()
    assert "--yes" in printed
    assert "would" in printed
    assert COMMAND_A in printed


def test_install_hooks_writes_backs_up_and_validates_when_confirmed(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """C6: back up, write, validate after writing — and say where the backup went."""
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks": {}}', encoding="utf-8")

    code = hooks_cli(
        ["install-hooks", "--settings", str(settings), "--yes"], out, err, tmp_path
    )

    assert code == EXIT_OK, err.getvalue()
    written = settings.read_text(encoding="utf-8")
    assert COMMAND_A in written
    assert "_shepherd_managed" in written
    backup = tmp_path / "settings.json.shepherd-backup"
    assert backup.read_text(encoding="utf-8") == '{"hooks": {}}'
    assert str(backup) in out.getvalue()


def test_install_hooks_refuses_a_file_it_cannot_parse(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Nothing we did not understand is overwritten — and the refusal is loud."""
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    settings.write_text("{not json", encoding="utf-8")

    code = hooks_cli(
        ["install-hooks", "--settings", str(settings), "--yes"], out, err, tmp_path
    )

    assert code == EXIT_FAILURE
    assert settings.read_text(encoding="utf-8") == "{not json"
    assert "JSON" in err.getvalue()


def test_uninstall_hooks_is_a_dry_run_without_yes(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    assert (
        hooks_cli(["install-hooks", "--settings", str(settings), "--yes"], out, err, tmp_path)
        == EXIT_OK
    )
    installed = settings.read_text(encoding="utf-8")

    dry_out = io.StringIO()
    code = hooks_cli(["uninstall-hooks", "--settings", str(settings)], dry_out, err, tmp_path)

    assert code == EXIT_OK, err.getvalue()
    assert settings.read_text(encoding="utf-8") == installed
    assert "--yes" in dry_out.getvalue()


def test_uninstall_hooks_removes_exactly_our_entries_when_confirmed(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    assert (
        hooks_cli(["install-hooks", "--settings", str(settings), "--yes"], out, err, tmp_path)
        == EXIT_OK
    )
    assert COMMAND_A in settings.read_text(encoding="utf-8")

    removed_out = io.StringIO()
    code = hooks_cli(
        ["uninstall-hooks", "--settings", str(settings), "--yes"], removed_out, err, tmp_path
    )

    assert code == EXIT_OK, err.getvalue()
    assert COMMAND_A not in settings.read_text(encoding="utf-8")
    assert "removed" in removed_out.getvalue()


def test_doctor_reports_an_installed_but_stale_hook_command(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """The command no longer matches this host — the third hook state (C6)."""
    register_tools(store, projects_root, command=COMMAND_A)
    settings = tmp_path / "settings.json"
    assert (
        hooks_cli(["install-hooks", "--settings", str(settings), "--yes"], out, err, tmp_path)
        == EXIT_OK
    )

    reset_registry()
    register_tools(store, projects_root, command=COMMAND_B)
    stale_out = io.StringIO()
    stale_err = io.StringIO()
    code = main(
        ["doctor", "--settings", str(settings)],
        out=stale_out,
        err=stale_err,
        host=scripted_host(runtime_dir=tmp_path / "run"),
    )

    assert code == EXIT_FAILURE
    hooks_line = next(
        line for line in stale_out.getvalue().splitlines() if line.startswith("hooks:")
    )
    assert "stale" in hooks_line
    assert "install-hooks" in stale_err.getvalue()


def test_doctor_in_a_standalone_process_still_reports_real_facts(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """T17-3's other half: a `shepherd` process the daemon did not start.

    `cli/` reaches capabilities through `invoke()`, so with an empty registry
    every tool-backed line was *unknown*. The two facts that need no database
    writer — the schema version and the engine version — are read-only local
    projections, so the CLI process registers them for itself. Nothing here
    opens the store: §7 migration rule 3 keeps migration to `controld`.
    """
    reset_registry()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    code = main(
        ["doctor"],
        out=out,
        err=err,
        host=scripted_host(runtime_dir=tmp_path / "run", data_dir=data_dir),
        correlation_id="cid",
    )

    assert code == EXIT_OK, err.getvalue()
    lines = out.getvalue().splitlines()
    database = next(line for line in lines if line.startswith("database:"))
    engine = next(line for line in lines if line.startswith("engine:"))
    # No database file has been written there yet — said as a fact, not a blank.
    assert "no database file" in database
    assert "expects schema version 4" in database
    # The engine version is discovered from the host, not from a constant.
    assert "schemas pinned 2.1.270" in engine
    assert "no registered tool" not in engine
