"""T19 remediation: is page 3 **reachable**, and does it really render?

`test_session_page.py` is a per-file scan suite, and per-file scans have two
blind spots that an adversarial review found eight live mutations in:

* **Reachability.** Eight tests read `session.js` as text and not one walked the
  module graph from `index.html`, so every one of them passed against a module
  the page never loaded. `app.js` imported `fleet.js`, `rail.js` and `sse.js`
  and nothing else; `terminal.js` was imported only by `session.js`; the vendored
  emulator was therefore never fetched by a browser and the WebSocket the whole
  server half exists to feed was never opened. The scans said the code was
  correct, and they were right, and it was dead.
* **Renders.** The scans asserted that a *constant was defined* or that an
  *assignment was present somewhere in the file*. Deleting four separate
  assignments left the suite at 171 passed. `hidden` in static markup inverts
  the failure direction: a deleted `banner.hidden = false` is invisible to a
  `textContent` assertion, and the element silently never appears.

The answer to the second one is **enumeration, not four more one-off
assertions** — the same defect had already been caught twice inside this one
file (`m7`, `m8`) and four more instances shipped anyway. The rule is stated at
`REQUIRED_ASSIGNMENTS` and enforced as a whole-set equality, so the next
assignment anybody adds is covered by construction rather than by remembering.

Seam: unchanged — the shipped static files, parsed and never executed (G-M3-6).
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable

from web.test_session_page import (
    STATIC_ROOT,
    code_only,
    module_specifiers,
    source,
)

_SCRIPT_SRC = re.compile(r"""<script[^>]*\bsrc="/static/([^"]+)\"""")

#: `static/vendor/` is excluded from the reachability comparison **by name and
#: with the reason stated**: it is upstream code with a module graph of its own
#: (`xterm.js` is 344 970 minified bytes), this rule has no authority over it,
#: and `test_the_page_imports_only_files_that_ship` already asserts that the
#: specifier the page asks for resolves to the file that is there. The walk
#: still *records* reaching it — that is how we know the emulator is loaded —
#: it simply does not descend into it.
VENDOR_PREFIX = "vendor/"

#: The one shipped module that is deliberately not on the graph, with its reason.
#: An exclusion list with no reason per entry is how dead code becomes permanent.
UNREACHABLE_BY_DESIGN = {
    "escape.js": (
        "§13's escaping helper. The chosen style is static markup filled with"
        " `textContent`, so the page has **zero** HTML sinks today and nothing"
        " to wrap; `test_frontend_escaping.py::test_escape_html_exists_and_is"
        "_used_where_required` proves the helper is correct for the first sink"
        " that ever needs it, and `test_no_unescaped_interpolation_in_frontend`"
        " is what would fail if one appeared unwrapped."
    ),
}


def reachable_modules(markup: str, read: Callable[[str], str]) -> set[str]:
    """Every module the page really loads, walked from `index.html`'s scripts.

    The entry points are the `<script src="/static/…">` tags — the page's only
    way in — and the edges are `module_specifiers`, which follows static
    imports, bare side-effect imports, and a dynamic `import(CONST)` through one
    hop of a module-level constant (which is how the vendored emulator is
    loaded). Names are relative to `static/`.
    """
    entries = _SCRIPT_SRC.findall(markup)
    assert entries != [], "arrival: the page has no module entry point at all"

    seen: set[str] = set()
    queue = list(entries)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        if name.startswith(VENDOR_PREFIX):
            continue
        here = posixpath.dirname(name)
        for specifier in module_specifiers(read(name)):
            queue.append(posixpath.normpath(posixpath.join(here, specifier)))
    return seen


def test_every_shipped_module_is_reachable_from_the_page() -> None:
    """The check no per-file scan can make: is this module loaded at all?

    Before the remediation this failed on `session.js` and `terminal.js` —
    §12's whole page 3, plus the vendored emulator behind it — and eight tests
    asserting their contents all passed.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    reached = reachable_modules(markup, source)

    assert "app.js" in reached, "arrival: the walk did not even reach the bootstrap"
    shipped = {path.name for path in STATIC_ROOT.glob("*.js")}
    assert len(shipped) >= 7, shipped

    assert shipped - reached == set(UNREACHABLE_BY_DESIGN), sorted(shipped - reached)
    # Named rather than merely implied by the set difference: these three are
    # what the review found dead, and the vendored emulator is what page 3 is.
    assert {"session.js", "terminal.js"} <= reached, sorted(reached)
    # T24 extends the rule to §12's page 1. The set comparison above already
    # covers it; the name is here for the reason the two above are — the
    # difference says *something* is dead and the name says *which page*.
    assert "chat.js" in reached, sorted(reached)
    assert "vendor/xterm.js" in reached, sorted(reached)


def test_the_reachability_walk_bites() -> None:
    """B1: the walk is only a gate if an unreachable module fails it.

    Two runs over the same three modules, differing by one import line: the
    orphan is reported in the first and reached in the second. A walk that
    returned everything, or nothing, would pass one of these and not both.
    """
    markup = '<script type="module" src="/static/app.js"></script>'
    orphaned = {
        "app.js": 'import { live } from "./live.js";\nlive();',
        "live.js": "export function live() {}",
        "orphan.js": "export function orphan() {}",
    }
    reached = reachable_modules(markup, lambda name: orphaned[name])
    assert reached == {"app.js", "live.js"}, reached
    assert "orphan.js" not in reached

    linked = dict(orphaned)
    linked["app.js"] = 'import { live } from "./live.js";\nimport "./orphan.js";'
    assert reachable_modules(markup, lambda name: linked[name]) == {
        "app.js",
        "live.js",
        "orphan.js",
    }


def test_a_fleet_row_click_reaches_the_session_page() -> None:
    """The navigation the plan never assigned to a task, and now T19 owns.

    `index.html` ships exactly one `<script>` and it loads `app.js`, so the only
    way page 3 can ever run is for `app.js` to reach it. The chain asserted here
    is the whole of it: a click on a fleet row carries the row's own session id,
    `app.js` reads that session through the API it already knows, and hands the
    projection to `renderSession`.

    The id comes off the row's `data-session-id` rather than out of a closure,
    because `fleet.js` builds the rows and `app.js` owns the navigation; a
    positional match between DOM order and payload order would be the kind of
    implicit coupling that breaks silently when either side re-orders.
    """
    app = code_only(source("app.js"))
    assert re.search(r'import\s*\{[^}]*\brenderSession\b[^}]*\}\s*from\s*"\./session\.js"', app)

    # The listener, the row identity it reads, and the call it ends in.
    assert re.search(r'addEventListener\(\s*"click"', app), app
    assert "data-session-id" in app or "dataset.sessionId" in app, app
    assert "renderSession(" in app, app

    # …and `fleet.js` really puts that identity on the row (arrival: without
    # this the selector above matches nothing at runtime and the page is dead
    # again, with every scan still green).
    fleet = code_only(source("fleet.js"))
    assert re.search(r"\w+\.dataset\.sessionId\s*=\s*\w+\.session_id", fleet), (
        "no fleet row carries its session id"
    )

    # §16: the click opens a row, it does not re-derive an order.
    for shape in (".sort(", "localeCompare"):
        assert shape not in app, shape


# ----- the enumeration rule --------------------------------------------------

_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_$][\w$.]*)\s*=(?!=)\s*(.+?);\s*$")
_DECLARATION = re.compile(r"^\s*(?:const|let|var|export|import)\b")


def assignments(text: str) -> list[str]:
    """Every assignment `session.js` performs, normalised, in source order.

    **The enumeration rule, stated once so the next person can apply it:** an
    assignment is any single-line statement of the form `target = value;` whose
    target is an identifier or a property path, excluding declarations
    (`const`/`let`/`var`) — which are bindings, not renders. Every one of them
    is listed in `REQUIRED_ASSIGNMENTS` with the requirement it discharges, and
    the two are compared as **whole sets**. Adding one, deleting one, or
    changing one value fails here; nothing has to be remembered.

    The rule is deliberately syntactic and total rather than semantic and
    selective, because the four mutations that survived were each *a render
    nobody had thought to assert*, and a list of the renders somebody thought of
    is exactly the artefact that failed.
    """
    found: list[str] = []
    for line in code_only(text).splitlines():
        if _DECLARATION.match(line):
            continue
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        found.append(" ".join(f"{match.group(1)} = {match.group(2)}".split()))
    return found


#: Every assignment `session.js` is required to perform, and why. A value here
#: is a **requirement**, not a transcription: each line is what §9/§12/D21/D29/
#: K6/principle 5 say page 3 must put on the screen.
REQUIRED_ASSIGNMENTS = {
    # `fill(id, value)`: principle 5's em dash for a datum the row does not carry.
    # Bound as `node` rather than `element` since D67: the shared node helper is
    # imported from `flock.js` under that name, and a local binding shadowing it
    # would turn every later `element(...)` into a call on a DOM node.
    'node.textContent = value === null || value === undefined ? "—" : String(value)',
    # D21's buttons, relocated to the pane by **D67**. `text` and `kind` are the
    # fields `project_action` emits — the page once read `action.label`, which
    # exists nowhere in the projection layer, so every stopped-band button
    # rendered empty and no unknown was counted. They are now built through
    # `flock.js::element`, which sets the class and the text in one call, so the
    # two lines that used to do it by hand are gone rather than missing.
    'button.type = "button"',
    "button.dataset.kind = kind",
    # RD6, which moved with the list it governs: an action whose capability
    # lands later is **labelled and inert**, never an unlabelled dead button.
    # One inert path, two reasons — a second `disabled` write would be the same
    # render performed twice, which the duplicate check above refuses.
    "button.disabled = true",
    "button.title = reason",
    # G-M2-7's `external` with somewhere to go: live at M2 because it needs
    # nothing of ours. The three lines are one affordance and move together.
    "link.href = action.target",
    'link.target = "_blank"',
    'link.rel = "noopener noreferrer"',

    # D29's click-to-edit rename, and DP1's boundary: this is the **local**
    # rename. The engine write-back stays behind `can_set_title`, server-side.
    'input.className = "session-rename-input"',
    'input.type = "text"',
    'input.value = row.title === null || row.title === undefined ? "" : String(row.title)',
    'status.textContent = ""',
    "status.textContent = `${RENAME_FAILED}: ${body.error} (${body.correlation_id})`",
    "status.textContent = `${RENAME_FAILED}: ${body.data.reason}`",
    "status.textContent = RENAME_UNREACHABLE",
    # The marker after a rename, keyed on the outcome the server returned
    # (`local_only` — `tools_rename.py::project_rename`), which is the one
    # reading of D29 that can actually light up today.
    'marker.textContent = data.local_only ? LOCAL_ONLY_MARKER : ""',
    "marker.hidden = !data.local_only",
    # …and on first render, keyed on the row's own two fields (T19-b: neither is
    # on the wire yet, which is recorded rather than guessed around).
    'marker.textContent = localOnly(row) ? LOCAL_ONLY_MARKER : ""',
    "marker.hidden = !localOnly(row)",
    # The page is hidden in static markup until a session is opened. Nothing
    # cleared it, so page 3 could not have appeared even once loaded.
    "view.hidden = false",
    # K6/§9: an attached session gets the banner and no terminal of ours.
    "banner.textContent = READ_ONLY_BANNER",
    "banner.hidden = false",
    "terminal.hidden = true",
    'note.textContent = ""',
    # …and an owned one gets the terminal, with T19-c's reason for the keys.
    'banner.textContent = ""',
    "banner.hidden = true",
    "terminal.hidden = false",
    "note.textContent = INPUT_UNAVAILABLE",
    # The rename affordance `index.html` has always shipped and nothing wired.
    "rename.onclick = () => beginRename(row)",
    # One terminal at a time: a second open with the first socket still live
    # would hold a `pipe-pane` open for the life of the tab.
    "attached = null",
    "attached = openTerminal(row.session_id, terminal)",
}


def test_render_session_performs_every_assignment_the_spec_requires() -> None:
    """Enumerated, not sampled — see `assignments`' docstring for the rule.

    Four deletions and one operator flip survived the previous suite at 171
    passed. Each of them changes this set.
    """
    performed = assignments(source("session.js"))
    assert performed != [], "arrival: the enumeration read no assignment at all"
    assert len(performed) == len(set(performed)), "a duplicated render"
    assert set(performed) == REQUIRED_ASSIGNMENTS, {
        "missing": sorted(REQUIRED_ASSIGNMENTS - set(performed)),
        "unexpected": sorted(set(performed) - REQUIRED_ASSIGNMENTS),
    }


def test_local_only_is_the_conjunction_d29_states() -> None:
    """`&&` → `||` survived at 171 passed, and it is not a cosmetic difference.

    D29: `title_synced_at` is stamped **only** from a read-back of the engine's
    own `nameSource:"user"`, so the marker means *this title was set here and
    never reached the engine*. Under `||` the marker lights for **every**
    unsynced row regardless of `title_source` — including one the engine itself
    titled — which turns D29's honest degrade into a false claim about where a
    name came from.
    """
    body = code_only(source("session.js"))
    match = re.search(r"function localOnly\(\w+\)\s*\{(.*?)\}", body, flags=re.DOTALL)
    assert match is not None, "the marker's rule is inline, so nothing can test it"
    assert " ".join(match.group(1).split()) == (
        'return row.title_source === "user" && !row.title_synced_at;'
    )


def test_the_pages_read_only_fields_the_projection_emits() -> None:
    """One payload, one set of field names, across the JSON seam.

    `session.js` read `action.label`. `project_action` emits `text`, `kind`,
    `target` and `source`, and there is no `label` anywhere in the projection
    layer — so D21's buttons rendered empty and, because the page had no
    fallback, no unknown was counted either. `fleet.js` got the same payload
    right *with* a fallback, so the two pages disagreed about one payload.

    The expected names come from the **producer**, called on a real shipped
    action, not from anyone's memory of the payload.
    """
    from shepherd.core.stops import StopReason
    from shepherd.signals.stop_rules import DEFAULT_ACTIONS
    from shepherd.toolsurface.tools_m1 import project_action

    real = DEFAULT_ACTIONS[StopReason.CRASHED]
    assert real != (), "arrival: no real action to project"
    emitted: set[str] = set()
    for action in real:
        emitted |= set(project_action(action))
    assert emitted == {"text", "kind", "target", "source"}, emitted

    read: set[str] = set()
    for name in ("session.js", "fleet.js"):
        read |= set(re.findall(r"\baction\.(\w+)", code_only(source(name))))
    assert "text" in read, "arrival: no page reads an action's label at all"
    assert read <= emitted, sorted(read - emitted)

    # Principle 5: the unknown is a value, displayed — both pages the same way.
    for name in ("session.js", "fleet.js"):
        text = code_only(source(name))
        assert re.search(
            r'typeof action\.text === "string" && action\.text !== "" \? action\.text : UNKNOWN',
            text,
        ), name


def test_every_id_in_the_session_view_is_wired_by_the_scripts() -> None:
    """The mirror of `test_every_slot_the_scripts_fill_exists_in_the_markup`.

    That test asserts slots ⊆ markup, which is blind in exactly one direction:
    an element the markup ships and **nothing wires** is invisible to it. That
    is how `#session-rename` — the rename affordance §12's Objective names, with
    a `POST /api/sessions/{id}/rename` route already waiting for it — shipped as
    a button with no behaviour for a whole task.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    section = re.search(
        r'<section id="session-view".*?</section>', markup, flags=re.DOTALL
    )
    assert section is not None, "arrival: page 3's markup is not in index.html"
    ids = set(re.findall(r'id="([^"]+)"', section.group(0)))
    ids.add("session-view")
    assert len(ids) >= 11, sorted(ids)

    wired = {
        identifier
        for name in ("session.js", "terminal.js")
        for identifier in re.findall(
            r"""(?:getElementById|slot|fill)\(\s*["']([^"']+)["']""", source(name)
        )
    }
    # No exclusion list: every element page 3 ships is an element page 3 fills.
    assert ids - wired == set(), sorted(ids - wired)


# ==============================================================================
# The vendor record's claims, checked as a structure rather than as a sentence.
#
# `tests/web/test_session_page.py::test_the_vendor_record_claims_only_what_is_
# proved` bans the one sentence review finding 8 caught. The router then planted
# the **same retracted claim in a paraphrase** and that gate stayed green — a
# spelling, not a property, which is precisely the defect this repo keeps finding
# in the checks written to close it. Both layers ship: the literal ban is cheap
# and catches the copy-paste return, and the three rules below catch the
# paraphrase, because none of them can be satisfied by choosing different words.
# ==============================================================================

VENDOR_RECORD = STATIC_ROOT / "vendor" / "VERSION.txt"

#: A `VERSION.txt` section is a title line followed by a line of dashes. Nothing
#: else in the file uses that shape, and the parser below asserts it found the
#: sections it names rather than silently matching none.
_SECTION_RE = re.compile(r"^(?P<title>\S.*)\n-{4,}\s*$", re.MULTILINE)

#: The two words that name the retracted claim. They are legitimate in exactly
#: two places: the section that says the path does **not** exist, and the section
#: that says which seams really do prove `send-keys` byte-exactness.
RETRACTED_TOKENS = ("keystroke", "send-keys")

SECTIONS_ALLOWED_THE_RETRACTED_TOKENS = (
    "What this vendoring does NOT prove — G-M3-6",
    "Where `send-keys -H` byte-exactness *is* proved, which is a different seam",
)

#: The closed claim set. Compared **whole**, so a claim cannot be added or
#: dropped quietly — which is the failure mode a `not in` assertion cannot see.
EXPECTED_CLAIMS = frozenset(
    {
        "the WS frame payload is the capture byte-for-byte",
        "the stream is torn down with the last client",
        "every shipped module is reachable from the page",
        "the vendored bytes match the digests recorded above",
    }
)


def _sections() -> dict[str, str]:
    """`VERSION.txt` split into title -> body, with the split asserted."""
    text = VENDOR_RECORD.read_text(encoding="utf-8")
    assert "G-M3-6" in text, "arrival: this is not the vendor record"
    starts = list(_SECTION_RE.finditer(text))
    assert len(starts) >= 4, [match.group("title") for match in starts]
    bodies: dict[str, str] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        bodies[match.group("title")] = text[match.end() : end]
    return bodies


def test_the_vendor_record_names_the_retracted_claim_only_where_it_is_denied() -> None:
    """A paraphrase is caught because the rule is about *where*, not *how*.

    The retracted claim — a browser->pane path this tree does not have — can be
    written a hundred ways. It cannot be written anywhere but the two sections
    that exist to deny it and to point at the seam that really proves it, and
    that is a property of the file's structure rather than of its vocabulary.
    """
    bodies = _sections()
    for title in SECTIONS_ALLOWED_THE_RETRACTED_TOKENS:
        assert title in bodies, sorted(bodies)

    # Arrival: the tokens are genuinely present in the allowed sections, so a
    # file that simply stopped mentioning the retraction cannot pass this.
    allowed_text = "".join(
        bodies[title] for title in SECTIONS_ALLOWED_THE_RETRACTED_TOKENS
    )
    for token in RETRACTED_TOKENS:
        assert token in allowed_text, token

    strays = {
        title: token
        for title, body in bodies.items()
        if title not in SECTIONS_ALLOWED_THE_RETRACTED_TOKENS
        for token in RETRACTED_TOKENS
        if token in body
    }
    assert strays == {}, strays


def test_the_vendor_records_claim_list_is_closed_and_compared_whole() -> None:
    """Praise added elsewhere in the file is not a claim; the list is the claims."""
    bodies = _sections()
    title = "Claims on the browser path, and the test that proves each"
    assert title in bodies, sorted(bodies)
    body = bodies[title]

    claims: set[str] = set()
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().startswith("-> "):
            continue
        claim = lines[index - 1].strip()
        assert claim and not claim.startswith("->"), (index, claim)
        claims.add(claim)

    assert claims == set(EXPECTED_CLAIMS), {
        "unrecorded": sorted(claims - EXPECTED_CLAIMS),
        "missing": sorted(EXPECTED_CLAIMS - claims),
    }


def test_every_test_the_vendor_record_names_actually_exists() -> None:
    """A citation to a test that does not exist is a claim with no proof at all.

    Resolved through the file system and the AST, never through a string match:
    the node id names a module and a function, and both have to be there.
    """
    import ast

    text = VENDOR_RECORD.read_text(encoding="utf-8")
    repo_root = STATIC_ROOT.parents[3]
    node_ids = set(re.findall(r"(tests/[\w/]+\.py)::(\w+)", text))
    assert len(node_ids) >= 4, sorted(node_ids)

    for relative, function in sorted(node_ids):
        module = repo_root / relative
        assert module.is_file(), relative
        tree = ast.parse(module.read_text(encoding="utf-8"))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert function in defined, (relative, function)

    # The seam citations carry a line number rather than a node id; they are
    # asserted to name files that exist, which is all a `path:line` can promise.
    for relative in set(re.findall(r"(tests/[\w/]+\.py):\d", text)):
        assert (repo_root / relative).is_file(), relative
