"""T6: the screen classifier, read against the checked-in captures only.

**No fixture copies.** Every byte this module classifies is read **by path** out
of `docs/probes/`, so a fixture can never drift from the capture it claims to be,
and no test here can be made green by editing evidence.

**Two capture forms, and the difference is the point.** `read_pane` consumes
`capture-pane -e -p` bytes — the `.ansi` files. A plain `-p` `.txt` capture is
cited here only as a **format field** (`14-list-sessions-after-sigterm.txt`) or as
a **negative** (`A1-suggestion.txt`), never as the positive example of a screen:
a `-p` capture cannot separate ghost text from a draft, and asserting a byte
shape production never produces is how revision 1's table went wrong.

**Populations are asserted, never implied.** The classification table is checked
against the directory listing (`*.ansi`), and the degradation loop asserts its
generated case count equals the constant it states — M2 shipped a "never raises"
claim whose loop could shrink silently and whose generator produced a fraction of
the cases it advertised.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.runner import PaneFields, PaneKind
from shepherd.runner.pane import (
    PANE_FORMAT,
    PANE_RULES,
    PERMISSION_MARKER,
    TRUST_MARKER,
    parse_pane_fields,
    read_pane,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui"
RUN = PROBES / "run-20260914T154946Z"
SUPP2 = PROBES / "supp2-20260914T155625Z"
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"

#: One row per `-e` capture in `run-20260914T154946Z`, with the format line the
#: run's own `*-fmt.txt` files and `14-list-sessions-after-sigterm.txt` recorded
#: for that pane, in `PANE_FORMAT` order. The host name `01-trust-dialog-fmt.txt`
#: carries as `pane_title` is redacted here exactly as `data-schemas.md` redacts
#: it — it is a host identifier, not session content, and no assertion reads it.
#:
#: `alternate_on`: `0` for the trust dialog (`01-trust-dialog-fmt.txt`), `1` once
#: the TUI is up (`02-after-trust-fmt.txt`, and the `probe_a` row of
#: `14-list-sessions-after-sigterm.txt`). Size `160x45` comes from that same row;
#: `70x30` for the resized pane from `09-resize-fmt.txt`.
DOCUMENTED: dict[str, tuple[PaneKind, str]] = {
    "01-trust-dialog.ansi": (PaneKind.TRUST_DIALOG, "0|0||<redacted: host name>|160|45|4041880"),
    "02-after-trust.ansi": (PaneKind.PROMPT_READY, "1|0||✳ Claude Code|160|45|4041880"),
    "03-after-stop.ansi": (PaneKind.PROMPT_READY, "1|0||✳ shp-probe-title-1|160|45|4041880"),
    "06-permission-dialog.ansi": (
        PaneKind.PERMISSION_DIALOG,
        "1|0||✳ shp-probe-title-1|160|45|4041880",
    ),
    "08-prompt-with-suggestion.ansi": (
        PaneKind.PROMPT_READY,
        "1|0||✳ shp-probe-title-1|160|45|4041880",
    ),
    "09-resize-after-70x30.ansi": (
        PaneKind.PROMPT_READY,
        "1|0||✳ shp-probe-title-1|70|30|4041880",
    ),
}

#: `14-list-sessions-after-sigterm.txt`, `probe_sig`: dead, status 143, no title.
DEAD_FIELDS_LINE = "0|1|143||160|45|4042531"

#: The three degraded inputs that are not truncations, plus every prefix of every
#: `-e` capture. Stated as a constant so the loop cannot shrink without this
#: number disagreeing with the generated one.
DEGRADED_CASES = 10778


def fields_for(name: str) -> PaneFields:
    return parse_pane_fields(DOCUMENTED[name][1])


def capture(name: str) -> bytes:
    return (RUN / name).read_bytes()


def sink() -> list[Anomaly]:
    return []


# ----- the table --------------------------------------------------------------


def test_every_ansi_capture_classifies_to_its_documented_kind() -> None:
    """The population is the directory listing, not a hand-written list.

    Goes red if a predicate is loosened enough to swallow a neighbour — the trust
    marker widened to match the permission screen, or the input-line structure
    weakened until a dialog looks ready for input — and red if a capture appears
    or disappears without a row here to say what it is.
    """
    on_disk = {path.name for path in RUN.glob("*.ansi")}
    assert on_disk == set(DOCUMENTED), on_disk.symmetric_difference(DOCUMENTED)
    assert len(on_disk) == 6

    for name, (kind, _) in sorted(DOCUMENTED.items()):
        anomalies = sink()
        state = read_pane(capture(name), fields_for(name), anomalies)
        assert state.kind is kind, f"{name}: {state.kind}"
        assert anomalies == [], f"{name}: a classified screen is not an anomaly"


def test_the_dialog_kinds_carry_the_text_that_identified_them() -> None:
    """A refusal a UI has to render needs the sentence it refused on."""
    trust = read_pane(capture("01-trust-dialog.ansi"), fields_for("01-trust-dialog.ansi"), sink())
    assert trust.dialog_text is not None and TRUST_MARKER in trust.dialog_text

    name = "06-permission-dialog.ansi"
    permission = read_pane(capture(name), fields_for(name), sink())
    assert permission.dialog_text is not None and PERMISSION_MARKER in permission.dialog_text


def test_dead_is_decided_by_pane_dead_alone() -> None:
    """`pane_dead == 1` is sufficient, and no pane capture is consulted.

    Goes red if the withdrawn text marker `Pane is dead (status ` creeps back as
    a detector: this repo has **no `-e` capture of a dead pane**, so a text rule
    for `DEAD` would assert a byte shape production never feeds `read_pane`. The
    second half is the same rule from the other side — the marker in a *live*
    pane's bytes must not make it dead.
    """
    dead = parse_pane_fields(DEAD_FIELDS_LINE)
    anomalies = sink()
    state = read_pane(b"", dead, anomalies)

    assert state.kind is PaneKind.DEAD
    assert state.fields.pane_dead_status == 143
    assert anomalies == [], "a dead pane carries a real exit status; it is not an unknown"

    marker = (RUN / "13-dead-pane.txt").read_bytes()
    alive = fields_for("03-after-stop.ansi")
    assert read_pane(marker, alive, sink()).kind is not PaneKind.DEAD


def test_busy_is_the_residual_and_cites_no_capture() -> None:
    """`BUSY` asserts no byte shape, and its row must say so.

    Goes red if someone points the row at `07-running-after-send.txt`: that is
    plain `-p` bytes, which production never feeds `read_pane`.
    """
    (busy,) = [rule for rule in PANE_RULES if rule.kind is PaneKind.BUSY]
    assert "derived" in busy.evidence
    assert ".ansi" not in busy.evidence and ".txt" not in busy.evidence
    assert "07-running-after-send" not in busy.evidence

    # …and the classifier agrees with the row: a live alternate screen with no
    # dialog and no input-line structure is what is left. Built by removing the
    # input line from `03-after-stop.ansi` — a derivation, not a capture.
    lines = capture("03-after-stop.ansi").split(b"\n")
    without_input = b"\n".join(line for line in lines if "❯ ".encode() not in line)
    assert without_input != b"\n".join(lines)
    assert read_pane(without_input, fields_for("03-after-stop.ansi"), sink()).kind is PaneKind.BUSY


# ----- ghost text -------------------------------------------------------------


def test_ghost_text_is_not_a_draft() -> None:
    """E-M3-5: the SGR-2 run in the input box is a placeholder, never input.

    Goes red if the dim split is dropped — `input_text` would then carry
    `cat hello.txt`, which is the exact trap `data-schemas.md` warns about, and
    the write policy would treat a suggestion as a draft the user typed.
    """
    fields = parse_pane_fields("1|0||✳ Claude Code|160|45|4041880")
    state = read_pane((SUPP2 / "A1-suggestion.ansi").read_bytes(), fields, sink())

    assert state.kind is PaneKind.PROMPT_READY
    assert state.ghost_text == "cat hello.txt"
    assert state.input_text == ""


def test_a_plain_capture_cannot_separate_ghost_from_input() -> None:
    """The negative, over the **same screen** in both capture forms.

    A future "optimisation" from `-e` to `-p` fails here rather than in
    production: with plain bytes the suggestion is indistinguishable from a
    draft, so nothing is reported as ghost and the text lands in `input_text`.
    """
    fields = parse_pane_fields("1|0||✳ Claude Code|160|45|4041880")
    plain = read_pane((SUPP2 / "A1-suggestion.txt").read_bytes(), fields, sink())

    assert plain.ghost_text is None
    assert plain.input_text == "cat hello.txt"

    ansi = read_pane((SUPP2 / "A1-suggestion.ansi").read_bytes(), fields, sink())
    assert ansi.ghost_text != plain.ghost_text and ansi.input_text != plain.input_text


# ----- the format line --------------------------------------------------------


def test_parse_pane_fields_reads_the_listing_the_format_prints() -> None:
    """Both observed shapes: an alive pane (empty status) and a dead one (143)."""
    assert PANE_FORMAT.count("|") == 6

    alive = parse_pane_fields(DOCUMENTED["03-after-stop.ansi"][1])
    assert alive.alternate_on is True
    assert alive.pane_dead is False
    assert alive.pane_dead_status is None  # empty while alive
    assert (alive.width, alive.height) == (160, 45)
    assert alive.pane_pid == 4041880

    dead = parse_pane_fields(DEAD_FIELDS_LINE)
    assert dead.pane_dead is True and dead.pane_dead_status == 143
    assert dead.pane_title is None  # empty on a dead pane


def test_a_format_line_that_does_not_parse_is_refused_rather_than_guessed() -> None:
    """Principle 5: a half-read listing is not a pane with default fields."""
    with pytest.raises(ValueError):
        parse_pane_fields("1|0|")


# ----- degradation ------------------------------------------------------------


def degraded_inputs() -> list[tuple[str, bytes]]:
    """Every prefix of every `-e` capture, plus three inputs that are not screens.

    Truncating **the whole capture** rather than its last line is the correction
    revision 2 made: `13-dead-pane.txt`'s last line is 49 bytes, so a last-line
    generator cannot reach 200 cases at all, and M2's version silently tested an
    absent file for most of the cuts it claimed.
    """
    cases: list[tuple[str, bytes]] = []
    for name in sorted(DOCUMENTED):
        raw = capture(name)
        cases += [(f"{name}[:{cut}]", raw[:cut]) for cut in range(len(raw) + 1)]
    cases.append(("empty", b""))
    cases.append(("non-utf8", b"\xff\xfe\x80\x00 not text"))
    try:  # a directory where a capture was expected: the bytes a caller that
        RUN.read_bytes()  # swallowed the read error would hand us
    except OSError as error:
        cases.append(("directory", str(error).encode("utf-8")))
    return cases


def test_read_pane_never_raises() -> None:
    """P-M3-9, with its population asserted rather than advertised.

    Every input returns a value; every input that could not be classified returns
    `UNREADABLE` **and counts `AnomalyKind.PANE_UNREADABLE`** with a detail
    string; a classified screen counts nothing. Goes red if any input escapes as
    an exception, or if the generated count disagrees with `DEGRADED_CASES`.
    """
    cases = degraded_inputs()
    assert len(cases) == DEGRADED_CASES
    assert len({name for name, _ in cases}) == DEGRADED_CASES
    assert DEGRADED_CASES > 200

    fields = fields_for("03-after-stop.ansi")
    unreadable = 0
    for name, raw in cases:
        anomalies = sink()
        state = read_pane(raw, fields, anomalies)
        assert isinstance(state.kind, PaneKind), name
        if state.kind is PaneKind.UNREADABLE:
            unreadable += 1
            assert [entry.kind for entry in anomalies] == [AnomalyKind.PANE_UNREADABLE], name
            assert anomalies[0].detail != "", name
        else:
            assert anomalies == [], name
    assert unreadable > 0


def test_the_unreadable_count_names_which_absence_it_saw() -> None:
    """One member, three detail strings — `TRANSCRIPT_TAIL_ABSENT`'s shape."""
    live = fields_for("03-after-stop.ansi")
    # The third absence needs a pane that is not on the alternate screen: with
    # `alternate_on == 1` unrecognisable text is the **residual** (`BUSY`), not an
    # unknown. `alternate_on == 0` and no dialog is the screen we cannot place.
    starting = fields_for("01-trust-dialog.ansi")
    details = set()
    for raw, fields in ((b"", live), (b"\xff\xfe\x80", live), (b"nothing recognisable\n", starting)):
        anomalies = sink()
        assert read_pane(raw, fields, anomalies).kind is PaneKind.UNREADABLE
        assert len(anomalies) == 1
        details.add(anomalies[0].detail)
    assert len(details) == 3, details


def test_read_pane_counts_nothing_when_no_sink_is_given() -> None:
    """The anomaly sink is optional; the classification never is."""
    fields = fields_for("03-after-stop.ansi")
    assert read_pane(b"", fields).kind is PaneKind.UNREADABLE


# ----- evidence ---------------------------------------------------------------


def test_every_pane_rule_cites_an_existing_section() -> None:
    """P-M3-16, both halves: the section exists, and so does every capture cited.

    Goes red if a row names a `data-schemas.md` section that is not in the
    document, or a capture path that is not on disk.
    """
    document = SCHEMAS.read_text(encoding="utf-8")
    headings = {line.lstrip("# ").strip() for line in document.splitlines() if line.startswith("#")}
    assert len(PANE_RULES) == len(PaneKind)
    assert {rule.kind for rule in PANE_RULES} == set(PaneKind)

    for rule in PANE_RULES:
        section, _, rest = rule.evidence.partition(" · ")
        assert section in headings, f"{rule.kind}: {section!r}"
        assert rest != "", rule.kind
        for cited in re.findall(r"[\w./-]+\.(?:ansi|txt)", rest):
            assert (PROBES / cited).exists(), f"{rule.kind}: {cited}"


def test_the_module_is_pure() -> None:
    """No I/O, no clock, no process: the captures come in as bytes.

    The source is read rather than the import graph walked, because a module that
    imports nothing today can grow an import inside a function tomorrow.
    """
    source = (REPO_ROOT / "src" / "shepherd" / "runner" / "pane.py").read_text(encoding="utf-8")
    for forbidden in ("import subprocess", "import os", "import time", "open("):
        assert forbidden not in source, forbidden
    assert len(source.splitlines()) <= 600
