"""Wave 2, SUB lane: refused starts — C7 (occupied port), C8 (the 103/104 socket
budget), C9 (a second controld on the same TMPDIR), C10 (a newer database).

Each gets its own instance (env-plan §5): a refusal that wrote the DB would
contaminate every later instance's idea of "fresh". C7, C8's 104 case and C10's
first boot are started without the harness's pre-seeded DB (env-plan §4 step 4
"Skipped for …"), because "writes nothing" is exactly what they observe.
"""

from __future__ import annotations

import hashlib
import os
import socket
import sqlite3
import time
from pathlib import Path

from shepherd.host.base import SocketPathTooLong
from shepherd.host.mac import MacHost
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

from .. import hostprobe, paths
from ..instance import Controld, seed_db
from ..pool import InstancePool
from ..sandbox import RunContext, mint_instance, sandbox_env
from ..scenario import scenario
from ..verdict import Blocked, Recorder, observe

REFUSAL_PREFIX = "controld refuses to start: "
EXIT_BOUND_S = 15.0


def await_exit(controld: Controld, bound_s: float = EXIT_BOUND_S) -> int | None:
    code, _elapsed = observe(lambda: controld.child.popen.poll() is not None or None, bound_s)
    if code is None:
        return None
    controld.child.join_drains()
    return controld.child.popen.returncode


def first_stdout(controld: Controld) -> str:
    lines = controld.child.lines("stdout")
    return lines[0] if lines else ""


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


@scenario("C7")
def test_c7_occupied_port_refuses_and_writes_nothing(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    root = mint_instance(qa6_run)
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = int(holder.getsockname()[1])
    try:
        rec.check("given.port_not_forbidden", port != paths.FORBIDDEN_PORT, "an ephemeral port, never the forbidden one", port)
        rec.check("given.no_data_dir", not root.data_dir.exists(), "a fresh HOME with no data dir", root.data_dir.exists())
        # Unseeded on purpose (the DB's absence is the observation), so its tmux
        # calls go to the separate unseeded log; they are recorded below.
        unseeded_before = _lines(qa6_run.unseeded_tmux_argv_log)
        controld = pool.start(root, port=port, path_mode="unseeded")
        code = await_exit(controld)
        rec.equal("proc.exit_2", 2, code)
        line = first_stdout(controld)
        rec.check("logs.refusal_line", line.startswith(f"{REFUSAL_PREFIX}port {port} is not available ("),
                  f"{REFUSAL_PREFIX}port {port} is not available (…", line)
        rec.check("files.no_db", not root.db_path.exists(), f"{root.db_path} does not exist", root.db_path.exists())
        rec.check("files.no_socket", not root.controld_socket.exists(), "no controld.sock left", root.controld_socket.exists())
        argvs = _lines(qa6_run.unseeded_tmux_argv_log)[len(unseeded_before):]
        rec.record("tmux.refused_start_argvs", argvs)
        rec.note(f"C7: the refused start ran {len(argvs)} tmux argv(s) before refusing: {argvs}")
        if code is None:
            controld.stop()
    finally:
        holder.close()
    rec.finish()


def crafted_tmpdir(root: Path, total: int) -> Path:
    """A TMPDIR such that `<TMPDIR>/Shepherd/controld.sock` is exactly `total` bytes."""
    suffix = len("/Shepherd/controld.sock")
    prefix = str(root) + "/"
    pad = total - suffix - len(prefix)
    if pad < 1:
        raise AssertionError(f"the run root is too long to craft a {total}-byte socket path")
    return root / ("p" * pad)


@scenario("C8")
def test_c8_socket_budget_103_starts_104_refuses(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    ok_root = mint_instance(qa6_run)
    ok_tmp = crafted_tmpdir(ok_root.root, 103)
    ok_tmp.mkdir(mode=0o700)
    plan = MacHost(environ={"HOME": str(ok_root.home), "TMPDIR": str(ok_tmp)}).control_socket("controld")
    rec.equal("given.product_path_103", 103, len(str(plan.path).encode("utf-8")))
    seed_db(ok_root, runner_socket=qa6_run.runner_socket(ok_root.k))
    ok = pool.start(ok_root, env=sandbox_env(qa6_run, ok_root, tmpdir=ok_tmp))
    try:
        ok.wait_ready()
        rec.check("proc.103_ready", True, "ready by W1's four signals", ok.ready_notes)
        rec.equal("api.103_fleet_200", 200, ok.client.get("/api/fleet").status)
    except Blocked as error:  # a readiness failure here IS the 103 clause's verdict
        rec.check("proc.103_ready", False, "ready by W1's four signals", f"{type(error).__name__}: {error}")
    ok.stop()

    bad_root = mint_instance(qa6_run)
    bad_tmp = crafted_tmpdir(bad_root.root, 104)
    bad_tmp.mkdir(mode=0o700)
    try:
        MacHost(environ={"HOME": str(bad_root.home), "TMPDIR": str(bad_tmp)}).control_socket("controld")
        refused_len = -1
    except SocketPathTooLong as refused:
        refused_len = len(str(refused.path).encode("utf-8"))
    rec.equal("given.product_path_104", 104, refused_len)
    bad = pool.start(bad_root, env=sandbox_env(qa6_run, bad_root, path_mode="unseeded", tmpdir=bad_tmp))
    code = await_exit(bad)
    rec.equal("proc.104_exit_2", 2, code)
    line = first_stdout(bad)
    rec.check("logs.104_refusal", line.startswith(REFUSAL_PREFIX) and ("budget" in line or str(bad_tmp) in line),
              f"{REFUSAL_PREFIX}… naming the socket path or budget", line)
    rec.check("files.104_no_db", not bad_root.db_path.exists(), "no shepherd.db under that HOME", bad_root.db_path.exists())
    sockets = list((bad_tmp / "Shepherd").glob("*.sock")) if (bad_tmp / "Shepherd").exists() else []
    rec.equal("files.104_no_socket", [], [str(s) for s in sockets])
    if code is None:
        bad.stop()
    rec.finish()


@scenario("C9")
def test_c9_second_controld_does_not_steal_the_socket(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    first = pool.ready()
    sock = first.socket_path
    assert sock is not None
    inode_before = os.stat(sock).st_ino
    second = pool.start(first.root, env=dict(first.env), name="controld-B")
    code = await_exit(second, 6.0)
    started = second.start_line(0.5) is not None
    rec.note(f"B: exit={code} stdout={second.child.lines('stdout')[:3]} stderr_tail={second.child.lines('stderr')[-3:]}")
    rec.equal("proc.b_exits_2", 2, code)
    line = first_stdout(second)
    rec.check("logs.b_refusal", line.startswith(REFUSAL_PREFIX), f"{REFUSAL_PREFIX}…", line)
    inode_after = os.stat(sock).st_ino if sock.exists() else None
    rec.equal("files.socket_inode_unchanged", inode_before, inode_after)
    holders = [name for name in hostprobe.open_files(first.child.pid) if name == str(sock)]
    rec.check("files.socket_held_by_a", bool(holders), f"lsof shows {sock} held by A's pid", holders)
    b_db = [name for name in hostprobe.open_files(second.child.pid) if name.startswith(str(first.root.data_dir))] \
        if second.child.alive() else []
    rec.check("db.no_second_writer", not started and not b_db, "B never opened A's DB (it refused before the store)",
              {"b_started": started, "b_open_db_files": b_db})
    rec.equal("api.a_fleet_still_200", 200, first.client.get("/api/fleet").status)
    if second.child.alive():
        second.stop()
    first.stop()
    rec.finish()


@scenario("C10")
def test_c10_newer_database_refuses_start(pool: InstancePool, qa6_run: RunContext, rec: Recorder) -> None:
    root = mint_instance(qa6_run)
    # Seeded (a departure from env-plan §4 step 4's "C10's first boot needs no
    # DB"): unseeded, the first boot's reconcile would name the default socket
    # `shepherd-runner` in the product tmux log Z2 reads. Nothing C10 observes
    # depends on the first boot being unseeded.
    seed_db(root, runner_socket=qa6_run.runner_socket(root.k))
    boot = pool.start(root)
    boot.wait_ready()
    boot.stop()
    # fixture-fiction (test-plan C10 label): simulate a newer binary's DB by
    # raising the product's own schema-version record (store/migrate.py
    # `schema_migration`, read by `_refuse_on_future_schema`) by one.
    connection = sqlite3.connect(root.db_path, isolation_level=None)
    try:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) VALUES (?, 'qa6_fixture_fiction', 'qa6', ?)",
            (EXPECTED_SCHEMA_VERSION + 1, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    before = sha_file(root.db_path)
    refused = pool.start(root, name="controld-newer")
    code = await_exit(refused)
    rec.note(f"exit={code} stdout={refused.child.lines('stdout')[:3]} stderr_tail={refused.child.lines('stderr')[-4:]}")
    rec.equal("proc.exit_2", 2, code)
    rec.check("logs.refusal_line", first_stdout(refused).startswith(REFUSAL_PREFIX), f"{REFUSAL_PREFIX}…",
              first_stdout(refused) or refused.child.lines("stderr")[-1:])
    rec.equal("files.db_sha_unchanged", before, sha_file(root.db_path))
    rec.check("files.no_socket", not root.controld_socket.exists(), "no socket left", root.controld_socket.exists())
    if code is None:
        refused.stop()
    rec.finish()
