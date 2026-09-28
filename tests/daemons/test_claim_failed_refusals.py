"""D72: a claim the kernel will not give is a readable refusal, not a held port.

Seam: `controld.main` and `sessiond.main`, in-process, against the throwaway host
(`world_fixture.world`). The claim's own syscalls are made to fail the way a host
can fail them — `flock` answering `ENOLCK` (no lock table room, an NFS runtime
dir), `open` of the lock file answering `EACCES` — and each daemon is watched
for what an operator reads: one refusal line naming the lock file, exit 2, no
traceback, and nothing about a port that was never the problem.

No daemon starts here: the claim is the first thing either `main` does, so each
refusal happens before any bind, store or thread.
"""

from __future__ import annotations

import errno
import fcntl
import os
import socket

import pytest

from shepherd.daemons import controld, sessiond
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME, INGEST_SOCKET_NAME
from shepherd.host.detect import detect_host
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from world_fixture import World, world  # noqa: F401 - the shared fixture, imported by name


def lock_of(socket_name: str) -> str:
    plan = detect_host().control_socket(socket_name)
    return str(plan.path.with_name(plan.path.name + ".lock"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_controld_names_the_lock_not_the_port_when_flock_fails(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_locks(fd: int, operation: int) -> None:
        raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))

    port, lock = free_port(), lock_of(CONTROL_SOCKET_NAME)
    with monkeypatch.context() as syscalls:  # only the syscall: `world`'s env stays redirected
        syscalls.setattr(fcntl, "flock", no_locks)
        code = controld.main(["--port", str(port), "--engine-config-dir", str(world.engine_config_dir)])

    out = capsys.readouterr().out
    assert code == controld.EXIT_REFUSED
    assert f"port {port}" not in out and "is not available" not in out, out
    assert out.startswith("controld refuses to start:"), out
    assert lock in out, out
    assert os.strerror(errno.ENOLCK) in out, out
    assert not (world.data_dir / controld.DB_NAME).exists()


def test_sessiond_refuses_a_lock_file_it_cannot_open(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_open = os.open

    def refuse_the_lock(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if os.fspath(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), os.fspath(path))
        return real_open(path, flags, mode)

    lock = lock_of(INGEST_SOCKET_NAME)
    with monkeypatch.context() as syscalls:
        syscalls.setattr(os, "open", refuse_the_lock)
        try:
            code = sessiond.main(["--expected-schema-version", str(EXPECTED_SCHEMA_VERSION)])
        except OSError as escaped:
            pytest.fail(f"sessiond.main let the claim's OSError escape as a traceback: {escaped!r}")

    err = capsys.readouterr().err
    assert code == sessiond.EXIT_REFUSED
    assert err.startswith("sessiond refuses to start:"), err
    assert lock in err, err
    assert "Traceback" not in err
