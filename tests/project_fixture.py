"""The one project a fixture means, for every suite that seeds sessions.

**Why this file exists.** `create_project` is no longer keyed by name (E1:
`/work/api` and `/personal/api` are two projects, and there is no unique index
on `name`), so a `seed()` helper that calls it per session no longer returns one
project — it mints a new one each time. Four `seed()` helpers did exactly that;
two were repaired with a local `the_project` helper copied verbatim between
`tests/toolsurface/test_tools_m1.py` and `test_tools_m2.py`, and the other two
were missed *because* the repair was a copy rather than a name.

Nothing was red either way, which is the part that matters: the surviving
fixtures model "four projects, one session each" where they modelled "one
project, four sessions", and a Flock **grouping** test written on one of them
would pass while proving nothing about grouping. One definition, imported by
every caller — the same rule `chokepoint_fixture` states, and the third time
this repo has paid for a copied fixture (RD-T4-3, RD-T5-5).

Selection is **by name, and only inside a fixture**, which is not the ban N2
states: `reads.list_workspaces` is ordered by name and its first row is the
seeded `Unassigned`, so production and test callers alike select by a captured
id. Here the name *is* what the fixture captured, and the row it would collide
with — a second project of the same name — is one only this helper creates, and
it creates it once.
"""

from __future__ import annotations

from shepherd.store.db import Store


def the_project(store: Store, name: str = "shepherd") -> str:
    """The id of the project of that name, created on first ask and reused after."""
    for workspace in store.list_workspaces():
        if workspace.name == name:
            return workspace.id
    return store.create_project(name=name, description=None).id
