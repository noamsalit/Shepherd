"""§3a — the SSE client rig, one owner, for the whole run.

**This module exists because round 1 did not have one.** The clients were
attached inside a scenario, left attached "for wave 2", and nothing said who
owned them after that — so eight scenarios counted frames against a rig with no
stated owner, and one of them asserted *zero frames on the second SSE client* at
a point in bring-up where **no SSE client had been attached at all**.

Three rules this module makes mechanical:

1. **Two clients, A and B**, attached once by the session fixture and never
   re-attached by a scenario. `sse.py:124-128` records an unclosed
   tail-subscription window; re-attaching is the one operation that can walk into
   it.
2. **A zero frame count means nothing without an in-scenario liveness control.**
   `Rig.control()` creates and deletes a throwaway project, which is **two**
   frames — `project.created` then `project.deleted` — because `announce()`
   publishes iff a record's own positive key is True. A strictly-positive,
   unbounded-above expectation is self-controlling and needs none; a zero, a
   conditional zero, or an exact count does.
3. **The counted window is named by its two endpoints, both control frames.** It
   opens on the *previous* control's `project.deleted` and closes on *this*
   control's `project.deleted`. The four control frames at the ends are outside
   it and are asserted separately, by kind and by order.

**The control's footprint** (§3a): it runs **last** in a scenario body, it costs
two frames, **two gated invokes — so two audit records** — and one workspace row
created and then destroyed, i.e. net zero surviving rows. Frame counts exclude
its two frames; appended-record counts are taken to the moment before it runs;
surviving-row counts are read after it and are net of it. Without that rule
S26's "exactly three new JSONL records" and S33's "exactly one new workspace row"
are both wrong by the control's own footprint.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from .constants import CEILING_S, FRAME_CEILING_S
from .runroot import HarnessBlocked
from .wire import PROJECT_KEY, Client, await_true

CREATED, DELETED = "project.created", "project.deleted"

#: Bounded, and above the socket timeout so the bound is not the thing that
#: expires first. A teardown that ignores its own result leaks silently.
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
    raw_fields: dict[str, str]

    @property
    def has_event_name(self) -> bool:
        return "event" in self.raw_fields


class Subscriber:
    """One `GET /api/events` connection, read on a thread.

    Nothing here polls: the socket is opened once and frames arrive when the
    server pushes them. `: open` and `: keep-alive` are **comment lines** and are
    recorded separately from frames, so "no frame arrived" stays distinguishable
    from "the socket is alive" — which is the distinction every zero in this
    plan is read against.
    """

    def __init__(self, name: str, port: int, last_event_id: str | None = None) -> None:
        self.name = name
        self.frames: list[Frame] = []
        self.comments: list[str] = []
        self.parse_failures: list[str] = []
        self.reader_fault: str | None = None
        self._closing = False
        self._lock = threading.Lock()
        headers = {"Host": f"127.0.0.1:{port}"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        # **A blocking read, woken by `shutdown()`.** `sse.py`'s
        # Three attempts, and the first two are recorded because each failed in
        # a way that would have been invisible:
        #
        # 1. a 10 s socket timeout — shorter than `sse.py`'s 15 s keep-alive
        #    cadence, so the reader died in the first quiet stretch and every
        #    later "zero frames" assertion would have passed on a dead socket.
        #    §3a's control is what caught it: client A stopped at seq 31.
        # 2. a timeout used as a *poll* interval — once a `socket.makefile`
        #    buffered reader times out, CPython marks it unusable
        #    (`OSError: cannot read from timed out object`), so the next read
        #    raised rather than resuming.
        #
        # So the socket blocks, and `close()` wakes it with `shutdown()` on a
        # handle captured **here** — `HTTPConnection.sock` is not guaranteed to
        # still be the reader's socket by the time teardown runs.
        self._connection = http.client.HTTPConnection("127.0.0.1", port, timeout=None)
        self._connection.request("GET", "/api/events", headers=headers)
        # Captured **before** `getresponse()`. An SSE response carries no
        # `Content-Length`, so `will_close` is true and `getresponse()` sets
        # `HTTPConnection.sock` to `None` while handing ownership of the socket
        # to `response.fp`. Reading `.sock` afterwards yields `None`, and the
        # teardown shutdown then wakes nothing — which is exactly why the join
        # timed out twice before this line existed.
        self._socket = self._connection.sock
        self._response = self._connection.getresponse()
        self.status = self._response.status
        self.headers = {key.lower(): value for key, value in self._response.getheaders()}
        if self.status != 200:
            self._connection.close()
            raise HarnessBlocked(f"{name}: the stream answered {self.status}")
        self._thread = threading.Thread(target=self._read, name=f"sse-{name}", daemon=True)
        self._thread.start()

    # ----- reading ----------------------------------------------------------
    def _read(self) -> None:
        """Read until EOF. An exit this harness did not ask for is a **fault**.

        A reader that returns quietly is indistinguishable from a socket that
        went quiet, and every zero in this plan would then pass for the wrong
        reason. Only a close *we* initiated is silent; anything else is recorded
        and raised by the next assertion that reads the tape.
        """
        try:
            self._read_frames()
        except OSError as error:
            if not self._closing:
                with self._lock:
                    self.reader_fault = f"reader died mid-run: {error!r}"
            return
        if not self._closing:
            with self._lock:
                self.reader_fault = "reader saw EOF mid-run: the server closed the stream"

    def _read_frames(self) -> None:
        current: dict[str, str] = {}
        while True:
            raw = self._response.fp.readline() if self._response.fp else b""
            if raw == b"":
                return
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                if current:
                    self._append(current)
                    current = {}
                continue
            if line.startswith(":"):
                with self._lock:
                    self.comments.append(line)
                continue
            field_name, _, value = line.partition(":")
            current[field_name] = value.lstrip(" ")

    def _append(self, fields: dict[str, str]) -> None:
        try:
            body = json.loads(fields["data"])
            frame = Frame(
                seq=int(fields["id"]),
                kind=str(body["type"]),
                project_id=body.get("project_id"),
                session_id=body.get("session_id"),
                at=str(body.get("at", "")),
                data=dict(body.get("data", {})),
                raw_fields=dict(fields),
            )
        except (KeyError, ValueError, TypeError) as error:
            with self._lock:
                self.parse_failures.append(f"{error}: {fields!r}")
            return
        with self._lock:
            self.frames.append(frame)

    # ----- reading the accumulated tape ------------------------------------
    def snapshot(self) -> list[Frame]:
        with self._lock:
            if self.reader_fault is not None:
                raise HarnessBlocked(f"{self.name}: {self.reader_fault}")
            return list(self.frames)

    def count(self) -> int:
        return len(self.snapshot())

    def close(self) -> None:
        """Close the socket and **join** the reader.

        `HTTPConnection.close()` alone is not enough: the reader is parked in
        `readline()` on the socket, and closing the handle from another thread
        does not wake it — it waits out the socket timeout. `shutdown(SHUT_RDWR)`
        is what delivers the EOF the reader is waiting for, so the join is a
        real join and not a bound this harness quietly exceeds. A reader that
        never joined would keep a server thread busy through `controld.stop`.
        """
        self._closing = True
        socket_handle = self._socket
        if socket_handle is not None:
            try:
                socket_handle.shutdown(socket.SHUT_RDWR)
            except OSError:
                # Already half-closed by the server. The close below still runs.
                pass
        self._connection.close()
        self._thread.join(timeout=JOIN_CEILING_S)
        if self._thread.is_alive():
            raise HarnessBlocked(
                f"{self.name}: the reader thread did not join in {JOIN_CEILING_S}s"
            )


@dataclass
class Window:
    """One counted window: the interior, and the control frames that bound it."""

    scenario: str
    interior: dict[str, list[Frame]] = field(default_factory=dict)
    control: dict[str, list[Frame]] = field(default_factory=dict)

    def kinds(self, client: str = "B", prefix: str | None = None) -> list[str]:
        """The interior's kinds, optionally narrowed to one event family.

        **`prefix` exists because the ring is not only projects.** A kill
        publishes `session.killed` on the same stream, so a scenario that reads
        its window as a bare list is asserting about every event the product
        emits, not about the property it is testing. Narrowing is stated at the
        call site so the reader can see which family the count is over.
        """
        frames = self.interior[client]
        if prefix is not None:
            frames = [frame for frame in frames if frame.kind.startswith(prefix)]
        return [frame.kind for frame in frames]

    def assert_empty(self, reason: str, prefix: str | None = None) -> None:
        for name in self.interior:
            seen = self.kinds(name, prefix)
            assert seen == [], f"{self.scenario}: client {name} saw {seen} — {reason}"

    def assert_kinds(
        self, expected: Sequence[str], client: str = "B", prefix: str | None = None
    ) -> None:
        seen = self.kinds(client, prefix)
        assert seen == list(expected), (
            f"{self.scenario}: client {client} interior was {seen}, expected {list(expected)}"
        )


class Rig:
    """The two clients and the cursor that defines every counted window."""

    def __init__(self, client: Client, port: int) -> None:
        self._client = client
        self.a = Subscriber("A", port)
        self.b = Subscriber("B", port)
        self._cursor = {"A": 0, "B": 0}
        self._controls_run: list[str] = []

    @property
    def subscribers(self) -> dict[str, Subscriber]:
        return {"A": self.a, "B": self.b}

    # ----- the control ------------------------------------------------------
    def control(self, scenario: str, since: dict[str, int] | None = None) -> Window:
        """Drive the known-good control and close this scenario's window.

        **`since` narrows the window's opening end, and it is not optional in
        practice.** §3a defines the window as opening on the *previous* control's
        `project.deleted` frame. That definition is exact only while every
        scenario runs a control — and cell (ii) scenarios deliberately do not,
        because a strictly-positive count is self-controlling. S4 sits between
        S0 and S5 and legitimately emits six frames, so S5's literal §3a window
        can never be the zero its own Queue row asserts. Passing the scenario's
        own opening mark keeps the **closing** endpoint a control frame — which
        is what makes a zero meaningful — and makes the opening endpoint the
        scenario itself rather than an unrelated predecessor. Recorded as a
        finding against §3a rather than resolved silently.

        Creates `LIVENESS-<scenario>`, asserts `project.created` at both clients,
        deletes it, asserts `project.deleted` at both. The project has no
        sessions, so the delete lands on its **first** call. Returns the window
        whose interior is everything that arrived since the previous control's
        `project.deleted`.
        """
        name = f"LIVENESS-{scenario}"
        # The mark is taken **before** the create, not after. A mark taken after
        # the POST returns can already contain the frame it is meant to bound —
        # the publish is synchronous inside the handler and the reader thread is
        # free-running — and the search window would then be empty while the
        # frame sat just behind it. That is a race that fails a healthy socket.
        opened = {label: sub.count() for label, sub in self.subscribers.items()}
        floor = dict(self._cursor if since is None else since)
        created = self._client.create_project(name)
        project = created.get("project")
        if not isinstance(project, dict):
            raise HarnessBlocked(f"{scenario}: the control's create answered no project: {created!r}")
        project_id = str(project[PROJECT_KEY])
        self._await_frame(CREATED, project_id, opened)
        deleted = self._client.delete_project(project_id)
        if deleted.get("deleted") is not True:
            raise HarnessBlocked(
                f"{scenario}: the control's delete did not land: {deleted!r}. "
                "A control that left a row behind is a failure of the control, not a "
                "product finding."
            )
        self._await_frame(DELETED, project_id, opened)

        window = Window(scenario=scenario)
        for label, sub in self.subscribers.items():
            frames = sub.snapshot()
            control_frames = [
                frame
                for frame in frames[opened[label] :]
                if frame.project_id == project_id and frame.kind in (CREATED, DELETED)
            ]
            if [frame.kind for frame in control_frames] != [CREATED, DELETED]:
                raise HarnessBlocked(
                    f"{scenario}: client {label} did not see the control's two frames in "
                    f"order; saw {[f.kind for f in control_frames]}. A dead socket must "
                    "never be able to pass a zero."
                )
            first_control_index = frames.index(control_frames[0], opened[label])
            window.interior[label] = frames[floor[label] : first_control_index]
            window.control[label] = control_frames
            self._cursor[label] = len(frames)
        self._controls_run.append(scenario)
        return window

    def _await_frame(self, kind: str, project_id: str, opened: dict[str, int]) -> None:
        for label, sub in self.subscribers.items():
            start = opened[label]
            await_true(
                lambda sub=sub, start=start: any(
                    frame.kind == kind and frame.project_id == project_id
                    for frame in sub.snapshot()[start:]
                ),
                f"client {label} never received {kind} for {project_id}; "
                f"frames={[(f.seq, f.kind, f.project_id) for f in sub.snapshot()]}, "
                f"comments={sub.comments}, parse_failures={sub.parse_failures}",
                FRAME_CEILING_S,
            )

    # ----- windows for the self-controlling cell ----------------------------
    def open_window(self) -> dict[str, int]:
        """A mark for a strictly-positive, unbounded-above expectation.

        Cell (ii) of §0 rule 4: a dead socket delivers nothing and the row fails
        on its own, so these scenarios take a mark and need no control.
        """
        return {label: sub.count() for label, sub in self.subscribers.items()}

    def since(self, mark: dict[str, int], client: str = "B") -> list[Frame]:
        return self.subscribers[client].snapshot()[mark[client] :]

    def await_kind(self, mark: dict[str, int], kind: str, client: str = "B") -> Frame:
        await_true(
            lambda: any(frame.kind == kind for frame in self.since(mark, client)),
            f"client {client} never received a {kind} frame",
            FRAME_CEILING_S,
        )
        return next(frame for frame in self.since(mark, client) if frame.kind == kind)

    def await_count(self, mark: dict[str, int], n: int, client: str = "B") -> list[Frame]:
        await_true(
            lambda: len(self.since(mark, client)) >= n,
            f"client {client} received {len(self.since(mark, client))} frames, expected {n}",
            FRAME_CEILING_S,
        )
        return self.since(mark, client)

    # ----- liveness between waves ------------------------------------------
    def reprove(self, wave: str) -> Window:
        """Re-run the control at a wave's own start — a rig that died between
        waves is caught here rather than inside the first scenario that counts."""
        return self.control(f"WAVE{wave}")

    def close(self) -> None:
        errors: list[str] = []
        for sub in (self.a, self.b):
            try:
                sub.close()
            except HarnessBlocked as error:
                errors.append(str(error))
        if errors:
            raise HarnessBlocked("; ".join(errors))
