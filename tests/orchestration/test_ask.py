"""T15 — `ask()` via a headless fork: acceptance clause 6, in four claims.

Clause 6 reads: *"`ask()` forks headlessly, **never touches its target**, and
**never deletes a file the engine owns**. The target's transcript sha256 is
unchanged live; `method` is **always** reported; the `can_fork=False` mailbox
fallback exists and says so. Any transcript residue is **named and counted,
never removed**."*

**The claim most likely to be satisfied by code that never reaches the file is
"never removes".** A module that does not open the project directory at all
passes any test that only asserts a file still exists. So every residue test
here **asserts arrival before absence**: the anomaly count and the durable
`app_state` record prove `ask()` walked the directory and *found* the file, and
only then is the file's continued existence and byte-identity asserted. A scan
of the module's own AST for the write verbs backs it up, and that scan has a
negative control proving it stays quiet and a positive fixture proving it fires.

**Nothing here writes its own copy of the engine's answer.** `parse_fork_result`
is fed **P2's real captured stdout bytes** —
`docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/02-fork-with-session-id.stdout.json`
and its `--no-session-persistence` sibling — because a fixture hand-written in
the shape the parser accepts proves only that the parser agrees with the test
(M1's `signals/ordering.py` finding). The fork argv's flag order is likewise
**parsed out of P2's `.argv.txt` captures**, never typed here.

**The `ASK_FORK_RESIDUE` inversion (BLOCKER-T1-2, router note).** P2 measured
that `--no-session-persistence` leaves **no** transcript at all, so the member's
original sentence — "P2 says a fork transcript is left" — fired on the *normal*
path and was silent on the regression. The corrected member fires when residue
is **found**. Both directions are asserted: silent when the flag did its job,
counted when a transcript is there.

`tests/` is not a package, so `markdown_headings` comes from
`engines.test_spawn_argv` — the `from golden.corpus import ...` idiom.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from engines.test_spawn_argv import markdown_headings
from shepherd.core.anomalies import AnomalyKind
from shepherd.core.mailbox import MailboxOrigin
from shepherd.core.runner import RunnerRefusal
from shepherd.core.states import Origin, SessionState
from shepherd.core.stops import StopReason
from shepherd.engines.claude_code.fork import (
    FORK_RULES,
    ForkResult,
    fork_argv,
    parse_fork_result,
)
from shepherd.orchestration.ask import ASK_RECORD_PREFIX, AskResult, ask_session
from shepherd.store.db import Store, open_store
from shepherd.store.models import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "shepherd"
ASK_MODULE = SRC_ROOT / "orchestration" / "ask.py"
FORK_MODULE = SRC_ROOT / "engines" / "claude_code" / "fork.py"
ANOMALIES_MODULE = SRC_ROOT / "core" / "anomalies.py"
PROBES = REPO_ROOT / "docs" / "probes"
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"

P2 = PROBES / "2026-09-17-m3-tmux" / "p2-fork-20260917T110431Z"
#: The fork that was given `--session-id` and left a transcript (the control).
FORK_STDOUT = P2 / "02-fork-with-session-id.stdout.json"
#: The same fork *with* `--no-session-persistence`: rc 0, no transcript left.
NSP_STDOUT = P2 / "03-fork-nsp-with-session-id.stdout.json"
NSP_ARGV = P2 / "03-fork-nsp-with-session-id.argv.txt"

#: A **real** transcript, written by the engine, used as the ask target's file.
#: Hashing bytes we wrote ourselves would prove only that we can copy a string.
REAL_TRANSCRIPT = (
    PROBES
    / "2026-09-14-schemas"
    / "transcripts"
    / "copies"
    / "-tmp-shp-schemas-fork-RgNHRN-work"
    / "de7c8ce7-f01c-4dcb-8219-b3d3d8b46178.jsonl"
)
#: The fork's own transcript from the same probe — the shape residue really has.
REAL_FORK_TRANSCRIPT = (
    PROBES
    / "2026-09-14-schemas"
    / "transcripts"
    / "copies"
    / "-tmp-shp-schemas-fork-RgNHRN-work"
    / "76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl"
)

SESSION_ID = "01J0000000000000000TARGET"
TARGET_ENGINE_ID = "bf35fe01-96ca-4f9b-923c-3b8c9331191f"
#: P2's own uuids, so the ids in this file are the ones the probe really used.
FORK_ENGINE_ID = "356b6e66-635e-424c-80fd-fef653880906"
NSP_FORK_ENGINE_ID = "d8c9ba08-690b-429a-8339-b15d2b78544d"
SLUG = "-tmp-shp-m3-t15-work"
BINARY = "/usr/local/bin/claude"
QUESTION = "What is the codeword? Reply with only the codeword."
NOW = "2026-09-17T11:04:31.500000+00:00"
LATER = "2026-09-17T11:04:33.176000+00:00"
#: `LATER - NOW`, worked out by hand from the two stamps above: 1.676 s.
EXPECTED_DURATION_MS = 1676


# ----- doubles ---------------------------------------------------------------


class ForkRuns:
    """A fork runner that records, and that **enforces the timeout it is given**.

    The production adapter is `subprocess.run(argv, timeout=...)`, which kills
    the child before it raises. This double models exactly that: it kills only
    when a timeout it was actually handed has elapsed, so a caller that forgets
    to pass one leaves `killed` false — which is the mutation
    `test_a_timeout_kills_the_fork_and_returns_a_readable_refusal` watches for.
    """

    def __init__(self, stdout: bytes, *, rc: int = 0, runs_for_ms: int = 0) -> None:
        self._stdout = stdout
        self._rc = rc
        self._runs_for_ms = runs_for_ms
        self.argvs: list[list[str]] = []
        self.timeouts: list[int] = []
        self.killed = False

    def __call__(self, argv: list[str], *, timeout_ms: int) -> object:
        from shepherd.runner.local import CommandResult

        self.argvs.append(list(argv))
        self.timeouts.append(timeout_ms)
        if self._runs_for_ms > timeout_ms:
            self.killed = True
            raise RunnerRefusal(
                f"the fork was killed after {timeout_ms} ms without answering"
            )
        return CommandResult(rc=self._rc, stdout=self._stdout, stderr=b"")


class Clock:
    """One clock, two readings: the stamp before the fork and the one after."""

    def __init__(self, *stamps: str) -> None:
        self._stamps = list(stamps)
        self.reads = 0

    def __call__(self) -> str:
        value = self._stamps[min(self.reads, len(self._stamps) - 1)]
        self.reads += 1
        return value


# ----- fixtures --------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def workspace_id(store: Store, tmp_path: Path) -> str:
    root = tmp_path / "work"
    root.mkdir()
    return store.upsert_workspace("shepherd", str(root)).id


@pytest.fixture()
def projects_root(tmp_path: Path) -> Path:
    """`<config>/projects/`, with the **target's real transcript** already in it."""
    root = tmp_path / "projects"
    (root / SLUG).mkdir(parents=True)
    (root / SLUG / f"{TARGET_ENGINE_ID}.jsonl").write_bytes(REAL_TRANSCRIPT.read_bytes())
    return root


@pytest.fixture()
def target(store: Store, workspace_id: str, tmp_path: Path) -> str:
    store.create_owned_session(
        session_id=SESSION_ID,
        engine_session_id=TARGET_ENGINE_ID,
        workspace_id=workspace_id,
        repo_id=None,
        cwd=str(tmp_path / "work"),
        started_at=NOW,
        origin=Origin.ORCHESTRATOR,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=None,
        model=None,
        effort=None,
    )
    return SESSION_ID


def ask(
    store: Store,
    projects_root: Path,
    runs: ForkRuns,
    *,
    can_fork: bool = True,
    clock: Clock | None = None,
    timeout_ms: int = 120_000,
) -> AskResult:
    return ask_session(
        store=store,
        run_fork=runs,
        now=clock or Clock(NOW, LATER),
        binary=BINARY,
        projects_root=projects_root,
        can_fork=can_fork,
        session_id=SESSION_ID,
        question=QUESTION,
        timeout_ms=timeout_ms,
    )


def anomaly(store: Store, kind: AnomalyKind) -> int:
    return store.list_anomaly_counts().get(str(kind.value), 0)


def ask_rows(store: Store) -> list[Session]:
    return [row for row in store.list_sessions() if row.origin is Origin.ASK_FORK]


def residue(projects_root: Path, engine_session_id: str) -> Path:
    path = projects_root / SLUG / f"{engine_session_id}.jsonl"
    path.write_bytes(REAL_FORK_TRANSCRIPT.read_bytes())
    return path


#: ADR-6's one declared structural exclusion, named once here as `_imports.py`
#: names its own: the module constants that exist only to build an `evidence`
#: string. A citation must be free to name the probe folder it cites —
#: `2026-09-17-m3-tmux` — without the folder's name reading as a dependency.
EVIDENCE_CONSTANTS = frozenset({"_P2", "_FORK_SECTION"})


def spelled(path: Path, *, exclude_assigned_to: frozenset[str] = EVIDENCE_CONSTANTS) -> set[str]:
    """Every string literal and every identifier a module really *uses*.

    **Comments and docstrings are excluded, and that is the point.** A raw-text
    scan cannot tell the rule from the prose explaining the rule: T12's first
    draft went red because its docstring quoted the SQL its own rule forbids
    (T12-5). Here the module explains that `forkedFrom` does not exist, and a
    `in source` check would read that sentence as the violation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    excluded = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id in exclude_assigned_to
            for target in node.targets
        )
    }
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    words: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings and node not in excluded:
                words.add(node.value)
        elif isinstance(node, ast.Attribute):
            words.add(node.attr)
        elif isinstance(node, ast.Name):
            words.add(node.id)
        elif isinstance(node, ast.ImportFrom) and node.module:
            words.add(node.module)
            words.update(alias.name for alias in node.names)
    return words


def test_the_spelling_scan_reads_code_and_not_prose(tmp_path: Path) -> None:
    """The scan's own self-check, both directions (the M3 T2/T3 rule).

    A word only in a docstring is invisible; the same word in a literal fires.
    Without this, every assertion built on `spelled()` could be vacuous.
    """
    prose = tmp_path / "prose.py"
    prose.write_text('"""We never read forkedFrom."""\nX = 1\n', encoding="utf-8")
    assert "forkedFrom" not in spelled(prose)
    real = tmp_path / "real.py"
    real.write_text('X = {"forkedFrom": 1}\n', encoding="utf-8")
    assert "forkedFrom" in spelled(real)
    # …and the evidence exclusion is what silences a citation, not an unread
    # file: the same literal fires when it is not in the excluded position (B1).
    cited = tmp_path / "cited.py"
    cited.write_text('_P2 = "probes/m3-tmux"\n', encoding="utf-8")
    assert "probes/m3-tmux" not in spelled(cited)
    assert "probes/m3-tmux" in spelled(cited, exclude_assigned_to=frozenset())
    with pytest.raises(FileNotFoundError):
        spelled(tmp_path / "missing.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----- 1. the result object comes from a real capture -------------------------


def test_parse_fork_result_reads_p2s_own_captured_stdout() -> None:
    """The parser is fed the engine's bytes, never a shape this file invented."""
    parsed = parse_fork_result(FORK_STDOUT.read_bytes())
    assert parsed == ForkResult(
        result="PINEAPPLE-M3",
        session_id=FORK_ENGINE_ID,
        is_error=False,
        subtype="success",
    )
    nsp = parse_fork_result(NSP_STDOUT.read_bytes())
    assert nsp is not None
    assert (nsp.session_id, nsp.result) == (NSP_FORK_ENGINE_ID, "PINEAPPLE-M3")


@pytest.mark.parametrize(
    ("name", "stdout"),
    [
        ("not json at all", b"claude: command not found\n"),
        ("json but not an object", b"[1, 2, 3]"),
        ("an object with no session_id", b'{"type":"result","result":"hi"}'),
        ("session_id of the wrong type", b'{"session_id": 7, "result": "hi"}'),
        ("invalid utf-8", b"\xff\xfe{}"),
        ("empty", b""),
    ],
)
def test_parse_fork_result_degrades_and_never_raises(name: str, stdout: bytes) -> None:
    """`None` degrades; a raise here would turn a bad answer into a crash."""
    assert parse_fork_result(stdout) is None, name


def test_the_degrade_cases_are_the_six_written_down() -> None:
    """A parametrized loop asserts its own case count (this repo's rule)."""
    cases = test_parse_fork_result_degrades_and_never_raises.pytestmark[0].args[1]
    assert len(cases) == 6
    assert len({name for name, _ in cases}) == 6


# ----- 2. the argv, parsed out of P2's capture --------------------------------


def captured_fork_flags() -> list[str]:
    """P2's own `--no-session-persistence` fork argv, flags only, in order.

    Read from the capture rather than retyped: a flag order typed in two places
    can agree with itself while both are wrong.
    """
    words = NSP_ARGV.read_text(encoding="utf-8").split()
    return [word for word in words if word.startswith("--") or word == "-p"]


def test_the_fork_argv_matches_p2s_captured_argv_verbatim() -> None:
    """Every flag P2 ran, in P2's order, minus the two the probe alone passes."""
    probe_only = {"--model", "--settings"}
    expected = [flag for flag in captured_fork_flags() if flag not in probe_only]
    argv = fork_argv(
        binary=BINARY,
        engine_session_id=TARGET_ENGINE_ID,
        question=QUESTION,
        fork_session_id=FORK_ENGINE_ID,
    )
    assert [word for word in argv if word.startswith("-")] == expected
    assert expected == [
        "-p",
        "--output-format",
        "--resume",
        "--fork-session",
        "--session-id",
        "--no-session-persistence",
    ], expected
    assert argv[0] == BINARY
    assert argv[-1] == QUESTION
    assert argv[argv.index("--resume") + 1] == TARGET_ENGINE_ID
    assert argv[argv.index("--session-id") + 1] == FORK_ENGINE_ID


def test_the_fork_argv_has_no_shell_and_carries_no_settings_of_ours() -> None:
    """K5: separate words, no `--settings`, nothing a shell would re-read.

    A19: one command string goes through `sh -c`, which expands `$()` and strips
    quotes — so a question carrying either must survive as one argv word.
    """
    hostile = 'What is $(whoami)? Use "quotes" & ; | backticks `x`'
    argv = fork_argv(
        binary=BINARY,
        engine_session_id=TARGET_ENGINE_ID,
        question=hostile,
        fork_session_id=FORK_ENGINE_ID,
    )
    assert hostile in argv, "the question must stay one word, never a command string"
    assert len(argv) == 11, argv
    assert "--settings" not in argv
    assert not any(" " in word for word in argv if word.startswith("-"))


def test_the_fork_session_id_is_optional_and_p2_says_pass_it() -> None:
    """P2's control ran without it; the engine then generates the id."""
    without = fork_argv(
        binary=BINARY,
        engine_session_id=TARGET_ENGINE_ID,
        question=QUESTION,
        fork_session_id=None,
    )
    assert "--session-id" not in without
    assert "--no-session-persistence" in without


def test_a_question_that_could_be_read_as_a_flag_is_refused() -> None:
    """A11's `--` separator is captured for the spawn argv and **not** for this
    one, so a leading `-` is refused rather than guessed at (K1)."""
    with pytest.raises(RunnerRefusal) as refused:
        fork_argv(
            binary=BINARY,
            engine_session_id=TARGET_ENGINE_ID,
            question="--help me",
            fork_session_id=None,
        )
    assert "--" in refused.value.reason


# ----- 3. the row: ephemeral from birth, unbound, bound afterwards -------------


def test_the_fork_row_is_ephemeral_from_birth(
    store: Store, target: str, projects_root: Path
) -> None:
    """DP2: an ask that is ephemeral only *after* the process starts is on the
    fleet page for the window in between. Proved by catching the row at the
    moment the fork runs, not by reading it back at the end."""
    seen: list[tuple[bool, str | None, int]] = []

    class Peeking(ForkRuns):
        def __call__(self, argv: list[str], *, timeout_ms: int) -> object:
            rows = ask_rows(store)
            assert len(rows) == 1, rows
            row = rows[0]
            seen.append((bool(row.ephemeral), row.engine_session_id, row.depth))
            return super().__call__(argv, timeout_ms=timeout_ms)

    ask(store, projects_root, Peeking(NSP_STDOUT.read_bytes()))
    assert seen == [(True, None, 1)], seen


def test_an_unbound_ask_row_is_created_and_bound_afterwards(
    store: Store, target: str, projects_root: Path
) -> None:
    """The row is born unbound and bound from the **result object's** id.

    `bind_engine_session_id` is the verb — the conditional write for an unbound
    row — and its rowcount is honoured. `rebind_engine_session_id` is C14's move
    and would be wrong here: swapping it in binds a row nobody may repoint.
    """
    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    rows = ask_rows(store)
    assert len(rows) == 1
    assert rows[0].engine_session_id == NSP_FORK_ENGINE_ID
    assert rows[0].parent_session_id == SESSION_ID
    record = store.get_app_state(f"{ASK_RECORD_PREFIX}{rows[0].id}")
    assert isinstance(record, dict)
    assert record["bound"] is True, record


def test_a_row_another_caller_bound_first_is_not_repointed(
    store: Store, target: str, projects_root: Path
) -> None:
    """Blocker T4-1's whole point, at this seam.

    `bind_engine_session_id` binds an **unbound** row and reports whether *this*
    call bound it; `rebind_engine_session_id` is C14's *move* of an existing
    binding. Swapping one for the other is invisible on the happy path — the row
    really is unbound there, so both succeed — and catastrophic here: a second
    binder would silently repoint a live row and then believe its own fork id was
    on it while the winner's was.

    The other caller binds **during** the fork, which is the only window in which
    this can happen at all. The loser is told `bound: False` and the row keeps
    the id it already had.
    """
    other = "99999999-8888-7777-6666-555555555555"

    class BindsFirst(ForkRuns):
        def __call__(self, argv: list[str], *, timeout_ms: int) -> object:
            assert store.bind_engine_session_id(ask_rows(store)[0].id, other) == 1
            return super().__call__(argv, timeout_ms=timeout_ms)

    ask(store, projects_root, BindsFirst(NSP_STDOUT.read_bytes()))

    row = ask_rows(store)[0]
    assert row.engine_session_id == other, "a bound row may not be repointed"
    record = store.get_app_state(f"{ASK_RECORD_PREFIX}{row.id}")
    assert isinstance(record, dict)
    assert record["bound"] is False, record
    # …and the answer still came back: losing the bind is not losing the reply.
    assert record["engine_session_id"] == NSP_FORK_ENGINE_ID


def test_the_ask_row_is_marked_stopped(
    store: Store, target: str, projects_root: Path
) -> None:
    """The plan's last step. An ask row left `starting` for ever is a phantom."""
    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    row = ask_rows(store)[0]
    assert row.state is SessionState.STOPPED
    assert row.stop_reason == StopReason.COMPLETED.value
    assert row.ended_at == LATER


def test_the_target_row_is_not_touched(
    store: Store, target: str, projects_root: Path
) -> None:
    """"Never touches its target" reaches the row as well as the file."""
    before = store.get_owned_session(SESSION_ID)
    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    assert store.get_owned_session(SESSION_ID) == before


# ----- 4. clause 6: the target's transcript is unchanged ----------------------


def test_the_target_transcript_is_unchanged(
    store: Store, target: str, projects_root: Path
) -> None:
    """C-M3-10, deterministically (T24 runs the live row).

    The digest is taken of a **real** engine-written transcript, and residue is
    planted in the same directory so the walk that finds the residue is the same
    walk that could have touched this file.
    """
    target_file = projects_root / SLUG / f"{TARGET_ENGINE_ID}.jsonl"
    before = sha256(target_file)
    residue(projects_root, NSP_FORK_ENGINE_ID)

    result = ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))

    assert result.text == "PINEAPPLE-M3"
    assert target_file.exists()
    assert sha256(target_file) == before


# ----- 5. clause 6: residue is named and counted, never removed ---------------


def test_residue_found_is_counted_named_and_left_on_disk(
    store: Store, target: str, projects_root: Path
) -> None:
    """**Arrival before absence.** The count and the record prove `ask()` reached
    the file; only then is "it is still there, byte for byte" worth asserting.

    A module that never opens the project directory fails the first two
    assertions, so it can never reach the third and claim the property.
    """
    left = residue(projects_root, NSP_FORK_ENGINE_ID)
    digest = sha256(left)
    assert anomaly(store, AnomalyKind.ASK_FORK_RESIDUE) == 0

    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))

    # arrival: it looked, and it found.
    assert anomaly(store, AnomalyKind.ASK_FORK_RESIDUE) == 1
    record = store.get_app_state(f"{ASK_RECORD_PREFIX}{ask_rows(store)[0].id}")
    assert isinstance(record, dict)
    assert record["residue_path"] == str(left), record
    # …and only now: it did not remove it, and did not rewrite it either.
    assert left.exists()
    assert sha256(left) == digest


def test_the_anomaly_is_silent_when_the_flag_did_its_job(
    store: Store, target: str, projects_root: Path
) -> None:
    """The inversion's other half (BLOCKER-T1-2).

    P2's `--no-session-persistence` run left **no** file. The member as T2 wrote
    it — "P2 says a fork transcript is left" — would have fired here, on the
    normal path, and stayed silent on the regression above. A counter that fires
    every time is a lie (K9).
    """
    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    assert anomaly(store, AnomalyKind.ASK_FORK_RESIDUE) == 0
    record = store.get_app_state(f"{ASK_RECORD_PREFIX}{ask_rows(store)[0].id}")
    assert isinstance(record, dict)
    assert record["residue_path"] is None, record


def test_residue_is_looked_for_under_the_id_the_engine_reported(
    store: Store, target: str, projects_root: Path
) -> None:
    """If `--session-id` were ever ignored, the residue carries the **engine's**
    id, not ours. Looking only under the id we asked for would report a clean
    run on exactly the regression this member exists to catch."""
    left = residue(projects_root, FORK_ENGINE_ID)  # 02's id: not the one 03 reports
    runs = ForkRuns(FORK_STDOUT.read_bytes())
    ask(store, projects_root, runs)
    assert anomaly(store, AnomalyKind.ASK_FORK_RESIDUE) == 1
    assert left.exists()


def member_docstring(path: Path, member: str) -> str:
    """The docstring written under one enum member, read from the source.

    A string under an assignment is **not** kept at runtime — `AnomalyKind.X.__doc__`
    answers with the *class* docstring — so a test asserting on the attribute
    would have been asserting on the wrong text entirely and passing by accident.
    """
    body = ast.parse(path.read_text(encoding="utf-8")).body
    classes = [node for node in body if isinstance(node, ast.ClassDef)]
    statements = [line for node in classes for line in node.body]
    for index, line in enumerate(statements[:-1]):
        assigned = (
            isinstance(line, ast.Assign)
            and len(line.targets) == 1
            and isinstance(line.targets[0], ast.Name)
            and line.targets[0].id == member
        )
        following = statements[index + 1]
        if assigned and isinstance(following, ast.Expr):
            value = following.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    raise AssertionError(f"{member} has no docstring in {path}")


def test_the_member_docstring_reader_is_not_reading_the_class_docstring() -> None:
    """The reader's own control: a neighbour's text is a *different* string, and
    the class docstring is not any member's."""
    residue = member_docstring(ANOMALIES_MODULE, "ASK_FORK_RESIDUE")
    neighbour = member_docstring(ANOMALIES_MODULE, "MAILBOX_INPUT_NOT_EMPTY")
    assert residue != neighbour
    assert residue != (AnomalyKind.__doc__ or "")
    assert "DP10" in neighbour


def test_the_anomaly_docstring_names_the_corrected_trigger() -> None:
    """The member's sentence is what the next reader believes (M2 T12 finding 10).

    It must say residue was **found**, and must not still say "P2 says a fork
    transcript is left" — the sentence that fired on the normal path.
    """
    text = member_docstring(ANOMALIES_MODULE, "ASK_FORK_RESIDUE")
    lowered = " ".join(text.split()).lower()
    # The **first sentence** is the trigger: it is what a reader takes as the
    # definition and what `doctor`'s column means. Asserted on its own rather
    # than over the whole text, because the paragraph below it deliberately
    # *quotes* the superseded sentence to explain the correction — and a
    # whole-text scan cannot tell a rule from the prose about the rule (T12-5).
    trigger = lowered.split(".")[0]
    assert "found" in trigger, trigger
    assert "left" not in trigger, trigger
    assert "corrected" in lowered, text
    assert "blocker-t1-2" in lowered, text
    assert "never deleted" in lowered or "never removed" in lowered, text


#: The set as it stood when T15 landed, in order. **A prefix, not the whole
#: list**: clause 14 forbids *reordering*, not *appending*, and T16 appended
#: `DIALOG_TEXT_UNRECOGNISED` while this task was in flight. An assertion
#: written as "the last seven are …" would have turned that legal append red
#: and taught the next builder to edit the test instead of the code.
MEMBERS_AT_T15: tuple[str, ...] = (
    "MALFORMED_PAYLOAD", "UNKNOWN_EVENT_NAME", "UNMAPPED_NOTICE", "SUBAGENT_UNDERFLOW",
    "MISSING_SUBAGENT_TRANSCRIPT", "SUBAGENT_STATE_UNKNOWN", "TOOL_BLOCKED_BY_HOOK",
    "TOOL_PERMISSION_REFUSED", "UNKNOWN_REGISTRY_STATUS", "STOP_FAILED", "GIT_NO_REMOTE",
    "GIT_AMBIGUOUS_REMOTE", "GIT_DUBIOUS_OWNERSHIP", "GIT_BARE_REPO", "GIT_NOT_A_REPO",
    "STOP_UNMAPPED_VALUE", "STOP_DEFERRED_VALUE", "EXIT_CODE_UNOBSERVABLE",
    "TRANSCRIPT_TAIL_ABSENT", "TRANSCRIPT_TAIL_TRUNCATED", "TOOL_RESULT_UNPAIRED",
    "KILL_WITHOUT_SESSION_END", "MAILBOX_INPUT_NOT_EMPTY", "ASK_FORK_RESIDUE",
    "ORPHANED_PANE", "PANE_UNREADABLE", "SIDECAR_ABSENT", "MAILBOX_CLIENT_ATTACHED",
    "TMUX_UNAVAILABLE",
)


def test_the_anomaly_members_are_appended_never_reordered() -> None:
    """Acceptance clause 14, as the property it actually is: **append-only**.

    `doctor` seeds a zero row per member and M2's ordering blocker (T3-2/T4-1)
    stays deferred on this set never being resequenced, so a docstring edit that
    also moved a member would be a different change from the one T15 was asked
    for. The prefix is frozen and growth is permitted only past its end.
    """
    names = [member.name for member in AnomalyKind]
    assert names[: len(MEMBERS_AT_T15)] == list(MEMBERS_AT_T15)
    assert len(names) >= len(MEMBERS_AT_T15)
    # The member T15 edited, pinned by position as well as by presence: a
    # docstring change may not move it.
    assert names.index("ASK_FORK_RESIDUE") == 23
    assert names[22:25] == ["MAILBOX_INPUT_NOT_EMPTY", "ASK_FORK_RESIDUE", "ORPHANED_PANE"]


def test_the_ordering_rule_would_catch_a_reorder_and_allow_an_append() -> None:
    """Both directions of the rule, on the rule's own comparison.

    Without this, "prefix equality" could be satisfied by a prefix so short it
    asserts nothing — and the append allowance could be hiding a resequence.
    """
    names = list(MEMBERS_AT_T15)
    assert names[: len(MEMBERS_AT_T15)] == list(MEMBERS_AT_T15)
    appended = [*names, "SOMETHING_NEW"]
    assert appended[: len(MEMBERS_AT_T15)] == list(MEMBERS_AT_T15)
    swapped = list(names)
    swapped[23], swapped[24] = swapped[24], swapped[23]
    assert swapped[: len(MEMBERS_AT_T15)] != list(MEMBERS_AT_T15)
    assert len(MEMBERS_AT_T15) == 29


# ----- 6. clause 6: never deletes a file the engine owns ----------------------

#: Every verb that could remove or overwrite a file. `read_bytes`, `glob`,
#: `exists` and `stat` are absent on purpose: reading is the whole job.
DESTRUCTIVE = frozenset(
    {
        "unlink", "rmdir", "remove", "rmtree", "rename", "replace", "write_text",
        "write_bytes", "truncate", "touch", "chmod", "mkdir", "makedirs", "open",
    }
)


def destructive_calls(path: Path) -> list[str]:
    """Names in `DESTRUCTIVE` called anywhere in one module. Opens the file first
    (B1): a scan that returns `[]` for a path that does not exist is a tautology.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in DESTRUCTIVE:
            found.append(f"line {node.lineno}: {name}")
    return found


def test_ask_never_calls_a_verb_that_could_remove_a_file() -> None:
    """K3/N6: D13's "discard" means the session, never the file.

    The AST rule is the second proof, not the first — the behavioural test above
    is what shows the file was *reached*. This one catches the delete that is
    typed but not yet exercised.
    """
    assert destructive_calls(ASK_MODULE) == []
    with pytest.raises(FileNotFoundError):
        destructive_calls(ASK_MODULE.with_name("no_such_module.py"))


def test_the_destructive_scan_actually_fires(tmp_path: Path) -> None:
    """A scan needs a positive control as well as a negative one. This is the
    exact line the plan forbids — the fork-transcript cleanup step."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "from pathlib import Path\n"
        "def clean(p: Path) -> None:\n"
        "    p.unlink()\n",
        encoding="utf-8",
    )
    assert [entry.split(": ")[1] for entry in destructive_calls(planted)] == ["unlink"]


def test_the_fork_id_comes_from_the_result_object_not_the_sidecar(
    store: Store, target: str, projects_root: Path, tmp_path: Path
) -> None:
    """`registry.py:3-5` — the engine deletes the sidecar on exit, so by the time
    `ask()` has a result the file is reliably gone. Reading it is a race this
    plan elsewhere depends on losing. Asserted two ways: the module names no
    sidecar path, and the bound id is the one the *result object* carried."""
    words = spelled(ASK_MODULE)
    assert not [word for word in words if "sessions/" in word], words
    assert "parse_sidecar" not in words
    assert not [word for word in words if "registry" in word], words

    ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    assert ask_rows(store)[0].engine_session_id == NSP_FORK_ENGINE_ID


def test_from_fork_of_comes_from_our_own_row_not_from_the_transcript(
    store: Store, target: str, projects_root: Path
) -> None:
    """E-M3-33. There is no `forkedFrom` field — the engine's only parent link is
    the original `sessionId` left on copied entries, and a copied entry is
    exactly what is planted here. `from_fork_of` must be **our** row's value."""
    planted = projects_root / SLUG / f"{NSP_FORK_ENGINE_ID}.jsonl"
    planted.write_text(
        json.dumps({"sessionId": "11111111-2222-3333-4444-555555555555"}) + "\n",
        encoding="utf-8",
    )
    result = ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()))
    assert result.from_fork_of == TARGET_ENGINE_ID
    assert "forkedFrom" not in spelled(ASK_MODULE)


# ----- 7. `method` is always reported -----------------------------------------


@pytest.mark.parametrize(
    ("case", "can_fork", "expected"),
    [
        ("the fork answers", True, "fork"),
        ("can_fork is False", False, "mailbox"),
    ],
)
def test_the_method_is_reported_never_silently_downgraded(
    store: Store,
    target: str,
    projects_root: Path,
    case: str,
    can_fork: bool,
    expected: str,
) -> None:
    """Principle 5 at the return value: a caller is always told **how** it was
    answered. `method` has no `None`, so a downgrade cannot be silent."""
    result = ask(
        store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()), can_fork=can_fork
    )
    assert result.method == expected, case
    assert result.from_fork_of == TARGET_ENGINE_ID


def test_method_is_reported_on_every_failure_path_too(
    store: Store, target: str, projects_root: Path
) -> None:
    """The three ways a fork can fail to answer still report `fork`."""
    outcomes = {
        "unparseable stdout": ForkRuns(b"not json"),
        "non-zero rc": ForkRuns(NSP_STDOUT.read_bytes(), rc=1),
        "timeout": ForkRuns(NSP_STDOUT.read_bytes(), runs_for_ms=999_999),
    }
    seen = {}
    for name, runs in outcomes.items():
        result = ask_session(
            store=store,
            run_fork=runs,
            now=Clock(NOW, LATER),
            binary=BINARY,
            projects_root=projects_root,
            can_fork=True,
            session_id=SESSION_ID,
            question=QUESTION,
            timeout_ms=1_000,
        )
        seen[name] = (result.method, result.text, result.refusal is not None)
    assert len(seen) == 3
    assert all(method == "fork" for method, _, _ in seen.values()), seen
    assert all(text is None for _, text, _ in seen.values()), seen
    assert all(said_why for _, _, said_why in seen.values()), seen


def test_the_two_methods_are_the_whole_space() -> None:
    """A third method added without a row here would go unasserted."""
    import typing

    annotation = typing.get_type_hints(AskResult, include_extras=False)["method"]
    assert set(typing.get_args(annotation)) == {"fork", "mailbox"}


# ----- 8. the `can_fork=False` mailbox fallback exists and says so -------------


def test_the_fallback_is_the_mailbox_and_it_says_so(
    store: Store, target: str, projects_root: Path
) -> None:
    """Clause 6's third claim. The question is queued for the target — as a
    message, never as a fork — and the refusal names the capability."""
    runs = ForkRuns(NSP_STDOUT.read_bytes())
    result = ask(store, projects_root, runs, can_fork=False)

    assert runs.argvs == [], "nothing may be started when the engine cannot fork"
    assert result.method == "mailbox"
    assert result.text is None
    assert result.refusal is not None
    assert "can_fork" in result.refusal
    assert "mailbox" in result.refusal.lower()

    pending = store.pending_for(SESSION_ID)
    assert [message.body for message in pending] == [QUESTION]
    assert pending[0].origin is MailboxOrigin.SESSION
    assert ask_rows(store) == [], "a mailbox fallback starts no session"


# ----- 9. the timeout ---------------------------------------------------------


def test_a_timeout_kills_the_fork_and_returns_a_readable_refusal(
    store: Store, target: str, projects_root: Path
) -> None:
    """A timeout that leaves a process behind is a leak per call on a fleet
    machine. The timeout must **reach the runner**: the double kills only when
    it was handed one, so a caller that drops it leaves `killed` false."""
    runs = ForkRuns(NSP_STDOUT.read_bytes(), runs_for_ms=999_999)
    result = ask(store, projects_root, runs, timeout_ms=1_500)

    assert runs.timeouts == [1_500], "the caller's timeout must reach the runner"
    assert runs.killed is True
    assert result.method == "fork"
    assert result.text is None
    assert result.refusal is not None
    assert "1500" in result.refusal or "1,500" in result.refusal
    row = ask_rows(store)[0]
    assert row.state is SessionState.STOPPED
    assert row.stop_reason == StopReason.KILLED.value


def test_the_default_timeout_is_the_plans_number() -> None:
    """120 s, and it is a default a caller may override rather than a constant
    buried in the call."""
    signature = inspect.signature(ask_session)
    assert signature.parameters["timeout_ms"].default == 120_000


# ----- 10. no tmux ------------------------------------------------------------


def test_ask_needs_no_tmux(store: Store, target: str, projects_root: Path) -> None:
    """The one mind-reading capability must work on a host with no pane driver.

    Asserted twice: no argv the module builds is a tmux argv, and the module
    imports nothing from `runner/` but the result record's type.
    """
    runs = ForkRuns(NSP_STDOUT.read_bytes())
    ask(store, projects_root, runs)
    assert runs.argvs != []
    for argv in runs.argvs:
        assert "tmux" not in " ".join(argv)
        assert Path(argv[0]).name == "claude"

    words = spelled(ASK_MODULE)
    assert not [word for word in words if "tmux" in word], words
    assert "send-keys" not in words
    # The seam itself, not a spelling of it: `runner/` may be imported only for
    # the process-result record T8 defines, never for the pane driver.
    from_runner = {word for word in words if word.startswith("shepherd.runner")}
    assert from_runner == {"shepherd.runner.local"}, from_runner
    assert "Runner" not in {
        word for word in words if word in {"Runner", "LocalRunner", "ScriptedRunner"}
    }


# ----- 11. K1: every rule cites a section that exists --------------------------


def test_every_fork_rule_cites_an_existing_section() -> None:
    """P-M3-16 / K1: no data shape asserted without a real captured example.

    The three result-object fields `ask()` reads — `result`, `session_id`,
    `is_error` — each need a row naming **§Fork**'s field table, which P2
    appended, and a capture that is really on disk.
    """
    headings = markdown_headings(SCHEMAS.read_text(encoding="utf-8"))
    assert FORK_RULES != ()
    named = {rule.name for rule in FORK_RULES}
    assert {"result", "session_id", "is_error"} <= named, named

    for rule in FORK_RULES:
        section, _, rest = rule.evidence.partition(" · ")
        assert section in headings, f"{rule.name}: {section!r}"
        assert rest != "", rule.name
        cited = re.findall(r"[\w./-]+\.(?:txt|json|jsonl|stderr|ansi)", rest)
        assert cited != [], rule.name
        for capture in cited:
            assert (PROBES / capture).exists(), f"{rule.name}: {capture}"


def test_the_field_table_p2_appended_really_carries_these_fields() -> None:
    """The citation must be true, not merely well-formed: §Fork's appended table
    has a row for each field, with P2's own observed example."""
    document = SCHEMAS.read_text(encoding="utf-8")
    assert "| `session_id` | string | `356b6e66-635e-424c-80fd-fef653880906` |" in document
    assert "| `result` | string | `PINEAPPLE-M3` |" in document
    assert "| `is_error` | bool | `false` |" in document
    assert "| `subtype` | string | `success` |" in document


def test_the_duration_is_measured_from_one_clock(
    store: Store, target: str, projects_root: Path
) -> None:
    """`duration_ms` is the difference of two reads of the injected clock, worked
    out from the two stamps by hand — never from a second clock this module
    reached for itself."""
    clock = Clock(NOW, LATER)
    result = ask(store, projects_root, ForkRuns(NSP_STDOUT.read_bytes()), clock=clock)
    assert result.duration_ms == EXPECTED_DURATION_MS
    assert clock.reads >= 2
    assert not (spelled(ASK_MODULE) & {"monotonic", "perf_counter", "time", "datetime"})
