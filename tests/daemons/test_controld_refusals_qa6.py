"""qa6 BC-16 / BC-21 (C10): a refused start is a refusal, never a theft or a traceback.

Seam: `controld.main` and `sessiond.main`, in-process, against a throwaway host.
`main` takes no host argument, so — exactly as `tests/daemons/test_controld.py`
does — every directory variable any driver reads is redirected under
`tmp_path` and `detect_host()` is asked where things are. That module's `world`
fixture is copied here rather than edited or imported: a helper shared across
test files would make one file's edit silently change the other's meaning.

`install_shutdown_handlers` is replaced by one that sets the shutdown event at
once. A `main` that wrongly *starts* then returns straight away instead of
waiting for a SIGTERM that never comes, so a regression is a failed assertion,
not a hung run. No test here reaches port 8787: every start asks for port 0.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.frames import Frame
from shepherd.daemons import controld, sessiond
from shepherd.daemons.control_ingest import serve_control_ingest
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME, INGEST_SOCKET_NAME
from shepherd.engines.claude_code.ingest_socket import bind_listener
from shepherd.host.detect import detect_host
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION, migrate

CEILING_S = 5.0

HOST_DIR_ENV: tuple[str, ...] = (
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "HOME",
    "TMPDIR",
)


@dataclass(frozen=True)
class World:
    data_dir: Path
    engine_config_dir: Path


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    targets = {
        "XDG_DATA_HOME": tmp_path / "xdg_data_home",
        "XDG_CONFIG_HOME": tmp_path / "xdg_config_home",
        "XDG_STATE_HOME": tmp_path / "xdg_state_home",
        "XDG_CACHE_HOME": tmp_path / "xdg_cache_home",
        "XDG_RUNTIME_DIR": tmp_path / "run",
        "HOME": tmp_path / "home",
        "TMPDIR": tmp_path / "run",
    }
    assert tuple(targets) == HOST_DIR_ENV
    for name, target in targets.items():
        monkeypatch.setenv(name, str(target))
    engine_config_dir = tmp_path / "engine-config"
    (engine_config_dir / "sessions").mkdir(parents=True)
    dirs = detect_host().dirs()
    for directory in (dirs.data_dir, dirs.runtime_dir):
        assert tmp_path in directory.parents, f"{directory} escaped the throwaway host"
    shutdown_at_once = lambda shutdown: shutdown.set()  # noqa: E731
    monkeypatch.setattr(controld, "install_shutdown_handlers", shutdown_at_once)
    monkeypatch.setattr(sessiond, "install_shutdown_handlers", shutdown_at_once)
    return World(data_dir=dirs.data_dir, engine_config_dir=engine_config_dir)


def controld_argv(world: World) -> list[str]:
    return ["--port", "0", "--engine-config-dir", str(world.engine_config_dir)]


def hello_from(path: Path) -> bytes | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(CEILING_S)
            client.connect(str(path))
            received = b""
            while b"\n" not in received:
                chunk = client.recv(4096)
                if not chunk:
                    return None
                received += chunk
            return received
    except OSError:
        return None


@contextmanager
def first_control_owner(path: Path) -> Iterator[threading.Thread]:
    """A first `controld`'s ingest loop, already serving on `path`."""
    plan = detect_host().control_socket(CONTROL_SOCKET_NAME)
    assert plan.path == path
    shutdown, bound = threading.Event(), threading.Event()
    frames: list[Frame] = []
    owner = threading.Thread(
        target=serve_control_ingest,
        kwargs={"plan": plan, "schema_version": EXPECTED_SCHEMA_VERSION,
                "on_frame": frames.append, "shutdown": shutdown, "bound": bound},
        daemon=True,
    )
    owner.start()
    try:
        assert bound.wait(CEILING_S), "the first owner never bound"
        yield owner
    finally:
        shutdown.set()
        owner.join(CEILING_S)


def test_controld_refuses_a_held_control_socket_and_writes_nothing(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    path = detect_host().control_socket(CONTROL_SOCKET_NAME).path
    with first_control_owner(path) as owner:
        inode = os.stat(path).st_ino

        assert controld.main(controld_argv(world)) == controld.EXIT_REFUSED

        out = capsys.readouterr().out
        assert "controld refuses to start:" in out
        assert "is held by a running process" in out
        assert not (world.data_dir / controld.DB_NAME).exists()
        assert os.stat(path).st_ino == inode
        assert owner.is_alive(), "the refusal's probe ended the first owner's loop"
        assert hello_from(path) is not None, "the first owner no longer greets a client"


def test_controld_refuses_a_newer_schema(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = world.data_dir / controld.DB_NAME
    migrate(db_path)
    future = EXPECTED_SCHEMA_VERSION + 1
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            (future, f"{future:03d}_from_the_future", "x", "2026-09-24T00:00:00Z"),
        )
    connection.close()

    assert controld.main(controld_argv(world)) == controld.EXIT_REFUSED

    out = capsys.readouterr().out
    assert "controld refuses to start:" in out
    assert str(future) in out and "newer" in out
    assert "Traceback" not in out


def test_sessiond_refuses_a_held_ingest_socket(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = detect_host().control_socket(INGEST_SOCKET_NAME)
    owner = bind_listener(plan)
    try:
        inode = os.stat(plan.path).st_ino

        assert sessiond.main(["--expected-schema-version", str(EXPECTED_SCHEMA_VERSION)]) == (
            sessiond.EXIT_REFUSED
        )

        err = capsys.readouterr().err
        assert "sessiond refuses to start:" in err
        assert os.stat(plan.path).st_ino == inode
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(plan.path))
            owner.settimeout(CEILING_S)
            accepted, _ = owner.accept()
            accepted.close()
    finally:
        owner.close()
