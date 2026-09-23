"""The raw HTTP seam: what a browser and an operator actually have.

Every request carries `Host: 127.0.0.1:{port}` and every POST carries
`Origin: http://127.0.0.1:{port}`, because §13's origin **and** host check runs
before the body is read on every POST and on both streams. A helper that omitted
either would make every mutation in this harness a 403 and the failure would
read as a product refusal.

`raw_post` exists beside `post` so S34 can send a body that is not JSON, an
`Origin` that is not ours, and a path no template matches — the three shapes
that produce the `GENERIC_ERROR` envelope, which until round 5 no scenario had
ever produced at all.
"""

from __future__ import annotations

import http.client
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from shepherd.toolsurface.registry import GENERIC_ERROR

from .constants import CEILING_S
from .runroot import HarnessBlocked

#: D22: a project **is** a workspace, so the consumer-facing key on every
#: projection is `project_id`, never `id`. Spelled once.
PROJECT_KEY = "project_id"

#: `correlation_id` is `uuid4().hex` per request with no injection point, so it
#: is matched as a **pattern** and never as a value.
CORRELATION_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: str

    def json(self) -> dict[str, object]:
        try:
            parsed = json.loads(self.body)
        except json.JSONDecodeError as error:  # pragma: no cover - a real failure prints
            raise AssertionError(f"body is not JSON ({error}): {self.body[:400]!r}") from error
        if not isinstance(parsed, dict):
            raise AssertionError(f"body is not a JSON object: {self.body[:200]!r}")
        return parsed

    def data(self) -> dict[str, object]:
        """The `data` envelope, asserting `ok` on the way through."""
        envelope = self.json()
        if envelope.get("ok") is not True:
            raise AssertionError(f"envelope is not ok: {self.body[:400]!r}")
        payload = envelope.get("data")
        if not isinstance(payload, dict):
            raise AssertionError(f"data is not an object: {self.body[:200]!r}")
        return payload


class Client:
    """One loopback origin, and the headers §13 requires on every call."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.host = f"127.0.0.1:{port}"
        self.origin = f"http://127.0.0.1:{port}"

    # ----- the ordinary front door -----------------------------------------
    def get(self, path: str) -> Response:
        return self.request("GET", path, headers={"Host": self.host})

    def post(self, path: str, body: Mapping[str, object] | None = None) -> Response:
        payload = json.dumps(body if body is not None else {})
        return self.request(
            "POST",
            path,
            body=payload,
            headers={
                "Host": self.host,
                "Origin": self.origin,
                "Content-Type": "application/json",
            },
        )

    # ----- the seam S34 needs ----------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        body: str | bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=CEILING_S)
        try:
            connection.request(method, path, body=body, headers=dict(headers or {}))
            response = connection.getresponse()
            return Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.getheaders()},
                body=response.read().decode("utf-8", "replace"),
            )
        finally:
            connection.close()

    # ----- the projects verbs, spelled once ---------------------------------
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

    def describe_project(self, project_id: str, description: object) -> dict[str, object]:
        body = {} if description is None else {"description": description}
        return self.post(f"/api/projects/{project_id}/description", body).data()

    def add_repo(self, project_id: str, root_path: str) -> dict[str, object]:
        return self.post(f"/api/projects/{project_id}/repos/add", {"root_path": root_path}).data()

    def remove_repo(self, project_id: str, repo_id: str) -> dict[str, object]:
        return self.post(f"/api/projects/{project_id}/repos/remove", {"repo_id": repo_id}).data()

    def projects(self) -> list[dict[str, object]]:
        payload = self.get("/api/projects").data()
        rows = payload.get("projects")
        if not isinstance(rows, list):
            raise AssertionError(f"list_projects did not answer a list: {payload!r}")
        return [row for row in rows if isinstance(row, dict)]

    def project_id_named(self, name: str) -> str:
        found = [row for row in self.projects() if row.get("name") == name]
        if len(found) != 1:
            raise AssertionError(f"expected exactly one project named {name!r}, found {len(found)}")
        return str(found[0][PROJECT_KEY])


def assert_generic_error(response: Response, status: int) -> str:
    """The envelope, exactly, with the id matched as a pattern (B17).

    Returns the correlation id so a caller can print it into the run report.
    """
    assert response.status == status, f"expected {status}, got {response.status}: {response.body!r}"
    envelope = response.json()
    assert envelope.get("ok") is False, envelope
    assert envelope.get("data") is None, envelope
    # **`GENERIC_ERROR` is the constant's NAME; its value is what goes on the
    # wire.** The plan quotes the envelope as `"error":"GENERIC_ERROR"`;
    # `registry.py:69` defines `GENERIC_ERROR = "request failed"`, so that is
    # the literal a client sees. Read from the product rather than re-spelled,
    # which is also what makes this assertion survive a change to the wording.
    assert envelope.get("error") == GENERIC_ERROR, envelope
    correlation = envelope.get("correlation_id")
    assert isinstance(correlation, str) and CORRELATION_ID.match(correlation), envelope
    assert set(envelope) == {"ok", "data", "error", "correlation_id"}, envelope
    return correlation


def await_true(predicate: Callable[[], bool], message: str, ceiling_s: float = CEILING_S) -> None:
    """A bounded predicate wait. Never `sleep N`, and loud when the bound is hit.

    A blown bound is a harness liveness bound — `BLOCKED`, never a product
    `FAIL`: no latency SLO is stated anywhere in the authority documents, so a
    time bound here is this harness's own patience and nothing else.
    """
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise HarnessBlocked(f"bounded wait of {ceiling_s}s expired: {message}")
