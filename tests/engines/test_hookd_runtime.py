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

import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, LinuxHost

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

LATENCY_BUDGET_S = 0.010
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


def hook_entry(socket_path: Path) -> HookEntry:
    plan = SocketPlan(
        path=socket_path,
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )
    return build_hook_entry(plan, LinuxHost().hook_dispatch(plan))


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

    Measured 3.2 ms with the flag and 253.6 ms without, so the budget separates
    the two by a factor of 25 in either direction.
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
