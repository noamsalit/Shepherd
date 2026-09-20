"""§12's Needs-You rail: on every page, never a page you navigate to (T16).

Two halves, and the return says which is which. The **payload** half runs over
HTTP against a real store: the rail renders `fleet_summary`'s `needs_you` list
and composes nothing, so what the fold wrote is what a human reads. The
**rendering** half is a scan of the shipped module — there is no browser and no
JS runtime on this host, so a scan can show the branch and the wording and
cannot show a pixel.

The wording is the point (C21, M1's gap M10). `idle_prompt` flips an idle TUI to
`needs_you` 60 s after a `Stop`, so idle sessions **will** appear in this rail on
a real machine. `idle — waiting for your next instruction` is the difference
between a rail that is wrong and a rail that is precise; "session needs
attention" would be the former.
"""

from __future__ import annotations

import re
from pathlib import Path

from web.conftest import NOW, Client, seed

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import SessionState
from shepherd.core.stops import PALETTE, Bucket
from shepherd.store.db import Store

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"

#: C21's exact ask — §8's wording, not a summary of it.
IDLE_ASK = "idle — waiting for your next instruction"

_RAIL_EMPTY_RULE = re.compile(r"\.rail-empty\s*\{([^}]*)\}")


def rail_js() -> str:
    return (STATIC_ROOT / "rail.js").read_text(encoding="utf-8")


def needs_you(client: Client) -> list[dict[str, object]]:
    data = client.request("/api/fleet").json()["data"]
    assert isinstance(data, dict)
    listed = data["needs_you"]
    assert isinstance(listed, list)
    return listed


def test_rail_shows_the_actual_ask(client: Client, store: Store) -> None:
    """Never "needs attention": the exact `needs_you_reason` the fold composed."""
    session = seed(store)
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=SessionState.NEEDS_YOU,
            needs_you_reason="permission: Bash(git push)",
            last_event_at=NOW,
        ),
    )
    listed = needs_you(client)
    assert listed[0]["needs_you_reason"] == "permission: Bash(git push)"

    source = rail_js()
    assert "needs_you_reason" in source
    assert "needs attention" not in source
    # The rail renders the list; it does not compose a reason of its own.
    assert "export function renderRail" in source


def test_idle_prompt_is_needs_you_and_the_rail_says_idle(
    client: Client, store: Store
) -> None:
    """C21, surfaced rather than softened: idle sessions do appear here."""
    session = seed(store)
    store.apply_fold_delta(
        session.id,
        FoldDelta(
            state=SessionState.NEEDS_YOU, needs_you_reason=IDLE_ASK, last_event_at=NOW
        ),
    )
    listed = needs_you(client)
    assert listed[0]["needs_you_reason"] == IDLE_ASK
    assert "idle" in str(listed[0]["needs_you_reason"])


def test_rail_renders_with_a_null_reason(client: Client, store: Store) -> None:
    """Principle 5: unknown, never a blank row — and never an invented ask."""
    session = seed(store)
    store.apply_fold_delta(
        session.id, FoldDelta(state=SessionState.NEEDS_YOU, last_event_at=NOW)
    )
    listed = needs_you(client)
    assert listed[0]["needs_you_reason"] is None

    source = rail_js()
    fallback = re.search(r"RAIL_UNKNOWN_ASK\s*=\s*\n?\s*\"([^\"]+)\"", source)
    assert fallback is not None, "the null reason has a named, honest fallback"
    wording = fallback.group(1).lower()
    assert "not recorded" in wording or "unknown" in wording
    assert "needs attention" not in wording


def test_empty_rail_collapses_to_a_line() -> None:
    """§12: empty is a 4 px green line, not an empty panel announcing nothing."""
    css = (STATIC_ROOT / "app.css").read_text(encoding="utf-8")
    rule = _RAIL_EMPTY_RULE.search(css)
    assert rule is not None, ".rail-empty must exist"
    body = rule.group(1)
    assert "4px" in body
    # The same green as the `finished` chip, from the one palette (T14).
    assert PALETTE[Bucket.FINISHED].colour.upper() in body.upper()
    assert "rail-empty" in rail_js()


def test_rail_is_on_every_page() -> None:
    """The slot is in `index.html`, so it is the shell — not one view's child."""
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="rail"' in markup
    # …outside `<main>`, which is the part a future view replaces.
    assert markup.index('id="rail"') < markup.index("<main")
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert "renderRail" in app
    assert "./rail.js" in app


def test_rail_updates_from_sse_not_polling() -> None:
    """§12: no polling anywhere in the UI. The stream is the liveness path."""
    source = rail_js()
    for shape in ("setInterval", "setTimeout", "requestAnimationFrame", "fetch("):
        assert shape not in source, shape
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    # The rail is redrawn by the same function an arriving event drives.
    assert "onEnvelope" in app
    assert "new EventSource" in (STATIC_ROOT / "sse.js").read_text(encoding="utf-8")


def test_rail_says_unknown_before_the_fleet_has_been_read() -> None:
    """Principle 5, on the rail's own state: *not read yet* is not *empty*.

    The green line means "nothing is waiting on you" — a claim. Before the first
    `fleet_summary` lands, and after a read that failed, nobody has established
    that, so the rail shows a third state that says so instead of a green line
    asserting a fact the page does not have.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    rail = markup[markup.index('id="rail"') : markup.index('id="rail"') + 240]
    assert "rail-unknown" in rail
    assert "rail-empty" not in rail

    source = rail_js()
    assert "rail-unknown" in source

    css = (STATIC_ROOT / "app.css").read_text(encoding="utf-8")
    rule = re.search(r"\.rail-unknown\s*\{([^}]*)\}", css)
    assert rule is not None
    # The `unclassified` grey from the one palette — never green, never amber.
    assert PALETTE[Bucket.UNCLASSIFIED].colour.upper() in rule.group(1).upper()
