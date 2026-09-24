"""The SSE client: one `GET /api/events` connection, read on a thread.

Copied from `tests/qa5/rig.py` (re-proved by `fixtures/mutations/sse_rig.json`,
env-plan §4 step 1a) with three repairs the existing-harness audit asked for:

* **A missing frame after a green control is FAIL, not BLOCKED.** qa5's rig
  raised `HarnessBlocked` for any missing frame. Here `Subscriber.await_frames`
  is a product wait (`await_product`) and takes the control latency measured on
  the same channel; only the *control itself* failing is `Blocked`.
* **Comment lines keep their arrival time**, so E1 can bound the keep-alive
  (`: keep-alive` must not arrive in the first 13 s and must by 17 s).
* **A refused stream is a value**: `open_stream` returns the status and headers
  of a non-200 answer instead of raising, for A5's 403 cases.
* **A frame that does not parse is a FAIL, not a dropped line** (hunter H5):
  `snapshot`/`since`/`mark` raise `AssertionError` once the product has sent
  one; and a stream the server closes after a green control on that
  subscriber is FAIL too (before any control it is `Blocked`).

Kept from qa5, because each was measured: a *blocking* read woken by
`shutdown()` on a socket handle captured before `getresponse()` (a timeout used
as a poll interval makes a `makefile` reader unusable; `HTTPConnection.sock`
is `None` after `getresponse()` on a stream with no Content-Length), and a
reader exit this harness did not ask for is a **fault**, never a quiet stop.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from .verdict import Blocked, await_env, await_product

#: Bounded, and above any socket timeout so the bound is not what expires first.
JOIN_CEILING_S = 15.0


@dataclass(frozen=True)
class Frame:
    """One SSE frame, parsed. Comment lines never become one of these."""

    seq: int
    kind: str
    project_id: str | None
    session_id: str | None
    at: str
    data: dict[str, object]
    body_keys: tuple[str, ...]
    raw_fields: dict[str, str]
    received_at: float

    @property
    def has_event_name(self) -> bool:
        return "event" in self.raw_fields


@dataclass(frozen=True)
class Comment:
    text: str
    received_at: float


@dataclass(frozen=True)
class Refusal:
    status: int
    headers: dict[str, str]
    body: bytes


class Subscriber:
    """One live stream. Construct with `open_stream`, which may refuse."""

    def __init__(self, name: str, connection: http.client.HTTPConnection, sock: socket.socket | None,
                 response: http.client.HTTPResponse) -> None:
        self.name = name
        self.frames: list[Frame] = []
        self.comments: list[Comment] = []
        self.parse_failures: list[str] = []
        self.first_bytes: bytes = b""
        self.reader_fault: str | None = None
        self.green_control: str | None = None
        self.opened_at = time.monotonic()
        self._closing = False
        self._lock = threading.Lock()
        self._connection = connection
        self._socket = sock
        self._response = response
        self.status = response.status
        self.headers = {key.lower(): value for key, value in response.getheaders()}
        self._thread = threading.Thread(target=self._read, name=f"sse-{name}", daemon=True)
        self._thread.start()

    # ----- reading ----------------------------------------------------------
    def _read(self) -> None:
        try:
            self._read_frames()
        except (OSError, ValueError) as error:
            if not self._closing:
                with self._lock:
                    self.reader_fault = f"reader died mid-run: {error!r}"
            return
        if not self._closing:
            with self._lock:
                self.reader_fault = "reader saw EOF mid-run: the server closed the stream"

    def _read_frames(self) -> None:
        current: dict[str, str] = {}
        fp = self._response.fp
        while True:
            raw = fp.readline() if fp is not None else b""
            if raw == b"":
                return
            with self._lock:
                if len(self.first_bytes) < 64:
                    self.first_bytes += raw[: 64 - len(self.first_bytes)]
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                if current:
                    self._append(current)
                    current = {}
                continue
            if line.startswith(":"):
                with self._lock:
                    self.comments.append(Comment(line, time.monotonic()))
                continue
            field_name, _, value = line.partition(":")
            current[field_name] = value[1:] if value.startswith(" ") else value

    def _append(self, fields: dict[str, str]) -> None:
        received = time.monotonic()
        try:
            decoded: object = json.loads(fields["data"])
            if not isinstance(decoded, dict):
                raise TypeError("data is not an object")
            body = {str(key): value for key, value in decoded.items()}
            data = body.get("data", {})
            project = body.get("project_id")
            session = body.get("session_id")
            frame = Frame(
                seq=int(fields["id"]),
                kind=str(body["type"]),
                project_id=project if isinstance(project, str) else None,
                session_id=session if isinstance(session, str) else None,
                at=str(body.get("at", "")),
                data={str(k): v for k, v in data.items()} if isinstance(data, dict) else {},
                body_keys=tuple(body),
                raw_fields=dict(fields),
                received_at=received,
            )
        except (KeyError, ValueError, TypeError) as error:
            with self._lock:
                self.parse_failures.append(f"{error}: {fields!r}")
            return
        with self._lock:
            self.frames.append(frame)

    # ----- reading the tape ---------------------------------------------------
    def snapshot(self) -> list[Frame]:
        """The tape so far — or the reason it cannot be trusted (hunter H5).

        * a frame the product sent that does not parse (bad JSON, no `type`, a
          non-integer `id`) is a product fault the tape would otherwise drop
          silently, so every "no frame of kind X" clause would pass against it:
          `AssertionError` (FAIL);
        * the server closing the stream mid-run AFTER a green control on this
          subscriber (the channel was proven to work): `AssertionError` (FAIL);
        * a reader fault with no green control yet: `Blocked`.
        """
        with self._lock:
            if self.parse_failures:
                raise AssertionError(f"{self.name}: {len(self.parse_failures)} product frame(s) did not parse: "
                                     f"{self.parse_failures[:3]}")
            if self.reader_fault is not None:
                if self.green_control is not None:
                    raise AssertionError(f"{self.name}: {self.reader_fault} (after a green control on this stream: "
                                         f"{self.green_control})")
                raise Blocked(f"{self.name}: {self.reader_fault}")
            return list(self.frames)

    def mark_green(self, what: str) -> None:
        """Record that a positive control succeeded on this subscriber (a later EOF is the product's)."""
        with self._lock:
            if self.green_control is None:
                self.green_control = what

    def comment_snapshot(self) -> list[Comment]:
        with self._lock:
            return list(self.comments)

    def mark(self) -> int:
        return len(self.snapshot())

    def since(self, mark: int) -> list[Frame]:
        return self.snapshot()[mark:]

    def await_frames(
        self,
        predicate: Callable[[list[Frame]], bool],
        bound_s: float,
        what: str,
        control_latency_s: float | None,
        mark: int = 0,
    ) -> list[Frame]:
        """A **product** wait on this stream (FAIL(bound) when a control qualifies it)."""
        await_product(lambda: predicate(self.since(mark)), bound_s, f"{self.name}: {what}", control_latency_s)
        self.mark_green(f"await_frames: {what}")
        return self.since(mark)

    def close(self) -> None:
        """Close the socket and **join** the reader (see the module docstring)."""
        self._closing = True
        handle = self._socket
        if handle is not None:
            try:
                handle.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # already half-closed by the server; the close below still runs
        self._connection.close()
        self._thread.join(timeout=JOIN_CEILING_S)
        if self._thread.is_alive():
            raise Blocked(f"{self.name}: the reader thread did not join in {JOIN_CEILING_S}s")


def open_stream(
    name: str,
    port: int,
    *,
    last_event_id: str | None = None,
    headers: Mapping[str, str] | None = None,
    path: str = "/api/events",
    timeout_s: float = 10.0,
) -> Subscriber | Refusal:
    """Open the stream. A non-200 answer comes back as a `Refusal`."""
    merged = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    if last_event_id is not None:
        merged["Last-Event-ID"] = last_event_id
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout_s)
    connection.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
    for key, value in merged.items():
        connection.putheader(key, value)
    connection.endheaders()
    sock = connection.sock
    response = connection.getresponse()
    if response.status != 200:
        refusal = Refusal(
            status=response.status,
            headers={key.lower(): value for key, value in response.getheaders()},
            body=response.read(),
        )
        connection.close()
        return refusal
    # The stream blocks between events; the read must too (see module docstring).
    if sock is not None:
        sock.settimeout(None)
    return Subscriber(name, connection, sock, response)


def subscribe(name: str, port: int, *, last_event_id: str | None = None) -> Subscriber:
    """`open_stream` that insists on a 200 (an environment precondition)."""
    opened = open_stream(name, port, last_event_id=last_event_id)
    if isinstance(opened, Refusal):
        raise Blocked(f"{name}: the stream answered {opened.status}")
    await_env(lambda: opened.first_bytes.startswith(b": open") or None, 5.0, f"{name}: ': open' comment")
    return opened


# ----- the in-scenario liveness control ------------------------------------------


@dataclass(frozen=True)
class ControlResult:
    """What arrived between a mark and the control, and how fast the control was."""

    interior: list[Frame]
    control_frames: list[Frame]
    latency_s: float


class _ProjectVerbs(Protocol):
    """The two verbs the control needs (structural: `httpclient.Client` fits)."""

    def create_project(self, name: str, description: str | None = None) -> dict[str, object]: ...

    def delete_project(self, project_id: str, on_running: str | None = None) -> dict[str, object]: ...


def run_control(sub: Subscriber, client: _ProjectVerbs, name: str, mark: int, bound_s: float = 10.0) -> ControlResult:
    """Create and delete a throwaway project; both frames must arrive on `sub`.

    **A zero means nothing without this** (qa5 §3a, kept): a dead socket
    delivers nothing and would pass every "no frame" clause. The control runs
    *last*, costs two frames and two audit rows (create, delete), and leaves no
    row. Its latency is the same-channel positive control a FAIL(bound) on this
    stream needs (Difference 1). The control failing is `Blocked`.
    """
    started = time.monotonic()
    created = client.create_project(f"LIVENESS-{name}")
    project = created.get("project")
    project_id = project.get("project_id") if isinstance(project, dict) else None
    if not isinstance(project_id, str):
        raise Blocked(f"control {name}: create answered no project: {created!r}")
    deleted = client.delete_project(project_id)
    if deleted.get("deleted") is not True:
        raise Blocked(f"control {name}: delete did not land: {deleted!r}")

    def both() -> list[Frame] | None:
        frames = [f for f in sub.since(mark) if f.project_id == project_id and f.kind in ("project.created", "project.deleted")]
        return frames if [f.kind for f in frames] == ["project.created", "project.deleted"] else None

    control = await_env(both, bound_s, f"control {name}: project.created then project.deleted on {sub.name}")
    sub.mark_green(f"control {name}")
    latency = control[0].received_at - started
    frames = sub.since(mark)
    first = frames.index(control[0])
    return ControlResult(interior=frames[:first], control_frames=control, latency_s=max(latency, 1e-3))


def run_control_on(subs: list[tuple[Subscriber, int]], client: _ProjectVerbs, name: str,
                   bound_s: float = 10.0) -> list[ControlResult]:
    """One control, observed on several subscribers (each with its own mark).

    Two sequential `run_control` calls would put the first control's frames in
    the second window's interior; this runs the control once.
    """
    started = time.monotonic()
    created = client.create_project(f"LIVENESS-{name}")
    project = created.get("project")
    project_id = project.get("project_id") if isinstance(project, dict) else None
    if not isinstance(project_id, str):
        raise Blocked(f"control {name}: create answered no project: {created!r}")
    if client.delete_project(project_id).get("deleted") is not True:
        raise Blocked(f"control {name}: delete did not land")
    results: list[ControlResult] = []
    for sub, mark in subs:
        def both(sub: Subscriber = sub, mark: int = mark) -> list[Frame] | None:
            frames = [f for f in sub.since(mark) if f.project_id == project_id and f.kind in ("project.created", "project.deleted")]
            return frames if [f.kind for f in frames] == ["project.created", "project.deleted"] else None

        control = await_env(both, bound_s, f"control {name}: both frames on {sub.name}")
        sub.mark_green(f"control {name}")
        frames = sub.since(mark)
        results.append(ControlResult(interior=frames[: frames.index(control[0])], control_frames=control,
                                     latency_s=max(control[0].received_at - started, 1e-3)))
    return results
