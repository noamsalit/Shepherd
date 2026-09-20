"""BLOCKING 1: the liveness backstop must read what the real writers write.

`ordering.parse_stamp` is the only reader of `last_event_at`, and `is_live` is
the only thing standing between §16's `running` bucket and an empty one. Every
assertion in this module takes its stamp from a **production writer** — the
discovery lane's clock, the hook lane's clock, the tool surface's clock — and
never from a literal. A liveness suite whose fixtures hand-write the parser's
own format proves only that the parser agrees with the tests.

The one literal here is the *shape* itself (`_CANONICAL`), which is the spec:
one UTC stamp, millisecond precision, `Z`. It is written down so that a writer
drifting to a second spelling fails here instead of silently emptying a bucket.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.frames import Frame
from shepherd.core.states import SessionState
from shepherd.core.stream import StreamEvent
from shepherd.engines.claude_code.ingest_socket import now_iso
from shepherd.engines.claude_code.registry import SESSIONS_DIRNAME
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    Liveness,
    LoginPersistence,
    SocketPlan,
    Supervision,
)
from shepherd.host.linux import LinuxHost
from shepherd.signals.discovery_loop import discovery_pass, iso_from_epoch_ms
from shepherd.signals.hook_lane import HookLane
from shepherd.signals.ordering import effective_state, is_live, parse_stamp
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface.tools_m1 import fleet_tree, utc_now

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNING_CAPTURE = (
    REPO_ROOT
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "tmux-tui"
    / "run-20260914T154946Z"
    / "07-sidecar-running.json"
)

ENGINE_SESSION_ID = "5d1202ea-3765-459d-8299-8630c710c50d"

#: The spec, as a literal: UTC, millisecond precision, `Z`. Not derived from the
#: code under test — a format constant compared against itself proves nothing.
_CANONICAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture(autouse=True)
def never_the_real_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-such-config"))


def test_every_production_stamp_writer_emits_the_one_format() -> None:
    """One helper, one shape — asserted by calling each real writer.

    These are the functions that actually stamp rows: the hook lane's frame
    clock, the discovery lane's scan clock and its sidecar conversion, the tool
    surface's `now`, and the store's own row clock. If any one of them drifts,
    `parse_stamp` starts returning `None` for real data and `is_live` goes
    quietly false — which is exactly how BLOCKING 1 happened.
    """
    from shepherd.host import linux as linux_host
    from shepherd.signals import discovery_loop
    from shepherd.store import db as store_db
    from shepherd.store import migrate as store_migrate

    written = {
        "ingest_socket.now_iso": now_iso(),
        "discovery_loop._now": discovery_loop._now(),
        "discovery_loop.iso_from_epoch_ms": iso_from_epoch_ms(int(time.time() * 1000)),
        "tools_m1.utc_now": utc_now(),
        "store.db._now": store_db._now(),
        "store.migrate._now": store_migrate._now(),
        "host.linux._now": linux_host._now(),
    }
    misshapen = {
        name: stamp for name, stamp in written.items() if _CANONICAL.fullmatch(stamp) is None
    }
    assert misshapen == {}

    unreadable = {name: stamp for name, stamp in written.items() if parse_stamp(stamp) is None}
    assert unreadable == {}


def test_the_hook_lane_writes_a_stamp_the_backstop_reads_as_live(
    store: Store, tmp_path: Path
) -> None:
    """The hook lane, end to end, with its own clock — and `running` survives.

    `received_at` comes from `ingest_socket.now_iso`, the function the real
    listener stamps every frame with. That stamp used to be an `isoformat()`
    with a `+00:00` offset that `parse_stamp` read as `None`, so this row was
    demoted to `starting` at an age of a few milliseconds — with no fixture
    anywhere able to notice, because every fixture wrote the parser's format.
    """
    published: list[StreamEvent] = []

    def publish(event: StreamEvent) -> int:
        published.append(event)
        return len(published)

    lane = HookLane(store=store, publish=publish)
    payload = {
        "session_id": ENGINE_SESSION_ID,
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_use_id": "toolu_012CQgKZPPKKLQx9nH3Qjkbi",
    }
    lane.apply(
        Frame(
            payload=json.dumps(payload).encode("utf-8") + b"\n",
            received_at=now_iso(),  # the real writer, not a literal
            peer_pid=None,
        )
    )

    rows = store.fleet()
    assert len(rows) == 1
    row = rows[0]
    assert row.state is SessionState.RUNNING
    assert row.last_event_at is not None
    assert is_live(row.last_event_at, utc_now())
    assert effective_state(row, utc_now()) is SessionState.RUNNING

    # …and through the projection the fleet page actually reads (§16): the
    # `running` bucket is reachable, which is the whole of BLOCKING 1.
    tree = fleet_tree(store, utc_now)
    workspaces = tree["workspaces"]
    assert isinstance(workspaces, list)
    states = [
        session["state"]
        for workspace in workspaces
        for session in workspace["sessions"]  # type: ignore[index,union-attr]
    ]
    assert states == ["running"]


def test_the_discovery_lane_writes_a_stamp_the_backstop_reads_as_live(
    store: Store, tmp_path: Path
) -> None:
    """The registry lane's stamp is `iso_from_epoch_ms`, and it must read live.

    The sidecar is the real `07-sidecar-running.json` capture with its
    `statusUpdatedAt` moved to now — the shape is captured, and the recency is
    what the liveness window is about.
    """
    config_dir = tmp_path / "engine"
    fields = json.loads(RUNNING_CAPTURE.read_text(encoding="utf-8"))
    assert isinstance(fields, dict)
    pid = int(fields["pid"])
    now_ms = int(time.time() * 1000)
    fields["statusUpdatedAt"] = now_ms
    fields["updatedAt"] = now_ms
    fields["cwd"] = str(tmp_path)
    sessions = config_dir / SESSIONS_DIRNAME
    sessions.mkdir(parents=True)
    (sessions / f"{pid}.json").write_text(json.dumps(fields), encoding="utf-8")

    host = ScriptedHost(
        host_dirs=HostDirs(
            data_dir=config_dir / "data",
            config_dir=config_dir,
            runtime_dir=config_dir / "run",
        ),
        socket_plan=SocketPlan(
            path=config_dir / "run" / "x.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(command="true", requires=(), available=True, reason=""),
        supervision_plan=Supervision(
            kind="foreground", detail="", manageable=False, start_limit_note=""
        ),
        login=LoginPersistence(enabled=None, mechanism="none", detail=""),
        liveness_by_pid={
            pid: Liveness(
                alive=True,
                start_token=str(fields["procStart"]),
                observed_at=now_iso(),
            )
        },
    )

    discovery_pass(store, host, lambda result: None, utc_now(), config_dir)

    rows = store.fleet()
    assert len(rows) == 1
    row = rows[0]
    assert row.last_event_at is not None
    assert is_live(row.last_event_at, utc_now())


def test_the_real_linux_host_stamps_liveness_in_the_same_format() -> None:
    """`Liveness.observed_at` becomes `ended_at`/`observed_at` on a real row."""
    host = LinuxHost()
    observed = host.process_liveness(1, None)
    assert _CANONICAL.fullmatch(observed.observed_at) is not None
    assert parse_stamp(observed.observed_at) is not None
