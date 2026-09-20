"""T8, principle 4: the real command, a real `/bin/sh`, a real socket.

Every test here spawns the command Claude Code would spawn — `/bin/sh -c` with
the payload on stdin and EOF after it (data-schemas §"Hook runtime contract") —
against a Unix socket in `tmp_path`. Nothing is mocked, because the property
being proved is "this cannot harm Claude Code", and a mock cannot be harmed.

The one that matters most is `test_dispatch_command_shuts_down_write_side`. The
missing-flag bug measured in `docs/probes/2026-09-16-hookd-latency.md` Result 1b
**still delivers every frame**: it costs 253.6 ms instead of 3.2 ms and fails no
assertion about content. Only the EOF clock can see it, so that is what this
file asserts — not the shape of the string.
"""

from __future__ import annotations

import shlex
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.host.base import SocketPlan
from shepherd.host.detect import detect_host

#: A real corpus payload: data-schemas §"Common input fields", first example
#: (`docs/probes/2026-09-14-schemas/hooks/live/S01_startup_tools/events.jsonl`).
CORPUS_PAYLOAD = (
    b'{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","transcript_path":'
    b'"/root/.claude/projects/-tmp-shp-hooks-base-dwqg6d95/'
    b'8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6.jsonl","cwd":"/tmp/shp-hooks-base-dwqg6d95",'
    b'"prompt_id":"23d7f57d-6e63-45f1-9217-c7395a4c98a9","permission_mode":"default",'
    b'"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":'
    b'{"command":"echo hello","description":"Echo hello"},'
    b'"tool_use_id":"toolu_015R8tPjv7FUHuW6MDJj8HpT"}\n'
)

#: Result 2: 40 KB is far above the largest real payload and arrives intact.
FRAME_40KB = b'{"pad":"' + b"x" * 40_000 + b'"}\n'

#: §8's bound on a hung `sessiond` is 250 ms; the process may not outlive it by
#: much, so the wall-clock ceiling for a pathological listener is 400 ms.
HUNG_LISTENER_CEILING_S = 0.4

#: E34: a listener reading to EOF sees it ~3 ms after the payload with `-q0` and
#: ~250 ms without. 50 ms is far above the former and far below the latter.
EOF_CEILING_S = 0.05

#: The cost budget per hook invocation, **per platform**, because the two
#: platforms' numbers are not close and neither is arbitrary.
#:
#: Linux (`docs/probes/2026-09-16-hookd-latency.md` Result 1): `sh` + `nc -U -q0`
#: costs 3.4 ms and a Python dispatcher costs 31.7 ms. 10 ms sits 2.9x above the
#: one and 3.2x below the other, which is what makes it a discriminator.
LINUX_LATENCY_BUDGET_S = 0.010

#: macOS (`docs/probes/2026-09-20-macos-g1-capture.md` §4): the same shape costs
#: **14.1-16.2 ms** over 12 measured attempts, and almost none of that is the
#: `perl` bound — `perl -e 0` is 3.56 ms and `sh -c true` alone is 4.19 ms on
#: this host, against ~1 ms on Linux. Process spawn is simply dearer here.
#:
#: So Linux's 10 ms is not portable and neither is its rationale: a Python
#: dispatcher costs 26 ms on this Mac, so the shell hook is 1.7x cheaper rather
#: than an order of magnitude cheaper, and no single number separates them the
#: way 10 ms separates them on Linux. What the budget still asserts here is the
#: property that matters to an agent: 40 ms is 2.6x the measured cost, 6x below
#: the 250 ms class of failure the Linux probe measured, and 125x below the 5 s
#: the settings entry gives the hook (E18). Stated rather than quietly widened.
MAC_LATENCY_BUDGET_S = 0.040

LATENCY_BUDGET_S = (
    MAC_LATENCY_BUDGET_S if sys.platform == "darwin" else LINUX_LATENCY_BUDGET_S
)

#: The alternative dispatcher design, as a command, so the budget above can be
#: compared against something measured on the same host in the same run rather
#: than against a number written down on another machine. This is the "Python
#: dispatcher" both probes cite: interpreter start, `AF_UNIX` connect, one
#: `sendall`, exit. It is a **baseline**, never the product path.
PYTHON_DISPATCHER = (
    "exec {python} -c '"
    "import socket,sys\n"
    "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
    "s.connect(sys.argv[1])\n"
    "s.sendall(sys.stdin.buffer.read())\n"
    "s.close()\n"
    "' {path}"
)

#: How much cheaper the shell hook must be than that baseline before the
#: comparison is saying anything. The macOS capture measured 14-16 ms against
#: ~26 ms, i.e. ~1.7x; 1.25x leaves room for load without letting the two
#: shapes converge unnoticed.
MAC_DISPATCHER_MARGIN = 1.25

#: The floor the baseline must clear for the comparison above to be a
#: comparison at all. `docs/probes/2026-09-20-macos-g1-capture.md` §4 measured
#: the Python-dispatcher class on this host at **≥26 ms** (`python3 -c pass`
#: alone is 26.11 ms, before the socket), against 14-16 ms for the shell hook.
#: 20 ms is that class with room for load underneath it, and still 25% above
#: the hook's worst measured attempt — so it separates the two designs, which
#: is the whole job. If a future baseline came in under it, the relative
#: assertion would be comparing the hook against something that is no longer a
#: slow case, and this is what says so out loud instead of passing quietly.
MAC_PYTHON_DISPATCHER_FLOOR_S = 0.020

LATENCY_INVOCATIONS = 25
LATENCY_ATTEMPTS = 3
LATENCY_ATTEMPTS_REQUIRED = 2


@dataclass
class Received:
    """What a listener saw: the frames, and when each connection hit EOF."""

    frames: list[bytes] = field(default_factory=list)
    eof_delays_s: list[float] = field(default_factory=list)


@contextmanager
def listener(path: Path, *, read_to_eof: bool = True) -> Iterator[Received]:
    """A real UDS server. `read_to_eof=False` accepts and never reads (hung)."""
    received = Received()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(16)
    server.settimeout(0.05)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = server.accept()
            except (socket.timeout, OSError):
                continue
            with connection:
                if not read_to_eof:
                    stop.wait(HUNG_LISTENER_CEILING_S * 2)
                    continue
                chunks: list[bytes] = []
                first_byte_at: float | None = None
                connection.settimeout(2.0)
                while True:
                    try:
                        chunk = connection.recv(65536)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    if first_byte_at is None:
                        first_byte_at = time.perf_counter()
                    chunks.append(chunk)
                if first_byte_at is not None:
                    received.eof_delays_s.append(time.perf_counter() - first_byte_at)
                received.frames.append(b"".join(chunks))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield received
    finally:
        stop.set()
        thread.join(timeout=3.0)
        server.close()


#: **The host this suite is running on**, not Linux. These fixtures used to
#: build their entry from `LinuxHost()` and call it "the real host's dispatch
#: command". On Linux that is true. On macOS `LinuxHost.hook_dispatch()` probes
#: for `timeout`, which does not exist there, reports `available=False`, and the
#: `pytest.skip` below fired — silently removing 28 tests of the hook-install
#: and hook-runtime lane on the one platform whose hook lane had never been
#: exercised. The guard itself is right: a host with no dispatcher cannot test
#: one. It has to ask about *this* host to mean anything.
HOST = detect_host()
HOST_SOCKET_PATH_BUDGET = HOST.control_socket("sessiond").socket_path_budget


def hook_entry(socket_path: Path) -> HookEntry:
    plan = SocketPlan(
        path=socket_path,
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=HOST_SOCKET_PATH_BUDGET,
    )
    return build_hook_entry(plan, HOST.hook_dispatch(plan))


@pytest.fixture
def entry(tmp_path: Path) -> HookEntry:
    built = hook_entry(tmp_path / "sessiond.sock")
    if not built.available:
        pytest.skip(f"no dispatcher on this host: {built.reason}")
    return built


def dispatch(entry: HookEntry, payload: bytes) -> subprocess.CompletedProcess[bytes]:
    """Exactly how Claude Code runs it: `/bin/sh -c <command>`, payload, EOF."""
    return subprocess.run(
        ["/bin/sh", "-c", entry.command],
        input=payload,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_hookd_delivers_payload_bytes(tmp_path: Path, entry: HookEntry) -> None:
    with listener(tmp_path / "sessiond.sock") as received:
        result = dispatch(entry, CORPUS_PAYLOAD)
        deadline = time.monotonic() + 2.0
        while not received.frames and time.monotonic() < deadline:
            time.sleep(0.005)
    assert result.returncode == 0
    assert received.frames == [CORPUS_PAYLOAD]


def test_hookd_delivers_40kb_frame(tmp_path: Path, entry: HookEntry) -> None:
    with listener(tmp_path / "sessiond.sock") as received:
        result = dispatch(entry, FRAME_40KB)
        deadline = time.monotonic() + 3.0
        while not received.frames and time.monotonic() < deadline:
            time.sleep(0.005)
    assert result.returncode == 0
    assert received.frames == [FRAME_40KB]
    assert len(received.frames[0]) == len(FRAME_40KB)


def test_dispatch_command_shuts_down_write_side(tmp_path: Path, entry: HookEntry) -> None:
    """E34, the regression guard: EOF within 50 ms, not at the 250 ms timeout."""
    with listener(tmp_path / "sessiond.sock") as received:
        result = dispatch(entry, CORPUS_PAYLOAD)
        deadline = time.monotonic() + 2.0
        while not received.eof_delays_s and time.monotonic() < deadline:
            time.sleep(0.005)
    assert result.returncode == 0
    assert received.eof_delays_s, "the listener never observed a frame at all"
    assert received.eof_delays_s[0] < EOF_CEILING_S, (
        f"EOF observed {received.eof_delays_s[0] * 1000:.1f} ms after the payload — "
        "the dispatcher is not shutting down its write side (probe Result 1b)"
    )


def test_hookd_exits_zero_with_no_listener(tmp_path: Path, entry: HookEntry) -> None:
    """P4: nothing is bound at the path — the agent pays milliseconds, not an error."""
    assert not (tmp_path / "sessiond.sock").exists()
    started = time.perf_counter()
    result = dispatch(entry, CORPUS_PAYLOAD)
    assert result.returncode == 0
    assert time.perf_counter() - started < HUNG_LISTENER_CEILING_S


def test_hookd_exits_zero_on_hung_listener(tmp_path: Path, entry: HookEntry) -> None:
    """A `sessiond` that accepts and never reads is bounded from outside (§8)."""
    with listener(tmp_path / "sessiond.sock", read_to_eof=False):
        started = time.perf_counter()
        result = dispatch(entry, CORPUS_PAYLOAD)
        elapsed = time.perf_counter() - started
    assert result.returncode == 0
    assert elapsed < HUNG_LISTENER_CEILING_S, f"{elapsed * 1000:.1f} ms on a hung listener"


def test_hookd_exits_zero_on_empty_stdin(tmp_path: Path, entry: HookEntry) -> None:
    with listener(tmp_path / "sessiond.sock") as received:
        result = dispatch(entry, b"")
        time.sleep(0.1)
    assert result.returncode == 0
    assert received.frames in ([], [b""])


def test_hookd_latency_under_10ms(tmp_path: Path, entry: HookEntry) -> None:
    """Probabilistic (plan): 3 attempts, 2 must come in under budget.

    The name records Linux's budget, which is where this test was written and
    where 10 ms separates a shell hook (3.2 ms with `-q0`) from a lost flag
    (253.6 ms) by a factor of 25 in either direction. macOS costs 14-16 ms for
    the same work and is held to `MAC_LATENCY_BUDGET_S`; see that constant for
    why the Linux number is not portable and what the macOS one still asserts.
    Renaming the test would drop its node id out of
    `tests/boundaries/collected_node_ids.txt`, which is Clause 16's baseline.
    """
    means: list[float] = []
    with listener(tmp_path / "sessiond.sock"):
        for _ in range(LATENCY_ATTEMPTS):
            started = time.perf_counter()
            for _ in range(LATENCY_INVOCATIONS):
                assert dispatch(entry, CORPUS_PAYLOAD).returncode == 0
            means.append((time.perf_counter() - started) / LATENCY_INVOCATIONS)
    under = [mean for mean in means if mean < LATENCY_BUDGET_S]
    assert len(under) >= LATENCY_ATTEMPTS_REQUIRED, (
        f"means (ms): {[round(mean * 1000, 2) for mean in means]}"
    )

    if sys.platform != "darwin":
        return

    # macOS companion, added 2026-09-20 after review. On Linux the assertion
    # above is a *discriminator*: 10 ms sits 2.9x above the shell hook and 3.2x
    # below a Python dispatcher, so only one of the two designs can pass it. On
    # macOS it is not — a Python dispatcher costs ~26 ms here and passes a 40 ms
    # budget — so on this platform the assertion above is a ceiling on
    # agent-felt cost and nothing more. `MAC_LATENCY_BUDGET_S` says so in
    # writing, which is honest, but one node id was then carrying two meanings
    # and the weaker one was invisible from the test name.
    #
    # So the discriminator is restored here as a *relative* one. The baseline is
    # measured in the same run against the same listener, which is what makes it
    # a comparison rather than another written-down number: if the machine is
    # loaded, both sides move together.
    #
    # It carries its own negative control, and the control is the *first*
    # assertion below: the baseline has to still be in the slow class
    # (`MAC_PYTHON_DISPATCHER_FLOOR_S`, §4's ≥26 ms with room for load). If the
    # alternative design ever became cheap enough to sit near the hook, the
    # relative assertion would be comparing the hook against something that is
    # no longer a slow case and would stop discriminating silently. That is the
    # exact failure mode this companion exists to close, so it is not allowed
    # to recur one level up — which means the precondition has to be a number
    # that can actually be missed. The first draft used
    # `baseline > LATENCY_BUDGET_S`; a second used `baseline > 0.0`. Both are
    # dealt with directly above the assertion.
    #
    # The baseline is measured in the same shape as `means` — `LATENCY_ATTEMPTS`
    # attempts of `LATENCY_INVOCATIONS` invocations, best of attempts — so the
    # two sides of the comparison are symmetric. An earlier version took
    # `min(means)` against a single-attempt baseline: load inflated the one-shot
    # baseline while the `min` discarded the hook's worst attempt, which biases
    # only toward passing. That is stable but it spends discrimination to buy
    # stability the relative form already provides.
    socket_path = tmp_path / "baseline.sock"
    baseline_command = PYTHON_DISPATCHER.format(
        python=shlex.quote(sys.executable), path=shlex.quote(str(socket_path))
    )
    baseline_means: list[float] = []
    with listener(socket_path):
        for _ in range(LATENCY_ATTEMPTS):
            started = time.perf_counter()
            for _ in range(LATENCY_INVOCATIONS):
                assert (
                    subprocess.run(
                        ["/bin/sh", "-c", baseline_command],
                        input=CORPUS_PAYLOAD,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    ).returncode
                    == 0
                )
            baseline_means.append((time.perf_counter() - started) / LATENCY_INVOCATIONS)
    baseline = min(baseline_means)

    # Measured here on 2026-09-20: baseline 29.6 ms against a 40 ms budget. The
    # baseline passes the budget — which is the finding, restated as data, and
    # the reason an absolute ceiling cannot do this job on macOS. A first draft
    # of this companion asserted `baseline > LATENCY_BUDGET_S` as its
    # precondition; it went red on the first run, correctly, and is recorded
    # here rather than deleted because "the negative control failed and the
    # assertion it guarded was the wrong one" is the useful half. Its
    # replacement, `baseline > 0.0`, was worse: a wall-clock delta over 25
    # invocations is positive for every possible input, so it could not fail
    # and the paragraph above claiming a negative control was false about the
    # shipped code. The floor below is measured, so it can be missed.
    assert baseline > MAC_PYTHON_DISPATCHER_FLOOR_S, (
        f"the Python-dispatcher baseline came in at {baseline * 1000:.2f} ms, "
        f"under the {MAC_PYTHON_DISPATCHER_FLOOR_S * 1000:.0f} ms class §4 "
        "measured it at. The comparison below is only a discriminator while "
        "the slow case is still slow, so it is not run against this baseline."
    )
    best = min(means)
    assert best * MAC_DISPATCHER_MARGIN < baseline, (
        f"the shell hook costs {best * 1000:.2f} ms against a Python "
        f"dispatcher's {baseline * 1000:.2f} ms on this host — under the "
        f"{MAC_DISPATCHER_MARGIN}x margin that makes the shell one-liner worth "
        "its portability cost. On macOS this, not the budget above, is what "
        "discriminates between the two dispatcher designs."
    )
