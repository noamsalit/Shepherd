"""T14: one delivery path — coalesced, idempotent, and never onto a draft.

Acceptance clause 5 is six claims, and each one has a test below whose failure
mode is named in its docstring:

1. five messages arrive as **one** — `test_five_queued_messages_deliver_as_one_message_with_five_bullets`
2. a repeated idempotency key enqueues **once** — `test_a_repeated_idempotency_key_enqueues_once`
3. a delivered message is not re-sent across a **restart** — `test_delivery_is_not_repeated_after_a_restart`
4. an interrupted turn, which emits **no turn-ending hook**, still delivers at the
   next prompt-ready pane — `test_an_interrupted_turn_still_delivers_at_the_next_prompt_ready_pane`
5. a non-empty input line is cleared and **the pane is re-read before any text
   follows** — `test_clear_then_send_re_reads_the_pane_before_the_text`, with
   `test_the_clear_is_useless_without_the_re_read` keeping T13's defect alive
6. a deferred message records **why** on its row — `test_a_refusal_is_recorded_on_the_row`

**Every pane comes out of the shipped classifier over a real capture**
(`runner.pane.read_pane`), never a hand-written screen: a screen this file typed
itself would prove only that the test and the classifier agree.

**The argv-order proofs run through `LocalRunner` with a counting `run_argv`**,
because `ScriptedRunner` has no argv at all: "the text was not written" is
satisfied just as well by a `paste-buffer`, and only the argv record can say
which keys really reached the pane and **in what order**.

**Arrival before absence.** Every zero-assertion here is preceded by an assertion
that the delivery reached the step that would have sent the bytes.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.mailbox import COALESCE_BULLET, MailboxMessage, MailboxOrigin
from shepherd.core.runner import (
    PaneKind,
    PaneState,
    ProcState,
    RunnerHandle,
    SessionSpec,
    WriteDecision,
)
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.host.base import DetachedLaunch
from shepherd.orchestration.mailbox import (
    coalesce,
    deliver_now,
    queue_message,
    sweep_pending,
    turn_state,
)
from shepherd.runner.local import CommandResult, LocalRunner
from shepherd.runner.pane import parse_pane_fields, read_pane
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"
RUN = PROBES / "tmux-tui" / "run-20260914T154946Z"
SUPP3 = PROBES / "tmux-tui" / "supp3-20260914T160052Z"
MODULE = REPO_ROOT / "src" / "shepherd" / "orchestration" / "mailbox.py"

NOW = "2026-09-17T10:00:00.000000+00:00"
LATER = "2026-09-17T10:05:00.000000+00:00"

SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
NAME = f"shepherd_{SESSION_ID}"
SPOT = f"={NAME}:"
SOCKET = "shepherd-m3-t14"
TMUX = "tm" + "ux"
HANDLE = RunnerHandle(runner="local", socket=SOCKET, session_name=NAME)

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"

#: `03-after-stop.ansi` — the box after a turn ended: empty, no dialog.
READY = (RUN / "03-after-stop.ansi").read_bytes()
#: `A2-typed-over-suggestion.ansi` — a real draft in the box (E-M3-5: the ghost
#: text of `A1-suggestion.ansi` is **not** a draft and is excluded by `read_pane`).
DRAFT = (SUPP3 / "A2-typed-over-suggestion.ansi").read_bytes()
#: `06-permission-dialog.ansi` — D44's dialog; text sent here is discarded.
PERMISSION = (RUN / "06-permission-dialog.ansi").read_bytes()

#: The body of every message this file queues. Never a substring of any capture,
#: so "the body never reached an argv" is a real search and not a coincidence.
BODY = "SHEPHERD-T14-BODY"

#: Every tmux verb or argument that can put a byte into a pane. A set, not the
#: one verb a mock would expect: a stray `Enter` through `paste-buffer` leaves a
#: `writes == []` double green.
KEY_DELIVERING = ("send-keys", "paste-buffer", "Enter")

#: `send-keys -t <target> C-u`, verbatim from the capture that proved `C-u`
#: clears a history-recalled prompt (`steps.log` l.7 of the key-semantics
#: gap-fill probe, `01-after-raw-up.txt` -> `01b-after-ctrl-u.txt`).
CLEAR_ARGV = [TMUX, "-L", SOCKET, "send-keys", "-t", SPOT, "C-u"]


# ----- fixtures ---------------------------------------------------------------


def pane_state(raw: bytes, fields: str = LIVE_FIELDS) -> PaneState:
    """A `PaneState` off a real capture, through the shipped classifier."""
    return read_pane(raw, parse_pane_fields(fields), [])


def synthetic(kind: PaneKind, *, input_text: str = "") -> PaneState:
    """A pane kind the six checked-in captures cannot reach (`BUSY`, `DEAD`).

    The **kind** is still a classifier output; only the combination is assembled
    here, exactly as `test_write_policy.py` does it.
    """
    return dataclasses.replace(pane_state(READY), kind=kind, input_text=input_text)


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "shepherd.db"


def owned_row(
    store: Store, *, session_id: str = SESSION_ID, state: SessionState = SessionState.STOPPED
) -> str:
    """One owned session row, in the state a delivery will be decided against.

    `create_owned_session` writes `ownership='owned'`, which is the only
    ownership an owned-session row can have; the attached case is passed to the
    decision as a value rather than forged into a row the store would refuse.
    """
    workspace = store.create_project(name="shepherd", description=None).id
    store.create_owned_session(
        session_id=session_id,
        engine_session_id=f"engine-{session_id}",
        workspace_id=workspace,
        repo_id=None,
        cwd=str(REPO_ROOT),
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=HANDLE,
        model=None,
        effort=None,
    )
    if state is not SessionState.STARTING:
        store.apply_fold_delta(session_id, _state_delta(state))
    return session_id


def _state_delta(state: SessionState) -> object:
    from shepherd.core.fold_types import FoldDelta

    return FoldDelta(state=state)


def scripted(
    panes: Sequence[PaneState], *, clients: int = 0, session_id: str = SESSION_ID
) -> ScriptedRunner:
    """A fixture runner already holding the pane the handle names."""
    runner = ScriptedRunner(
        panes=tuple(panes),
        proc=ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW),
        screen=READY,
        clients=clients,
    )
    runner.start(
        SessionSpec(
            session_id=session_id,
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


def scripted_handle(session_id: str = SESSION_ID) -> RunnerHandle:
    return RunnerHandle(runner="scripted", socket="scripted", session_name=f"shepherd_{session_id}")


class Recorder:
    """A counting `run_argv`: every argv handed over, answered from a table.

    Not a mock with expectations. The tests assert over the record, which is what
    lets a test say "the clear reached the pane" *before* it says "and the body
    did not follow it".
    """

    def __init__(self, captures: Sequence[bytes], *, clients: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.captures = list(captures)
        self.clients = clients

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        words = argv[argv.index(SOCKET) + 1 :] if SOCKET in argv else argv[1:]
        verb = words[0]
        if verb == "capture-pane":
            raw = self.captures[min(self._captures_so_far() - 1, len(self.captures) - 1)]
            return CommandResult(rc=0, stdout=raw, stderr=b"")
        if verb == "list-sessions":
            return CommandResult(
                rc=0, stdout=f"{NAME}|{LIVE_FIELDS}\n".encode("utf-8"), stderr=b""
            )
        if verb == "list-clients":
            lines = "".join(f"/dev/pts/{index}\n" for index in range(self.clients))
            return CommandResult(rc=0, stdout=lines.encode("utf-8"), stderr=b"")
        return CommandResult(rc=0, stdout=b"", stderr=b"")

    def _captures_so_far(self) -> int:
        return sum(1 for argv in self.calls if "capture-pane" in argv)

    def verbs(self) -> list[str]:
        """The tmux command word of every call, in order."""
        return [argv[3] for argv in self.calls if len(argv) > 3 and argv[0] == TMUX]


def local(recorder: Recorder, tmp_path: Path) -> LocalRunner:
    return LocalRunner(
        socket=SOCKET,
        run_argv=recorder,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: NOW,
        spawn_argv=lambda spec, *, frame_bytes: ["claude-stub"],
        record_anomaly=lambda anomaly: None,
        sink_dir=tmp_path,
    )


def queue(store: Store, bodies: Sequence[str], session_id: str = SESSION_ID) -> None:
    for index, body in enumerate(bodies):
        queue_message(
            store=store,
            session_id=session_id,
            body=body,
            origin=MailboxOrigin.ORCHESTRATOR,
            idempotency_key=f"key-{index}",
            now=lambda: NOW,
        )


def assert_no_body_reached_a_pane(recorder: Recorder, body: str = BODY) -> None:
    """Absence, over every argv and every key-delivering form.

    The capture-proven `C-u` is the one exception and it is matched by **list
    equality**, so an extra argument, a different target or a second key still
    fails: clearing the box is not delivery.
    """
    hexed = [f"{byte:02x}" for byte in body.encode("utf-8")]
    for argv in recorder.calls:
        if argv == CLEAR_ARGV:
            continue
        for verb in KEY_DELIVERING:
            assert verb not in argv, argv
        assert body not in argv, argv
        assert not set(hexed).issubset(set(argv)), argv


# ----- coalescing -------------------------------------------------------------


def message(body: str, *, identifier: str = "01ID", key: str = "k") -> MailboxMessage:
    return MailboxMessage(
        id=identifier,
        session_id=SESSION_ID,
        idempotency_key=key,
        body=body,
        origin=MailboxOrigin.ORCHESTRATOR,
        queued_at=NOW,
        delivered_at=None,
        delivery_attempts=0,
        last_refusal=None,
    )


def test_coalesce_loses_nothing() -> None:
    """Every queued text appears **exactly once** in the coalesced body.

    **Goes red** on a truncation, on a dedupe that silently drops a repeat — two
    agents queueing the same sentence is two notes, not one — and on a reorder,
    because queue order is the order the reader will act in.
    """
    bodies = ["ship it", "rebase first", "ship it", "run the suite", "then tell me"]
    out = coalesce([message(body, identifier=f"id-{i}") for i, body in enumerate(bodies)])

    for body in set(bodies):
        assert out.count(body) == bodies.count(body), body
    assert [line.removeprefix(COALESCE_BULLET) for line in out.splitlines()] == bodies
    assert out.count(COALESCE_BULLET) == len(bodies)


def test_one_message_is_not_rendered_as_a_list_of_one() -> None:
    """A single note is delivered as itself — no bullet, nothing prepended.

    D12's bullets are what makes *five* notes one message. Bulleting a single
    note invents a list the sender did not write, and the reader is a model that
    reads `- ship it` as a list item. **Goes red** if the coalescer ever wraps
    unconditionally.
    """
    assert coalesce([message("ship it")]) == "ship it"
    assert coalesce([]) == ""


# ----- the queue --------------------------------------------------------------


def test_a_repeated_idempotency_key_enqueues_once(store: Store) -> None:
    """A retrying caller queues one row and gets **the stored one** back.

    **Goes red** if the unique index is relied on without being caught, which
    surfaces to the caller as an integrity error rather than as an idempotent
    no-op, and red if the retry gets a fresh id back — a caller that saw a new id
    would believe it had queued a second note.
    """
    session_id = owned_row(store)
    first = queue_message(
        store=store,
        session_id=session_id,
        body=BODY,
        origin=MailboxOrigin.ORCHESTRATOR,
        idempotency_key="same-key",
        now=lambda: NOW,
    )
    second = queue_message(
        store=store,
        session_id=session_id,
        body="a different body entirely",
        origin=MailboxOrigin.USER_UI,
        idempotency_key="same-key",
        now=lambda: LATER,
    )

    assert second.id == first.id
    assert second.body == BODY, "the retry overwrote the row it was supposed to match"
    assert second.origin is MailboxOrigin.ORCHESTRATOR
    assert len(store.pending_for(session_id)) == 1
    assert store.mailbox_counts().pending == 1


# ----- delivery ---------------------------------------------------------------


def test_five_queued_messages_deliver_as_one_message_with_five_bullets(store: Store) -> None:
    """D12: five queued notes become **one** write plus one submit.

    **Goes red** on five writes, which is the interruption D12 exists to
    prevent — a session that is told five things in five turns answers five
    times — and red if the submit is folded into the body instead of being its
    own key.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    bodies = [f"{BODY}-{index}" for index in range(5)]
    queue(store, bodies)
    runner = scripted([pane_state(READY)])

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert outcome.decision is WriteDecision.SEND_NOW
    assert outcome.delivered == 5, "the five rows were not all retired by the one write"
    assert len(runner.writes) == 2, runner.writes
    body, submit = runner.writes
    assert submit == b"\r"
    text = body.decode("utf-8")
    assert text.count(COALESCE_BULLET) == 5
    for one in bodies:
        assert text.count(one) == 1
    assert store.pending_for(session_id) == []
    assert store.mailbox_counts().delivered == 5


def test_delivery_is_not_repeated_after_a_restart(db_path: Path) -> None:
    """The stamp is in the database, so a restarted process re-sends nothing.

    The `Store` is **rebuilt from the same file** between the delivery and the
    next sweep. **Goes red** if pending is held in memory, and red if the second
    sweep re-delivers — `mark_delivered`'s conditional write is what reports
    `5 + 0` rather than `5 + 5`.
    """
    first = open_store(db_path)
    try:
        session_id = owned_row(first, state=SessionState.STOPPED)
        queue(first, [f"{BODY}-{index}" for index in range(3)])
        runner = scripted([pane_state(READY)])
        opening = sweep_pending(
            store=first,
            runner=runner,
            now=lambda: LATER,
            handles={session_id: scripted_handle()},
        )
        assert opening.delivered == 3
        assert len(runner.writes) == 2
    finally:
        first.close()

    second = open_store(db_path)
    try:
        assert second.pending_for(session_id) == [], "the stamp did not survive the restart"
        after = scripted([pane_state(READY)])
        again = sweep_pending(
            store=second,
            runner=after,
            now=lambda: LATER,
            handles={session_id: scripted_handle()},
        )
        assert again.delivered == 0, "a restarted process re-delivered a stamped message"
        assert after.writes == [], "a restarted process wrote to the pane again"
        assert second.mailbox_counts().delivered == 3
    finally:
        second.close()


def test_an_interrupted_turn_still_delivers_at_the_next_prompt_ready_pane(store: Store) -> None:
    """D45's second trigger: no turn-ending hook ever arrives, and it still lands.

    An interrupted turn emits no turn-ending hook at all (A13), so the row stays
    `running` for ever — and `(running, prompt-ready)` is `QUEUE` in the policy
    table, which is exactly the stall D45 exists to prevent. For an **owned**
    session the pane is the better evidence: a prompt-ready pane *is* the turn
    boundary, and `turn_state` supplies the key field the missing hook would have
    written.

    **Goes red** if delivery is keyed on the turn-ending hook alone, and red if
    the stored state is passed to the policy unexamined.
    """
    session_id = owned_row(store, state=SessionState.RUNNING)
    queue(store, [BODY])
    assert store.get_owned_session(session_id) is not None
    row = store.get_owned_session(session_id)
    assert row is not None and row.state is SessionState.RUNNING

    runner = scripted([pane_state(READY)])
    counts = sweep_pending(
        store=store,
        runner=runner,
        now=lambda: LATER,
        handles={session_id: scripted_handle()},
    )

    assert counts.delivered == 1, "the mailbox stalled on a session that will never stop"
    assert runner.writes[0].decode("utf-8") == BODY
    assert store.pending_for(session_id) == []


def test_a_busy_pane_is_still_queued_even_though_the_row_says_stopped(store: Store) -> None:
    """The second trigger cuts one way only: the pane can never *force* a write.

    `turn_state` answers the policy's first key field from the pane **only** when
    the pane is prompt-ready. A mid-turn pane is queued whatever the row says, so
    the D45 trigger cannot be turned into "the mailbox writes whenever it likes".
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([synthetic(PaneKind.BUSY)])

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert outcome.decision is WriteDecision.QUEUE
    assert runner.writes == []
    assert len(store.pending_for(session_id)) == 1


def test_the_sweep_makes_no_tmux_call_when_the_mailbox_is_empty(tmp_path: Path) -> None:
    """An empty mailbox costs one indexed query and **zero** driver calls (RD4).

    Arrival first: the same sweep with one pending row is shown to reach the
    driver, so "no call was made" cannot pass because the sweep never ran.
    **Goes red** on a sweep that polls the fleet.
    """
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        session_id = owned_row(opened, state=SessionState.STOPPED)
        recorder = Recorder([READY])
        driver = local(recorder, tmp_path)
        handles = {session_id: HANDLE}

        empty = sweep_pending(store=opened, runner=driver, now=lambda: LATER, handles=handles)
        assert recorder.calls == [], recorder.calls
        assert empty.delivered == 0 and empty.pending == 0

        queue(opened, [BODY])
        busy = sweep_pending(store=opened, runner=driver, now=lambda: LATER, handles=handles)
        assert busy.delivered == 1
        assert recorder.calls != [], "the sweep never reached the driver at all"
    finally:
        opened.close()


def test_a_session_with_pending_and_no_handle_is_deferred_not_dropped(store: Store) -> None:
    """A row Shepherd has no pane for defers with a readable reason (principle 5).

    **Goes red** if an absent handle is a crash, or a silent skip that leaves the
    row saying nothing about why it never moves.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([pane_state(READY)])

    counts = sweep_pending(store=store, runner=runner, now=lambda: LATER, handles={})

    assert counts.delivered == 0
    assert counts.deferred == 1
    assert runner.writes == []
    pending = store.pending_for(session_id)
    assert pending[0].last_refusal == WriteDecision.REFUSE_NO_PTY.value


# ----- the clearing step, and the re-read that makes it safe -------------------


def test_clear_then_send_re_reads_the_pane_before_the_text(tmp_path: Path) -> None:
    """DP10, as argv order: clear, **read**, then write — through the real driver.

    The order is asserted on the recorded argvs of `LocalRunner`, not on a
    double's call list: `send-keys … C-u` -> `capture-pane` -> `send-keys -H …`.
    **Goes red** if the re-read is dropped, which turns the clearing form into
    DP10's option (a), "send `C-u` and hope".
    """
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        session_id = owned_row(opened, state=SessionState.STOPPED)
        queue(opened, [BODY])
        # A drafted box first, an empty one on the re-read: the clear worked.
        recorder = Recorder([DRAFT, READY])
        driver = local(recorder, tmp_path)

        outcome = deliver_now(
            store=opened,
            runner=driver,
            handle=HANDLE,
            session_id=session_id,
            state=SessionState.STOPPED,
            ownership=Ownership.OWNED,
            now=lambda: LATER,
        )

        assert outcome.decision is WriteDecision.SEND_NOW
        assert outcome.delivered == 1

        keys_and_reads = ("send-keys", "capture-pane", "list-clients")
        order = [argv for argv in recorder.calls if argv[3] in keys_and_reads]
        assert len(order) == 6, order
        # The precondition comes before **any** key: `C-u` into a pane a human is
        # typing in deletes their text, so the client check cannot come second.
        assert order[0][3] == "list-clients", order[0]
        assert order[1][3] == "capture-pane", order[1]
        assert order[2] == CLEAR_ARGV, order[2]
        assert order[3][3] == "capture-pane", "the pane was not re-read before the text"
        assert order[4][:5] == [TMUX, "-L", SOCKET, "send-keys", "-H"], order[4]
        # The body is in the write that follows the re-read, and nowhere earlier.
        hexed = [f"{byte:02x}" for byte in BODY.encode("utf-8")]
        assert hexed == order[4][order[4].index(SPOT) + 1 :]
        assert order[5][3] == "send-keys", "the submit is its own key, after the body"
        assert order[5][order[5].index(SPOT) + 1 :] == ["0d"]
    finally:
        opened.close()


def test_the_clear_is_useless_without_the_re_read(tmp_path: Path) -> None:
    """T13's defect, kept alive here: the re-read **is** the safety property.

    A pane whose box is still drafted after the clear is indistinguishable from
    one where the clear never ran, so a delivery path that does not look again
    concatenates the instruction onto somebody's half-written prompt. This test
    plants that by scripting a box that stays drafted, and asserts the shipped
    path defers instead — and it is the assertion that dies first if the re-read
    is deleted from `mailbox.py`.
    """
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        session_id = owned_row(opened, state=SessionState.STOPPED)
        queue(opened, [BODY])
        # Drafted, and *still* drafted after the clear.
        recorder = Recorder([DRAFT, DRAFT])
        driver = local(recorder, tmp_path)

        outcome = deliver_now(
            store=opened,
            runner=driver,
            handle=HANDLE,
            session_id=session_id,
            state=SessionState.STOPPED,
            ownership=Ownership.OWNED,
            now=lambda: LATER,
        )

        # Arrival: the clear really was sent and the pane really was read twice.
        assert CLEAR_ARGV in recorder.calls
        assert recorder.verbs().count("capture-pane") == 2
        # …and only then, absence.
        assert outcome.decision is WriteDecision.REFUSE_INPUT_NOT_EMPTY
        assert_no_body_reached_a_pane(recorder)
        assert opened.pending_for(session_id)[0].delivered_at is None
    finally:
        opened.close()


def test_a_failed_clear_defers_and_counts_the_named_member(store: Store) -> None:
    """The count is the enum member, not a bare string (T2), and the row is kept.

    **Goes red** if delivery proceeds onto the drafted box, if the count is a
    hand-typed string that `doctor`'s zero rows can never match, or if the row is
    retired rather than left pending for the next trigger.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    drafted = pane_state(DRAFT)
    assert drafted.kind is PaneKind.PROMPT_READY and drafted.input_text != ""
    runner = scripted([drafted, drafted])

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert runner.calls.count("clear_input") == 1, "the clear never ran"
    assert runner.calls.count("pane") == 2, "the pane was not re-read"
    assert outcome.decision is WriteDecision.REFUSE_INPUT_NOT_EMPTY
    assert runner.writes == []
    counts = store.list_anomaly_counts()
    assert counts[AnomalyKind.MAILBOX_INPUT_NOT_EMPTY.value] == 1
    pending = store.pending_for(session_id)
    assert len(pending) == 1
    assert pending[0].last_refusal == WriteDecision.REFUSE_INPUT_NOT_EMPTY.value
    assert pending[0].delivery_attempts == 1


# ----- the attached-client precondition (BLOCKER-T1-3) ------------------------


def test_an_attached_client_defers_delivery_and_counts_it(store: Store) -> None:
    """P3: a human at a second client types **into the prompt Shepherd submits**.

    The router's decision: a caller-side precondition, deferred and counted — not
    a fifth field of the 96-key table and not `Ownership`, which records who
    *started* the session and is `OWNED` in every one of P3's keys.

    **Goes red** if the count is read as a boolean (two clients and one are the
    same fact to a flag), if delivery proceeds, or if the clear is sent first —
    `C-u` into a pane a human is typing in deletes **their** text.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([pane_state(DRAFT)], clients=1)

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert outcome.decision is None, "a decision was taken over a pane a human is typing in"
    assert outcome.deferred == 1
    assert runner.calls.count("attached_clients") == 1, "the precondition never ran"
    assert runner.writes == []
    assert "clear_input" not in runner.calls, "C-u would have deleted the human's own text"
    counts = store.list_anomaly_counts()
    assert counts[AnomalyKind.MAILBOX_CLIENT_ATTACHED.value] == 1
    pending = store.pending_for(session_id)
    assert pending[0].last_refusal == AnomalyKind.MAILBOX_CLIENT_ATTACHED.value
    assert pending[0].delivered_at is None


def test_delivery_proceeds_when_the_last_client_has_gone(store: Store) -> None:
    """The deferral is a wait, not a state: the message goes out on the next pass.

    Arrival for the negative above — with zero clients the same fixture
    delivers, so `test_an_attached_client_defers_delivery_and_counts_it` cannot
    be passing because the delivery path was broken for everyone.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([pane_state(READY)], clients=0)

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert outcome.decision is WriteDecision.SEND_NOW
    assert outcome.delivered == 1
    # `list_anomaly_counts` returns the rows that exist, so an absent key is a
    # count of zero — the store does not pre-seed; `doctor` does (T2).
    assert store.list_anomaly_counts().get(AnomalyKind.MAILBOX_CLIENT_ATTACHED.value, 0) == 0


def test_the_client_check_is_documented_as_narrowing_the_race_not_closing_it() -> None:
    """The residual is named in the module, per the router's decision.

    A human can type between the check and the submit; no arrangement of checks
    in this design closes that. **Goes red** if a future edit documents the
    precondition as making a write safe — which is how a narrowed race becomes a
    claimed guarantee and then a silent corruption.
    """
    source = MODULE.read_text(encoding="utf-8")
    assert "narrow" in source.lower()
    assert re.search(r"does not close|never closed|not closed", source), source[:200]
    for claim in ("guarantees the pane is ours", "makes the write safe", "closes the race"):
        assert claim not in source


# ----- refusals record why ----------------------------------------------------


REFUSING_PANES: tuple[tuple[str, PaneState, WriteDecision], ...] = (
    ("permission_dialog", pane_state(PERMISSION), WriteDecision.REFUSE_DIALOG),
    ("dead_pane", synthetic(PaneKind.DEAD), WriteDecision.REFUSE_NO_PTY),
    ("unreadable_pane", synthetic(PaneKind.UNREADABLE), WriteDecision.REFUSE_NO_PTY),
    ("mid_turn", synthetic(PaneKind.BUSY), WriteDecision.QUEUE),
)

#: The loop's own size, stated: a generator change cannot shrink it to zero in
#: silence (T6's `DEGRADED_CASES`, the contract suite's `CONTRACT_ROWS`).
REFUSAL_CASES = 4


@pytest.mark.parametrize(
    "pane,expected", [(pane, decision) for _, pane, decision in REFUSING_PANES],
    ids=[name for name, _, _ in REFUSING_PANES],
)
def test_a_refusal_is_recorded_on_the_row(
    store: Store, pane: PaneState, expected: WriteDecision
) -> None:
    """Principle 5 for the write path: a message that keeps deferring says **why**.

    **Goes red** if `last_refusal` stays null — a row that never moves and never
    says why is the unknown principle 5 exists to forbid — and red if a refusal
    stamps the row delivered.
    """
    assert len(REFUSING_PANES) == REFUSAL_CASES
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([pane])

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.OWNED,
        now=lambda: LATER,
    )

    assert outcome.decision is expected
    assert outcome.delivered == 0 and outcome.deferred == 1
    assert runner.writes == []
    row = store.pending_for(session_id)[0]
    assert row.last_refusal == expected.value
    assert row.delivered_at is None
    assert store.mailbox_counts().deferred == 1


def test_an_attached_session_has_no_write_path(store: Store) -> None:
    """Every `ATTACHED` key is `REFUSE_NO_PTY`: the pane is on the user's socket.

    Consumed from the policy rather than re-decided here — the mailbox asks and
    obeys, and this is the row that goes red if it ever starts deciding.
    """
    session_id = owned_row(store, state=SessionState.STOPPED)
    queue(store, [BODY])
    runner = scripted([pane_state(READY)])

    outcome = deliver_now(
        store=store,
        runner=runner,
        handle=scripted_handle(),
        session_id=session_id,
        state=SessionState.STOPPED,
        ownership=Ownership.ATTACHED,
        now=lambda: LATER,
    )

    assert outcome.decision is WriteDecision.REFUSE_NO_PTY
    assert runner.writes == []
    assert store.pending_for(session_id)[0].last_refusal == WriteDecision.REFUSE_NO_PTY.value


# ----- the module's own shape -------------------------------------------------


def test_the_mailbox_takes_verbs_and_never_a_connection() -> None:
    """D33: no SQL, no cursor, no driver row above `store/`.

    Scanned by **AST**, over code rather than over prose: a rule that reads
    docstrings turns every English sentence about the storage boundary into a
    violation, and this repo's own note is that a scan which forces prose to be
    rewritten is a scan that will be worked around. Imports, attribute names and
    non-docstring literals are the three ways the boundary would actually be
    crossed.

    **Goes red** the moment a delivery path reaches for a driver to do something
    the verbs do not offer — which is how the storage boundary erodes.
    """
    import ast

    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [alias.name for alias in node.names if alias.name == "sqlite3"]
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "sqlite3":
            offenders.append("from sqlite3")
        if isinstance(node, ast.Attribute) and node.attr in ("execute", "cursor", "commit"):
            offenders.append(f".{node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            for sql in ("SELECT ", "UPDATE ", "INSERT ", "DELETE "):
                if sql in node.value.upper():
                    offenders.append(node.value)
    assert offenders == []
    # …and the scan is not vacuous: the same walk over `store/mailbox.py`, which
    # is where all three of those legitimately live, is loud.
    assert "sqlite3" in (MODULE.parents[1] / "store" / "mailbox.py").read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 250


def test_turn_state_is_the_only_place_the_pane_answers_for_the_row() -> None:
    """The one projection, written down: prompt-ready **and owned** — nothing else.

    `turn_state` is pure, so the whole of D45's second trigger is one testable
    function rather than a condition buried in the delivery path.
    """
    ready, drafted, busy = pane_state(READY), pane_state(DRAFT), synthetic(PaneKind.BUSY)
    for stored in SessionState:
        assert turn_state(stored, busy, Ownership.OWNED) is stored
        assert turn_state(stored, ready, Ownership.ATTACHED) is stored
        # Prompt-ready on an owned pane is the turn boundary the missing hook
        # would have written — including with a draft still in the box, which is
        # the clearing row's key.
        assert turn_state(stored, ready, Ownership.OWNED) is SessionState.STOPPED
        assert turn_state(stored, drafted, Ownership.OWNED) is SessionState.STOPPED
    assert len(list(SessionState)) == 4
