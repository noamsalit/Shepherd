"""The route table: a path is a tool name and an argument mapping, nothing else.

This module is the whole of `web/`'s knowledge about the system. A path names a
capability in L4's registry (D32) and the arguments it may carry; resolving one
produces a `Resolved`, and `server.py` hands that straight to `invoke()`. There
is no handler with a body, which is what makes "`web/` reaches the system only
through `toolsurface`" (D19, D35) structural rather than a habit — a page that
wants a datum the registry does not hold has nowhere here to put the reach.

Two rules the table encodes:

* **Every query parameter is declared.** An undeclared one is dropped rather
  than forwarded, so a caller cannot smuggle an argument past `invoke()`'s
  schema check into a handler that happens to accept it (D53).
* **No polling endpoint.** §12 has one liveness path, `SSE_PATH`, and it is
  deliberately absent from `API_ROUTES`: liveness is a stream, not a route a
  page can learn to call on a timer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: §12: the one stream. It is not in `API_ROUTES` because it is not a call.
SSE_PATH = "/api/events"

SESSION_ID = "session_id"

#: path template -> tool name. The templates are the public shape of the API.
API_ROUTES: Mapping[str, str] = {
    "/api/fleet": "fleet_summary",
    "/api/fleet/tree": "fleet_tree",
    "/api/projects": "list_projects",
    "/api/sessions": "list_sessions",
    "/api/sessions/{session_id}": "get_session",
    "/api/sessions/{session_id}/subagents": "list_subagents",
    "/api/sessions/{session_id}/output": "get_session_output",
    "/api/mailbox": "list_mailbox",
    # M4's chat page (T24). Three reads, and every one of them is a tool the
    # registry already declares: the page is a path->name map like the rest, and
    # `web/` gained no knowledge of what any of them does.
    #
    # `/api/autonomy` is a **read** as well as a write because §12 says the
    # toggle is "visible at all times … you should never have to remember which
    # level you are on", and nothing else on the wire carries the level. It is
    # recorded as a deviation from T24's Allowed Scope in
    # `docs/plans/m4-blockers/t24.md` §T24-1 rather than slipped in.
    "/api/approvals": "list_approvals",
    "/api/audit": "get_audit_log",
    "/api/autonomy": "get_autonomy_level",
}

#: path template -> the query parameters it forwards. Anything else is dropped.
QUERY_ARGS: Mapping[str, tuple[str, ...]] = {
    "/api/sessions": ("project_id", "state"),
    "/api/sessions/{session_id}/output": ("scrollback",),
    "/api/mailbox": ("session_id",),
}

#: M3's mutations (T18). The **first** POST routes there have ever been: M1 and
#: M2 were read-only, and §13's origin check was proved on the stream handshake
#: precisely so that these inherit it rather than write it under deadline.
#:
#: `rename_session` is here and is registered by **T20**, which produces its
#: handler and depends on this task. A route is a path->name table and the name
#: is resolved through `invoke()` at call time, so a route may be declared
#: before its tool exists; T23's
#: `test_every_post_route_resolves_to_a_registered_tool` is what catches the
#: case where it never is.
POST_ROUTES: Mapping[str, str] = {
    "/api/sessions": "spawn_session",
    "/api/sessions/{session_id}/send": "send_to_session",
    "/api/sessions/{session_id}/ask": "ask_session",
    "/api/sessions/{session_id}/interrupt": "interrupt_session",
    "/api/sessions/{session_id}/kill": "kill_session",
    "/api/sessions/{session_id}/rename": "rename_session",
    "/api/sessions/{session_id}/permission": "answer_permission",
    # M4's three mutations (T24). `decide_approval` is the only one that takes a
    # path parameter, and it takes the **approval** id: a card is decided by its
    # own identity, never by position in a list that may have moved.
    "/api/master/send": "master_send",
    "/api/approvals/{approval_id}": "decide_approval",
    "/api/autonomy": "set_autonomy_level",
}

#: path template -> the **body** fields it forwards, and the same rule as
#: `QUERY_ARGS`: anything undeclared is dropped rather than forwarded, so a
#: caller cannot smuggle an argument past `invoke()`'s schema check into a
#: handler that happens to accept it (D53). A path parameter always wins — a
#: body claiming a different `session_id` than the URL cannot move the target.
BODY_ARGS: Mapping[str, tuple[str, ...]] = {
    "/api/sessions": (
        "workspace_id",
        "cwd",
        "brief",
        "title",
        "model",
        "effort",
        "parent_session_id",
        "ephemeral",
    ),
    "/api/sessions/{session_id}/send": ("body", "idempotency_key", "origin"),
    "/api/sessions/{session_id}/ask": ("question",),
    "/api/sessions/{session_id}/interrupt": (),
    "/api/sessions/{session_id}/kill": (),
    "/api/sessions/{session_id}/rename": ("title",),
    "/api/sessions/{session_id}/permission": ("choice",),
    "/api/master/send": ("text",),
    # `approval_id` is deliberately absent: it is the path parameter, and the
    # merge order means a body claiming another card could not move the target
    # even if it were declared.
    "/api/approvals/{approval_id}": ("choice",),
    "/api/autonomy": ("level",),
}

#: §12's page 3. Not in `API_ROUTES`: an upgrade is not a call, exactly as
#: `SSE_PATH` is not one.
TERMINAL_WS_PATH = "/api/sessions/{session_id}/terminal"


@dataclass(frozen=True)
class Resolved:
    """One call, ready for `invoke()`: a tool name and its arguments."""

    tool: str
    args: Mapping[str, object]


def _segments(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split("/") if part != "")


def _match(template: str, path: str) -> dict[str, object] | None:
    """The path parameters `template` captures from `path`, or `None`."""
    wanted, given = _segments(template), _segments(path)
    if len(wanted) != len(given):
        return None
    captured: dict[str, object] = {}
    for expected, actual in zip(wanted, given, strict=True):
        if expected.startswith("{") and expected.endswith("}"):
            if actual == "":
                return None
            captured[expected[1:-1]] = actual
        elif expected != actual:
            return None
    return captured


def _ordered(table: Mapping[str, str]) -> list[str]:
    """Static templates first, so `/api/sessions` is never read as a session id."""
    return sorted(table, key=lambda item: ("{" in item, item))


def resolve(path: str, query: Mapping[str, list[str]]) -> Resolved | None:
    """The tool a GET path names, with its declared arguments — or `None` (404)."""
    for template in _ordered(API_ROUTES):
        captured = _match(template, path)
        if captured is None:
            continue
        for name in QUERY_ARGS.get(template, ()):
            values = query.get(name)
            if values:
                captured[name] = values[0]
        return Resolved(tool=API_ROUTES[template], args=captured)
    return None


def resolve_post(path: str, body: Mapping[str, object]) -> Resolved | None:
    """The tool a POST path names, with its declared body — or `None` (404).

    The declared-field rule is the same one `QUERY_ARGS` encodes and it matters
    more here, because a body is bigger and a mutation is what is on the other
    end: an undeclared field is **dropped**, never forwarded. The path parameter
    is applied last, so a body carrying its own `session_id` cannot redirect a
    kill at a session the URL did not name.
    """
    for template in _ordered(POST_ROUTES):
        captured = _match(template, path)
        if captured is None:
            continue
        args: dict[str, object] = {
            name: body[name] for name in BODY_ARGS.get(template, ()) if name in body
        }
        args.update(captured)
        return Resolved(tool=POST_ROUTES[template], args=args)
    return None


def resolve_terminal(path: str) -> str | None:
    """The session id `TERMINAL_WS_PATH` names, or `None` — the WS upgrade's
    one route. It is resolved apart from `API_ROUTES` because an upgrade is not
    a call and must not be reachable as one."""
    captured = _match(TERMINAL_WS_PATH, path)
    if captured is None:
        return None
    found = captured.get(SESSION_ID)
    return found if isinstance(found, str) else None
