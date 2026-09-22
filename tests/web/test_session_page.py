"""T19: §12's page 3, asserted on the files the server actually serves.

**Seam: the shipped static files, parsed and never executed.** There is no node,
no npm and no browser on this host (`data-schemas.md` §Not probeable on this
host), which is the whole of **G-M3-6** and the reason acceptance clause 11
refuses to claim that the terminal *renders*. Every claim below is about bytes
on disk or bytes on a socket; none is about a picture.

Two rules this module keeps, because this repo's dominant defect is a check that
reports success without checking:

* **Arrival before absence.** A scan that finds no violation in a file it never
  opened passes. Every scan here first asserts it read the thing it claims to
  have checked, and every source scan carries a **negative fixture** that must
  trip it (`fixtures/pty_sinks.js`).
* **A parametrised loop states its own case count**, so a file quietly dropped
  from the table fails here rather than shrinking the evidence silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from shepherd.core.stops import NextActionKind

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "src" / "shepherd" / "web" / "static"
VENDOR_ROOT = STATIC_ROOT / "vendor"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: T19-a's outcome: the vendoring branch, not the degrade branch. These are the
#: files `VERSION.txt` accounts for, and the count is asserted below.
VENDORED = ("xterm.js", "xterm.css", "LICENSE", "VERSION.txt")

#: §9's banner, verbatim. A paraphrase is a different promise to the human.
READ_ONLY_BANNER = (
    "read-only — this session wasn't started here. Open it in the platform to"
    " get a terminal."
)

#: §12's marker text, and RD9: *exactly* this string, because it is what a
#: reviewer greps for when DP1 is decided.
LOCAL_ONLY = "local only"

#: T19-a step 3's wording. The degrade is a product state, not a stub.
DEGRADE_MESSAGE = "live terminal unavailable: xterm.js is not vendored"


def source(name: str) -> str:
    """A shipped module's text, with the read asserted rather than assumed."""
    path = STATIC_ROOT / name
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8")
    assert text.strip() != "", path
    return text


# ----- T19-a: the vendoring outcome -------------------------------------------


def test_the_vendored_files_are_present_and_accounted_for() -> None:
    """Branch taken: **vendored**. The degrade below still ships beside it.

    `VERSION.txt` is the record T19-a step 2 asks for — version, source URL and
    sha256 — and it is read back here rather than trusted: a manifest that names
    a file the directory does not hold, or a digest that does not match the
    bytes on disk, is a provenance claim nobody checked.
    """
    assert VENDOR_ROOT.is_dir(), "xterm.js was not vendored; see Progress notes"
    present = sorted(path.name for path in VENDOR_ROOT.iterdir() if path.is_file())
    assert present == sorted(VENDORED), present
    assert len(present) == 4


def test_the_vendor_manifest_pins_every_byte_it_ships() -> None:
    """The sha256 in `VERSION.txt` is recomputed from the bytes beside it."""
    import hashlib

    manifest = (VENDOR_ROOT / "VERSION.txt").read_text(encoding="utf-8")
    digests = dict(
        re.findall(r"^sha256\s+([0-9a-f]{64})\s+(\S+)$", manifest, flags=re.MULTILINE)
    )
    assert set(digests.values()) == {"xterm.js", "xterm.css", "LICENSE"}, digests
    assert len(digests) == 3
    for digest, name in digests.items():
        actual = hashlib.sha256((VENDOR_ROOT / name).read_bytes()).hexdigest()
        assert actual == digest, name
    # Arrival: the manifest names the package and the upstream URL it came from.
    assert "@xterm/xterm@6.0.0" in manifest
    assert "https://cdn.jsdelivr.net/npm/@xterm/xterm@6.0.0/" in manifest


def test_the_vendored_terminal_is_an_es_module_not_a_umd_bundle() -> None:
    """T19-a step 2: `export`, not a loader. D51 has no bundler to unwrap one.

    The `.mjs` upstream is vendored under the `.js` name the plan's
    Files/Surfaces gives it **and that the server can serve** — `web/server.py`'s
    `_CONTENT_TYPES` maps `.html`, `.js` and `.css` and 404s everything else, so
    a `.mjs` suffix would ship a file the page cannot load.
    """
    text = (VENDOR_ROOT / "xterm.js").read_text(encoding="utf-8")
    assert re.search(r"\bexport\s*\{[^}]*\bas Terminal\b", text), text[-400:]
    for loader in ("define.amd", "module.exports", "require(", "window.Terminal"):
        assert loader not in text, loader


# ----- the scans, and the negative control every one of them answers to -------

#: The sinks §13 names. `textContent` is not here: it is the whole point.
HTML_SINKS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "setHTMLUnsafe",
    "document.write",
    "eval(",
    "new Function",
)

#: The tokens that carry pane bytes in `terminal.js`. Every line mentioning one
#: must match an allowed shape below — an allow-list, because a deny-list of
#: sinks cannot see the sink someone invents next.
#:
#: **Widened at the T19 remediation (review finding 4).** The first version named
#: only the socket's three tokens, so §13's *second* pane-content path — the
#: degrade's `body.data.text`, which is `session_output`'s
#: `runner.snapshot(...).decode(...)` and therefore pty bytes — was never
#: inspected at all. Replacing that line with a real WHATWG parsing sink
#: (`setHTMLUnsafe`) left the whole of `tests/web` green. `screen.` is the dot
#: form on purpose: it names the property accesses on the degrade's `<pre>` and
#: not the bare identifier in `const screen = …` or `refreshScreen(screen, …)`.
PTY_TOKENS = ("event.data", "payload", "bytes", "body.data", "data.text", "screen.")

#: Where pane bytes are allowed to go: the emulator, a `textContent` slot, a
#: length, or a local binding on its way to one of those.
_ALLOWED_PTY_LINE = re.compile(
    r"""^\s*(?:
        (?:const|let)\s+\w+\s*=\s*[^=;]*;?            # binding it to a name
      | \w+\.write\(                                   # term.write(bytes)
      | \w+\.(?:textContent|className)\s*=             # a text slot, or its class
      | (?:return|if|\}|//|\*|/\*)                     # control flow, comments
      | \w+\s*\(\s*\w                                  # handing it to a function
    )""",
    re.VERBOSE,
)

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def code_only(text: str) -> str:
    """The source with comments removed, so a scan cannot be fooled by prose."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def html_sink_findings(text: str) -> list[str]:
    body = code_only(text)
    return [sink for sink in HTML_SINKS if sink in body]


def pty_lines(text: str) -> list[str]:
    """Every line the pty scan **inspects**, so arrival is assertable.

    A scan that inspects nothing reports nothing. `test_pty_bytes_never_reach_
    innerHTML` asserts this list actually contains both pane-content paths —
    the socket's `term.write` and the degrade's `body.data.text` — before it
    asserts that neither of them reaches a sink.
    """
    return [
        line.strip()
        for line in code_only(text).splitlines()
        if any(token in line for token in PTY_TOKENS)
    ]


def pty_path_findings(text: str) -> list[str]:
    """Every line carrying pane bytes that is not one of the allowed shapes."""
    findings: list[str] = []
    for line in code_only(text).splitlines():
        if not any(token in line for token in PTY_TOKENS):
            continue
        if any(sink in line for sink in HTML_SINKS):
            findings.append(line.strip())
            continue
        if not _ALLOWED_PTY_LINE.match(line):
            findings.append(line.strip())
    return findings


def block_after(text: str, keyword: str) -> str | None:
    """The `{...}` block that follows `keyword`, by brace matching.

    Used to ask a real structural question — *is the vendor import inside a
    `try`, and does its `catch` reach the degrade?* — rather than the
    substring question *does the word `catch` appear somewhere in the file*,
    which is true of any file that once had a `catch`.
    """
    body = code_only(text)
    start = body.find(keyword)
    if start < 0:
        return None
    opened = body.find("{", start)
    if opened < 0:
        return None
    depth = 0
    for index in range(opened, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return body[opened + 1 : index]
    return None


def attached_branch(text: str) -> str:
    """The body of `session.js`'s `ownership === "attached"` branch.

    Extracted rather than grepped for, because every claim about that branch —
    it shows the banner, it opens no terminal — is a claim about what is
    *inside* it, and a file-wide substring search answers neither.
    """
    body = code_only(text)
    marker = re.search(r"""ownership\s*===?\s*["']attached["']""", body)
    assert marker is not None, "nothing branches on ownership"
    block = block_after(body[marker.start() :], ")")
    assert block is not None
    return block


def module_specifiers(text: str) -> list[str]:
    """Every module this file loads, following a one-hop constant.

    `import("./x.js")` and `from "./x.js"` are literals; `import(VENDOR_MODULE)`
    is not, and it is the one that matters — a dynamic import is how the vendor
    file is loaded, and a specifier that resolves to nothing degrades the page on
    every load forever.
    """
    body = code_only(text)
    found = re.findall(r"""import\(\s*["']([^"']+)["']""", body)
    found += re.findall(r"""from\s+["']([^"']+)["']""", body)
    # A bare side-effect import (`import "./x.js";`) is an edge of the module
    # graph too, and `test_session_wiring.py` walks that graph from the page.
    found += re.findall(r"""import\s+["']([^"']+)["']""", body)
    constants = dict(re.findall(r"""const\s+(\w+)\s*=\s*["']([^"']+)["']""", body))
    for name in re.findall(r"""import\(\s*(\w+)\s*\)""", body):
        assert name in constants, f"import({name}) names no module-level constant"
        found.append(constants[name])
    return found


def test_the_scans_bite_on_the_negative_control() -> None:
    """B1: a gate is only a gate if the violating shapes trip it.

    Four planted shapes, four scans, asserted one at a time so a fixture that
    stops exercising one of them cannot be covered by another.
    """
    violating = (FIXTURES / "pty_sinks.js").read_text(encoding="utf-8")
    assert violating.strip() != ""

    sinks = html_sink_findings(violating)
    assert "innerHTML" in sinks and "insertAdjacentHTML" in sinks, sinks

    findings = pty_path_findings(violating)
    assert any("innerHTML" in finding for finding in findings), findings
    assert any("insertAdjacentHTML" in finding for finding in findings), findings

    # Review finding 4: the degrade's `<pre>` is the second pane-content path,
    # and `setHTMLUnsafe` is a real WHATWG HTML-parsing sink. Both the sink list
    # and the widened token list are asserted on it, one at a time, because
    # either alone would have let the shipped mutation through.
    assert "setHTMLUnsafe" in sinks, sinks
    assert any("setHTMLUnsafe" in finding for finding in findings), findings
    assert any("data.text" in finding for finding in findings), findings

    # The import is not inside a try, so there is no catch block to find.
    assert block_after(violating, "try") is None

    assert ".sort(" in code_only(violating)

    # And the same scans stay quiet on the shipped module — a scan that fires
    # on everything is not a scan either.
    assert html_sink_findings(source("terminal.js")) == []


def test_pty_bytes_never_reach_innerHTML() -> None:
    """§13, on the one file that carries untrusted terminal bytes.

    Two claims, not one: `terminal.js` has **no** HTML sink at all, and every
    line that touches a pane byte matches an allowed shape. The second is what
    survives someone inventing a sink this list has never heard of.
    """
    text = source("terminal.js")
    assert "term.write" in text, "arrival: the scan is reading the data path"

    # **Arrival, on both paths.** §13 names two: the socket's frames and the
    # degrade's screen text, which is `session_output`'s
    # `runner.snapshot(...).decode(...)` — pty bytes either way. The first
    # version of this scan inspected only the first, so a sink on the second
    # was invisible to it (review finding 4).
    inspected = pty_lines(text)
    assert any("term.write(" in line for line in inspected), inspected
    assert any("data.text" in line for line in inspected), inspected

    assert html_sink_findings(text) == []
    assert pty_path_findings(text) == []


def test_no_unescaped_interpolation_in_the_new_modules() -> None:
    """The inherited scan (T16's `unsafe_sinks`) over this task's two files."""
    from web.test_frontend_escaping import unsafe_sinks  # tests/ is on sys.path

    for name in ("terminal.js", "session.js"):
        assert unsafe_sinks(source(name)) == [], name


def test_the_terminal_degrades_to_a_screen_view_when_the_vendor_file_is_absent() -> None:
    """T19-a step 3: a missing vendor file is a message, never a blank pane.

    The vendor import is the one thing on this page that can fail on a
    correctly-built host — an installed wheel that shipped `static/*` and not
    `static/vendor/*` is exactly that host, and it is the defect M1 shipped once
    (T16-2). So the degrade is asserted structurally: the import is inside a
    `try`, its `catch` reaches the degrade, and the degrade paints text.
    """
    text = source("terminal.js")
    assert text.count("import(") == 1, "one dynamic import, or this scan is blind"

    guarded = block_after(text, "try")
    assert guarded is not None, "the vendor import is not inside a try"
    assert "import(" in guarded, guarded

    recovery = block_after(text, "catch")
    assert recovery is not None
    assert "degrade(" in recovery, recovery

    degraded = block_after(text, "function degrade")
    assert degraded is not None
    # The wording is a module constant, so the two halves are asserted apart:
    # the file carries T19-a's exact sentence, and the degrade is what paints it.
    assert text.count(DEGRADE_MESSAGE) == 1, "the degrade's wording moved"
    assert re.search(r"textContent\s*=\s*DEGRADE_MESSAGE", degraded), degraded
    assert "innerHTML" not in degraded
    # The degrade renders the screen, not an empty box: it is a product state.
    assert "<pre>" in text or 'createElement("pre")' in text


def test_the_page_imports_only_files_that_ship() -> None:
    """A vendor path that resolves to nothing degrades on every load, forever.

    This is the check that turns "the file is vendored" into "the file the page
    asks for is the file that is there".
    """
    specifiers: list[str] = []
    for name in ("terminal.js", "session.js"):
        text = source(name)
        specifiers.extend(module_specifiers(text))
    # **Arrival, and it is the whole test.** The first version of this scan
    # collected string literals only, so `import(VENDOR_MODULE)` — an
    # identifier — was invisible and the one specifier that can realistically
    # be wrong was never checked. Mutation `m13` pointed the page at
    # `./vendor/xterm.min.js` and the test stayed green.
    assert "./vendor/xterm.js" in specifiers, specifiers
    assert "./terminal.js" in specifiers, specifiers
    for specifier in specifiers:
        assert specifier.startswith("./"), specifier
        assert (STATIC_ROOT / specifier[2:]).is_file(), specifier


def test_an_attached_session_shows_the_read_only_banner() -> None:
    """§9's wording, verbatim, and no terminal behind it.

    An attached session has no pane of ours. Rendering a live terminal for one
    would offer a write path into a pane on the **user's own** socket (K6), so
    the page must branch on `ownership` before it opens anything.
    """
    text = source("session.js")
    assert READ_ONLY_BANNER in text, "the §9 banner's wording is not on the page"
    assert text.count(READ_ONLY_BANNER) == 1

    # **Presence is not wiring.** Asserting the sentence is somewhere in the
    # file survives deleting the line that paints it — mutation `m7` proved
    # exactly that against the first version of this test. The assignment
    # inside the attached branch is the property; the constant's text is the
    # second half of it.
    branch = attached_branch(text)
    assert re.search(r"banner\.textContent\s*=\s*READ_ONLY_BANNER\b", branch), branch
    assert re.search(
        r"""const READ_ONLY_BANNER\s*=\s*\n?\s*"([^"]+)";""", text
    ), "the banner is not a named constant"

    # …and the attached branch really is the one that refuses: no terminal is
    # opened inside it, while the page does open one somewhere (arrival).
    assert "openTerminal(" in text
    assert "openTerminal(" not in branch


def test_a_renamed_session_says_local_only() -> None:
    """D29/RD9: the marker is `local only`, keyed on the row's own two fields.

    `title_synced_at` is stamped **only** from a read-back of the engine's own
    `nameSource:"user"` (D29), so `title_source == 'user'` with a null
    `title_synced_at` is precisely "renamed here, never synced there" —
    `store/models.py:238` states that rule on the column itself.

    **This marker cannot light up in production today** and that is recorded as
    blocker **T19-b**: `toolsurface/tools_m1.py::project_session` carries
    neither field, so §13's whitelist does not put them on the wire. The page
    keys on the documented rule rather than on a field it invented; closing the
    gap is a change to a projection this task does not own.
    """
    text = source("session.js")
    marker = re.search(r"function localOnly\(", text)
    assert marker is not None, "the marker is inline, so nothing can test it"
    body = block_after(text, "function localOnly")
    assert body is not None
    assert "title_source" in body and "title_synced_at" in body, body
    assert '"user"' in body or "'user'" in body, body

    # The wording, and the line that paints it. Mutation `m8` deleted the
    # second and the first version of this test stayed green, which is the
    # same shape `m7` caught one assertion up.
    assert re.search(rf'const LOCAL_ONLY_MARKER\s*=\s*"{LOCAL_ONLY}";', text)
    assert re.search(
        r"\w+\.textContent\s*=\s*localOnly\(\w+\)\s*\?\s*LOCAL_ONLY_MARKER", text
    ), "nothing renders the marker"


def test_the_page_does_not_re_derive_the_order() -> None:
    """Inherited (T16): ordering is the server's, on this page too."""
    for name in ("session.js", "terminal.js"):
        text = code_only(source(name))
        for shape in (".sort(", "localeCompare", "FLEET_STATE_ORDER"):
            assert shape not in text, f"{name}: {shape}"


def test_every_slot_the_scripts_fill_exists_in_the_markup() -> None:
    """A typo'd id is a slot that is silently never filled — and no scan of
    either file alone can see it, because each half is internally consistent.

    The scan follows the page's own indirection: `session.js` reaches a slot
    through `slot(id)` / `fill(id, value)` rather than calling
    `getElementById` at each site, so a scan that only knew the DOM call would
    have found nothing and passed. It asserted arrival first, which is how that
    was caught rather than shipped.
    """
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', markup))
    wanted = {
        identifier
        for name in ("session.js", "terminal.js")
        for identifier in re.findall(
            r"""(?:getElementById|slot|fill)\(\s*["']([^"']+)["']""", source(name)
        )
    }
    assert wanted != set(), "arrival: the scan found no slot to check"
    assert wanted <= ids, sorted(wanted - ids)


def test_the_keystroke_path_is_absent_and_says_so() -> None:
    """Principle 5: the browser cannot type into a pane yet, and it is shown.

    `POST_ROUTES` carries no path for `terminal_write` and `web/server.py` never
    **reads** the upgraded socket, so there is no browser→pane path in this tree
    at all (blocker **T19-c**). A terminal that silently swallowed keystrokes
    would be the "silent half-success" D29 forbids one page over, so input is
    disabled in the emulator and the reason is rendered.
    """
    text = source("terminal.js")
    assert "disableStdin: true" in text
    assert "INPUT_UNAVAILABLE" in text
    from shepherd.web import routes

    assert "terminal_write" not in set(routes.POST_ROUTES.values())


# ----- the failure paths the degrade and the socket each own ------------------


def function_body(text: str, name: str) -> str:
    """The body of a named function, by brace matching.

    `block_after(text, "try")` finds the *first* `try` in the file, which is a
    question about one function only. Every claim below is about a specific
    one, so the body is extracted by name first.
    """
    body = block_after(text, f"function {name}(")
    assert body is not None, f"no function {name} in this module"
    return body


def test_the_degrade_says_why_when_the_screen_cannot_be_read() -> None:
    """Review finding 5: the degrade's own failure mode was the blank pane it
    exists to prevent.

    `refreshScreen` was called with no `await` and no `.catch`, and had no error
    handling of its own: a failed fetch was an unhandled rejection that left the
    `<pre>` permanently empty, and `found: false` rendered `""` — which is
    indistinguishable from a pane that really is blank. Principle 5: an unknown
    is a value, said out loud.

    Three distinct outcomes, three distinct sentences, asserted apart:
    the request failed, the envelope said `ok: false`, and the pane was not
    found. None of them may be the empty string.
    """
    text = source("terminal.js")
    refresh = function_body(text, "refreshScreen")

    # The request itself is guarded, and the guard paints rather than swallows.
    assert "try" in refresh, refresh
    recovery = block_after(refresh, "catch")
    assert recovery is not None, "a failed fetch is still an unhandled rejection"
    assert re.search(r"\w+\.textContent\s*=\s*\w", recovery), recovery

    # `found: false` is a named state, never `""`.
    found = re.search(
        r"""\w+\.textContent\s*=\s*body\.data\.found\s*\?\s*body\.data\.text\s*:\s*(\S+?);""",
        refresh,
    )
    assert found is not None, refresh
    assert found.group(1) not in ('""', "''", "``"), "a blank pane is not an answer"

    # And the envelope's own failure is reported with the correlation id, which
    # is the only thing §13 lets the page say about a server-side error.
    assert "correlation_id" in refresh, refresh

    # Every sentence the degrade can paint is a module constant, so this file
    # is where the wording lives and a reviewer can grep for it.
    for constant in re.findall(r"\w+\.textContent\s*=\s*([A-Z_]{4,})", refresh):
        assert re.search(rf"^const {constant}\s*=", text, flags=re.MULTILINE), constant


def test_the_terminal_stream_has_a_failure_path() -> None:
    """Review finding 6: `onmessage` was wired and nothing else was.

    `web/server.py` answers **404** to a terminal upgrade for an orphaned owned
    row (T12's orphan), and a browser turns that into an `error` followed by a
    1006 `close` with no frame ever delivered. With only `onmessage` wired that
    is a blank `term` and no message at all — the same defect class as the
    vendor-absent case T19 *did* handle, on the path more likely to occur.

    The distinction asserted here is the one that matters to a human: a stream
    that **never** delivered a frame is a different fact from one that stopped,
    so the handler must read the frame count rather than say one thing for both.
    """
    text = source("terminal.js")
    opened = function_body(text, "openTerminal")

    for handler in ("socket.onerror", "socket.onclose"):
        assert handler in opened, f"{handler} is not wired"

    close_handler = block_after(opened, "socket.onclose")
    assert close_handler is not None
    # It branches on whether anything ever arrived, and both arms name a
    # constant rather than leaving the pane to speak for itself.
    named = re.findall(r"[A-Z][A-Z_]{4,}", close_handler)
    assert len(set(named)) == 2, close_handler
    for constant in set(named):
        assert re.search(rf"^const {constant}\s*=", text, flags=re.MULTILINE), constant

    # Arrival: the counter the branch reads is really incremented by a frame.
    message_handler = block_after(opened, "socket.onmessage")
    assert message_handler is not None
    counter = re.search(r"(\w+)\s*\+=\s*1", message_handler)
    assert counter is not None, message_handler
    assert counter.group(1) in close_handler, close_handler


def test_the_vendor_record_claims_only_what_is_proved() -> None:
    """Review finding 8: `VERSION.txt` listed a proof that does not exist.

    It said that among the things "asserted" on the browser path is *"a
    keystroke reaches the pane through `send-keys -H`"*. There is **no**
    browser→pane keystroke path in this tree — `POST_ROUTES` carries no
    `terminal_write`, `web/server.py` never reads the upgraded socket, and
    `test_the_keystroke_path_is_absent_and_says_so` asserts the absence one
    screen up. `send-keys -H` byte-exactness is real, at the `Runner` seam and
    the contract and the write path; it is simply not on the path that
    paragraph is about.

    A record that over-claims is the same defect as a test whose name promises
    more than its body, so it gets the same kind of gate.
    """
    manifest = (VENDOR_ROOT / "VERSION.txt").read_text(encoding="utf-8")
    assert "G-M3-6" in manifest, "arrival: this is the section under test"

    assert "a keystroke reaches the pane through" not in manifest
    # The blocker that explains *why* there is no such path, and the three
    # seams where the byte-exactness claim is actually proved.
    assert "T19-c" in manifest
    for proof in (
        "tests/runner/test_local.py",
        "tests/contracts/test_runner_contract.py",
        "tests/orchestration/test_write_policy.py",
    ):
        assert proof in manifest, proof


# ----- D67: the session view is the Flock's third pane ------------------------
#
# The view **relocates**; it is not deleted. What moves with it is D21's
# `next_actions` list, which §12 already placed in the Session view header —
# U7 fixes the card at four items, so the list has nowhere else to be. The
# stopped-row logic that used to live in `fleet.js` therefore lives here, and
# every rule it carried comes with it rather than being quietly dropped: RD6's
# labelled-and-inert unreachable kinds, N10's honest `[why?]`, §14's
# `nothing to do`, and G-M2-7's targetless `external`.

#: `const ACTION_MILESTONE = { resume: "M3", … }` — the table RD6 requires.
_MILESTONE_TABLE = re.compile(r"const\s+ACTION_MILESTONE\s*=\s*\{(.*?)\n\}", re.DOTALL)
_LIVE_TABLE = re.compile(r"const\s+LIVE_KINDS\s*=\s*\{(.*?)\n\}", re.DOTALL)
_ENTRY = re.compile(r"(\w+):\s*\"?([\w]+)\"?")


def session_code() -> str:
    """`session.js` with its comments removed, so prose cannot satisfy a scan."""
    return code_only(source("session.js"))


def session_function(name: str) -> str:
    """The text of one top-level function in `session.js`, up to the next one."""
    text = source("session.js")
    start = text.index(f"function {name}(")
    rest = text[start + 1 :]
    end = rest.find("\nfunction ")
    tail = rest.find("\nexport function ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


def test_the_session_pane_renders_why_and_every_action() -> None:
    """D67's successor to `test_stopped_row_renders_why_and_first_action`.

    The retired test asserted `stoppedRow` rendered `session-why` and
    `actions[0]` — **one** action, because a collapsed fleet row had space for
    one. The pane has space for the list, and §12 always said the list renders
    in the Session view header, so the successor asserts the property the
    redesign actually keeps: the `why`, and **every** action with its ordinal
    and the source it came from.
    """
    body = session_function("renderSession")
    assert "session-why" in body
    assert "actions[0]" not in body, "the pane renders the list, not its head"

    listing = session_function("actionList")
    assert "next_actions" in listing
    assert "index + 1" in listing
    assert "action-ordinal" in listing
    assert "action-source" in listing


def test_the_pane_labels_unreachable_action_kinds_rather_than_dropping_them() -> None:
    """RD6, relocated with the list it governs. `not yet`, with the milestone.

    This is the half a relocation most easily loses: the *list* is obviously
    load-bearing and moves, and the rules about what the buttons in it may claim
    are easy to leave behind. Totality is asserted, so a kind in neither table —
    the silent dead button — fails here.
    """
    text = source("session.js")
    milestone_match = _MILESTONE_TABLE.search(text)
    live_match = _LIVE_TABLE.search(text)
    assert milestone_match is not None, "RD6's table did not move with the list"
    assert live_match is not None, "the live-kind table did not move with the list"
    milestones = dict(_ENTRY.findall(milestone_match.group(1)))
    live = dict(_ENTRY.findall(live_match.group(1)))
    assert milestones == {
        "resume": "M3",
        "respawn": "M3",
        "retry": "M3",
        "escalate": "M4",
        "requeue": "M4",
        "reauth": "M4",
    }
    assert set(milestones) | set(live) == {kind.value for kind in NextActionKind}

    body = session_function("actionButton")
    assert "disabled" in body
    assert "not yet" in body
    assert ".title" in body


def test_the_panes_why_note_is_a_disclosure_not_a_verdict() -> None:
    """N10 / D34, relocated. A button that fires nothing is worse than none.

    `[why?]` expands the heuristic evidence the row already carries and says, in
    words, that the model verdict lane is not built in this build. It must not
    imply a verdict nobody computed.
    """
    text = source("session.js")
    body = session_function("whyNote")
    assert 'element("details"' in body
    assert "summary" in body
    assert "addEventListener" not in body

    note = re.search(r"MODEL_LANE_NOTE\s*=\s*\n?\s*\"([^\"]+)\"", text)
    assert note is not None, "the honest note is a named constant"
    wording = note.group(1).lower()
    assert "not built" in wording or "not available" in wording
    assert "model" in wording


def test_the_pane_is_mounted_in_the_flocks_third_pane() -> None:
    """D67. The view relocates rather than being deleted.

    `terminal.js` and the vendored emulator stay reachable from it — which is
    the whole difference between *relocated* and *removed*, and the reason the
    import below is asserted rather than assumed.
    """
    text = source("session.js")
    assert 'from "./terminal.js"' in text
    assert "openTerminal(" in session_code()
    # The relocation itself: opening a session walks the Flock's drill-down to
    # its third level. The pane's *markup* moves in the shell; what has to be in
    # this module is the fact that it knows it is a pane rather than a page.
    assert 'from "./flock.js"' in text
    assert 'showLevel("detail")' in session_code()


def test_the_pane_builds_its_nodes_through_the_flocks_helper() -> None:
    """One `element(tag, class, text)`, not a second copy of it.

    `session.js` used to build its own nodes with `document.createElement` and
    a hand-written `textContent` line each time. Two helpers doing the same
    thing under different names is how one of them acquires a sink and the
    escaping scan keeps passing on the other.
    """
    text = source("session.js")
    assert "import { element, showLevel }" in text
    body = session_code()
    assert "document.createElement(" not in body.replace(
        'document.createElement("input")', ""
    ), "every node but the rename input comes from the shared helper"
