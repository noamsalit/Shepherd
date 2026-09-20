"""§13 on the wire: loopback only, origin-checked, generic errors.

Seam: HTTP, plus a source scan for the one claim a request cannot make — that
**no** configuration widens the bind address. A server answering on 127.0.0.1
proves where it is bound, never that nothing could move it.
"""

from __future__ import annotations

import ast
import json
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from web.conftest import STATIC_ROOT, Client

from shepherd.toolsurface.registry import GENERIC_ERROR
from shepherd.web import routes, server as web_server

WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web"

#: Anything that would let an address in from outside the source.
CONFIG_READERS = frozenset({"getenv", "environ", "environb"})

WIDER_ADDRESSES = ("0.0.0.0", "::", "::0", "0:0:0:0:0:0:0:0")

FOREIGN_ORIGIN = "http://evil.example"


def web_sources() -> list[Path]:
    return sorted(WEB_ROOT.glob("*.py"))


def string_constants(tree: ast.Module) -> set[str]:
    return {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
    }


def identifiers(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


# ----- the bind address (§13) -------------------------------------------------


def test_binds_loopback_only(server: ThreadingHTTPServer) -> None:
    assert server.server_address[0] == "127.0.0.1"
    assert web_server.LOOPBACK_HOST == "127.0.0.1"
    for address in WIDER_ADDRESSES:
        with pytest.raises(web_server.BindAddressRefused):
            web_server.create_server(host=address, port=0, static_root=STATIC_ROOT)
    with pytest.raises(web_server.BindAddressRefused):
        web_server.create_server(host="", port=0, static_root=STATIC_ROOT)


def test_no_bind_address_configuration_exists() -> None:
    """§13: "no config knob to bind wider in v1" — not a default, the value.

    The scan separates string constants from identifiers (r3 F4), so a field
    named `host` can never be read as the literal `0.0.0.0`.
    """
    offenders: list[str] = []
    for path in web_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for literal in sorted(string_constants(tree) & set(WIDER_ADDRESSES)):
            offenders.append(f"{path.name} contains the address {literal!r}")
        for name in sorted(identifiers(tree) & CONFIG_READERS):
            offenders.append(f"{path.name} reads configuration via {name}")
    assert offenders == []
    # self-check: the same scan bites on a module that offers the knob.
    knob = ast.parse("import os\nHOST = os.environ.get('SHEPHERD_HOST', '0.0.0.0')\n")
    assert string_constants(knob) & set(WIDER_ADDRESSES)
    assert identifiers(knob) & CONFIG_READERS


# ----- the origin check (§13) -------------------------------------------------


def test_origin_is_checked(client: Client) -> None:
    """Asserted on the stream handshake, so M4's POSTs inherit it (T15)."""
    refused = client.request(routes.SSE_PATH, headers={"Origin": FOREIGN_ORIGIN})
    assert refused.status == 403
    assert refused.json()["error"] == GENERIC_ERROR

    posted = client.request("/api/fleet", method="POST", headers={"Origin": FOREIGN_ORIGIN})
    assert posted.status == 403

    # The bound origin is accepted — the check is not simply "no POST allowed".
    same_origin = client.request(
        "/api/fleet", method="POST", headers={"Origin": client.origin}
    )
    assert same_origin.status != 403

    # A plain same-origin page read carries no `Origin` and must still work.
    assert client.request("/api/fleet").status == 200


def test_a_forged_host_header_is_refused(client: Client) -> None:
    forged = client.request(routes.SSE_PATH, headers={"Host": "evil.example"})
    assert forged.status == 403


# ----- errors (§13) -----------------------------------------------------------


def test_error_body_is_generic_with_correlation_id(client: Client) -> None:
    missing = client.request("/api/nope")
    assert missing.status == 404
    body = missing.json()
    assert set(body) == {"ok", "data", "error", "correlation_id"}
    assert body["ok"] is False
    assert body["error"] == GENERIC_ERROR
    correlation_id = body["correlation_id"]
    assert isinstance(correlation_id, str) and correlation_id != ""

    refused = client.request("/api/sessions?state=not-a-state")
    assert refused.status == 400
    assert refused.json()["error"] == GENERIC_ERROR

    text = json.dumps(body) + refused.body
    for leak in ("Traceback", "/root/", "site-packages", "shepherd/store", "sqlite"):
        assert leak not in text

    # A second request gets its own id, so a report names one request.
    other = client.request("/api/nope").json()
    assert other["correlation_id"] != correlation_id


def test_static_traversal_is_refused(client: Client) -> None:
    for path in ("/static/../../../etc/passwd", "/static/../server.py", "/static/"):
        assert client.request(path).status == 404
