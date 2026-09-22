"""§4's eight buckets on the page, with **both** a colour and a glyph (T14).

There is no browser and no JS runtime on this host (D51, K8), so the gate is a
scan of the bytes the server actually serves, exactly as M1's escaping scan is.
What that proves and what it does not is stated plainly: it proves the palette
the page ships is `core.stops.PALETTE` and that every bucket carries a mark as
well as a colour; it does not prove a pixel. The rendering itself is the human
checkpoint T14 names.

The accessibility invariant is the reason the glyph half exists: amber
(`needs_you`) and red (`error`) are the two chips a colourblind reader most
needs to tell apart, and in greyscale they are the same grey.
"""

from __future__ import annotations

import re
from pathlib import Path

from web.conftest import Client, seed

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import SessionState
from shepherd.core.stops import BUCKET_ORDER, PALETTE, Bucket
from shepherd.store.db import Store

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"

#: `.bucket-<name> { --bucket-colour: #RRGGBB; }` — one class per bucket.
_CSS_BUCKET = re.compile(r"\.bucket-([a-z_]+)\s*\{[^}]*?--bucket-colour:\s*(#[0-9A-Fa-f]{6})")

#: The three tables `flock.js` ships, read out of the source rather than trusted.
#: `ACTS` joins them at M5: U10's legend carries an `acts:` line and `who_acts`
#: is a `PALETTE` field, so it is compared rather than hand-copied for exactly
#: the reason the other two are.
_JS_TABLE = re.compile(r"const\s+BUCKET_(ACTS|LABEL|MARK)\s*=\s*\{(.*?)\n\}", re.DOTALL)
_JS_ENTRY = re.compile(r"(\w+):\s*\"([^\"]+)\"")

#: `flock.js`'s header names `.sort(` and `BUCKET_ORDER` in prose, explaining
#: why neither may appear. A scan that cannot tell a statement from the comment
#: forbidding it fails on the explanation, which trains the next reader to
#: delete the explanation.
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def css() -> str:
    return (STATIC_ROOT / "app.css").read_text(encoding="utf-8")


def flock_js() -> str:
    """M5's page module (U9). **This changed with the page, in one task.**

    The old helper read `fleet.js`, which is still on disk and is no longer the
    module the Flock renders from — `app.js`'s import is the shell's and the
    integration pass rewires it. Leaving the scan pointed at the dead module
    would have left every assertion below green against bytes no page renders,
    which is the failure this file exists to prevent one layer up.
    """
    return (STATIC_ROOT / "flock.js").read_text(encoding="utf-8")


def css_colours() -> dict[str, str]:
    return {name: colour.upper() for name, colour in _CSS_BUCKET.findall(css())}


def js_table(which: str) -> dict[str, str]:
    for kind, body in _JS_TABLE.findall(flock_js()):
        if kind == which:
            return dict(_JS_ENTRY.findall(body))
    return {}


def test_every_bucket_has_a_colour_and_a_glyph() -> None:
    """The accessibility invariant: eight names, eight colours, eight glyphs."""
    names = {bucket.value for bucket in Bucket}
    assert len(names) == 8

    colours = css_colours()
    marks = js_table("MARK")
    labels = js_table("LABEL")
    assert set(colours) == names
    assert set(marks) == names
    assert set(labels) == names

    assert len(set(colours.values())) == 8, colours
    assert len(set(marks.values())) == 8, marks
    assert all(mark.strip() != "" for mark in marks.values()), marks
    assert all(label.strip() != "" for label in labels.values()), labels


def test_palette_matches_core_stops() -> None:
    """One source of truth: a hand-copied hex is how a palette drifts.

    **U5's three renames land here, in `PALETTE`, and nowhere else** —
    `unfinished` reads *stranded*, `paused` reads *limit exceeded* and
    `unclassified` reads *unknown*. This test is why a UI-side label table is
    not an option: it compares the page's tables against `PALETTE`, so a second
    table would either be checked against the first (and be redundant) or not be
    (and be the drift). The bucket **values** do not move, so `stop_rules.py`,
    the store and the 90-day stop log are untouched by the rename.
    """
    colours = css_colours()
    marks = js_table("MARK")
    labels = js_table("LABEL")
    acts = js_table("ACTS")
    for bucket, style in PALETTE.items():
        assert colours[bucket.value] == style.colour.upper(), bucket
        assert marks[bucket.value] == style.glyph, bucket
        assert labels[bucket.value] == style.label, bucket
        assert acts[bucket.value] == style.who_acts, bucket

    # U5, asserted on the values rather than only on the agreement above: two
    # tables that agree on the wrong word still agree, and the three renames are
    # the whole of T6.2.
    assert labels["unfinished"] == "stranded"
    assert labels["paused"] == "limit exceeded"
    assert labels["unclassified"] == "unknown"
    # …and the values themselves are untouched, which is what keeps the rename
    # off `stop_rules.py`, the store and the stop log.
    assert {bucket.value for bucket in Bucket} >= {"unfinished", "paused", "unclassified"}


def test_unclassified_chip_renders_and_is_not_green_or_red() -> None:
    """D-4: a stopped row with no verdict is neither good news nor bad."""
    colours = css_colours()
    grey = colours["unclassified"]
    assert grey == PALETTE[Bucket.UNCLASSIFIED].colour.upper()
    assert grey != colours["finished"]
    assert grey != colours["error"]
    assert js_table("MARK")["unclassified"] == "?"


def test_the_page_does_not_re_derive_the_order() -> None:
    """The order is the server's (`fleet_bucket_sort_key`); the page renders it."""
    for name in ("flock.js", "app.js", "session.js"):
        source = _COMMENTS.sub("", (STATIC_ROOT / name).read_text(encoding="utf-8"))
        for shape in (".sort(", "localeCompare", "BUCKET_ORDER", "FLEET_STATE_ORDER"):
            assert shape not in source, f"{name}: {shape}"
    # …and the order itself is a real order, so "renders what it was handed" has
    # something to be handed: `blocked` below `running`, deliberately (§12).
    assert BUCKET_ORDER.index(Bucket.BLOCKED) > BUCKET_ORDER.index(Bucket.RUNNING)
    assert BUCKET_ORDER[0] is Bucket.NEEDS_YOU


def test_unknown_rate_renders() -> None:
    """Principle 5's headline metric is on the page §12 puts it on."""
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="unknown-rate"' in markup
    app = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    assert "unknown_rate" in app or "unknown_rate" in flock_js()


def test_low_confidence_completions_render_beside_the_unknown_rate() -> None:
    """**DP10 / r3 BLOCKING 4.** D34's tuning signal is on the page.

    A clean stop is `completed` at 0.5, and `finished` is green whatever the
    confidence — so without this number the page shows a green chip claiming a
    verification nobody performed, for the *largest* cohort, and D34's own
    trigger for building the model lane exists nowhere a human looks.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="low-confidence"' in markup
    # …beside it, not somewhere else on the page: the same summary element.
    summary = markup[markup.index('id="stop-summary"') :]
    assert summary.index('id="unknown-rate"') < summary.index('id="low-confidence"')
    joined = (STATIC_ROOT / "app.js").read_text(encoding="utf-8") + flock_js()
    assert "completed_low_confidence" in joined
    assert "unclassified" in joined


def test_page_renders_with_every_field_null(client: Client, store: Store) -> None:
    """An M1-era row carries no verdict at all and must not break the page.

    The payload half is real: every stop field comes back `null` and the bucket
    is `unclassified`. The rendering half is a static check that the chip has a
    fallback — there is no JS runtime here to execute it (stated, not implied).
    """
    session = seed(store)
    store.apply_fold_delta(session.id, FoldDelta(state=SessionState.STOPPED))
    sessions = client.request("/api/fleet/tree").json()["data"]["workspaces"][0]["sessions"]
    row = sessions[0]
    assert row["bucket"] == "unclassified"
    for field in ("stop_reason", "outcome", "why", "confidence", "decided_by", "exit_code"):
        assert row[field] is None, field
    assert row["next_actions"] == []

    source = flock_js()
    assert "in BUCKET_LABEL" in source
