"""T20: a rename is honest — the ratchet, the `local only` marker, and a
write-back that ships **disabled** (D29, DP1, acceptance clause 12).

Every claim of clause 12 has a test below whose failure mode is named in its
docstring:

1. the ratchet is one-way over **all nine** source pairs —
   `test_user_beats_engine_and_never_reverts`, with
   `test_the_ratchet_matrix_covers_every_source_pair` asserting its own case count
2. no keys are sent while the ceiling is `False` —
   `test_no_keys_are_sent_while_can_set_title_is_false`
3. the shipped engine record keeps every rename local —
   `test_the_shipped_claude_code_ceiling_keeps_every_rename_local`
4. `title_synced_at` comes from a **read-back**, never from a send —
   `test_title_synced_at_requires_a_confirmation`
5. a slash command is never queued — `test_a_rename_is_refused_at_a_busy_pane`
6. DP1 option 3 is code, not a comment —
   `test_the_per_session_predicate_refuses_an_attached_session_even_with_the_ceiling_true`
7. the marker the UI renders is §12's exact string — `test_a_renamed_session_says_local_only`

**Arrival before absence.** Every `writes == []` assertion here is preceded by an
assertion that the call reached the step which *would* have sent the bytes: the
row's title really moved, or the pane was really read. "No keys were sent" is
satisfied just as well by a function that returned two lines in.

**The ceiling is never mutated.** The tests that exercise the write-back build
their own `EngineCapabilities(can_set_title=True)` value; the shipped record in
`engines/claude_code/spawn.py` is only ever **read**, which is what keeps
`test_can_set_title_ships_false` the single place a flip is decided.

**The panes come out of the shipped classifier over real captures**
(`runner/pane.py::read_pane`), never a screen this file typed itself.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from shepherd.core.runner import (
    EngineCapabilities,
    PaneKind,
    PaneState,
    ProcState,
    RunnerHandle,
    SessionSpec,
    WriteDecision,
)
from shepherd.core.states import TITLE_SOURCE_RANK, Origin, Ownership, TitleSource
from shepherd.engines.claude_code.spawn import capabilities
from shepherd.orchestration.rename import (
    LOCAL_ONLY_MARKER,
    RenameOutcome,
    confirm_engine_title,
    drive_engine_rename,
    rename_session,
)
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"
RUN = PROBES / "tmux-tui" / "run-20260914T154946Z"
SUPP3 = PROBES / "tmux-tui" / "supp3-20260914T160052Z"
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "rename.py"

#: The plan's `Expected Artifacts`: "one module <= 200 lines".
MAX_MODULE_LINES = 200

NOW = "2026-09-17T10:00:00.000000+00:00"

SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
NAME = f"shepherd_{SESSION_ID}"
PANE_PID = 4041880

#: The title this file renames to. Never a substring of any capture, so "the
#: title never reached a write" is a real search rather than a coincidence.
TITLE = "SHEPHERD-T20-TITLE"

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"
#: `01-trust-dialog-fmt.txt`: the trust screen is **not** on the alternate
#: screen, and `read_pane` keys on that (`tests/runner/test_pane.py` l.56).
TRUST_FIELDS = "0|0||<redacted: host name>|160|45|4041880"

#: `03-after-stop.ansi` — the box after a turn ended: empty, no dialog.
READY = (RUN / "03-after-stop.ansi").read_bytes()
#: `A2-typed-over-suggestion.ansi` — a real draft in the box (E-M3-5).
DRAFT = (SUPP3 / "A2-typed-over-suggestion.ansi").read_bytes()
#: `06-permission-dialog.ansi` — D44's dialog; text sent here is discarded.
PERMISSION = (RUN / "06-permission-dialog.ansi").read_bytes()
#: `01-trust-dialog.ansi` — a bare Enter here selects `No, exit` (C15, A11).
TRUST = (RUN / "01-trust-dialog.ansi").read_bytes()

#: `10-sidecar-after-rename.json`'s two fields, verbatim from data-schemas
#: §"Session title": a user rename is `nameSource:"user"` with the new `name`.
USER_NAME_SOURCE = "user"
DERIVED_NAME_SOURCE = "derived"

SOURCES: tuple[TitleSource, ...] = ("user", "engine", "brief")
#: All nine ordered pairs `(prior source, incoming source)`.
PAIRS: tuple[tuple[TitleSource, TitleSource], ...] = tuple(itertools.product(SOURCES, SOURCES))

CEILING_TRUE = dataclasses.replace(
    capabilities(pane_driver_available=True), can_set_title=True
)
CEILING_FALSE = capabilities(pane_driver_available=True)


# ----- fixtures ---------------------------------------------------------------


def pane_state(raw: bytes, fields: str = LIVE_FIELDS) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(raw, parse_pane_fields(fields), [])


def synthetic(kind: PaneKind, *, input_text: str = "") -> PaneState:
    """A pane kind the checked-in captures cannot reach (`BUSY`, `DEAD`)."""
    return dataclasses.replace(pane_state(READY), kind=kind, input_text=input_text)


#: Every pane kind, and what the write-back may do at it. **Seven** cases over
#: **six** kinds: `PROMPT_READY` appears twice, because an empty box and a
#: drafted one are different facts about the same kind.
PANE_CASES: tuple[tuple[PaneState, WriteDecision], ...] = (
    (pane_state(READY), WriteDecision.SEND_NOW),
    (pane_state(DRAFT), WriteDecision.REFUSE_INPUT_NOT_EMPTY),
    (pane_state(PERMISSION), WriteDecision.REFUSE_DIALOG),
    (pane_state(TRUST, TRUST_FIELDS), WriteDecision.REFUSE_DIALOG),
    (synthetic(PaneKind.BUSY), WriteDecision.QUEUE),
    (synthetic(PaneKind.DEAD), WriteDecision.REFUSE_NO_PTY),
    (synthetic(PaneKind.UNREADABLE), WriteDecision.REFUSE_NO_PTY),
)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def owned_row(store: Store, *, title: str | None = None, source: TitleSource = "brief") -> str:
    workspace = store.upsert_workspace("shepherd", str(REPO_ROOT)).id
    store.create_owned_session(
        session_id=SESSION_ID,
        engine_session_id=f"engine-{SESSION_ID}",
        workspace_id=workspace,
        repo_id=None,
        cwd=str(REPO_ROOT),
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=title,
        title_source=source,
        handle=RunnerHandle(runner="scripted", socket="scripted", session_name=NAME),
        model=None,
        effort=None,
    )
    return SESSION_ID


def scripted(panes: Sequence[PaneState], *, pid: int | None = PANE_PID) -> ScriptedRunner:
    runner = ScriptedRunner(
        panes=tuple(panes),
        proc=ProcState(alive=True, pid=pid, exit_code=None, exit_signal=None, observed_at=NOW),
        screen=READY,
    )
    runner.start(
        SessionSpec(
            session_id=SESSION_ID,
            engine_session_id="engine",
            cwd=str(REPO_ROOT),
            brief=None,
            title=None,
            model=None,
            effort=None,
            engine="stub",
            runner="scripted",
            env={},
        )
    )
    return runner


def handle() -> RunnerHandle:
    return RunnerHandle(runner="scripted", socket="scripted", session_name=NAME)


def sidecar(config_dir: Path, *, name: str, name_source: str, pid: int = PANE_PID) -> Path:
    """One registry sidecar, in the engine's own shape (data-schemas §sidecar).

    Written under a `tmp_path` config dir: nothing in this file ever resolves the
    user's real `~/.claude` (T10-R1 rule 3).
    """
    directory = config_dir / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pid}.json"
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "sessionId": "71757dd1-5375-4801-b467-7898a0bc1194",
                "cwd": "/tmp/shp-tui-A-4tvrx00n",
                "startedAt": 1789401012996,
                "procStart": "543824210",
                "version": "2.1.270",
                "kind": "interactive",
                "entrypoint": "cli",
                "name": name,
                "nameSource": name_source,
                "status": "idle",
                "updatedAt": 1789401085541,
                "statusUpdatedAt": 1789401085541,
            }
        ),
        encoding="utf-8",
    )
    return path


def do_rename(
    store: Store,
    runner: ScriptedRunner,
    *,
    config_dir: Path,
    caps: EngineCapabilities = CEILING_FALSE,
    ownership: Ownership = Ownership.OWNED,
    target: RunnerHandle | None = None,
) -> RenameOutcome:
    return rename_session(
        store=store,
        runner=runner,
        handle=target if target is not None else handle(),
        session_id=SESSION_ID,
        title=TITLE,
        now=lambda: NOW,
        capabilities=caps,
        ownership=ownership,
        config_dir=config_dir,
    )


# ----- 1. the ratchet, in both directions -------------------------------------


def test_the_ratchet_matrix_covers_every_source_pair() -> None:
    """The parametrised case count, asserted rather than assumed.

    **Goes red** if a source is added to `TitleSource` and the matrix below stops
    covering the pair that a new source creates — a loop that silently shrinks
    is the "check that reports success without checking" this repo keeps finding.
    """
    assert len(PAIRS) == 9, PAIRS
    assert set(PAIRS) == set(itertools.product(TITLE_SOURCE_RANK, TITLE_SOURCE_RANK))


@pytest.mark.parametrize(("prior", "incoming"), PAIRS)
def test_user_beats_engine_and_never_reverts(
    store: Store, prior: TitleSource, incoming: TitleSource
) -> None:
    """D29's one-way ratchet over all nine pairs, asserted in **both** directions.

    A strictly lower-ranked source must not move the title; an equal or higher
    one must. **Goes red** if the ratchet is implemented as last-writer-wins,
    which the discovery loop would then undo on its next sweep.
    """
    owned_row(store, title="PRIOR", source=prior)
    after = store.apply_title(SESSION_ID, "INCOMING", incoming)

    if TITLE_SOURCE_RANK[incoming] < TITLE_SOURCE_RANK[prior]:
        assert after.title == "PRIOR", (prior, incoming, after.title)
        assert after.title_source == prior
    else:
        assert after.title == "INCOMING", (prior, incoming, after.title)
        assert after.title_source == incoming


def test_an_engine_title_cannot_overwrite_a_rename(store: Store, tmp_path: Path) -> None:
    """The ratchet's one-way property at **this module's** seam, not the store's.

    **Goes red** if `rename_session` writes the title with any source other than
    `user` — the row would then be overwritten by the next engine title the
    discovery sweep reads.
    """
    owned_row(store)
    runner = scripted([pane_state(READY)])
    outcome = do_rename(store, runner, config_dir=tmp_path / "engine")
    assert outcome.source == "user"

    after = store.apply_title(SESSION_ID, "an engine title", "engine")
    assert after.title == TITLE
    assert after.title_source == "user"


# ----- 2/3. nothing is sent while the ceiling is False ------------------------


def test_no_keys_are_sent_while_can_set_title_is_false(store: Store, tmp_path: Path) -> None:
    """D29's literal value, honoured in the one place that could send keys.

    **Arrival first**: the rename really happened locally, so the absence below
    is the absence of a *send* and not of the whole call. **Goes red** the moment
    the flag is honoured in one place and not another.
    """
    owned_row(store)
    runner = scripted([pane_state(READY)])

    outcome = do_rename(store, runner, config_dir=tmp_path / "engine", caps=CEILING_FALSE)

    assert outcome.title == TITLE                      # arrival
    assert store.get_session(SESSION_ID) is not None
    assert outcome.local_only is True
    assert outcome.synced_at is None
    assert runner.writes == [], runner.writes
    assert "write" not in runner.calls, runner.calls


def test_the_shipped_claude_code_ceiling_keeps_every_rename_local(
    store: Store, tmp_path: Path
) -> None:
    """The shipped record, read rather than constructed (DP1, clause 12).

    **Goes red** if anyone flips `can_set_title` in
    `engines/claude_code/spawn.py` — the same flip
    `tests/engines/test_spawn_argv.py::test_can_set_title_ships_false` fails on,
    caught here at the seam that would do the writing.
    """
    owned_row(store)
    runner = scripted([pane_state(READY)])
    sidecar(tmp_path / "engine", name=TITLE, name_source=USER_NAME_SOURCE)

    outcome = do_rename(
        store, runner, config_dir=tmp_path / "engine", caps=capabilities(pane_driver_available=True)
    )

    assert outcome.title == TITLE                      # arrival
    assert outcome.local_only is True, (
        "DP1 is stated and NOT APPLIED: with the shipped ceiling every rename stays local"
    )
    assert outcome.synced_at is None
    assert runner.writes == []


# ----- 4. the stamp comes from a read-back ------------------------------------


def test_title_synced_at_requires_a_confirmation(store: Store, tmp_path: Path) -> None:
    """A send is not a sync (D29's "silent half-success").

    The ceiling is `True` here, the pane is ready and the keys really are sent —
    and the sidecar still says `derived`, so nothing is stamped. **Goes red** if
    a send stamps `title_synced_at`.
    """
    config_dir = tmp_path / "engine"
    owned_row(store)
    runner = scripted([pane_state(READY)])
    sidecar(config_dir, name="shp-tui-a-4tvrx00n-00", name_source=DERIVED_NAME_SOURCE)

    outcome = do_rename(store, runner, config_dir=config_dir, caps=CEILING_TRUE)

    assert runner.writes != [], "the keys must really have been sent"   # arrival
    assert outcome.synced_at is None
    assert outcome.local_only is True
    assert store.get_session(SESSION_ID) is not None
    assert store.get_session(SESSION_ID).title_synced_at is None  # type: ignore[union-attr]


def test_a_read_back_of_the_engines_own_user_title_stamps_it(
    store: Store, tmp_path: Path
) -> None:
    """The one way `title_synced_at` may be written: the engine's `nameSource:"user"`.

    **Goes red** if the confirmation reader is bypassed — the stamp would then
    mean "we typed something" rather than "the engine accepted it".
    """
    config_dir = tmp_path / "engine"
    owned_row(store)
    runner = scripted([pane_state(READY)])
    sidecar(config_dir, name=TITLE, name_source=USER_NAME_SOURCE)

    outcome = do_rename(store, runner, config_dir=config_dir, caps=CEILING_TRUE)

    assert runner.writes != []
    assert outcome.synced_at == NOW
    assert outcome.local_only is False
    assert store.get_session(SESSION_ID).title_synced_at == NOW  # type: ignore[union-attr]


def test_the_keys_are_the_slash_command_then_enter(store: Store, tmp_path: Path) -> None:
    """The write-back's shape, for the reviewer who will approve or reject it.

    `send-keys -l -- "/rename <title>"` then `Enter`, expressed as the seam's two
    byte writes. **Goes red** if the submit is folded into the text, which is how
    a half-typed slash command would be left on somebody's prompt.
    """
    owned_row(store)
    runner = scripted([pane_state(READY)])
    do_rename(store, runner, config_dir=tmp_path / "engine", caps=CEILING_TRUE)

    assert runner.writes == [f"/rename {TITLE}".encode(), b"\r"], runner.writes


@pytest.mark.parametrize(
    ("kind", "written"),
    [
        ("absent", None),
        ("unparsable", "{not json"),
        ("wrong-source", None),
        ("wrong-name", None),
    ],
)
def test_a_confirmation_is_refused_on_every_degraded_sidecar(
    tmp_path: Path, kind: str, written: str | None
) -> None:
    """Principle 5: an unknown is never read as a yes.

    **Goes red** if the reader treats an absent, truncated or `derived` sidecar
    as a confirmation — which would stamp `title_synced_at` from nothing at all.
    """
    config_dir = tmp_path / kind
    if kind == "unparsable":
        directory = config_dir / "sessions"
        directory.mkdir(parents=True)
        assert written is not None
        (directory / f"{PANE_PID}.json").write_text(written, encoding="utf-8")
    elif kind == "wrong-source":
        sidecar(config_dir, name=TITLE, name_source=DERIVED_NAME_SOURCE)
    elif kind == "wrong-name":
        sidecar(config_dir, name="somebody else's title", name_source=USER_NAME_SOURCE)

    assert confirm_engine_title(config_dir=config_dir, pid=PANE_PID, title=TITLE) is False


def test_a_confirmation_reads_the_engines_own_capture(tmp_path: Path) -> None:
    """The positive case, so the four refusals above are not vacuous.

    **Goes red** if the reader can never say yes — four negatives against a
    function that always answers `False` prove nothing.
    """
    sidecar(tmp_path, name=TITLE, name_source=USER_NAME_SOURCE)
    assert confirm_engine_title(config_dir=tmp_path, pid=PANE_PID, title=TITLE) is True


# ----- 5. a slash command is never queued -------------------------------------


def test_a_rename_is_refused_at_a_busy_pane(store: Store, tmp_path: Path) -> None:
    """E-M3-9: delivered mid-turn, `/rename <title>` reaches the model as *text*.

    **Arrival first**: the pane really was read, so the empty `writes` below is a
    refusal and not an early return. **Goes red** if a slash command can be
    queued.
    """
    owned_row(store)
    runner = scripted([synthetic(PaneKind.BUSY)])

    outcome = do_rename(store, runner, config_dir=tmp_path / "engine", caps=CEILING_TRUE)

    assert "pane" in runner.calls, runner.calls          # arrival
    assert runner.writes == [], runner.writes
    assert outcome.local_only is True
    assert outcome.synced_at is None
    assert outcome.title == TITLE


@pytest.mark.parametrize(("pane", "expected"), PANE_CASES)
def test_the_drive_path_sends_at_a_ready_pane_and_nowhere_else(
    pane: PaneState, expected: WriteDecision
) -> None:
    """Six pane kinds, one send. **Goes red** if a second kind starts sending.

    The decision vocabulary is `write_policy`'s: `QUEUE` here means *not sent*
    and the rename is **not** enqueued — nothing in this module keeps it for
    later.
    """
    runner = scripted([pane])
    decision = drive_engine_rename(runner=runner, handle=handle(), title=TITLE)

    assert decision is expected, (pane.kind, decision)
    assert (runner.writes != []) is (expected is WriteDecision.SEND_NOW), runner.writes


def test_the_drive_path_covers_every_pane_kind() -> None:
    """The case count above, asserted against the enum it claims to cover.

    **Goes red** if a seventh `PaneKind` appears and the loop above silently
    stops covering it — the shrinking-loop defect, which passes by default.
    """
    assert len(PANE_CASES) == 7, PANE_CASES
    assert {pane.kind for pane, _ in PANE_CASES} == set(PaneKind)
    assert sum(1 for _, decision in PANE_CASES if decision is WriteDecision.SEND_NOW) == 1


# ----- 6. DP1 option 3 is code, not a comment ---------------------------------


def test_the_per_session_predicate_refuses_an_attached_session_even_with_the_ceiling_true(
    store: Store, tmp_path: Path
) -> None:
    """DP1 option 3: the ceiling is the engine's, the answer is the session's.

    An attached session lives on the user's own socket (K6), and `/rename`
    against a session live in another process is **G-M3-5** — unverified, and
    declined because it risks two writers on one transcript. **Goes red** if the
    predicate is a comment rather than code, which is what would make DP1's
    "one-line reversal" claim false.
    """
    owned_row(store)
    runner = scripted([pane_state(READY)])
    sidecar(tmp_path / "engine", name=TITLE, name_source=USER_NAME_SOURCE)

    outcome = do_rename(
        store,
        runner,
        config_dir=tmp_path / "engine",
        caps=CEILING_TRUE,
        ownership=Ownership.ATTACHED,
    )

    assert outcome.title == TITLE                       # arrival: the rename happened
    assert outcome.local_only is True
    assert outcome.synced_at is None
    assert runner.writes == [], runner.writes
    assert runner.calls == ["start"], runner.calls


def test_a_session_with_no_pane_is_refused_even_with_the_ceiling_true(
    store: Store, tmp_path: Path
) -> None:
    """The third conjunct: `handle is not None`. **Goes red** if a runner is
    driven for a row that has no pane at all."""
    owned_row(store)
    runner = scripted([pane_state(READY)])

    outcome = rename_session(
        store=store,
        runner=runner,
        handle=None,
        session_id=SESSION_ID,
        title=TITLE,
        now=lambda: NOW,
        capabilities=CEILING_TRUE,
        ownership=Ownership.OWNED,
        config_dir=tmp_path / "engine",
    )

    assert outcome.title == TITLE                       # arrival
    assert outcome.local_only is True
    assert runner.writes == []


def test_an_unknown_pane_pid_is_never_read_as_a_confirmation(
    store: Store, tmp_path: Path
) -> None:
    """Principle 5: the sidecar is named by pid, and a pid we do not have is an
    unknown. **Goes red** if a missing pid falls through to some default file."""
    config_dir = tmp_path / "engine"
    owned_row(store)
    runner = scripted([pane_state(READY)], pid=None)
    sidecar(config_dir, name=TITLE, name_source=USER_NAME_SOURCE)

    outcome = do_rename(store, runner, config_dir=config_dir, caps=CEILING_TRUE)

    assert runner.writes != []                           # arrival
    assert outcome.synced_at is None
    assert outcome.local_only is True


# ----- 7. the marker, and the module's size -----------------------------------


def test_a_renamed_session_says_local_only(store: Store, tmp_path: Path) -> None:
    """§12's marker text, verbatim (RD9). **Goes red** if the marker is reworded
    into something that implies a sync that did not happen."""
    owned_row(store)
    runner = scripted([pane_state(READY)])
    outcome = do_rename(store, runner, config_dir=tmp_path / "engine")

    assert outcome.local_only is True
    assert LOCAL_ONLY_MARKER == "local only"


def test_the_module_stays_small() -> None:
    """The plan's `Expected Artifacts`: one module <= 200 lines."""
    lines = MODULE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_MODULE_LINES, len(lines)


def test_the_write_policy_is_asked_and_not_re_decided() -> None:
    """The six decisions this module returns are `write_policy`'s own, and the
    module builds no table of its own. **Goes red** if a private decision table
    appears here — a second write policy is the split `mypy` only catches where
    the two happen to meet."""
    source = MODULE.read_text(encoding="utf-8")
    assert "from shepherd.orchestration.write_policy import decide_write" in source
    assert "WriteDecision.SEND_NOW" in source
    assert "WRITE_RULES" not in source
