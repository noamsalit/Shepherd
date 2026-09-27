"""D71 / D72: `controld.start` claims, binds, then opens the store — in that order.

Seam: `controld.start()` against the throwaway host (`world_fixture.world`),
observed through what an operator and a second daemon can see — the loopback
port, the data dir, the control socket's lock file. Two spies wrap the root's
own collaborators (`create_server`, `compose_tool_surface`) to read the order
they run in; they call the real ones, so nothing is faked.

* C7 / PP2 — a busy port refuses the start having written no `shepherd.db`;
* PP3 — a request queued on the bound port before `serve_forever` is answered
  by the frozen registry (ADR-7 §4 as amended by D71: frozen before it
  *serves*);
* E-QR-5 — a newer schema refused after the bind releases the port, and a
  compose that raises closes the store and releases the port;
* E-QR-16 — a first start with no runtime dir claims and binds;
* D72 — the claim is held until `stop()`.
"""

from __future__ import annotations

import json
import socket
import stat
import subprocess
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

import pytest

from shepherd.daemons import controld
from shepherd.host.detect import detect_host
from shepherd.store.db import Store
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION, MigrationRefused, migrate
from shepherd.toolsurface.registry import RegistryFrozen, register, registered_tools
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef
from world_fixture import World, world  # noqa: F401 - the shared fixture, imported by name

CEILING_S = 10.0


class CreateServer(Protocol):
    """`controld.create_server`'s shape, as the root calls it."""

    def __call__(self, host: str, port: int, static_root: Path) -> ThreadingHTTPServer: ...


#: Tries `<socket>.lock` once from another process: exit 0 taken, 3 held.
TRY_LOCK = (
    "import fcntl, os, sys\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "try:\n"
    "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "except BlockingIOError:\n"
    "    sys.exit(3)\n"
    "sys.exit(0)\n"
)


@contextmanager
def running(world: World, port: int = 0) -> Iterator[controld.Controld]:
    started = controld.start(host=detect_host(), port=port, engine_config_dir=world.engine_config_dir)
    try:
        yield started
    finally:
        controld.stop(started)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def another_process_can_lock(path: Path) -> bool:
    done = subprocess.run(
        [sys.executable, "-c", TRY_LOCK, str(path)], capture_output=True, timeout=CEILING_S
    )
    assert done.returncode in (0, 3), done.stderr
    return done.returncode == 0


def seed_a_newer_schema(db_path: Path) -> None:
    """The shape `test_controld_refusals_qa6.py` seeds: one migration from the future."""
    migrate(db_path)
    future = EXPECTED_SCHEMA_VERSION + 1
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            (future, f"{future:03d}_from_the_future", "x", "2026-09-27T00:00:00Z"),
        )
    connection.close()


def test_an_occupied_port_writes_no_database(world: World) -> None:
    """C7 / PP2: the port is bound before the store is opened, so a start the
    port refuses has opened, migrated and written nothing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
        occupier.bind(("127.0.0.1", 0))
        occupier.listen(1)
        port = int(occupier.getsockname()[1])

        with pytest.raises(OSError):
            controld.start(host=detect_host(), port=port, engine_config_dir=world.engine_config_dir)

    assert not (world.data_dir / controld.DB_NAME).exists(), "a refused port still wrote shepherd.db"


def test_a_first_start_with_no_runtime_dir_claims_and_binds(world: World) -> None:
    """E-QR-16: the claim runs before anything has made the runtime dir."""
    assert not world.runtime_dir.exists(), "the fixture's runtime dir already exists"
    with running(world) as started:
        assert started.control_socket_path.parent == world.runtime_dir
        assert stat.S_IMODE(world.runtime_dir.stat().st_mode) == 0o700
        assert stat.S_ISSOCK(started.control_socket_path.stat().st_mode)
        assert (world.runtime_dir / f"{started.control_socket_path.name}.lock").is_file()


def server_spy(real_create_server: CreateServer, servers: list[ThreadingHTTPServer]) -> CreateServer:
    """A `create_server` that keeps a reference to what it built.

    The reference is the point: a refused start that forgets to close its
    server would otherwise be rescued by the garbage collector closing the
    unreferenced socket, and the rebind below would pass vacuously."""

    def spy_create_server(host: str, port: int, static_root: Path) -> ThreadingHTTPServer:
        server = real_create_server(host, port, static_root=static_root)
        servers.append(server)
        return server

    return spy_create_server


def assert_the_port_was_given_back(servers: list[ThreadingHTTPServer], port: int) -> None:
    assert [int(server.server_address[1]) for server in servers] == [port]
    assert servers[0].socket.fileno() == -1, "the refused start left its server's socket open"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as again:
        again.bind(("127.0.0.1", port))  # EADDRINUSE here is the leaked listener


def test_a_newer_schema_closes_the_port_it_bound(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """E-QR-5: the store refuses after the bind, and the bind does not outlive it.
    `refused` is held too: its traceback keeps `start`'s frame, and so its
    `server` local, alive."""
    seed_a_newer_schema(world.data_dir / controld.DB_NAME)
    servers: list[ThreadingHTTPServer] = []
    monkeypatch.setattr(controld, "create_server", server_spy(controld.create_server, servers))
    port = free_port()
    with pytest.raises(MigrationRefused) as refused:
        controld.start(host=detect_host(), port=port, engine_config_dir=world.engine_config_dir)

    assert servers, "the store was opened before the port was bound"
    assert_the_port_was_given_back(servers, port)
    assert refused.value is not None


def test_a_compose_that_raises_closes_the_store_and_the_port(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `ExitStack`'s other exit: a refusal from `compose_tool_surface`, after
    the bind *and* the store, undoes both — the writer thread is joined and the
    port rebinds."""
    servers: list[ThreadingHTTPServer] = []
    stores: list[Store] = []
    real_open_store = controld.open_store

    def spy_open_store(db_path: Path) -> Store:
        store = real_open_store(db_path)
        stores.append(store)
        return store

    def compose_that_raises(*args: object, **kwargs: object) -> object:
        raise RuntimeError("compose refused")

    monkeypatch.setattr(controld, "create_server", server_spy(controld.create_server, servers))
    monkeypatch.setattr(controld, "open_store", spy_open_store)
    monkeypatch.setattr(controld, "compose_tool_surface", compose_that_raises)
    port = free_port()
    with pytest.raises(RuntimeError, match="compose refused") as refused:
        controld.start(host=detect_host(), port=port, engine_config_dir=world.engine_config_dir)

    assert len(stores) == 1
    assert not stores[0].writer_is_alive(), "a refused compose left the store open"
    assert_the_port_was_given_back(servers, port)
    assert refused.value is not None


def test_the_registry_is_frozen_before_the_server_serves(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PP3: bound first, frozen next, served last. A request that arrives in
    the window between the bind and `serve_forever` waits in the backlog and is
    answered by the frozen registry — which is why D71 costs ADR-7 nothing."""
    order: list[str] = []
    queued: list[socket.socket] = []
    real_create_server, real_compose = controld.create_server, controld.compose_tool_surface

    def spy_create_server(host: str, port: int, static_root: Path) -> ThreadingHTTPServer:
        server = real_create_server(host, port, static_root=static_root)
        order.append("bind")
        bound_port = int(server.server_address[1])
        client = socket.create_connection(("127.0.0.1", bound_port), timeout=CEILING_S)
        client.sendall(
            f"GET /api/fleet HTTP/1.1\r\nHost: 127.0.0.1:{bound_port}\r\nConnection: close\r\n\r\n".encode()
        )
        queued.append(client)
        real_serve = server.serve_forever

        def serve_forever(poll_interval: float = 0.5) -> None:
            order.append("serve")
            real_serve(poll_interval)

        server.serve_forever = serve_forever  # type: ignore[method-assign]
        return server

    def spy_compose(*args: object, **kwargs: object) -> object:
        order.append("compose")
        return real_compose(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(controld, "create_server", spy_create_server)
    monkeypatch.setattr(controld, "compose_tool_surface", spy_compose)
    with running(world) as started:
        with queued[0] as client:
            response = b""
            while chunk := client.recv(65_536):
                response += chunk

        assert order == ["bind", "compose", "serve"]
        head, _, body = response.partition(b"\r\n\r\n")
        assert head.startswith(b"HTTP/1.") and b" 200 " in head.split(b"\r\n")[0], head
        assert "data" in json.loads(body)
        assert started.port != 0
        assert {"fleet_summary", "fleet_tree", "schema_status", "engine_version"} <= set(registered_tools())
        with pytest.raises(RegistryFrozen):
            register(
                ToolDef(
                    name="too_late",
                    description="registered after the server served",
                    input_schema={"type": "object", "properties": {}},
                    blast_class=BlastClass.LOCAL_READ,
                    handler=lambda args, ctx: None,
                    audiences=frozenset({Audience.HUMAN}),
                )
            )


def test_controld_holds_its_claim_until_stop(world: World) -> None:
    """D72: while `controld` runs no other process can take its socket's lock;
    after `stop()` the listener's `finally` has released it."""
    with running(world) as started:
        lock = started.control_socket_path.with_name(started.control_socket_path.name + ".lock")
        assert not another_process_can_lock(lock), "a running controld's claim was taken"
    assert another_process_can_lock(lock), "controld's claim outlived stop()"
