"""The raw HTTP seam: loopback only, same-origin by default, and two refusals.

Every request carries `Host: 127.0.0.1:<port>`; every POST carries a same-origin
`Origin`, because the product's origin **and** host check runs on every POST
and stream (spec S1, S2). A helper that omitted either would turn every
mutation into a 403 that reads as a product refusal.

Two refusals are made here, by construction, and counted:

* **the forbidden port** (`paths.FORBIDDEN_PORT`, R1, the user's WatchTower daemon) — never connected to. Each
  refusal is appended to the run's `port-refusals.log`; Z3 asserts it is empty.
* **`POST /api/master/send`** outside a caller that opts in (env-plan §2): a
  stray send in a non-live lane would start a real engine (qa5 S28's defect).
"""

from __future__ import annotations

import http.client
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from shepherd.toolsurface.registry import GENERIC_ERROR

from . import paths

#: `correlation_id` has no injection point, so it is matched as a pattern.
CORRELATION_ID = re.compile(r"^[0-9a-f]{32}$")
ENVELOPE_KEYS = frozenset({"ok", "data", "error", "correlation_id"})
MASTER_SEND_PATH = "/api/master/send"
DEFAULT_TIMEOUT_S = 10.0


class RefusedByHarness(RuntimeError):
    """A request this harness will not send (the forbidden port, or an unapproved master send)."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes
    elapsed_s: float

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> dict[str, object]:
        try:
            parsed: object = json.loads(self.text)
        except json.JSONDecodeError as error:
            raise AssertionError(f"body is not JSON ({error}): {self.text[:400]!r}") from error
        if not isinstance(parsed, dict):
            raise AssertionError(f"body is not a JSON object: {self.text[:200]!r}")
        return {str(key): value for key, value in parsed.items()}

    def data(self) -> dict[str, object]:
        envelope = self.json()
        if envelope.get("ok") is not True:
            raise AssertionError(f"envelope is not ok (HTTP {self.status}): {self.text[:400]!r}")
        payload = envelope.get("data")
        if not isinstance(payload, dict):
            raise AssertionError(f"data is not an object: {self.text[:200]!r}")
        return {str(key): value for key, value in payload.items()}


class Client:
    """One loopback daemon. Refuses the forbidden port and (unless allowed) the master send."""

    def __init__(self, port: int, *, refusals_log: Path | None = None, allow_master_send: bool = False) -> None:
        if port == paths.FORBIDDEN_PORT:
            if refusals_log is not None:
                with open(refusals_log, "a", encoding="utf-8") as handle:
                    handle.write(f"{time.time()} refused a client for port {port}\n")
            raise RefusedByHarness(f"port {port} belongs to the user's daemon (R1); never connected")
        self.port = port
        self.host = f"127.0.0.1:{port}"
        self.origin = f"http://127.0.0.1:{port}"
        self.allow_master_send = allow_master_send

    def get(self, path: str, headers: Mapping[str, str] | None = None) -> Response:
        merged = {"Host": self.host, **(headers or {})}
        return self.request("GET", path, headers=merged)

    def post(self, path: str, body: Mapping[str, object] | None = None, headers: Mapping[str, str] | None = None) -> Response:
        payload = json.dumps(dict(body) if body is not None else {})
        merged = {
            "Host": self.host,
            "Origin": self.origin,
            "Content-Type": "application/json",
            **(headers or {}),
        }
        return self.request("POST", path, body=payload.encode("utf-8"), headers=merged)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        skip_default_headers: bool = False,
    ) -> Response:
        if method == "POST" and path.split("?")[0] == MASTER_SEND_PATH and not self.allow_master_send:
            raise RefusedByHarness(
                "POST /api/master/send refused: a non-live lane must never start a real master"
            )
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout_s)
        started = time.monotonic()
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            sent = {key.lower() for key in (headers or {})}
            for key, value in (headers or {}).items():
                connection.putheader(key, value)
            if not skip_default_headers and "host" not in sent:
                connection.putheader("Host", self.host)
            if body is not None and "content-length" not in sent:
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            raw = response.read()
            return Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.getheaders()},
                body=raw,
                elapsed_s=time.monotonic() - started,
            )
        finally:
            connection.close()

    # ----- the projects verbs, spelled once --------------------------------
    def create_project(self, name: str, description: str | None = None) -> dict[str, object]:
        body: dict[str, object] = {"name": name}
        if description is not None:
            body["description"] = description
        return self.post("/api/projects", body).data()

    def delete_project(self, project_id: str, on_running: str | None = None) -> dict[str, object]:
        body: dict[str, object] = {} if on_running is None else {"on_running": on_running}
        return self.post(f"/api/projects/{project_id}/delete", body).data()

    def rename_project(self, project_id: str, name: str) -> dict[str, object]:
        return self.post(f"/api/projects/{project_id}/rename", {"name": name}).data()

    def describe_project(self, project_id: str, description: object | None) -> dict[str, object]:
        body: dict[str, object] = {} if description is None else {"description": description}
        return self.post(f"/api/projects/{project_id}/description", body).data()

    def add_repo(self, project_id: str, root_path: str) -> dict[str, object]:
        return self.post(f"/api/projects/{project_id}/repos/add", {"root_path": root_path}).data()

    def remove_repo(self, project_id: str, repo_id: str) -> dict[str, object]:
        return self.post(f"/api/projects/{project_id}/repos/remove", {"repo_id": repo_id}).data()

    def fleet(self) -> dict[str, object]:
        return self.get("/api/fleet").data()

    def fleet_tree(self) -> dict[str, object]:
        return self.get("/api/fleet/tree").data()

    def session(self, session_id: str) -> dict[str, object]:
        return self.get(f"/api/sessions/{session_id}").data()

    def projects(self) -> list[dict[str, object]]:
        payload = self.get("/api/projects").data()
        rows = payload.get("projects")
        if not isinstance(rows, list):
            raise AssertionError(f"list_projects did not answer a list: {payload!r}")
        return [as_dict(row) for row in rows if isinstance(row, dict)]


def as_dict(value: object) -> dict[str, object]:
    """Narrow a decoded JSON value to a `dict[str, object]`, or raise."""
    if not isinstance(value, dict):
        raise AssertionError(f"expected a JSON object, got {type(value).__name__}: {value!r}"[:300])
    return {str(key): item for key, item in value.items()}


def as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError(f"expected a JSON array, got {type(value).__name__}: {value!r}"[:300])
    return list(value)


def generic_error_problems(response: Response, status: int) -> list[str]:
    """What is wrong with `response` as the generic refusal envelope (empty = right)."""
    problems: list[str] = []
    if response.status != status:
        problems.append(f"status {response.status} != {status}")
    try:
        envelope = response.json()
    except AssertionError as error:
        return [*problems, str(error)]
    if set(envelope) != ENVELOPE_KEYS:
        problems.append(f"keys {sorted(envelope)}")
    if envelope.get("ok") is not False:
        problems.append(f"ok={envelope.get('ok')!r}")
    if envelope.get("data") is not None:
        problems.append("data is not null")
    if envelope.get("error") != GENERIC_ERROR:
        problems.append(f"error={envelope.get('error')!r} != {GENERIC_ERROR!r}")
    correlation = envelope.get("correlation_id")
    if not (isinstance(correlation, str) and CORRELATION_ID.match(correlation)):
        problems.append(f"correlation_id={correlation!r}")
    return problems
