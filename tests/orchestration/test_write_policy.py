"""T13: the write-policy table, and the proof that a refusal sends nothing.

**Totality is a set equality, never a length.** `len(WRITE_RULES) == 96` passes
while a `input_empty=False` row is dropped and another duplicated — the exact
defect that lets bytes into a pane the policy meant to refuse. So the key set is
compared against `itertools.product` and the length is only ever asserted
*against that set's size*.

**The expected decisions come from the plan, parsed.** The table in
`docs/plans/2026-09-17-m3-owned-sessions-plan.md` is read out of the document and
turned into expectations, so this file cannot agree with the module by
construction: the source of truth is prose a human wrote, not the code under
test.

**The refusal proof asserts arrival before absence.** "No bytes were sent" passes
just as well when the caller never got that far, which is this repo's dominant
defect class. Every refusal case first asserts that the pane was really read
through a counting `run_argv` and that the decision really came back, and only
then that no key-delivering verb appears in any argv.

**The reference caller lives here, not in `write_policy.py`.** The module is pure
and sends nothing; `attempt_delivery` below is the smallest caller that can hold
a refusal, and it is what T14's `orchestration/mailbox.py` must match. The
planted-mutation proofs are planted in it.
"""

from __future__ import annotations

import dataclasses
import itertools
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from shepherd.core.anomalies import Anomaly
from shepherd.core.mailbox import MailboxMessage, MailboxOrigin
from shepherd.core.runner import (
    PaneKind,
    PaneState,
    RunnerHandle,
    SessionSpec,
    WriteDecision,
)
from shepherd.core.states import Ownership, SessionState
from shepherd.orchestration.write_policy import (
    WRITE_RULES,
    WriteKey,
    decide_write,
    refusal_text,
)
from shepherd.runner.local import CommandResult, LocalRunner
from shepherd.runner.pane import parse_pane_fields

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"
TMUX_TUI = PROBES / "tmux-tui"
RUN = TMUX_TUI / "run-20260914T154946Z"
SUPP3 = TMUX_TUI / "supp3-20260914T160052Z"
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"
PLAN = REPO_ROOT / "docs" / "plans" / "2026-09-17-m3-owned-sessions-plan.md"
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "write_policy.py"

#: The 4-tuple key space, stated here as the plan states it: 4 x 6 x 2 x 2.
KEY_SPACE = 96

#: `test_decide_write_never_raises`' population, stated so the generator cannot
#: shrink to nothing without this number disagreeing with the generated one.
NEVER_RAISES_CASES = 576

TMUX = "tmux"
SOCKET = "shepherd-m3-t13"
NAME = "shepherd_01J9ZQ8T4E7WQ2B6M0X3YKV5RD"
SPOT = f"={NAME}:"
HANDLE = RunnerHandle(runner="local", socket=SOCKET, session_name=NAME)

#: The format-field line every capture in this file is classified against, taken
#: from `14-list-sessions-after-sigterm.txt`'s live `probe_a` row: on the
#: alternate screen, not dead, 160x45.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"

#: `14-list-sessions-after-sigterm.txt`, `probe_sig`: dead, status 143.
DEAD_FIELDS = "0|1|143||160|45|4042531"

#: `01-trust-dialog-fmt.txt`: the trust screen is **not** on the alternate
#: screen, and classifying it against a live pane's fields makes it `BUSY` —
#: which is why the fields travel with the capture here rather than defaulting.
TRUST_FIELDS = "0|0||<redacted: host name>|160|45|4041880"

#: The body a delivery would write. Never a substring of any capture, so "the
#: body never reached an argv" is a real search and not a coincidence.
BODY = "SHEPHERD-T13-BODY-NEVER-SENT"

#: `send-keys -t <target> C-u`, verbatim from the capture that proved `C-u`
#: clears a history-recalled prompt (`keys-claude-20260914T180105Z/steps.log`
#: l.7, `01-after-raw-up.txt` -> `01b-after-ctrl-u.txt`). A tmux **key name**,
#: not `-l` literal text.
CLEAR_ARGV = [TMUX, "-L", SOCKET, "send-keys", "-t", SPOT, "C-u"]

#: Every tmux verb or argument that can put a byte into a pane. Asserted as a
#: set rather than the one verb a mock would expect: a stray `Enter` through
#: `paste-buffer` leaves a `writes == []` double green.
KEY_DELIVERING = ("send-keys", "paste-buffer", "Enter")


def capture(path: Path) -> bytes:
    return path.read_bytes()


PERMISSION = capture(RUN / "06-permission-dialog.ansi")
TRUST = capture(RUN / "01-trust-dialog.ansi")
READY = capture(RUN / "03-after-stop.ansi")
GHOST = capture(SUPP3 / "A1-suggestion.ansi")
DRAFT = capture(SUPP3 / "A2-typed-over-suggestion.ansi")


def pane_state(raw: bytes, fields: str = LIVE_FIELDS) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    from shepherd.runner.pane import read_pane

    return read_pane(raw, parse_pane_fields(fields), [])


def synthetic(kind: PaneKind, *, input_text: str) -> PaneState:
    """A key the six checked-in captures cannot reach (`BUSY`, `DEAD`,

    `UNREADABLE`, and the non-empty variants of the dialogs). The **kind** is
    still a classifier output — only the combination is assembled here, because
    the key space is 96 and this repo has captures for four of its cells.
    """
    return dataclasses.replace(pane_state(READY), kind=kind, input_text=input_text)


# ----- the double -------------------------------------------------------------


class Recorder:
    """A counting `run_argv`: every argv, and a queue of capture answers.

    Not a mock with expectations. It records, so a test can say "the delivery
    reached its read" **before** it says "and nothing was sent".
    """

    def __init__(self, captures: Sequence[bytes], listing_fields: str = LIVE_FIELDS) -> None:
        self.calls: list[list[str]] = []
        self.captures = list(captures)
        self.listing = f"{NAME}|{listing_fields}\n".encode()

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        if "capture-pane" in argv:
            answer = self.captures.pop(0) if self.captures else b""
            return CommandResult(rc=0, stdout=answer, stderr=b"")
        if "list-sessions" in argv:
            return CommandResult(rc=0, stdout=self.listing, stderr=b"")
        return CommandResult(rc=0, stdout=b"", stderr=b"")

    def verbs(self) -> list[str]:
        return [argv[3] for argv in self.calls if len(argv) > 3 and argv[0] == TMUX]


def driver_for(recorder: Recorder, anomalies: list[Anomaly] | None = None) -> LocalRunner:
    from shepherd.host.base import DetachedLaunch

    sink = anomalies if anomalies is not None else []
    return LocalRunner(
        socket=SOCKET,
        run_argv=recorder,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: "2026-09-17T00:00:00.000Z",
        spawn_argv=lambda spec: _never_spawned(spec),
        record_anomaly=sink.append,
        sink_dir=Path("/tmp"),
    )


def _never_spawned(spec: SessionSpec) -> list[str]:
    raise AssertionError(f"the write policy never spawns: {spec.session_id}")


# ----- the reference caller ---------------------------------------------------


def message() -> MailboxMessage:
    return MailboxMessage(
        id="msg-1",
        session_id="ses-1",
        idempotency_key="k-1",
        body=BODY,
        origin=MailboxOrigin.ORCHESTRATOR,
        queued_at="2026-09-17T00:00:00.000Z",
        delivered_at=None,
        delivery_attempts=0,
        last_refusal=None,
    )


@dataclass(frozen=True)
class Attempt:
    """What one delivery attempt decided, and the row it left behind."""

    decision: WriteDecision
    row: MailboxMessage


def attempt_delivery(
    driver: LocalRunner,
    handle: RunnerHandle,
    state: SessionState,
    ownership: Ownership,
    row: MailboxMessage,
    *,
    send_clear: Callable[[], None],
    re_read: bool = True,
) -> Attempt:
    """The smallest caller the policy admits — D45's order, and nothing else.

    Read the pane, decide, and **only then** send. `CLEAR_THEN_SEND` sends the
    captured `C-u`, re-reads, and proceeds only if the box is now empty; if it is
    not, the outcome is `REFUSE_INPUT_NOT_EMPTY` and the body is never written.
    `re_read` exists so a test can plant D45's defect and watch it bite.
    """
    pane = driver.pane(handle)
    decision = decide_write(state, pane, ownership)

    if decision is WriteDecision.CLEAR_THEN_SEND:
        send_clear()
        if re_read:
            pane = driver.pane(handle)
            if pane.input_text != "":
                decision = WriteDecision.REFUSE_INPUT_NOT_EMPTY

    if decision in (WriteDecision.SEND_NOW, WriteDecision.CLEAR_THEN_SEND):
        driver.write(handle, row.body.encode("utf-8"))
        driver.write(handle, b"\r")
        return Attempt(decision, dataclasses.replace(row, delivered_at="2026-09-17T00:00:01Z"))

    return Attempt(decision, dataclasses.replace(row, last_refusal=decision.value))


def assert_no_bytes(recorder: Recorder, body: str = BODY) -> None:
    """Absence, stated over every argv and every key-delivering form.

    The capture-proven `C-u` is the one exception, matched by **list equality**
    so that an extra argument, a different target or a second key still fails:
    clearing the box is not delivery, and the whole point of the re-read is that
    a clear which did not work delivers nothing.
    """
    hexed = [f"{byte:02x}" for byte in body.encode("utf-8")]
    for argv in recorder.calls:
        if argv == CLEAR_ARGV:
            continue
        for verb in KEY_DELIVERING:
            assert verb not in argv, argv
        assert body not in argv, argv
        assert not set(hexed).issubset(set(argv)), argv


# ----- the key set (P-M3-4) ---------------------------------------------------


def test_the_key_set_equals_the_product() -> None:
    """P-M3-4: totality as a **set equality**, never as a length.

    Goes red when `SessionState`, `PaneKind` or `Ownership` grows and the table
    does not, and red when a row is dropped or duplicated — including the
    dropped-plus-duplicated form a `len(...) == 96` assertion cannot see.
    `WriteDecision` is the **value** space: growing it cannot break totality.
    """
    product: set[WriteKey] = set(
        itertools.product(SessionState, PaneKind, Ownership, (False, True))
    )
    keys = [(rule.state, rule.pane, rule.ownership, rule.input_empty) for rule in WRITE_RULES]

    assert set(keys) == product
    # the length is asserted **against the set**, never against a literal
    assert len(WRITE_RULES) == len(product), "a duplicate key, or a missing one"
    assert len(keys) == len(set(keys)), "duplicate rows"
    # and the plan's arithmetic is checked against the enums, not transcribed
    assert len(product) == len(SessionState) * len(PaneKind) * len(Ownership) * 2 == KEY_SPACE


def test_refuse_input_not_empty_is_reachable_only_through_the_fourth_field() -> None:
    """The fourth key field is why the space is 96 and not 48.

    Collapsing `input_empty` would make every `CLEAR_THEN_SEND` row vanish, and
    with it the re-read whose failure is `REFUSE_INPUT_NOT_EMPTY`. Goes red if
    the table stops distinguishing a drafted input line from an empty one.
    """
    by_empty = {
        rule.input_empty
        for rule in WRITE_RULES
        if rule.decision is WriteDecision.CLEAR_THEN_SEND
    }
    assert by_empty == {False}, "CLEAR_THEN_SEND exists only where the box is not empty"

    collapsed = {(rule.state, rule.pane, rule.ownership) for rule in WRITE_RULES}
    assert len(collapsed) == KEY_SPACE // 2
    for state, pane, ownership in collapsed:
        answers = {
            rule.decision
            for rule in WRITE_RULES
            if (rule.state, rule.pane, rule.ownership) == (state, pane, ownership)
        }
        if (pane, ownership) == (PaneKind.PROMPT_READY, Ownership.OWNED) and state in (
            SessionState.STOPPED,
            SessionState.NEEDS_YOU,
        ):
            assert len(answers) == 2, (state, answers)


# ----- the table, read out of the plan ----------------------------------------


def _plan_table() -> dict[tuple[SessionState, PaneKind, bool], WriteDecision]:
    """The plan's own projection, parsed. An independent source of truth.

    The expected decisions are prose a human wrote in
    `2026-09-17-m3-owned-sessions-plan.md`, not values recomputed the way the
    module computes them. Goes red if the plan and the table disagree in either
    direction.
    """
    lines = PLAN.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| state \\ pane |"))
    header = [cell.strip() for cell in lines[start].strip("|").split("|")][1:]
    columns: list[tuple[PaneKind, tuple[bool, ...]]] = []
    for cell in header:
        text = cell.replace("`", "").strip()
        if text.startswith("PROMPT_READY"):
            columns.append((PaneKind.PROMPT_READY, (True,) if "non-empty" not in text else (False,)))
        elif text == "DEAD/UNREADABLE":
            columns.append((PaneKind.DEAD, (False, True)))
            columns.append((PaneKind.UNREADABLE, (False, True)))
        else:
            columns.append((PaneKind(text.lower()), (False, True)))

    assert len(columns) == 7, columns

    expected: dict[tuple[SessionState, PaneKind, bool], WriteDecision] = {}
    rows = lines[start + 2 : start + 2 + len(SessionState)]
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        state = SessionState(cells[0].replace("`", "").strip())
        values = cells[1:]
        index = 0
        for pane, empties in columns:
            raw = re.sub(r"[`*]|\(.*\)", "", values[index]).strip()
            for empty in empties:
                expected[(state, pane, empty)] = WriteDecision(raw.lower())
            if pane is not PaneKind.DEAD:
                index += 1
    return expected


def test_every_owned_key_matches_the_plans_table() -> None:
    """The 48 owned keys, against the plan's projection. 24 cells, both `input_empty`."""
    expected = _plan_table()
    assert len(expected) == KEY_SPACE // 2, len(expected)
    for (state, pane, empty), decision in sorted(expected.items(), key=lambda kv: str(kv[0])):
        got = decide_write(state, synthetic(pane, input_text="" if empty else "draft"), Ownership.OWNED)
        assert got is decision, (state, pane, empty, got)


def test_a_permission_dialog_refuses_in_every_state() -> None:
    """D44: the dialog is a different kind of `needs_you` than a question.

    Text sent into an open dialog is discarded and the `Enter` that follows
    selects `1. Yes` — a queued message would approve a tool the human never
    saw. Goes red if any state reintroduces §9's "needs_you -> write
    immediately" row for the dialog.
    """
    dialog = pane_state(PERMISSION)
    assert dialog.kind is PaneKind.PERMISSION_DIALOG, "the capture must still classify"
    for state in SessionState:
        for ownership in Ownership:
            assert decide_write(state, dialog, ownership) in (
                WriteDecision.REFUSE_DIALOG,
                WriteDecision.REFUSE_NO_PTY,
            )
        assert decide_write(state, dialog, Ownership.OWNED) is WriteDecision.REFUSE_DIALOG


def test_ghost_text_is_not_a_draft() -> None:
    """E-M3-5: the dim suggestion is not something the user typed.

    `A1-suggestion.ansi` has a ghost and an empty box -> `SEND_NOW`.
    `A2-typed-over-suggestion.ansi` has a real draft -> `CLEAR_THEN_SEND`. Goes
    red if `input_empty` is computed from the rendered line rather than from
    `PaneState.input_text`.
    """
    ghost = pane_state(GHOST)
    draft = pane_state(DRAFT)
    assert ghost.ghost_text is not None and ghost.input_text == ""
    assert draft.input_text != ""

    assert decide_write(SessionState.STOPPED, ghost, Ownership.OWNED) is WriteDecision.SEND_NOW
    assert (
        decide_write(SessionState.STOPPED, draft, Ownership.OWNED)
        is WriteDecision.CLEAR_THEN_SEND
    )


# ----- attached: 48 keys, one answer ------------------------------------------


def test_every_attached_key_refuses_with_no_pty() -> None:
    """All 48 attached keys, driven through `decide_write`, not read off the table.

    Goes red if one ownership cell drifts, and red if the lookup stops consulting
    `ownership` at all — which would give Shepherd a write path into a pane on
    the user's own socket (K6).
    """
    seen: set[WriteKey] = set()
    for pane_kind, empty in itertools.product(PaneKind, (False, True)):
        for state in SessionState:
            pane = synthetic(pane_kind, input_text="" if empty else "draft")
            assert (
                decide_write(state, pane, Ownership.ATTACHED) is WriteDecision.REFUSE_NO_PTY
            ), (state, pane_kind, empty)
            seen.add((state, pane_kind, Ownership.ATTACHED, empty))
    assert len(seen) == KEY_SPACE // 2

    rows = [rule for rule in WRITE_RULES if rule.ownership is Ownership.ATTACHED]
    assert len(rows) == KEY_SPACE // 2
    assert {rule.decision for rule in rows} == {WriteDecision.REFUSE_NO_PTY}


def test_an_attached_session_has_no_write_path() -> None:
    """The banner §9 renders, and the one decision behind it.

    An attached session's pane can be `PROMPT_READY` with an empty box — the
    single most writable key there is — and the answer is still `REFUSE_NO_PTY`.
    """
    ready = pane_state(READY)
    assert ready.kind is PaneKind.PROMPT_READY and ready.input_text == ""
    assert (
        decide_write(SessionState.STOPPED, ready, Ownership.ATTACHED)
        is WriteDecision.REFUSE_NO_PTY
    )
    assert decide_write(SessionState.STOPPED, ready, Ownership.OWNED) is WriteDecision.SEND_NOW


# ----- never raises -----------------------------------------------------------


def test_decide_write_never_raises() -> None:
    """Non-members included, fed through `cast` — not `Any`, so K4 holds.

    Goes red if a lookup falls off the end instead of degrading. The generated
    case count is asserted: a generator that shrinks to zero would otherwise
    leave this test green and empty.
    """
    states: list[SessionState] = [*SessionState, cast(SessionState, "no-such-state"), cast(SessionState, "")]
    kinds: list[PaneKind] = [*PaneKind, cast(PaneKind, ""), cast(PaneKind, "PROMPT_READY")]
    owners: list[Ownership] = [*Ownership, cast(Ownership, "owner")]
    drafts = ["", "draft", "   ", "✳"]

    cases = 0
    for state, kind, ownership, text in itertools.product(states, kinds, owners, drafts):
        decision = decide_write(state, synthetic(kind, input_text=text), ownership)
        assert isinstance(decision, WriteDecision)
        if state not in set(SessionState) or kind not in set(PaneKind) or ownership not in set(Ownership):
            assert decision is WriteDecision.REFUSE_NO_PTY, (state, kind, ownership)
        cases += 1
    assert cases == NEVER_RAISES_CASES, cases


# ----- P-M3-5: the refusal sends no bytes -------------------------------------


def clear_through(recorder: Recorder) -> Callable[[], None]:
    """The captured `C-u` argv, issued at the same command seam the driver uses."""

    def send_clear() -> None:
        recorder(list(CLEAR_ARGV))

    return send_clear


def test_a_refusal_sends_no_bytes() -> None:
    """P-M3-5: **all three** refusals, through `LocalRunner` + a counting `run_argv`.

    Arrival first — the pane was really read and the decision really came back
    with `last_refusal` stamped on the row — and only then absence. Goes red if a
    refusal is implemented as "send, then check", and cannot go green because
    nothing ran: the `capture-pane`/`list-sessions` pair is asserted on every
    case.
    """
    cases: list[tuple[str, bytes, str, SessionState, Ownership, WriteDecision]] = [
        ("dialog", PERMISSION, LIVE_FIELDS, SessionState.NEEDS_YOU, Ownership.OWNED,
         WriteDecision.REFUSE_DIALOG),
        ("trust", TRUST, TRUST_FIELDS, SessionState.STARTING, Ownership.OWNED,
         WriteDecision.REFUSE_DIALOG),
        ("attached", READY, LIVE_FIELDS, SessionState.STOPPED, Ownership.ATTACHED,
         WriteDecision.REFUSE_NO_PTY),
        ("dead", READY, DEAD_FIELDS, SessionState.STOPPED, Ownership.OWNED,
         WriteDecision.REFUSE_NO_PTY),
        ("input-not-empty", DRAFT, LIVE_FIELDS, SessionState.STOPPED, Ownership.OWNED,
         WriteDecision.REFUSE_INPUT_NOT_EMPTY),
    ]
    proved: set[WriteDecision] = set()

    for name, raw, fields, state, ownership, expected in cases:
        recorder = Recorder([raw, raw], listing_fields=fields)
        driver = driver_for(recorder)

        attempt = attempt_delivery(
            driver, HANDLE, state, ownership, message(), send_clear=clear_through(recorder)
        )

        # arrival: the delivery reached the refusal
        assert attempt.decision is expected, (name, attempt.decision)
        assert attempt.row.last_refusal == expected.value, name
        assert attempt.row.delivered_at is None, name
        assert recorder.verbs()[:2] == ["capture-pane", "list-sessions"], (name, recorder.verbs())

        # …and only then, absence
        assert_no_bytes(recorder)
        proved.add(expected)

    assert proved == {
        WriteDecision.REFUSE_DIALOG,
        WriteDecision.REFUSE_NO_PTY,
        WriteDecision.REFUSE_INPUT_NOT_EMPTY,
    }, "all three refusals, or the proof covers only the dialog cells"


def test_a_non_empty_input_line_clears_then_re_reads_before_sending() -> None:
    """D45/DP10: the re-read is the whole safety property.

    A `C-u` that did not work is indistinguishable from never having tried, so
    the pane is read **again** and the body follows only if the box is now
    empty. Goes red if the re-read is skipped and the text is concatenated onto
    somebody's half-written prompt.
    """
    recorder = Recorder([DRAFT, READY])
    driver = driver_for(recorder)

    attempt = attempt_delivery(
        driver, HANDLE, SessionState.STOPPED, Ownership.OWNED, message(),
        send_clear=clear_through(recorder),
    )

    assert attempt.decision is WriteDecision.CLEAR_THEN_SEND
    assert attempt.row.delivered_at is not None
    # order: read, clear, re-read, then the body
    assert recorder.verbs() == [
        "capture-pane", "list-sessions", "send-keys",
        "capture-pane", "list-sessions", "send-keys", "send-keys",
    ], recorder.verbs()
    assert recorder.calls[2] == CLEAR_ARGV
    body_hex = [f"{byte:02x}" for byte in BODY.encode("utf-8")]
    assert recorder.calls[5][3:7] == ["send-keys", "-H", "-t", SPOT]
    assert recorder.calls[5][7:] == body_hex, "the body, byte-exact, and only after the re-read"
    assert recorder.calls[6][7:] == ["0d"], "the Enter that submits it, as its own write"


def test_the_clear_is_useless_without_the_re_read() -> None:
    """The planted D45 defect, as a test: skip the re-read and the body lands.

    This is the mutation `test_a_non_empty_input_line_clears_then_re_reads_before_sending`
    exists to catch, run here deliberately so the guard is one that has been seen
    to bite rather than one that has been described.
    """
    recorder = Recorder([DRAFT, DRAFT])
    driver = driver_for(recorder)

    skipped = attempt_delivery(
        driver, HANDLE, SessionState.STOPPED, Ownership.OWNED, message(),
        send_clear=clear_through(recorder), re_read=False,
    )
    assert skipped.decision is WriteDecision.CLEAR_THEN_SEND
    assert skipped.row.delivered_at is not None, "the defect: the body went out"

    honest = Recorder([DRAFT, DRAFT])
    refused = attempt_delivery(
        driver_for(honest), HANDLE, SessionState.STOPPED, Ownership.OWNED, message(),
        send_clear=clear_through(honest), re_read=True,
    )
    assert refused.decision is WriteDecision.REFUSE_INPUT_NOT_EMPTY
    assert_no_bytes(honest)


# ----- evidence, purity, size -------------------------------------------------


def test_every_write_rule_cites_an_existing_section() -> None:
    """P-M3-16, both halves: the section exists, and so does every capture cited.

    Goes red if a row's `evidence` names a `data-schemas.md` section that is not
    in the document, or a capture path that is not on disk.
    """
    document = SCHEMAS.read_text(encoding="utf-8")
    headings = {line.lstrip("# ").strip() for line in document.splitlines() if line.startswith("#")}

    assert len(WRITE_RULES) == KEY_SPACE
    for rule in WRITE_RULES:
        section, _, rest = rule.evidence.partition(" · ")
        assert section in headings, f"{rule.state}/{rule.pane}: {section!r}"
        assert rest != "", (rule.state, rule.pane)
        for cited in re.findall(r"[\w./-]+\.(?:ansi|txt)", rest):
            # Resolved by name under `docs/probes/`, not by a joined path: the
            # one directory that holds the C-u capture is named
            # `keys-claude-<date>`, and `tests/signals/test_verdict.py`'s
            # model-id rule reads that substring in a `src/` literal as a model
            # identifier. The capture is real either way, so it is cited by the
            # name it has on disk rather than by working the rule around
            # (recorded as T13-3).
            assert list(PROBES.rglob(cited)), f"{rule.state}/{rule.pane}: {cited}"


def test_refusal_text_is_total_and_never_says_failed() -> None:
    """§12: what the UI renders. A refusal is a state, never a failure."""
    for decision in WriteDecision:
        text = refusal_text(decision)
        assert text and text == text.strip()
        for forbidden in ("failed", "failure", "error", "crash"):
            assert forbidden not in text.lower(), (decision, text)
    assert len({refusal_text(decision) for decision in WriteDecision}) == len(WriteDecision)
    # §9's banner wording for the 48 attached keys
    assert "read-only" in refusal_text(WriteDecision.REFUSE_NO_PTY)


def test_write_policy_reads_no_clock() -> None:
    """Pure: no clock, no store, no runner, and no sending.

    The source is read rather than the import graph walked, because a module that
    imports nothing today can grow an import inside a function tomorrow. Goes red
    if the policy starts timing out a dialog, which would make it impure and
    untestable as a table.
    """
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "datetime", "time.", "import time", "open(", "import os", "subprocess",
        "run_argv", "tmux_argv", "sqlite", "shepherd.store", "shepherd.runner",
    ):
        assert forbidden not in source, forbidden
    assert len(source.splitlines()) <= 200, len(source.splitlines())


def test_the_module_imports_only_downward() -> None:
    """§5.0: `orchestration/` is L3. A pure table needs L1 and nothing else."""
    source = MODULE.read_text(encoding="utf-8")
    imported = set(re.findall(r"^from (shepherd[\w.]*) import", source, re.MULTILINE))
    assert imported <= {"shepherd.core.runner", "shepherd.core.states"}, imported


@pytest.mark.parametrize("decision", sorted(WriteDecision, key=str))
def test_every_decision_the_table_can_return_has_a_rule(decision: WriteDecision) -> None:
    """The five decisions the table reaches, and the one it deliberately does not.

    `REFUSE_INPUT_NOT_EMPTY` is the **re-read's** outcome, never the table's —
    `test_a_refusal_sends_no_bytes` proves it reachable through the caller. Goes
    red if it is quietly wired into a row, which would refuse before `C-u` was
    ever tried.
    """
    reached = {rule.decision for rule in WRITE_RULES}
    if decision is WriteDecision.REFUSE_INPUT_NOT_EMPTY:
        assert decision not in reached
    else:
        assert decision in reached
