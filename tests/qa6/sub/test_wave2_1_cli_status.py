"""Wave 2, SUB lane: C1 (`shepherd status`) and C2 (`shepherd doctor`) against a running daemon.

Both keep the spec's oracle and are predicted to FAIL (C-1: the CLI cannot
reach a running daemon). Their positive control is the daemon itself knowing:
`GET /api/fleet` shows `session_count == 2` after two sidecars are seeded.
Discovery is only validated in wave 3, so if that control fails within two scan
passes both are BLOCKED, never FAIL (test-plan §3 wave 2 stop-if; review pass 2
finding 11).

C2's `--settings` file is H1's artifact (`<run0>/artifacts/h1-settings.json`,
written by the unit lane earlier in this wave).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

from .. import paths
from ..httpclient import as_dict
from ..instance import Controld
from ..pool import InstancePool
from ..sandbox import RunContext, checked_env
from ..scenario import scenario
from ..sessions import await_session, sidecar, write_sidecar
from ..verdict import Blocked, Recorder, observe

#: Two scan passes plus margin (the sourced 2.0 s cadence, discovery_loop.py).
CONTROL_BOUND_S = 6.0
DOCTOR_LABELS = ("host", "directories", "control socket", "hook dispatch", "supervision", "login persistence",
                 "database", "hooks", "discovery", "engine", "anomalies", "fleet")


@dataclass
class Fleet:
    controld: Controld
    session_ids: list[str]
    engine_ids: list[str]
    control_error: str | None


@pytest.fixture(scope="module")
def fleet(pool: InstancePool, qa6_run: RunContext) -> Iterator[Fleet]:
    controld = pool.ready()
    engine_ids: list[str] = []
    for index in (1, 2):
        helper = pool.helper()
        body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(qa6_run.repos / "loose"),
                       status="busy", name=f"QA6 C1 {index}")
        write_sidecar(controld.root.sessions, body)
        engine_ids.append(str(body["sessionId"]))

    def two() -> dict[str, object] | None:
        data = controld.client.fleet()
        return data if data.get("session_count") == 2 else None

    counted, _elapsed = observe(two, CONTROL_BOUND_S)
    session_ids = [str(await_session(controld, engine)["id"]) for engine in engine_ids] if counted else []
    error = None if counted else f"/api/fleet never showed session_count == 2 within {CONTROL_BOUND_S}s"
    yield Fleet(controld=controld, session_ids=session_ids, engine_ids=engine_ids, control_error=error)


def cli(controld: Controld, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(paths.SHEPHERD_BIN), *args], env=checked_env(controld.env, "a CLI child"), cwd=str(controld.root.cwd),
                          capture_output=True, text=True, timeout=30, check=False)


def require_control(fleet: Fleet, rec: Recorder) -> None:
    if fleet.control_error is not None:
        raise Blocked(f"positive control failed: {fleet.control_error} (discovery is validated in wave 3)")
    rec.check("api.control_session_count", True, "GET /api/fleet session_count == 2 (the daemon knows)", 2)


@scenario("C1")
def test_c1_status_shows_the_running_fleet(fleet: Fleet, rec: Recorder) -> None:
    require_control(fleet, rec)
    done = cli(fleet.controld, "status")
    rec.note(f"rc={done.returncode} stdout={done.stdout!r} stderr={done.stderr!r}")
    rec.equal("proc.exit_0", 0, done.returncode)
    first = done.stdout.splitlines()[0] if done.stdout else ""
    rec.check("proc.first_line_fleet_2", first.startswith("fleet: 2 sessions · "), "fleet: 2 sessions · …", first)
    for index, (session_id, engine_id) in enumerate(zip(fleet.session_ids, fleet.engine_ids, strict=True), start=1):
        rec.check(f"proc.session_{index}_listed", session_id in done.stdout or engine_id in done.stdout,
                  f"{session_id} (or its engine id) listed", done.stdout[:200])
    rec.equal("logs.stderr_empty", "", done.stderr)
    rec.finish()


@scenario("C2")
def test_c2_doctor_reports_engine_schema_database_discovery(fleet: Fleet, qa6_run: RunContext, rec: Recorder) -> None:
    require_control(fleet, rec)
    plain = cli(fleet.controld, "doctor")
    rec.note(f"doctor rc={plain.returncode}\n{plain.stdout}\nstderr={plain.stderr!r}")
    labels = tuple(line.split(":", 1)[0] for line in plain.stdout.splitlines() if ":" in line)
    rec.equal("proc.labelled_lines_in_order", DOCTOR_LABELS, labels)
    lines = {line.split(":", 1)[0]: line for line in plain.stdout.splitlines() if ":" in line}
    rec.check("logs.host_unverified", "MacHost · UNVERIFIED" in lines.get("host", ""), "MacHost · UNVERIFIED",
              lines.get("host", "")[:120])
    database = lines.get("database", "")
    schema = f"schema version {EXPECTED_SCHEMA_VERSION}"
    rec.check("logs.database_schema_current", str(fleet.controld.root.data_dir) in database and schema in database,
              f"the sandbox DB at {schema}", database)
    discovery = lines.get("discovery", "")
    rec.check("logs.discovery_reports_the_daemon", "registry 2 sessions" in discovery,
              "the running daemon's discovery (registry sessions 2)", discovery)
    artifact = qa6_run.artifacts / "h1-settings.json"
    if not artifact.exists():
        rec.block("logs.hooks_with_settings", "H1's artifact is absent (the unit lane did not run first)")
    else:
        with_settings = cli(fleet.controld, "doctor", "--settings", str(artifact))
        rec.note(f"doctor --settings rc={with_settings.returncode}\n{with_settings.stdout}")
        hooks_line = next((line for line in with_settings.stdout.splitlines() if line.startswith("hooks:")), "")
        rec.check("logs.hooks_reports_managed_entries", " of our entries" in hooks_line and "not inspected" not in hooks_line,
                  "the file's managed entries", hooks_line)
    fleet_data = as_dict(fleet.controld.client.fleet())
    rec.record("api.fleet_session_count", fleet_data.get("session_count"))
    rec.finish()


# --- C3, moved here from the no-daemon CLI lane (qa6 rulings P10, RD-1) ------
#
# D68: the CLI reaches a running `controld` over its owner-only RPC socket, so
# C3's install-hooks runs in the daemon that registered the tool. The clauses
# are C3's own, unchanged; only the process that answers them moved.

from .. import hostprobe  # noqa: E402 - appended with C3 (P10), below P4's hunk

@scenario("C3")
def test_c3_install_hooks_dry_run_then_yes(fleet: Fleet, qa6_run: RunContext, rec: Recorder) -> None:
    directory = qa6_run.run0 / "hooks" / "c3"  # the path C3 used in the CLI lane
    directory.mkdir(parents=True)
    target = directory / "settings.json"
    dry = cli(fleet.controld, "install-hooks", "--settings", str(target), "--dry-run")
    rec.note(f"dry run: rc={dry.returncode} stdout={dry.stdout!r} stderr={dry.stderr!r}")
    rec.equal("proc.dry_run_exit", 0, dry.returncode)
    rec.check("proc.dry_run_would_install", "would install" in dry.stdout, "stdout contains 'would install'", dry.stdout[:300])
    rec.check("proc.dry_run_changed_nothing", "this run changed nothing. Pass --yes to apply it." in dry.stdout,
              "the dry-run sentence", dry.stdout[:300])
    rec.check("files.absent_after_dry_run", not target.exists(), "absent", target.exists())
    rec.equal("logs.dry_run_stderr_empty", "", dry.stderr)
    applied = cli(fleet.controld, "install-hooks", "--settings", str(target), "--yes")
    rec.note(f"--yes: rc={applied.returncode} stdout={applied.stdout!r} stderr={applied.stderr!r}")
    rec.equal("proc.yes_exit", 0, applied.returncode)
    rec.check("proc.yes_installed", "installed" in applied.stdout, "stdout contains 'installed'", applied.stdout[:300])
    rec.check("files.managed_entries_after_yes", target.exists() and "_shepherd_managed" in target.read_text(encoding="utf-8"),
              "the managed entries (H1's shape)", target.exists())
    rec.equal("logs.yes_stderr_empty", "", applied.stderr)
    rec.equal("files.real_settings_sha", paths.expected_settings_sha(), hostprobe.sha256(paths.REAL_SETTINGS))
    rec.finish()
