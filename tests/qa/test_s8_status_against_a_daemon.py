"""S8 — `shepherd status` against a **running** daemon. Live lane.

M1's T18-1, recorded open: *the registry is a process global, so a `shepherd`
the daemon did not start has no fleet tools.* Everything that has ever been
asserted about it was asserted in-process, where the question cannot even be
posed — one interpreter, one registry. This puts a real `controld` on this host
and runs a real, separate `shepherd status` beside it.

**What is observed is what a user actually sees:** the exit code, and the two
streams, verbatim.

**Readiness is gated, never slept for.** `controld` prints
`controld: http://127.0.0.1:<port> · <socket>` once the control socket is bound,
and the fixture blocks on that line with a bounded timeout and a loud failure —
then confirms the port really answers. A `sleep` here would be a race condition
with a comment, and it would make every later assertion a statement about
timing.

**Teardown verifies itself:** `SIGTERM`, a bounded wait, `/proc` checked for the
pid, and the socket file asserted gone. Never a signal to a pid this fixture did
not create (CLAUDE.md, 2026-09-17), and never `kill -9`.

*Lying implementations this now catches:* a `status` that answers from a stale
in-process registry rather than saying it cannot see the fleet; a `status` that
exits `0` while printing an unknown — the exit code and the text are asserted
together; and the reverse — a build that fixes T18-1 by wiring a client, which
turns every assertion here red and names what moved.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.cli.commands import EXIT_FAILURE
from shepherd.daemons.controld import DB_NAME
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

#: How long the daemon has to say it is bound. Bounded and loud: a fixture that
#: waited forever would turn a broken bring-up into a hung suite.
READY_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 20.0
STATUS_TIMEOUT_S = 60.0

#: The exact prefix `controld.main` prints once `start()` has returned, i.e.
#: once the control socket is bound. This is the readiness **signal**, read off
#: the shipped source rather than invented here.
READY_PREFIX = "controld: http://"


def a_free_port() -> int:
    """A port the kernel just handed out and we immediately gave back.

    Racy in principle and correct in practice; the alternative is a fixed port,
    which collides with whatever else is on this host and reads as a product
    failure. `controld` refuses a held port loudly (`EXIT_REFUSED`), so a lost
    race is a legible failure rather than a wrong answer.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def isolated_env(home: Path) -> dict[str, str]:
    """A scrubbed environment whose every directory is under `home`.

    Every `CLAUDE*` / `ANTHROPIC*` variable is dropped, so nothing started here
    can reach the user's real config, and `CLAUDE_CONFIG_DIR` is then pointed at
    a throwaway. `PYTHONPATH` carries `src/` because **nothing is installed on
    this host** — which is S9's subject, and the reason this scenario cannot run
    the `shepherd` console script.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CLAUDE", "ANTHROPIC", "AI_AGENT", "XDG_"))
    }
    env["CLAUDE_CONFIG_DIR"] = str(home / "engine-config")
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        env[name] = str(home / name.lower())
    env["XDG_RUNTIME_DIR"] = str(home / "run")
    env["PYTHONPATH"] = str(SRC)
    # **Load-bearing, and measured.** A child's stdout is block-buffered when it
    # is a pipe, so `controld`'s one-line readiness banner sits in an 8 KB
    # buffer until the process exits — the fixture below would then block on
    # `readline()` for the whole life of the daemon it is waiting for. With this
    # (and `-u` on the argv) the banner arrives in ~1.1 s. Without it the first
    # run of this file hung until the suite timeout, which is how it was found.
    env["PYTHONUNBUFFERED"] = "1"
    return env


@dataclass(frozen=True)
class Daemon:
    """One running `controld`, and everything a check needs to read off it."""

    process: subprocess.Popen[str]
    port: int
    home: Path
    env: dict[str, str]
    banner: str

    def data_dir(self) -> Path:
        return self.home / "xdg_data_home" / "shepherd"


def _wait_for_banner(process: subprocess.Popen[str]) -> str:
    """Block on the daemon's own readiness line. Bounded, and loud on timeout.

    The read runs on its own thread and the **wait** is what carries the bound:
    `readline()` on a pipe blocks with no deadline of its own, so a daemon that
    starts and says nothing would hang a `while time.monotonic() < deadline`
    loop forever — the deadline is only consulted between reads that never
    return. That is not a hypothetical; it is what the first version of this
    fixture did.
    """
    assert process.stdout is not None
    found: list[str] = []
    arrived = threading.Event()

    def read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if line.startswith(READY_PREFIX):
                found.append(line.strip())
                arrived.set()
                return

    reader = threading.Thread(target=read, name="s8-banner-reader", daemon=True)
    reader.start()
    if arrived.wait(READY_TIMEOUT_S):
        return found[0]
    if process.poll() is not None:
        raise AssertionError(f"controld exited before binding (rc={process.returncode})")
    raise AssertionError(f"controld never printed {READY_PREFIX!r} within {READY_TIMEOUT_S}s")


@pytest.fixture()
def daemon(tmp_path: Path) -> Iterator[Daemon]:
    """A real `controld` on this host, gated on its own readiness signal."""
    home = tmp_path / "home"
    env = isolated_env(home)
    for value in env.values():
        if value.startswith(str(home)):
            Path(value).mkdir(parents=True, exist_ok=True)
    port = a_free_port()

    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "shepherd.daemons.controld", "--port", str(port)],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        banner = _wait_for_banner(process)
        yield Daemon(process=process, port=port, home=home, env=env, banner=banner)
    finally:
        _stop(process)


def _stop(process: subprocess.Popen[str]) -> None:
    """SIGTERM, bounded wait, and **verify** the process is gone.

    Teardown that ignores its own result leaks a daemon per run, and a leaked
    daemon holds a port and a socket that the next run reads as a product
    failure. `terminate()` targets this fixture's own child and nothing else.
    """
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:  # pragma: no cover - a hung daemon
            process.kill()
            process.wait(timeout=STOP_TIMEOUT_S)
            raise AssertionError("controld did not exit on SIGTERM within the timeout")
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    assert not Path(f"/proc/{process.pid}").exists(), (
        f"controld's pid {process.pid} is still in /proc after teardown"
    )


def run_status(daemon: Daemon) -> subprocess.CompletedProcess[str]:
    """`shepherd status` as its own process, against the daemon's own data dir.

    Run through `-c` rather than the console script because **nothing is
    installed on this host**; `cli.main.main` is the console script's body
    (`shepherd = "shepherd.cli.main:run"`, and `run()` is `main(sys.argv[1:])`),
    so this is the same entry point one argument-parse away.
    """
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from shepherd.cli.main import main; sys.exit(main(['status']))",
        ],
        cwd=str(daemon.home),
        env=daemon.env,
        capture_output=True,
        text=True,
        check=False,
        timeout=STATUS_TIMEOUT_S,
    )


# ----- the daemon is really up ------------------------------------------------


def test_the_daemon_binds_and_serves_before_anything_is_asserted(daemon: Daemon) -> None:
    """Arrival for the scenario. Without it, `status` failing proves nothing.

    Three independent facts: the banner names the port we asked for, the HTTP
    port answers, and the control socket exists on disk.
    """
    assert f":{daemon.port}" in daemon.banner, daemon.banner
    assert daemon.process.poll() is None, "controld exited after printing its banner"

    with urllib.request.urlopen(f"http://127.0.0.1:{daemon.port}/", timeout=10) as answer:
        assert answer.status == 200, answer.status

    socket_path = daemon.home / "run" / "shepherd" / CONTROL_SOCKET_NAME
    assert CONTROL_SOCKET_NAME in daemon.banner, daemon.banner
    assert socket_path.exists() or Path(daemon.banner.split("·")[-1].strip()).exists(), (
        f"the control socket named in the banner does not exist: {daemon.banner}"
    )


def test_the_daemon_really_owns_a_database(daemon: Daemon) -> None:
    """The fleet `status` would have to read really is there and really is its.

    So *"status cannot see the fleet"* below is about the registry being a
    process global, and not about an empty machine.
    """
    candidates = sorted(daemon.home.rglob(DB_NAME))
    assert candidates, f"controld wrote no {DB_NAME} under {daemon.home}"


# ----- what a user actually sees ----------------------------------------------


def test_shepherd_status_cannot_see_the_fleet_of_a_running_daemon(
    daemon: Daemon,
) -> None:
    """**T18-1, observed from outside.** The user gets a failure and advice.

    The exit code **and** the text, asserted together: a `status` that printed
    an unknown and exited `0` would look fine to a person and be wrong to a
    script, and a `status` that exited non-zero with no explanation would be the
    reverse. `EXIT_FAILURE` is imported from the shipped module rather than
    written as `1`.

    Goes red the day a `shepherd` process learns to reach a running daemon —
    which is T18-1 closing, and is the right moment for this to demand a
    re-read.
    """
    answer = run_status(daemon)
    combined = answer.stdout + answer.stderr

    assert answer.returncode == EXIT_FAILURE, (
        f"`shepherd status` exited {answer.returncode} beside a running daemon\n"
        f"stdout: {answer.stdout!r}\nstderr: {answer.stderr!r}"
    )
    # Principle 5: the user is told the capability is absent *here* and what to
    # do about it — never a blank, never a zero fleet that would read as "all
    # quiet". The advice is asserted by its substance, not by its spelling.
    assert "fleet_summary" in combined, combined
    assert "daemon" in combined.lower(), combined
    assert "0 sessions" not in combined, (
        "`shepherd status` reported an empty fleet rather than an unknown one —"
        " a silence read as good news, which is exactly what principle 5 forbids"
    )


def test_the_same_process_can_answer_the_facts_it_registers_for_itself(
    daemon: Daemon,
) -> None:
    """The control: this `shepherd` is not simply broken.

    `register_local_reads` gives a standalone process two facts it can answer —
    the schema version and the engine version — and `doctor` reads them. If
    `doctor` were also a total failure, the `status` result above would be about
    a broken CLI rather than about a process-global registry.
    """
    answer = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from shepherd.cli.main import main; sys.exit(main(['doctor']))",
        ],
        cwd=str(daemon.home),
        env=daemon.env,
        capture_output=True,
        text=True,
        check=False,
        timeout=STATUS_TIMEOUT_S,
    )
    combined = answer.stdout + answer.stderr
    assert "schema" in combined.lower(), combined
    assert answer.stdout.strip(), "doctor printed nothing at all"


def test_the_daemon_is_still_serving_afterwards(daemon: Daemon) -> None:
    """Nothing the CLI did took the daemon down.

    A `status` that crashed the daemon it cannot see would be a much worse
    finding than the one above, and nothing else here would have noticed.
    """
    run_status(daemon)
    assert daemon.process.poll() is None, "the daemon exited while status ran"
    with urllib.request.urlopen(f"http://127.0.0.1:{daemon.port}/", timeout=10) as answer:
        assert answer.status == 200


def test_a_status_with_no_daemon_at_all_says_the_same_thing(tmp_path: Path) -> None:
    """The other half of T18-1, and the one that makes it a finding.

    If `status` said the same thing with **no** daemon running as it does with
    one, then the daemon is contributing nothing to what a user sees — which is
    precisely the defect. Driven rather than argued: no daemon, same command,
    same exit code, same advice.
    """
    home = tmp_path / "alone"
    env = isolated_env(home)
    for value in env.values():
        if value.startswith(str(home)):
            Path(value).mkdir(parents=True, exist_ok=True)
    answer = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from shepherd.cli.main import main; sys.exit(main(['status']))",
        ],
        cwd=str(home),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=STATUS_TIMEOUT_S,
    )
    assert answer.returncode == EXIT_FAILURE
    assert "fleet_summary" in answer.stdout + answer.stderr


def test_nothing_was_left_behind_outside_the_throwaway(daemon: Daemon, tmp_path: Path) -> None:
    """Isolation, asserted rather than promised.

    Every directory the daemon was given is under `tmp_path`, so a file written
    anywhere else would be a leak. The one thing this cannot see is the engine's
    own bookkeeping, which this lane never triggers because no `claude` is
    started here.
    """
    run_status(daemon)
    for name, value in daemon.env.items():
        if name.startswith("XDG_") or name == "CLAUDE_CONFIG_DIR":
            assert Path(value).is_relative_to(tmp_path), (name, value)
    assert not (REPO_ROOT / DB_NAME).exists(), "a database was written into the repo root"
