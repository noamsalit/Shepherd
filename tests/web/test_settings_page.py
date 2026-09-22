"""T7.2 — U13's Settings page: ten sections, four of them real.

**What this file proves and what it does not.** It proves that ten sections
exist under the two headings U13 names, that every unbuilt one carries a `not
built` chip **and says why in its panel**, that D25's audit whitelist is exactly
four fields, and that D65's autonomy control is here and U12's two options are
words rather than D8's numbers. It does **not** prove that any placeholder
section does anything — nine of ten were never built, and six of them are
labelled as such. That is the phase's stated limit, not an omission.

**Seam.** The same one every module in `tests/web/` uses: bytes on disk (the
shipped static files, parsed and never executed) plus real HTTP through
`invoke()` against a live loopback server. There is no browser here — the
browser-level evidence for this page is `tools/render_check.py` over
`fixtures/shell_harness.html`, recorded in the ledger.
"""

from __future__ import annotations

import re

from web.conftest import Client, MasterDoubles
from web.test_chat_page import field_reads, page_ids, page_root
from web.test_frontend_escaping import unsafe_sinks
from web.test_session_page import (
    FIXTURES,
    STATIC_ROOT,
    block_after,
    code_only,
    html_sink_findings,
    source,
)
from web.test_session_wiring import assignments

from shepherd.toolsurface.audit import encode_audit_record
from shepherd.toolsurface.types import ActorKind, AuditRecord, BlastClass


def settings_root() -> str:
    return page_root("settings")


def _audit_record() -> AuditRecord:
    """One decided call, as `invoke()` builds it. Only its **key list** is used."""
    return AuditRecord(
        at="2026-09-16T10:00:30Z",
        correlation_id="c-1",
        actor_kind=ActorKind.HUMAN,
        actor_id="web",
        tool="kill_session",
        blast_class=BlastClass.LOCAL_DESTRUCTIVE,
        args={"target": "shp-1"},
        autonomy_level=2,
        decision="allow",
        approved_by="user",
        approval_id="ap-1",
        result="ok",
        failure=None,
        duration_ms=3,
    )


# ----- U13: ten sections, two headings ----------------------------------------


#: U13, transcribed from `docs/design/ui-decisions.md` and **not** from the
#: module: *Yours* (Account, Notifications, API keys) and *This instance*
#: (Autonomy, Shepherd, Discovery, Limits, Users & access, Data, System). A
#: list read back out of `settings.js` would agree with it by construction.
REQUIRED_SECTIONS = (
    ("Yours", "Account"),
    ("Yours", "Notifications"),
    ("Yours", "API keys"),
    ("This instance", "Autonomy"),
    ("This instance", "Shepherd"),
    ("This instance", "Discovery"),
    ("This instance", "Limits"),
    ("This instance", "Users & access"),
    ("This instance", "Data"),
    ("This instance", "System"),
)

#: The four sections that read a real endpoint today. Everything else is a
#: placeholder and is required to say so — see the `not built` test below.
BUILT_SECTIONS = frozenset({"Autonomy", "Discovery", "Data", "System"})

_SECTION = re.compile(
    r"\{\s*id:\s*\"(?P<id>[^\"]+)\",\s*"
    r"group:\s*(?P<group>[A-Z_]+),\s*"
    r"title:\s*\"(?P<title>[^\"]+)\",\s*"
    r"built:\s*(?P<built>true|false),\s*"
    r"lead:\s*\"(?P<lead>[^\"]*)\",\s*"
    r"why:\s*(?P<why>\"[^\"]*\"|null)",
    re.DOTALL,
)

_GROUPS = {"YOURS": "Yours", "INSTANCE": "This instance"}


def sections() -> list[dict[str, str | bool]]:
    """`SECTIONS` in `settings.js`, parsed. The table *is* the page (U13)."""
    found = []
    for match in _SECTION.finditer(code_only(source("settings.js"))):
        found.append(
            {
                "id": match.group("id"),
                "group": _GROUPS[match.group("group")],
                "title": match.group("title"),
                "built": match.group("built") == "true",
                "lead": match.group("lead"),
                "why": None if match.group("why") == "null" else match.group("why")[1:-1],
            }
        )
    return found


def test_the_section_parser_reads_the_whole_table() -> None:
    """The parser above is the input to four tests; a broken one passes them."""
    parsed = sections()
    assert len(parsed) == 10, [row["title"] for row in parsed]
    assert parsed[0]["id"] != "", parsed[0]
    assert all(row["title"] != "" for row in parsed), parsed


def test_settings_is_ten_sections_under_two_headings() -> None:
    """U13, in order, compared as a whole sequence.

    A set comparison would pass on a page that printed *Data* above *Account*;
    the order is the reading order and it is part of the decision.
    """
    parsed = sections()
    assert tuple((row["group"], row["title"]) for row in parsed) == REQUIRED_SECTIONS


def test_every_unbuilt_section_carries_a_chip_and_says_why() -> None:
    """U13: *anything unbuilt carries a `not built` chip and says why*.

    Both halves, because either alone is the failure mode: a chip with no
    explanation is a dead end, and an explanation with no chip reads as a
    feature that is merely empty. The length floor is there because `""` and
    `"TODO"` both satisfy "says why" on a check that only asked for truthiness.
    """
    parsed = sections()
    unbuilt = [row for row in parsed if not row["built"]]
    assert len(unbuilt) == 6, [row["title"] for row in unbuilt]
    assert {row["title"] for row in parsed if row["built"]} == BUILT_SECTIONS

    for row in unbuilt:
        assert isinstance(row["why"], str), row
        assert len(row["why"]) >= 40, row
    # …and a built section carries no reason, because there is nothing to excuse.
    for row in parsed:
        if row["built"]:
            assert row["why"] is None, row

    settings = source("settings.js")
    # The chip's two halves: the class `app.css` styles, and the words U13 chose.
    assert '"soon"' in settings, "the `not built` chip has no class"
    assert '"not built"' in settings, "the chip does not say `not built`"
    assert '"notbuilt"' in settings, "the panel has no place for the reason"


def test_shepherd_uninstall_is_absent_from_the_ui_entirely() -> None:
    """U13's last clause, asserted because *absent* is not a thing you can see."""
    assert "uninstall" not in source("settings.js").lower()
    assert "uninstall" not in settings_root().lower()


# ----- D65 + U12: the autonomy control, in words --------------------------------


#: U12, verbatim from `docs/design/ui-decisions.md`.
ASK_SENTENCE = "Ask me before anything leaves this machine"
AUTO_SENTENCE = "Approve automatically"

_OPTION_TEXT = re.compile(r"(?:label|note):\s*\"([^\"]*)\"")

#: `const AUTONOMY_OPTIONS = [ … ];` — the whole array, not the first object in
#: it. `block_after` balances braces and would stop at the first option, which
#: is a prefix that passes "the sentence is here" and misses the other one.
_OPTIONS_TABLE = re.compile(r"const AUTONOMY_OPTIONS = \[(.*?)\n\];", re.DOTALL)


def test_the_autonomy_options_are_words_and_never_numbers() -> None:
    """U12: D8's scale starts at 2 for reasons the spec never justifies.

    The numbers are in the module, because `set_autonomy_level` takes an
    integer — and they are proved to stay out of the *rendering* by scanning
    every label and note the option table can display for a digit. A rule
    written as "don't show the number" and checked by reading is a rule that
    comes back; this one fails on `"Level 2 — ask me"`.
    """
    settings = code_only(source("settings.js"))
    assert "const LEVEL_ASK = 2;" in settings, "D8's asking level is not named"
    assert "const LEVEL_AUTO = 3;" in settings, "D8's auto level is not named"

    table = _OPTIONS_TABLE.search(settings)
    assert table is not None, "the two options are not a table"
    options = table.group(1)
    assert options.count("level:") == 2, options
    displayed = _OPTION_TEXT.findall(options)
    assert len(displayed) == 4, displayed
    assert ASK_SENTENCE in displayed, displayed
    assert AUTO_SENTENCE in displayed, displayed
    for text in displayed:
        assert not any(character.isdigit() for character in text), text

    # U12's second clause: the auto option states that auto-approved is never
    # unlogged. The wording is free; the two things it must name are not.
    auto_note = [text for text in displayed if "log" in text]
    assert auto_note != [], displayed
    assert any("audit" in text for text in auto_note), auto_note


def test_the_autonomy_route_is_read_and_written_through_invoke(
    client: Client, master_doubles: MasterDoubles
) -> None:
    """D8's toggle, over the socket a browser has — moved here by D65.

    It used to live in `test_chat_page.py`. The level is readable before it is
    written and the write reports what it moved from, so a `set_autonomy_level`
    that answered without moving anything is a different failure from a route
    that resolved to the wrong tool.
    """
    assert client.request("/api/autonomy").json()["data"] == {"level": 2}
    moved = client.post("/api/autonomy", {"level": 3})
    assert moved.status == 200, moved.body
    assert moved.json()["data"] == {"level": 3, "previous": 2}
    assert client.request("/api/autonomy").json()["data"] == {"level": 3}


# ----- U6 + D25: the audit tail, moved, with its whitelist intact ---------------


#: D25's four, and no fifth. `args` is **deliberately** excluded: the record
#: carries them redacted for the *log*, and a page is a wider audience than a
#: log.
AUDIT_WHITELIST = frozenset({"at", "tool", "decision", "approved_by"})


def test_the_audit_tail_shows_four_fields_and_never_the_arguments() -> None:
    """The whitelist survived the move from `chat.js` to Settings → Data.

    The producer is **called**, so a record that stopped carrying `args` would
    fail the arrival rather than silently making the exclusion vacuous.
    """
    record_keys = frozenset(encode_audit_record(_audit_record()))
    assert "args" in record_keys, "arrival: the record really carries the arguments"
    assert AUDIT_WHITELIST <= record_keys, sorted(AUDIT_WHITELIST - record_keys)

    read = field_reads(source("settings.js"), "record")
    assert read == AUDIT_WHITELIST, sorted(read.symmetric_difference(AUDIT_WHITELIST))
    assert "args" not in read


def test_the_audit_route_answers_through_invoke(client: Client) -> None:
    """The tail's endpoint, over the socket — D25's literal tail, newest first."""
    body = client.request("/api/audit").json()
    assert body["ok"] is True, body
    assert set(body["data"]) == {"records", "limit"}, sorted(body["data"])
    assert isinstance(body["data"]["records"], list)


# ----- §13: no HTML sink, with the negative control ---------------------------


def test_the_settings_page_has_no_html_sink() -> None:
    """F6: `panelHead` is the one of the prototype's eight sinks that is ours.

    The prototype assigned the panel heading through `innerHTML`. It is built
    with `createElement` here, so the expected number of sinks on this page is
    **zero** — and the scan is proved to see one by running the same functions
    over `fixtures/pty_sinks.js`, which plants five.
    """
    settings = source("settings.js")
    assert "textContent" in settings, "arrival: the page renders no text at all"
    assert len(settings.splitlines()) > 100, len(settings.splitlines())

    assert html_sink_findings(settings) == []
    assert unsafe_sinks(settings) == []

    planted = (FIXTURES / "pty_sinks.js").read_text(encoding="utf-8")
    assert html_sink_findings(planted) != [], "the sink scan no longer sees a sink"
    assert unsafe_sinks(planted) != [], "the escaping scan no longer sees one"

    # …and the heading the prototype built with a sink is built as nodes.
    head = block_after(code_only(settings), "function panelHead")
    assert head is not None, "the rewritten `panelHead` is not a function"
    assert "innerHTML" not in head, head
    assert "el(" in head, head


def test_the_settings_page_asks_again_for_nothing() -> None:
    """§12: no polling anywhere in the UI. The stream is the update mechanism.

    `test_rail_updates_from_sse_not_polling` went with the rail; the rule did
    not. Every read on this page is caused by the first paint or by a click.
    """
    settings = code_only(source("settings.js"))
    assert "fetch(" in settings, "arrival: the page makes no call at all"
    for shape in ("setInterval", "setTimeout", "requestAnimationFrame", "EventSource"):
        assert shape not in settings, shape


# ----- the renders, enumerated ------------------------------------------------


#: Every assignment `settings.js` is required to perform, by the same rule
#: `test_session_wiring.assignments` applies to page 3 and `test_chat_page`
#: applies to page 1: a single-line `target = value;` that is not a declaration,
#: compared as a **whole set**.
REQUIRED_SETTINGS_ASSIGNMENTS = {
    # Principle 5's em dash, in the one place every slot goes through.
    "element.textContent = textOf(value)",
    # `el(tag, className, text)`: the one node constructor, text as text (§13).
    "element.className = className",
    "element.textContent = text",
    # A `<button>` with no `type` inside a form submits it.
    'element.type = "button"',
    # Which section is open. The nav and the panel are rendered from it, so a
    # click is one assignment and one re-render rather than two DOM edits that
    # can disagree.
    "state.section = id",
    "item.onclick = () => open(row.id)",
    # D8's two level writes, and they are two on purpose: one is what the first
    # paint read and one is what the route reported after a click. Folding them
    # into a single site would make an optimistic render — the page showing the
    # level it asked for rather than the level the daemon confirmed.
    "state.level = autonomy.level",
    "state.level = data.level",
    "pick.onclick = () => choose(option.level)",
    # What the other two reads brought back, held so a re-render does not
    # re-ask — which is the polling §12 forbids, arriving by the back door.
    "state.audit = audit.records",
    "state.fleet = fleet",
    # The phone drill-down: `.panes2` shows the list or the panel, never both.
    'root.dataset.level = "detail"',
    'root.dataset.level = "list"',
    "back.onclick = () => showList()",
}


def test_render_settings_performs_every_assignment_the_spec_requires() -> None:
    performed = assignments(source("settings.js"))
    assert performed != [], "arrival: the enumeration read no assignment at all"
    assert len(performed) == len(set(performed)), "a duplicated render"
    assert set(performed) == REQUIRED_SETTINGS_ASSIGNMENTS, {
        "missing": sorted(REQUIRED_SETTINGS_ASSIGNMENTS - set(performed)),
        "unexpected": sorted(set(performed) - REQUIRED_SETTINGS_ASSIGNMENTS),
    }


# ----- the shell contract, against the committed harness ----------------------


def test_every_id_the_settings_page_ships_is_wired_by_the_script() -> None:
    """Slots ⊆ markup **and** markup ⊆ slots, the mirror M3 needed."""
    ids = page_ids(settings_root())
    assert len(ids) >= 3, sorted(ids)

    settings = source("settings.js")
    wired = set(re.findall(r"""(?:slot|fill)\(\s*["']([^"']+)["']""", settings))
    assert ids - wired == set(), sorted(ids - wired)
    assert wired - ids == set(), sorted(wired - ids)


def test_the_settings_root_renders_its_own_name_before_the_script_runs() -> None:
    """`tools/render_check.py` asserts each page shows its own name.

    Both containers ship empty, so the name has to be in the static markup — a
    page whose name arrives with the first fetch is a page the nav is lying
    about until the daemon answers.
    """
    root = settings_root()
    assert "Settings" in root, root
    assert re.search(r'id="settings-nav">\s*</div>', root) is not None, root
    assert re.search(r'id="settings-panel">\s*</div>', root) is not None, root

    # Found in a browser, not by reading: `.col-head` carries
    # `text-transform: uppercase`, and Playwright's `inner_text()` returns the
    # **transformed** text — so a name in a `.col-head` reads as `SETTINGS` and
    # `render_check.py` reports the page as missing its own name. The first
    # version of this markup did exactly that and the tool caught it.
    stylesheet = (STATIC_ROOT / "app.css").read_text(encoding="utf-8")
    head = re.search(r"\.col-head \{[^}]*\}", stylesheet)
    assert head is not None and "text-transform: uppercase" in head.group(0), head
    titled = re.findall(r'<[^>]*class="([^"]*)"[^>]*>\s*Settings\s*<', root)
    assert titled != [], root
    for classes in titled:
        assert "col-head" not in classes.split(), classes
        assert "set-group" not in classes.split(), classes


#: The class contract this page takes from `app.css`. Checked in both
#: directions: a name the page writes and the stylesheet does not know is an
#: unstyled node on a dark page, and a rule the page never writes is dead CSS.
SETTINGS_CLASSES = (
    "set-group",
    "set-item",
    "soon",
    "set-body",
    "set-lead",
    "notbuilt",
    "rows",
    "row",
    "row-text",
    "row-name",
    "row-note",
    "row-ctl",
    "opt",
    "facts",
    "audit",
    "audit-row",
    "audit-when",
    "audit-what",
    "src",
    "src-provider",
    "src-dot",
    "src-state",
)


def test_every_class_the_settings_page_renders_has_a_rule_in_the_stylesheet() -> None:
    settings = source("settings.js")
    stylesheet = (STATIC_ROOT / "app.css").read_text(encoding="utf-8")
    for name in SETTINGS_CLASSES:
        assert f'"{name}"' in settings, name
        assert f".{name}" in stylesheet, name

    # The decision's two outcomes wear the stylesheet's own two colours, so a
    # rejected call does not read as an allowed one.
    for name in ("audit-yes", "audit-no"):
        assert f'"{name}"' in settings, name
        assert f".{name}" in stylesheet, name


def test_the_settings_module_is_scanned_by_the_escaping_gate() -> None:
    """A gate widened by name, not by glob — the rule the list already states."""
    from web.test_frontend_escaping import EXPECTED_MODULES

    assert "settings.js" in EXPECTED_MODULES
    assert (STATIC_ROOT / "settings.js").is_file()
