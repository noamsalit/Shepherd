"""T20's rename capability, registered where T23 could fit it (leftover 1).

The plan puts `register_rename_tool` in `toolsurface/tools_m3.py`. That module
ships at **447 lines against its own 450-line guard**
(`test_the_three_modules_are_each_under_the_cap`), and the handler, its
projection and its schema are ~110 — so appending it would have meant editing a
size assertion to make a plan item fit, which is the K11/K17 failure T23 is most
exposed to. This repo has answered that collision with a split ten times now
(`rows.py`, `stops.py`, `signals/fields.py`, `reads.py`, `writes.py`,
`admission.py`, `tools_messaging.py`, `tools_terminal.py`, …); this is the same
trade, recorded in `docs/plans/2026-09-17-m3-BLOCKERS.md` rather than taken
quietly. **The plan's sentence is false of this tree, and the guard is intact.**

What the plan's sentence was protecting is unchanged: the tool is **not** in
`register_m3_tools` (double registration would be refused at freeze time,
ADR-7), its `blast_class` is `local_write`, its audiences are `(MASTER, HUMAN)`,
and `tests/toolsurface/test_tools_m3.py` holds both halves.

**Two injections beyond the plan's `(store, runner, now)`**, for T18's reason:
`rename_session` takes the **engine's** config directory (T20 made it required
so no default can reach the user's real `~/.claude`) and the capability record
carrying D29's ceiling. The record arrives as a **value**, never read here:
`capabilities(pane_driver_available=)` has one production caller per
`tests/boundaries/test_capability_degrade.py`, and this layer is not it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.runner import EngineCapabilities
from shepherd.orchestration.rename import RenameOutcome, rename_session
from shepherd.runner.base import Runner
from shepherd.store.db import Store
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef, arg_str

__all__ = ["RENAME_TOOL_NAME", "project_rename", "register_rename_tool", "rename"]

Clock = Callable[[], str]

#: The name `web/routes.py::POST_ROUTES` resolves `/api/sessions/{id}/rename` to.
RENAME_TOOL_NAME = "rename_session"

_MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})

def project_rename(outcome: RenameOutcome | None, session_id: str) -> dict[str, object]:
    """One shape for both answers, the way `project_spawn` carries a refusal.

    `local_only` is §12's marker as a boolean, and it is `True` on a rename that
    did not happen at all: "the engine has not confirmed this title" is the
    truthful reading of a session nobody renamed.
    """
    if outcome is None:
        return {
            "session_id": session_id,
            "renamed": False,
            "title": None,
            "source": None,
            "synced_at": None,
            "local_only": True,
            "reason": f"there is no session {session_id!r} to rename",
        }
    return {
        "session_id": session_id,
        "renamed": True,
        "title": outcome.title,
        "source": str(outcome.source),
        "synced_at": outcome.synced_at,
        "local_only": outcome.local_only,
        "reason": None,
    }


def rename(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    config_dir: Path,
    capabilities: EngineCapabilities,
    session_id: str,
    title: str,
) -> dict[str, object]:
    """D29's rename, composed: the ratchet is `store.apply_title`'s and the
    ceiling predicate is `rename_session`'s. Nothing is re-decided here.

    The row is read with `get_session` rather than `get_owned_session`: the
    **local** half of a rename applies to an attached session too, and
    `rename_session` is what refuses to drive an engine we do not own.
    """
    row = store.get_session(session_id)
    if row is None:
        return project_rename(None, session_id)
    return project_rename(
        rename_session(
            store=store,
            runner=runner,
            handle=row.runner_handle,
            session_id=session_id,
            title=title,
            now=now,
            capabilities=capabilities,
            ownership=row.ownership,
            config_dir=config_dir,
        ),
        session_id,
    )


def register_rename_tool(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    config_dir: Path,
    capabilities: EngineCapabilities,
) -> None:
    """T20's capability, registered where its handler is written (revision 2).

    **Two injections beyond the plan's `(store, runner, now)`**, both required
    for the same reason T18's twelve are: `rename_session` takes the engine's
    config directory (T20 made it required so no default can reach the user's
    real `~/.claude`) and the capability record that carries D29's ceiling. The
    record arrives as a **value** because `capabilities(pane_driver_available=)`
    has one production caller and it is not this layer (T10-R2).
    """
    register(
        ToolDef(
            name=RENAME_TOOL_NAME,
            description="Set a session's title. Local until the engine confirms it (D29).",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["session_id", "title"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: rename(
                store=store,
                runner=runner,
                now=now,
                config_dir=config_dir,
                capabilities=capabilities,
                session_id=arg_str(args, "session_id"),
                title=arg_str(args, "title"),
            ),
            audiences=_MASTER_AND_HUMAN,
        )
    )
