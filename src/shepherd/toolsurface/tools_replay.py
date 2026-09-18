"""The `replay` capability (T12, D32, D38.1).

One `ToolDef`, in its own module because T13 owns `tools_m2.py` and two
builders must never share a file — half of M1's blocker file is that lesson.

**`LOCAL_DESTRUCTIVE`, `audiences={HUMAN}`.** It is the one M2 capability that
can overwrite every verdict in the database, and §8's review artefact — the
diff — is only useful if a human read it before `apply` was passed.

**What actually keeps a page from calling it is `web/routes.API_ROUTES`**, the
fixed whitelist of six paths: a path that is not in it is a 404 before
`invoke()` is reached. This docstring used to say "the audience set is the
gate", and that was false — `web/server.py` supplies `Audience.HUMAN` for every
browser request, so `audiences={HUMAN}` excludes nothing the web layer does.
The audience set is still right (it keeps a *session* or the master from
calling it); it is simply not the gate that holds D25's line here, and
`test_replay_is_not_reachable_from_any_api_route` now asserts the one that is.
M4 replaces the whitelist with one policy-table row, per D38.1's precedent for
the installer trio.

**`since` is a date, and the schema cannot say so.** `{"type": "string"}` does
not mean `YYYY-MM-DD`, so the handler turns the engine's refusal into a
`ToolArgumentRefused` — a usage error a consumer can render, rather than a
crash indistinguishable from a missing capability.

**The handler projects plain values** (§13's response rule). A consumer at L5
cannot import `ReplayReport`, so what crosses the seam is a mapping of strings,
integers and floats — including the diff's path, because a report whose
artefact the reader cannot open is the artefact missing.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from shepherd.signals.replay import ReplayReport, SinceIsNotADate, replay
from shepherd.store.db import Store
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
)

__all__ = ["REPLAY_TOOL", "build_replay_tool", "project_report", "register_replay_tool"]

#: One name, spelled here, so the CLI and the registry cannot drift apart.
REPLAY_TOOL = "replay"

_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "since": {"type": "string"},
        "apply": {"type": "boolean"},
    },
}

_DESCRIPTION = (
    "Re-run the current classifier over the stop log, write the before/after"
    " diff, and — only with apply — overwrite the stop columns."
)


def project_report(report: ReplayReport) -> dict[str, object]:
    """§13: named keys of plain values, never a row type reconstructed at L5."""
    return {
        "read": report.read,
        "skipped_malformed": report.skipped_malformed,
        "skipped_version": report.skipped_version,
        "orphaned": report.orphaned,
        "reclassified": report.reclassified,
        "unreadable_files": report.unreadable_files,
        "skipped_undated": report.skipped_undated,
        "classifier_failures": report.classifier_failures,
        "changed": len(report.changes),
        "changes": [
            {
                "session_id": change.session_id,
                "before": change.before,
                "after": change.after,
                "columns": list(change.columns),
            }
            for change in report.changes
        ],
        "unknown_rate_before": report.unknown_rate_before,
        "unknown_rate_after": report.unknown_rate_after,
        "applied": report.applied,
        "diff_path": str(report.diff_path),
    }


def build_replay_tool(store: Store, log_dir: Path, diff_dir: Path) -> ToolDef:
    def handler(args: ToolArgs, ctx: CallerContext) -> object:
        since = args.get("since")
        apply = args.get("apply")
        try:
            report = replay(
                store=store,
                log_dir=log_dir,
                since=since if isinstance(since, str) and since else None,
                apply=apply is True,
                diff_dir=diff_dir,
            )
        except SinceIsNotADate as refusal:
            # A value the schema cannot describe: `{"type": "string"}` cannot
            # say *a date*. Refused as a usage error rather than surfacing as
            # a crash, which a consumer cannot render as advice.
            raise ToolArgumentRefused(str(refusal)) from refusal
        return project_report(report)

    return ToolDef(
        name=REPLAY_TOOL,
        description=_DESCRIPTION,
        input_schema=_SCHEMA,
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        handler=handler,
        audiences=frozenset({Audience.HUMAN}),
    )


def register_replay_tool(store: Store, log_dir: Path, diff_dir: Path) -> None:
    """Called by `compose_tool_surface` at startup, before `freeze_registry()`."""
    register(build_replay_tool(store, log_dir, diff_dir))
