"""What a project mutation tells a second client — D7, QA run 4.

**The defect this module is the fix for.** Run 4 enumerated all sixteen
`POST_ROUTES` first, drove the six project mutations against a live server, and
counted the `/api/events` frames a second client received: six 200s and **zero
frames**, with a `publish()` probe on the same reader proving the reader was not
blind. Two real browser contexts against one server showed what that costs — tab
B deletes a project and tab A still lists it, still shows its detail pane, still
offers Edit and Delete, and its delete dialog reads *"this deletes the project
and 0 session records"*. `app.js` had been re-reading the tree on any envelope
the whole time and saying so in a comment: the consumer was waiting, and only the
producer was missing.

**A third module in this family, rather than four lines in each of the other
two.** `tools_*.py` is capped at 450 lines and `tools_projects.py` was already
at 441 before this; but the cap is only the reason it happened now. The reason
it is *right* is that the rule deciding whether anything happened is one rule
for six verbs — the record's own positive key — and a rule spelled six times is
a rule that will be spelled five times after the next edit.

**One announcement, one call site per verb.** `announce` is wrapped around each
handler in `tools_projects.py::build_project_tools` rather than called from
inside the handlers. The handlers stay what the family docstring says they are —
arrange arguments, call one store verb, project the record — and stay callable
by a test that does not care about the ring.

**A refusal announces nothing**, because nothing changed. A producer that fires
on every call teaches the page that an envelope means a change and then lies
about it, and the only thing a stale tab could do with the lie is re-read a tree
that is identical.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from shepherd.core.stream import StreamEvent

__all__ = [
    "PROJECT_EVENT_KINDS",
    "Announce",
    "Publish",
    "announce",
    "created_project_id",
    "drops_every_event",
]

#: Take one event and drop the count. The same seam `compose.py` already hands
#: `register_m3_tools` and the approval store: a capability has no use for how
#: many subscribers took an event, so the `int` `stream.publish` returns is
#: dropped once, at the composition root, rather than by widening this type.
Publish = Callable[[StreamEvent], None]

#: Hand the project id and the record to whoever publishes, and take the record
#: back. `tools_projects_delete.py` is imported *by* `tools_projects.py`, so the
#: announcer reaches it as an argument — the direction that keeps the split
#: acyclic.
Announce = Callable[[str, dict[str, object]], dict[str, object]]


def drops_every_event(event: StreamEvent) -> None:
    """The default injection: a process with no ring, announcing to nobody.

    Unlike `refuses_every_kill` this one is genuinely safe — the worst a lost
    envelope costs is a page that re-reads on the next one — which is why
    `build_project_tools` may default it while `register_project_tools` may not.
    A composition that forgot would be silent in exactly the way D7 was.
    """


#: The kind each tool publishes, and the record key that decides whether it
#: happened at all.
#:
#: `noun.pastverb`, which is the vocabulary already in the ring —
#: `session.spawned`, `session.killed`, `session.interrupted`,
#: `session.classified` — rather than a second one invented for projects. The
#: verbs are the records' **own** positive keys (`created`, `renamed`,
#: `described`, `deleted`, `added`, `removed`), so the name of the event and the
#: field that gates it cannot drift apart.
PROJECT_EVENT_KINDS: Mapping[str, tuple[str, str]] = {
    "create_project": ("project.created", "created"),
    "rename_project": ("project.renamed", "renamed"),
    "set_project_description": ("project.described", "described"),
    "delete_project": ("project.deleted", "deleted"),
    "add_repo": ("project.repo_added", "added"),
    "remove_repo": ("project.repo_removed", "removed"),
}


def announce(
    record: Mapping[str, object],
    *,
    tool: str,
    project_id: str | None,
    publish: Publish,
    now: Callable[[], str],
) -> dict[str, object]:
    """Publish iff the record says something happened, then hand it back.

    **The gate is the record, not the call.** Every verb in this family answers
    a boolean under its own key and a `refused` string when it is `False`, which
    is the one shape `tools_projects.py`'s docstring exists to defend; reusing
    it here means a refusal cannot announce a change that did not happen, and a
    verb that grows a new failure mode is gated by the same key it already sets.

    `project_id` rides in the **payload** rather than on `StreamEvent`, which
    carries only `session_id`: `web/sse.py::envelope` promotes `project_id` out
    of the payload into §12's envelope, so a browser reads it at the top level
    without this layer knowing what SSE is.
    """
    kind, key = PROJECT_EVENT_KINDS[tool]
    if record.get(key) is not True:
        return dict(record)
    publish(
        StreamEvent(
            kind=kind,
            session_id=None,
            payload={"project_id": project_id},
            occurred_at=now(),
        )
    )
    return dict(record)


def created_project_id(record: Mapping[str, object]) -> str | None:
    """The id of the project a create just minted, read off its own answer.

    The other five verbs are told which project they are acting on; this one
    learns it from the record, and `project_workspace`'s consumer-facing key is
    `project_id` (D22) — not `id`, which is the row's. `None` is reachable only
    on a refusal, which never reaches `announce`'s publish anyway.
    """
    project = record.get("project")
    if not isinstance(project, Mapping):
        return None
    found = project.get("project_id")
    return found if isinstance(found, str) else None
