"""T16: answering a permission dialog (D44), and the half of clause 4 T13 left.

**Every pane here comes out of the shipped classifier over a real capture**
(`runner.pane.read_pane`) — a screen this file typed itself would prove only
that the test and the classifier agree (`.cc10x/patterns.md`, "a test that
supplies its own input shape").

The two captures that carry this file are P4's, taken 2026-09-17:

* `02a-tab-dialog.ansi.txt` — the dialog as it is raised, `1. Yes` at position 1;
* `02b-tab-after.ansi.txt` — **the same dialog after `Tab`**, still up, with
  option 1 re-labelled `1. Yes, and tell Claude what to do next`.

`read_pane` classifies **both** as `PERMISSION_DIALOG` — asserted below, because
that is the whole reason this module has to match the text: a gate keyed on the
pane kind alone would send `3` at the second screen, where `3` is a position
nobody captured an outcome for, and a `1` there approves with a follow-up
instruction the human never wrote.

**Arrival before absence.** Every "no key was sent" assertion is preceded by an
assertion that the call reached the refusal that would have sent it — a zero
count is satisfied just as well by a call that never got that far.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.runner import (
    PaneKind,
    PaneState,
    ProcState,
    RunnerHandle,
    WriteDecision,
)
from shepherd.orchestration import dialog_keys, dialogs
from shepherd.orchestration.dialogs import (
    ALLOW_OPTION_PREFIX,
    DIALOG_EVIDENCE,
    PERMISSION_KEYS,
    TRUST_KEYS,
    DialogAnswer,
    SidecarState,
    answer_permission,
    answer_trust,
)
from shepherd.runner.base import PaneRef
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET, ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes"
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "dialogs.py"
KEYS_MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "dialog_keys.py"

P4 = PROBES / "2026-09-17-m3-tmux" / "p4-permission-20260917T110527Z"
RUN = PROBES / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"

#: P4's dialog, un-amended: `❯ 1. Yes` / `2. Yes, and always allow access to …`
#: / `3. No`, footer `Esc to cancel · Tab to amend`.
DIALOG = (P4 / "02a-tab-dialog.ansi.txt").read_bytes()
#: The same dialog **after `Tab`** — still up, option 1 re-labelled.
AMENDED = (P4 / "02b-tab-after.ansi.txt").read_bytes()
#: An idle prompt from the same run: a pane with no dialog at all.
IDLE = (P4 / "01-idle-prompt.ansi.txt").read_bytes()
#: The workspace-trust dialog: `❯ No, exit` then `Yes, I trust this folder`.
TRUST = (RUN / "01-trust-dialog.ansi").read_bytes()

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
#: The trust dialog is drawn on the **primary** screen (`alternate_on=0`), which
#: is half of its detector (`01-trust-dialog-fmt.txt`).
TRUST_FIELDS = "0|0||host|160|45|4041880"

SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
NAME = f"shepherd_{SESSION_ID}"
HANDLE = RunnerHandle(runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=NAME)

#: Every byte that can select an option or submit at either dialog. A set, not
#: the one key a mock would expect: `writes == []` is only meaningful if the
#: double records every byte, and `ScriptedRunner.write` does.
CHOICES: tuple[str, ...] = ("approve", "approve_always", "deny")


# ----- fixtures ---------------------------------------------------------------


def pane_state(raw: bytes, fields: str = LIVE_FIELDS) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(raw, parse_pane_fields(fields), [])


def runner(*panes: PaneState) -> ScriptedRunner:
    """A `ScriptedRunner` that owns exactly this file's one pane."""
    return ScriptedRunner(
        panes=panes,
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at="2026-09-17"
        ),
        screen=b"",
        owned_panes=(
            PaneRef(session_name=NAME, session_id=SESSION_ID, pane_pid=4041880, dead=False),
        ),
    )


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def counts(store: Store) -> dict[str, int]:
    return store.list_anomaly_counts()


def parametrised_cases(test: object) -> tuple[tuple[object, ...], ...]:
    """The argument rows a `@pytest.mark.parametrize` will actually generate.

    Read off the mark rather than retyped, so `test_the_*_loop_covers_*` below
    observe the loop instead of agreeing with a second copy of it. A single
    parameter is normalised into a one-tuple, as pytest does.
    """
    marks = [mark for mark in getattr(test, "pytestmark", []) if mark.name == "parametrize"]
    assert len(marks) == 1, marks
    rows = marks[0].args[1]
    return tuple(tuple(row) if isinstance(row, tuple) else (row,) for row in rows)


# ----- the fixtures are what this file says they are --------------------------


def test_both_captures_classify_as_a_permission_dialog() -> None:
    """The premise of the whole module, asserted rather than assumed.

    Goes red if a future `read_pane` learns to tell the two screens apart — at
    which point the gate below could be simplified, and should not be until
    this test says so.
    """
    assert pane_state(DIALOG).kind is PaneKind.PERMISSION_DIALOG
    assert pane_state(AMENDED).kind is PaneKind.PERMISSION_DIALOG
    assert pane_state(IDLE).kind is PaneKind.PROMPT_READY
    assert pane_state(TRUST, TRUST_FIELDS).kind is PaneKind.TRUST_DIALOG

    # …and the two dialogs really do differ in the one place the gate reads.
    dialog = pane_state(DIALOG).dialog_text or ""
    amended = pane_state(AMENDED).dialog_text or ""
    assert "\n ❯ 1. Yes\n" in dialog
    assert "\n ❯ 1. Yes\n" not in amended
    assert "1. Yes, and tell Claude what to do next" in amended


# ----- approve / approve_always / deny ----------------------------------------


def test_approve_sends_exactly_one_enter(store: Store) -> None:
    """D44's `approve`: the highlighted default is `1. Yes`, so Enter approves.

    Capture-proven at the un-amended dialog (`B-hooks.json`, `B-file-created.txt`:
    `PostToolUse` fired and `dialog-probe.txt exists: True`).

    Goes red on any extra key — including a "clear the line first" convenience,
    which at a dialog is discarded text followed by an approval.
    """
    driver = runner(pane_state(DIALOG))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert answer == DialogAnswer(decision=WriteDecision.SEND_NOW, reason=None, keys_sent=1)
    assert driver.writes == [b"\r"]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("approve", [b"\r"]), ("approve_always", [b"2"]), ("deny", [b"3"])],
)
def test_each_choice_sends_only_its_captured_key(
    store: Store, choice: str, expected: list[bytes]
) -> None:
    """P4's five rounds, as the three keys this module may send.

    `1` ran the tool (`perm-1.txt`), `2` ran it and allow-listed the directory
    (`perm-2.txt`), `3` did not run it — and the end-of-run listing is exactly
    those two files (`99-cwd-listing.txt`). Enter selects the highlighted `1`.

    Goes red if a guessed keystroke ships, or if any choice sends a second key.
    """
    driver = runner(pane_state(DIALOG))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice=choice,  # type: ignore[arg-type]
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.SEND_NOW
    assert driver.writes == expected


def test_the_parametrised_loop_covers_every_choice() -> None:
    """The case count, asserted — a loop that shrank would otherwise pass."""
    cases = {row[0] for row in parametrised_cases(test_each_choice_sends_only_its_captured_key)}
    assert cases == set(CHOICES) == set(PERMISSION_KEYS)
    assert len(cases) == 3


def test_deny_sends_the_captured_key(store: Store) -> None:
    """P4 closed `deny`: `send-keys -H 33`, and the tool did not run.

    Goes red if `deny` ever becomes `Esc` (the same *end state*, but a different
    key and one the caller cannot tell from an interrupt), or a guess.
    """
    driver = runner(pane_state(DIALOG))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.SEND_NOW
    assert driver.writes == [b"3"]
    assert PERMISSION_KEYS["deny"] == ("3",)


# ----- the headline: a re-labelled dialog is refused, not answered ------------


@pytest.mark.parametrize("choice", CHOICES)
def test_an_amended_dialog_is_refused_and_no_key_is_sent(store: Store, choice: str) -> None:
    """BLOCKER-T1-4, and the single most important check in this file.

    `Tab` leaves the dialog **up** with option 1 re-labelled, and Shepherd cannot
    see an amendment it did not make. A digit is positional, so at this screen
    `3` is a position with no captured outcome and Enter approves *with a
    follow-up instruction*. The only safe answer is to refuse.

    Goes red if the gate keys off `PaneKind.PERMISSION_DIALOG` alone — which is
    what `read_pane` returns for this very capture.
    """
    driver = runner(pane_state(AMENDED))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice=choice,  # type: ignore[arg-type]
        sidecar=SidecarState.WAITING,
    )
    # Arrival first: the refusal names the screen it read…
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.reason is not None and "amend" in answer.reason
    assert "pane" in driver.calls
    # …and only then, absence.
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_the_amended_loop_covers_every_choice() -> None:
    """The case count again: the refusal holds for all three, not for one."""
    cases = parametrised_cases(test_an_amended_dialog_is_refused_and_no_key_is_sent)
    assert tuple(row[0] for row in cases) == CHOICES
    assert len(CHOICES) == 3


def test_an_unrecognised_option_set_is_refused(store: Store) -> None:
    """P4 probed **only** the Bash dialog; other tools' option sets are `unknown`.

    A dialog whose options are not the captured three is refused for the same
    reason the amended one is: the digits are positional and nothing here knows
    what is at position 3. Built by replacing one option line in a **real**
    capture, so everything else on the screen is still the real screen.

    Goes red if the matcher only looks for the `Tab` re-label rather than
    requiring the whole captured option set.
    """
    text = (pane_state(DIALOG).dialog_text or "").replace("3. No", "3. No, and tell me why")
    driver = runner(dataclasses.replace(pane_state(DIALOG), dialog_text=text))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_a_fourth_option_is_refused(store: Store) -> None:
    """The option count is bounded above as well as below.

    Found by mutation: `len(options) == 3` -> `>= 3` survived, because the
    unrecognised-option-set case above still has exactly three. P4 probed **only**
    the Bash dialog and says outright that other tools raise other option sets,
    so a screen carrying a fourth option is a screen nobody has captured — and
    Enter selects whatever is highlighted, which on such a screen is unknown.

    Goes red if the upper bound is dropped.
    """
    text = (pane_state(DIALOG).dialog_text or "").replace(
        "   3. No", "   3. No\n   4. No, and tell Claude what to do next"
    )
    driver = runner(dataclasses.replace(pane_state(DIALOG), dialog_text=text))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_the_directory_in_option_two_is_not_pinned(store: Store) -> None:
    """Option 2 is directory-scoped, so its tail varies by cwd and must not pin.

    Goes red if the matcher hard-codes P4's own throwaway directory, which would
    refuse every real dialog on the machine.
    """
    text = (pane_state(DIALOG).dialog_text or "").replace(
        "/tmp/shp-m3-p4-vh9n71hn/work", "/home/someone/src/project"
    )
    assert ALLOW_OPTION_PREFIX in text
    driver = runner(dataclasses.replace(pane_state(DIALOG), dialog_text=text))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.SEND_NOW
    assert driver.writes == [b"3"]


# ----- the precondition -------------------------------------------------------


def test_answering_requires_a_permission_dialog_pane(store: Store) -> None:
    """An `Enter` at an ordinary prompt submits whatever is in the box.

    Goes red if the precondition is dropped: the pane here is the real idle
    prompt from the same P4 run.
    """
    driver = runner(pane_state(IDLE))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.reason is not None and PaneKind.PROMPT_READY.value in answer.reason
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_a_trust_dialog_is_not_a_permission_dialog(store: Store) -> None:
    """The two screens have different options and different keys (DP8).

    Goes red if `answer_permission` starts serving the trust screen, where a
    bare Enter selects `No, exit` and the process leaves with status 1.
    """
    driver = runner(pane_state(TRUST, TRUST_FIELDS))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.keys_sent == 0
    assert driver.writes == []


# ----- clause 4's remaining half: the sidecar ---------------------------------


def test_an_absent_sidecar_is_counted_not_assumed_clear(store: Store) -> None:
    """Acceptance clause 4, the half T13 could not close (T13-1).

    An absent sidecar is **counted**, never read as "no dialog open": it is the
    normal state during the trust dialog (`01-trust-dialog-sidecar.json` is
    literally `<absent: …>`), so inferring "clear" from it would answer a
    dialog Shepherd cannot see.

    Goes red if the gate treats `ABSENT` as clear, and — separately — if it
    refuses without counting, which is the silent half of the same defect.
    """
    assert counts(store).get(AnomalyKind.SIDECAR_ABSENT.value) is None

    driver = runner(pane_state(DIALOG))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.ABSENT,
    )
    # Arrival: the refusal names the sidecar, and it was counted…
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.reason is not None and "sidecar" in answer.reason
    assert counts(store)[AnomalyKind.SIDECAR_ABSENT.value] == 1
    # …then absence.
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_a_sidecar_that_disagrees_with_the_pane_refuses(store: Store) -> None:
    """Clause 4's "**both** … must be clear": one source agreeing is not enough.

    Goes red if only the pane is consulted. Not counted as an absence — nothing
    is missing here, the two sources disagree.
    """
    driver = runner(pane_state(DIALOG))
    answer = answer_permission(
        store=store,
        runner=driver,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.NOT_WAITING,
    )
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.reason is not None and "sidecar" in answer.reason
    assert counts(store).get(AnomalyKind.SIDECAR_ABSENT.value) is None
    assert answer.keys_sent == 0
    assert driver.writes == []


def test_the_sidecar_state_has_no_default(store: Store) -> None:
    """`sidecar` is required and keyword-only: a caller cannot forget it.

    The `record_anomaly` idiom (T6-2, T12-1). Goes red if a default appears —
    and a default of "present" is exactly how an absent sidecar becomes clear.
    """
    import inspect

    parameter = inspect.signature(answer_permission).parameters["sidecar"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert set(SidecarState) == {
        SidecarState.WAITING,
        SidecarState.NOT_WAITING,
        SidecarState.ABSENT,
    }


# ----- the trust dialog, and its separate key map -----------------------------


def test_answer_trust_sends_down_then_enter(store: Store) -> None:
    """A11/C15: `Yes, I trust this folder` is the **second** option.

    Capture: `01c-trust-yes-selected.txt` shows `❯ Yes, I trust this folder`
    after `Down`, and `SessionStart` followed the `Enter`.
    """
    driver = runner(pane_state(TRUST, TRUST_FIELDS))
    answer = answer_trust(runner=driver, handle=HANDLE, session_id=SESSION_ID, trust=True)
    assert answer.decision is WriteDecision.SEND_NOW
    assert driver.writes == [b"\x1b[B", b"\r"]


def test_trust_and_permission_use_different_key_maps(store: Store) -> None:
    """Goes red if one function serves both dialogs.

    The maps differ where it matters — trusting is `Down` then `Enter`, approving
    is `Enter` alone — and each function refuses the other's screen. Mixing them
    is how a bare `Enter` reaches the trust dialog and picks `No, exit`.
    """
    assert TRUST_KEYS[True] != PERMISSION_KEYS["approve"]
    assert TRUST_KEYS[True] == ("\x1b[B", "\r")

    # `answer_trust` at a permission dialog: refused, nothing sent.
    driver = runner(pane_state(DIALOG))
    refused = answer_trust(runner=driver, handle=HANDLE, session_id=SESSION_ID, trust=True)
    assert refused.decision is WriteDecision.REFUSE_DIALOG
    assert refused.keys_sent == 0
    assert driver.writes == []


def test_a_trust_dialog_with_the_options_swapped_is_refused(store: Store) -> None:
    """The trust screen's options are positional too, and `Down` is positional.

    Goes red if `answer_trust` trusts the screen's *kind* rather than its text:
    with the two options swapped, `Down` then `Enter` would select `No, exit`.
    """
    text = (pane_state(TRUST, TRUST_FIELDS).dialog_text or "").replace(
        " ❯ No, exit\n   Yes, I trust this folder",
        " ❯ Yes, I trust this folder\n   No, exit",
    )
    driver = runner(dataclasses.replace(pane_state(TRUST, TRUST_FIELDS), dialog_text=text))
    answer = answer_trust(runner=driver, handle=HANDLE, session_id=SESSION_ID, trust=True)
    assert answer.decision is WriteDecision.REFUSE_DIALOG
    assert answer.keys_sent == 0
    assert driver.writes == []


# ----- P-M3-16, and the module's own shape ------------------------------------


def test_every_dialog_rule_cites_an_existing_section() -> None:
    """P-M3-16, both halves: the section exists, and so does every capture.

    Goes red if an entry's `evidence` names a `data-schemas.md` section that is
    not in the document, or a capture file that is not on disk — which is how a
    guessed keystroke would get in.
    """
    document = SCHEMAS.read_text(encoding="utf-8")
    headings = {line.lstrip("# ").strip() for line in document.splitlines() if line.startswith("#")}

    assert set(DIALOG_EVIDENCE) == set(CHOICES) | {"amended", "sidecar", "trust", "refuse_trust"}
    for action, evidence in DIALOG_EVIDENCE.items():
        section, _, rest = evidence.partition(" · ")
        assert section in headings, f"{action}: {section!r}"
        assert rest != "", action
        cited = re.findall(r"[\w./-]+\.(?:ansi|txt|json)", rest)
        assert cited, f"{action}: no capture cited"
        for name in cited:
            assert list(PROBES.rglob(name)), f"{action}: {name}"


def test_every_published_key_is_one_of_the_captured_keys() -> None:
    """No key crosses this seam that no capture shows (K1).

    Goes red if a fourth key appears, or if a choice's key changes to one P4
    never pressed.
    """
    assert PERMISSION_KEYS == {"approve": ("\r",), "approve_always": ("2",), "deny": ("3",)}
    assert TRUST_KEYS == {True: ("\x1b[B", "\r"), False: ("\r",)}
    every = {key for keys in PERMISSION_KEYS.values() for key in keys}
    every |= {key for keys in TRUST_KEYS.values() for key in keys}
    assert every == {"\r", "2", "3", "\x1b[B"}


def test_both_halves_are_small_and_import_only_downward() -> None:
    """§5.0: `orchestration/` is L3, and Task 16's artifact is ≤ 150 lines.

    The cap collided, so the split was taken rather than the cap raised — the
    seventh time in this repo. **Both halves are size-asserted**, so the split
    cannot hide the growth it was taken to avoid.

    Goes red if either half starts reaching sideways for the sidecar itself: it
    is taken as a value, so no engine module is imported and no engine field
    name is spelled.
    """
    for module, allowed in (
        (
            MODULE,
            {
                "shepherd.core.anomalies",
                "shepherd.core.runner",
                "shepherd.orchestration.dialog_keys",
                "shepherd.runner.base",
                "shepherd.store.db",
            },
        ),
        (KEYS_MODULE, {"shepherd.runner.pane"}),
    ):
        source = module.read_text(encoding="utf-8")
        imported = set(re.findall(r"^from (shepherd[\w.]*) import", source, re.MULTILINE))
        assert imported <= allowed, (module.name, imported)
        assert len(source.splitlines()) <= 150, (module.name, len(source.splitlines()))


def test_the_captured_half_is_pure() -> None:
    """`dialog_keys.py` decides; it never sends, stores or times anything.

    The source is read rather than the import graph walked, because a module
    that imports nothing today can grow an import inside a function tomorrow —
    the shape `test_write_policy_reads_no_clock` already uses.

    The tokens are punctuated call forms, not bare words: this module's prose
    quotes the driver's own verb, and a raw-text scan cannot exempt a docstring
    (T12-5). A self-check below proves each token still bites.
    """
    source = KEYS_MODULE.read_text(encoding="utf-8")
    forbidden = (
        "datetime", "time.", "import time", "open(", "import os", "subprocess",
        "shepherd.store", ".write(", "bump_anomaly(", "_send(",
    )
    for token in forbidden:
        assert token not in source, token
    # self-check: every token above really does fire on the shape it names.
    fires = "import os\nimport time\nimport subprocess\nfrom shepherd.store.db import Store\n"
    fires += "open(p)\ndatetime.now()\ntime.sleep(0)\nr.write(h, b'')\ns.bump_anomaly(k)\n_send(r)"
    assert [token for token in forbidden if token in fires] == list(forbidden)


def test_the_re_exports_are_the_same_objects() -> None:
    """M1's F9: an alias is only safe while something pins it to one object.

    Goes red if a second copy of a key map or of `SidecarState` appears in
    `dialogs.py` — two structurally identical values are a split `mypy` only
    catches where they happen to meet.
    """
    assert dialogs.PERMISSION_KEYS is dialog_keys.PERMISSION_KEYS
    assert dialogs.TRUST_KEYS is dialog_keys.TRUST_KEYS
    assert dialogs.SidecarState is dialog_keys.SidecarState
    assert dialogs.DIALOG_EVIDENCE is dialog_keys.DIALOG_EVIDENCE
    assert dialogs.ALLOW_OPTION_PREFIX is dialog_keys.ALLOW_OPTION_PREFIX


def test_an_unrecognised_dialog_text_is_counted_not_only_refused(store: Store) -> None:
    """T16-1, authorised: the refusal reaches the counter `doctor` renders.

    T16 shipped the refusal and could **not** count it — the member did not
    exist, and it declined the workaround of passing a module-local constant to
    `bump_anomaly`, which would have evaded
    `test_every_anomaly_claim_names_a_member` rather than satisfied it. So the
    one refusal standing between a positional digit and a tool no human
    approved was visible only in a returned `reason`: one caller sees it and
    nobody reading `list_anomaly_counts` ever does. That is precisely what
    principle 5 forbids — unknown is a first-class value, **counted and
    displayed**, never hidden.

    Two different unrecognised screens are exercised because the member must
    count the *class*, not one capture: `Tab`'s re-label (P4) and an option set
    with a fourth entry nobody has captured.

    **Goes red** if the text gate refuses without bumping the member (the
    mutation actually run: deleting the `bump_anomaly` line leaves every
    refusal assertion green and this one red) — and, in the other direction, if
    the member is bumped on a dialog that *was* recognised, which would make the
    count fire on the normal path and say nothing (K9).
    """
    assert counts(store).get(AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value) is None

    # 1. The amended screen: still a `PERMISSION_DIALOG`, option 1 re-labelled.
    amended = runner(pane_state(AMENDED))
    first = answer_permission(
        store=store,
        runner=amended,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.WAITING,
    )
    # Arrival before absence: the refusal is the text gate's, and it counted…
    assert first.decision is WriteDecision.REFUSE_DIALOG
    assert first.reason is not None and "amend" in first.reason
    assert counts(store)[AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value] == 1
    # …and only then, that no key went to the pane.
    assert first.keys_sent == 0
    assert amended.writes == []

    # 2. A second, unrelated unrecognised screen — the count is per refusal.
    text = (pane_state(DIALOG).dialog_text or "").replace(
        "   3. No", "   3. No\n   4. No, and tell Claude what to do next"
    )
    fourth = runner(dataclasses.replace(pane_state(DIALOG), dialog_text=text))
    second = answer_permission(
        store=store,
        runner=fourth,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert second.decision is WriteDecision.REFUSE_DIALOG
    assert counts(store)[AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value] == 2
    assert second.keys_sent == 0
    assert fourth.writes == []

    # 3. The captured dialog is recognised, so the member does **not** move.
    recognised = runner(pane_state(DIALOG))
    third = answer_permission(
        store=store,
        runner=recognised,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="approve",
        sidecar=SidecarState.WAITING,
    )
    assert third.decision is WriteDecision.SEND_NOW
    assert recognised.writes == [b"\r"]
    assert counts(store)[AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value] == 2

    # 4. And the other three refusals do not borrow this member: a pane that is
    #    not a dialog at all is a different fact and has no count here.
    idle = runner(pane_state(IDLE))
    fourth_answer = answer_permission(
        store=store,
        runner=idle,
        handle=HANDLE,
        session_id=SESSION_ID,
        choice="deny",
        sidecar=SidecarState.WAITING,
    )
    assert fourth_answer.decision is WriteDecision.REFUSE_DIALOG
    assert counts(store)[AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value] == 2
