"""Planted violation, frozen as a fixture: a new tool, in a new module, `SESSION`.

The M4 remediation measured clause 14's residue by planting a third `SESSION`
audience one tool per row and running the **whole default suite** each time. On
`list_subagents`, on `engine_version` and on a terminal snapshot the suite stayed
green at 1779 passed: a `SESSION` audience is caught **by rule** only on a
destructive M3 tool and **by name** only where some test pins that tool's
audiences with an equality. This file is the case with neither — a module no
shipped rule has heard of, holding a tool nobody has named.

It matters because `invoke()` checks `ctx.audience` and then discards the caller,
so no handler can scope a request to its caller. That is why Track C was cut, and
a new tool acquiring the `SESSION` audience unnoticed is the same hole widening.

The second tool is here on purpose: a rule asserted merely *non-empty* over a
fixture cannot tell "it read the audiences" from "it reported everything", and
the test writes out both reported sets.

Inert. Nothing imports this module; both constructions sit inside a function that
is never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

from shepherd.toolsurface.types import Audience, BlastClass, ToolDef

#: Spelled as set literals rather than `frozenset(...)` calls so the module body
#: performs **no call at all** — `test_the_fixtures_are_inert`'s first property,
#: and the one the 2026-09-17 reboot is the price of. The rule under test reads
#: both spellings.
_EVERY_AUDIENCE = {Audience.MASTER, Audience.SESSION, Audience.HUMAN}
_HUMAN_ONLY = {Audience.HUMAN}


def build_tools() -> tuple[ToolDef, ToolDef]:
    return (
        ToolDef(
            name="snapshot_everything",
            description="read every pane in the fleet",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: None,
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="quiet_reader",
            description="the same module's uncontroversial tool",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_READ,
            handler=lambda args, ctx: None,
            audiences=_HUMAN_ONLY,
        ),
    )
