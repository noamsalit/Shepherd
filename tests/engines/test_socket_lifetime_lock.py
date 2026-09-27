"""D72 / ADR-QR-2: a socket claim is an exclusive `flock` held for the owner's life.

Seam: `claim_socket` / `release_claim` over `tmp_path` (the ingest-socket seam),
observed from outside the way a second daemon would meet it — a second
descriptor in this process, or a second process, trying the same
`<socket>.lock`. Nothing here reads the registry the claim keeps.

The children below lock and **return normally**; none is signalled or killed
(CLAUDE.md, mutations rule 3). A holder releases by exiting when its stdin
closes, which is the ordinary end of a process, not a teardown verb.
"""

from __future__ import annotations

import errno
import fcntl
import os
import socket
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from shepherd.daemons import control_ingest
from shepherd.engines.claude_code import ingest_socket
from shepherd.engines.claude_code.ingest_socket import SocketInUse, bind_listener, claim_socket, serve_ingest
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE

CEILING_S = 10.0

#: A process that takes the lock, says so, and holds it until its stdin closes.
HOLD_SCRIPT = (
    "import fcntl, os, sys\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "sys.stdout.write('locked\\n')\n"
    "sys.stdout.flush()\n"
    "sys.stdin.read()\n"
)

#: A process that tries the lock once and exits 0 (taken) or 3 (held elsewhere).
TRY_SCRIPT = (
    "import fcntl, os, sys\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "try:\n"
    "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "except BlockingIOError:\n"
    "    sys.exit(3)\n"
    "sys.exit(0)\n"
)


def plan_for(tmp_path: Path) -> SocketPlan:
    return SocketPlan(
        path=tmp_path / "shepherd" / "controld.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


def lock_path(plan: SocketPlan) -> Path:
    """`<socket>.lock`, spelled from D72 rather than read from the module."""
    return plan.path.with_name(plan.path.name + ".lock")


def make_socket_dir(plan: SocketPlan) -> None:
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(plan.path.parent, plan.dir_mode)


def second_descriptor_can_lock(path: Path) -> bool:
    """Whether a fresh descriptor in *this* process can take the lock (`flock`
    locks belong to an open file description, not to a process)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(fd)
    return True


def another_process_can_lock(path: Path) -> bool:
    done = subprocess.run(
        [sys.executable, "-c", TRY_SCRIPT, str(path)], capture_output=True, timeout=CEILING_S
    )
    assert done.returncode in (0, 3), done.stderr
    return done.returncode == 0


@contextmanager
def held_by_another_process(path: Path) -> Iterator[None]:
    """A second owner holding `path`'s lock, released by its ordinary exit."""
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLD_SCRIPT, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdin is not None and holder.stdout is not None
    try:
        assert holder.stdout.readline() == "locked\n", "the holder never took the lock"
        yield
    finally:
        holder.stdin.close()
        holder.wait(timeout=CEILING_S)


def stale_file(plan: SocketPlan) -> None:
    """A socket file nobody listens on: connecting to it is `ECONNREFUSED`."""
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    left.bind(str(plan.path))
    left.close()


@pytest.fixture()
def claims() -> Iterator[list[Path]]:
    """Paths this test claimed, released at teardown so no lock outlives it."""
    paths: list[Path] = []
    yield paths
    for path in paths:
        ingest_socket.release_claim(path)


def test_a_second_descriptor_cannot_take_a_held_claim(tmp_path: Path, claims: list[Path]) -> None:
    """PP1: the claim is exclusive across descriptors, not just across calls."""
    plan = plan_for(tmp_path)
    claims.append(plan.path)
    assert claim_socket(plan) is plan

    assert not second_descriptor_can_lock(lock_path(plan)), "a second descriptor took a held claim"
    assert not another_process_can_lock(lock_path(plan)), "another process took a held claim"


def test_a_held_claim_refuses_even_when_the_socket_file_is_absent(tmp_path: Path) -> None:
    """E16's window: the holder has claimed and not yet bound. There is no file
    for a probe to meet, and the path is still not free."""
    plan = plan_for(tmp_path)
    make_socket_dir(plan)
    with held_by_another_process(lock_path(plan)):
        assert not plan.path.exists()
        with pytest.raises(SocketInUse, match="is held by a running process") as refused:
            claim_socket(plan)
        assert str(plan.path) in str(refused.value)


def test_a_held_claim_refuses_a_path_that_answers_econnrefused(tmp_path: Path) -> None:
    """The macOS full-backlog case, by fixture: a path that refuses the probe
    reads as stale to a probe alone. With the lock held elsewhere it is held,
    and the second bind leaves the file where it is."""
    plan = plan_for(tmp_path)
    make_socket_dir(plan)
    stale_file(plan)
    inode = os.stat(plan.path).st_ino
    with held_by_another_process(lock_path(plan)):
        with pytest.raises(SocketInUse):
            claim_socket(plan)
        with pytest.raises(SocketInUse):
            bind_listener(plan)
        assert os.stat(plan.path).st_ino == inode, "a refused bind unlinked the holder's path"


def test_a_second_claim_in_the_owning_process_is_reentrant(tmp_path: Path, claims: list[Path]) -> None:
    plan = plan_for(tmp_path)
    claims.append(plan.path)
    assert claim_socket(plan) is plan
    assert claim_socket(plan) is plan
    assert not another_process_can_lock(lock_path(plan)), "the re-entrant claim dropped the lock"


def test_a_reentrant_claim_still_probes_and_refuses_a_live_listener(
    tmp_path: Path, claims: list[Path]
) -> None:
    """PP20: re-entrancy skips the lock, never the probe. An in-process owner
    keeps both its lock and its socket through the refusal."""
    plan = plan_for(tmp_path)
    claims.append(plan.path)
    owner = bind_listener(plan)
    try:
        inode = os.stat(plan.path).st_ino
        with pytest.raises(SocketInUse):
            claim_socket(plan)

        assert not second_descriptor_can_lock(lock_path(plan)), "the refusal released the owner's lock"
        assert os.stat(plan.path).st_ino == inode
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(plan.path))
            owner.settimeout(CEILING_S)
            accepted, _ = owner.accept()
            accepted.close()
    finally:
        owner.close()


def test_a_claim_refused_by_the_probe_does_not_keep_the_lock_it_took(tmp_path: Path) -> None:
    """PP20's other half: an older binary listens with no lock of ours. The
    claim takes the lock, meets the live listener, refuses — and keeps nothing."""
    plan = plan_for(tmp_path)
    make_socket_dir(plan)
    older_binary = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        older_binary.bind(str(plan.path))
        older_binary.listen(1)
        with pytest.raises(SocketInUse):
            claim_socket(plan)
        assert another_process_can_lock(lock_path(plan)), "the refused claim kept the lock it took"
    finally:
        older_binary.close()


def test_release_frees_the_claim_for_the_next_owner(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    claim_socket(plan)
    assert not another_process_can_lock(lock_path(plan))

    ingest_socket.release_claim(plan.path)

    assert another_process_can_lock(lock_path(plan)), "the released claim is still held"
    assert second_descriptor_can_lock(lock_path(plan))
    ingest_socket.release_claim(plan.path)  # a second release is a no-op, not an error
    assert lock_path(plan).exists(), "lock files are never unlinked (D72)"


def test_the_lock_file_is_0600_in_the_socket_dir(tmp_path: Path, claims: list[Path]) -> None:
    plan = plan_for(tmp_path)
    claims.append(plan.path)
    previous_umask = os.umask(0o022)
    try:
        claim_socket(plan)
    finally:
        os.umask(previous_umask)

    lock = lock_path(plan)
    assert ingest_socket.LOCK_SUFFIX == ".lock"
    assert lock.parent == plan.path.parent
    assert stat.S_ISREG(lock.stat().st_mode)
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600, f"{stat.S_IMODE(lock.stat().st_mode):04o}"


def test_a_claim_with_the_runtime_dir_absent_creates_it_at_the_plans_mode(
    tmp_path: Path, claims: list[Path]
) -> None:
    """PP18: `controld.start` claims before anything has made the runtime dir,
    so the claim makes it — at the plan's mode — before it opens the lock."""
    plan = plan_for(tmp_path)
    claims.append(plan.path)
    assert not plan.path.parent.exists()

    claim_socket(plan)

    assert plan.path.parent.is_dir()
    assert stat.S_IMODE(plan.path.parent.stat().st_mode) == plan.dir_mode
    assert (plan.path.parent / "controld.sock.lock").exists()
    listener = bind_listener(plan)  # re-entrant: the claim above is this process's
    listener.close()


def test_a_child_process_that_exits_frees_its_lock(tmp_path: Path, claims: list[Path]) -> None:
    """A holder that exits frees the claim with no unlock of its own: the lock
    belongs to its descriptor, and exit closes it."""
    plan = plan_for(tmp_path)
    make_socket_dir(plan)
    assert another_process_can_lock(lock_path(plan))  # locks, then returns normally

    claims.append(plan.path)
    assert claim_socket(plan) is plan
    assert not another_process_can_lock(lock_path(plan))


def failing_flock(error: OSError) -> Callable[[int, int], None]:
    """An `fcntl.flock` that meets `error` on a lock and passes an unlock through."""
    real_flock = fcntl.flock

    def flock(fd: int, operation: int) -> None:
        if operation & fcntl.LOCK_EX:
            raise error
        real_flock(fd, operation)

    return flock


def fd_is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError as error:
        assert error.errno == errno.EBADF, error
        return False
    return True


@pytest.mark.parametrize(
    ("error", "maps_to_in_use"),
    [
        (BlockingIOError(errno.EWOULDBLOCK, os.strerror(errno.EWOULDBLOCK)), True),
        (OSError(errno.ENOLCK, os.strerror(errno.ENOLCK)), False),
        (OSError(errno.EACCES, os.strerror(errno.EACCES)), False),
    ],
    ids=["EWOULDBLOCK", "ENOLCK", "EACCES"],
)
def test_only_a_would_block_lock_is_a_socket_in_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError, maps_to_in_use: bool
) -> None:
    """A lock another process holds is `SocketInUse`; a lock the kernel will
    not give at all (`ENOLCK`, `EACCES`) is not a held socket, and says so."""
    plan = plan_for(tmp_path)
    monkeypatch.setattr(fcntl, "flock", failing_flock(error))
    with pytest.raises(RuntimeError) as refused:
        claim_socket(plan)

    assert isinstance(refused.value, SocketInUse) is maps_to_in_use, repr(refused.value)
    if not maps_to_in_use:
        assert isinstance(refused.value, ingest_socket.ClaimFailed), repr(refused.value)


def test_a_lock_the_kernel_refuses_is_a_claim_failure_that_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENOLCK is not "held by a running process": the claim fails with a typed
    error naming the lock file and the errno's text, holds no claim, and closes
    the descriptor it opened."""
    plan = plan_for(tmp_path)
    opened: list[int] = []
    real_open = os.open

    def spy_open(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        fd = real_open(path, flags, mode)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(fcntl, "flock", failing_flock(OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))))
    with pytest.raises(Exception) as refused:
        claim_socket(plan)
    monkeypatch.undo()

    assert not isinstance(refused.value, OSError), f"a raw OSError reached the caller: {refused.value!r}"
    assert isinstance(refused.value, ingest_socket.ClaimFailed)
    assert not isinstance(refused.value, SocketInUse)
    assert str(lock_path(plan)) in str(refused.value)
    assert os.strerror(errno.ENOLCK) in str(refused.value)
    assert plan.path not in ingest_socket._HELD, "a failed claim was recorded as held"
    assert len(opened) == 1 and not fd_is_open(opened[0]), "the failed claim leaked its lock descriptor"
    assert another_process_can_lock(lock_path(plan)), "a failed claim holds the lock"


def test_a_lock_file_that_cannot_be_opened_is_a_claim_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_for(tmp_path)
    real_open = os.open

    def refuse_the_lock(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if os.fspath(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), os.fspath(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", refuse_the_lock)
    with pytest.raises(Exception) as refused:
        claim_socket(plan)
    monkeypatch.undo()

    assert not isinstance(refused.value, OSError), f"a raw OSError reached the caller: {refused.value!r}"
    assert isinstance(refused.value, ingest_socket.ClaimFailed)
    assert str(lock_path(plan)) in str(refused.value)
    assert os.strerror(errno.EACCES) in str(refused.value)
    assert plan.path not in ingest_socket._HELD


def test_a_socket_dir_that_cannot_be_made_is_a_claim_failure(tmp_path: Path) -> None:
    """The dir half of the claim: a file where the socket dir should be."""
    plan = plan_for(tmp_path)
    plan.path.parent.write_text("not a directory")
    with pytest.raises(Exception) as refused:
        claim_socket(plan)

    assert not isinstance(refused.value, OSError), f"a raw OSError reached the caller: {refused.value!r}"
    assert isinstance(refused.value, ingest_socket.ClaimFailed)
    assert str(plan.path.parent) in str(refused.value)


def test_a_release_whose_unlock_fails_still_closes_and_forgets_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`release_claim` is exception-safe: an unlock that raises still closes
    the descriptor (which drops the lock) and the claim is not left recorded."""
    plan = plan_for(tmp_path)
    claim_socket(plan)
    fd = ingest_socket._HELD[plan.path]
    real_flock = fcntl.flock

    def failing_unlock(descriptor: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            raise OSError(errno.EIO, os.strerror(errno.EIO))
        real_flock(descriptor, operation)

    monkeypatch.setattr(fcntl, "flock", failing_unlock)
    with pytest.raises(OSError):
        ingest_socket.release_claim(plan.path)
    monkeypatch.undo()

    assert plan.path not in ingest_socket._HELD
    assert not fd_is_open(fd), "a failed unlock leaked the lock descriptor"
    assert another_process_can_lock(lock_path(plan)), "a failed unlock kept the claim"


def failing_unlink(path: Path, inode: int) -> None:
    raise OSError(errno.EIO, os.strerror(errno.EIO), str(path))


def test_the_ingest_listener_releases_its_claim_when_the_unlink_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`serve_ingest`'s `finally`: `release_claim` runs even if the unlink
    raises. A shutdown already set makes the loop return at once, on this thread."""
    plan = claim_socket(plan_for(tmp_path))
    shutdown = threading.Event()
    shutdown.set()
    monkeypatch.setattr(ingest_socket, "unlink_owned_socket", failing_unlink)
    with pytest.raises(OSError):
        serve_ingest(plan=plan, on_frame=lambda frame: None, on_shutdown=lambda: None, shutdown=shutdown)

    assert another_process_can_lock(lock_path(plan)), "a failed unlink kept the ingest claim"


def test_the_control_listener_releases_its_claim_when_the_unlink_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = claim_socket(plan_for(tmp_path))
    shutdown = threading.Event()
    shutdown.set()
    monkeypatch.setattr(control_ingest, "unlink_owned_socket", failing_unlink)
    with pytest.raises(OSError):
        control_ingest.serve_control_ingest(plan=plan, schema_version=1, on_frame=lambda frame: None, shutdown=shutdown)

    assert another_process_can_lock(lock_path(plan)), "a failed unlink kept the control claim"
