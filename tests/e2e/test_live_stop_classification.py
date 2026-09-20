"""T19: one real stopped session, classified end to end.

`pytest tests/e2e -m live -q`. Excluded from the default run, which stays
`pytest -m "not live"`.

M1 built this lane; M2 adds the five checks below. What they prove is the part
`tmp_path` cannot reach: `tests/daemons/test_controld.py` already drives the
stop path through the real ingest socket with **captured** payloads, so the
wiring is proven — what is not, until here, is that a session this host really
runs produces the same thing.

**Four claims, and nothing more.**

1. a real `-p` run that ends normally produces a `Stop`, a transcript whose
   last `assistant` entry is `end_turn`, and a verdict with
   `decided_by = heuristic`;
2. the stop record is on disk under `logs/stops/`, readable, and re-classifying
   it reproduces the columns — **C-M2-7 in the real world**;
3. `replay` inside `controld`'s own process is idempotent against that record
   (**DP9**: the only place the command is exercised in the process that owns
   the store);
4. the fleet page's tree carries the row's bucket.

**What one real run turned out to be, measured rather than assumed.** A `-p`
run fires `Stop` and then `SessionEnd`, 65-70 ms apart, and **both** are in
`STOP_KINDS` — so one run leaves *two* stop records, not one. On the run this
module was written against the `Stop` arrived while the transcript still held
only the prompt (`entry_count 1`, `ending absent`) and the `SessionEnd` 65 ms
later saw the flushed assistant entries (`entry_count 3`, `ending ended_turn`).
That is **A9's append race, observed**: the race the plan says can be bounded
but not closed. So nothing here asserts *which* of the two records carries the
transcript's verdict — only that one of them does, and that the row and the
tree agree with whichever landed last.

**Isolation posture — F10/K3, and the conftest docstring is the long version.**
The real `CLAUDE_CONFIG_DIR` is used, because an isolated one has no
credentials (probe Finding 3: `Not logged in`, rc=1). Isolation is therefore by
throwaway working directory plus an explicit `--settings` file, the real
`~/.claude/settings.json` is asserted unchanged **per test**, and the hook this
run dispatches through is installed into the *throwaway* settings file by the
production installer.

**No tmux.** M2 needs no pty — that is M3. This module starts no terminal
multiplexer, names none, and `test_no_tmux_socket_is_touched` asserts that over
the argv of every process it spawned rather than over a promise. CLAUDE.md's
rules 1-4 and the 2026-09-12 incident in §18 are satisfied by absence.

**What a run leaves behind:** Claude Code's own bookkeeping for the throwaway
directory — a `~/.claude.json` trust entry and a transcript under
`~/.claude/projects/-tmp-…`. Named here so a reader knows, exactly as the
sibling module names it.
"""

from __future__ import annotations

import ast
import http.client
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from conftest import SettingsObservation, observe_settings
from e2e.conftest import (
    CLAUDE_TIMEOUT_S,
    SHEPHERD_HOME_DIRNAME,
    Throwaway,
    real_config_dir,
    settings_digest,
    throwaway_host,
)

from shepherd.daemons import controld
from shepherd.daemons.sessiond import INGEST_SOCKET_NAME
from shepherd.engines.claude_code.events import SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.engines.claude_code.hooks_config import install_hooks
from shepherd.engines.claude_code.transcript import locate_transcript
from shepherd.logs.stops import STOP_PREFIX, read_stop_records
from shepherd.signals.replay import DIFF_DIRNAME, ReplayReport, replay
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from shepherd.toolsurface.compose import log_root, transcript_root

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The whole prompt. Short on purpose: this lane proves a stop is classified,
#: not that the engine can think.
PROMPT = "Reply with exactly: SHEPHERD_STOP_OK"
MARKER = "SHEPHERD_STOP_OK"

#: A ceiling on *waiting for a condition*, never an assertion about how long
#: anything took — the lane forbids timing assertions, and a ceiling that is
#: reached fails with the condition's own message.
CEILING_S = 45.0

#: Measured, not assumed: a `-p` run fires `Stop` and then `SessionEnd`, and
#: both are in `STOP_KINDS`, so one run leaves two records. If an engine
#: upgrade changes that, this lane should say so loudly rather than quietly
#: assert over whichever subset arrived first.
STOP_FAMILY_EVENTS = ("Stop", "SessionEnd")

#: `data-schemas.md` §Transcript JSONL: `system.subtype = stop_hook_summary` is
#: written **only when a Stop hook is configured**, and in `-p` runs it is the
#: turn-end marker. It is therefore the engine's own evidence that a real
#: `Stop` fired — independent of anything Shepherd wrote (K1).
STOP_HOOK_SUMMARY = "stop_hook_summary"

#: Assembled from parts for the same reason the sibling module assembles them:
#: this package's own source is scanned for these tokens, and a literal
#: spelling one out would be the only hit — a boundary check that cries wolf
#: gets an exemption added to it.
FORBIDDEN_TOKENS: tuple[str, ...] = ("tm" + "ux", "kill" + "-server")

#: Every argv this module has handed to the operating system. Not a decoration:
#: `test_no_tmux_socket_is_touched` reads it, and a check over an empty ledger
#: would pass because nothing ran, which is the one failure this lane is most
#: exposed to.
SPAWNS: list[tuple[str, ...]] = []


# ----- the two spawn seams, both recorded -------------------------------------


def run_recorded(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """The one foreground spawn. No `shell=True`, ever (K5)."""
    SPAWNS.append(tuple(argv))
    return subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=CLAUDE_TIMEOUT_S,
    )


def start_sessiond(home: Path) -> subprocess.Popen[bytes]:
    """The real relay process, with Shepherd's dirs pointed at a throwaway."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    argv = (
        sys.executable,
        "-c",
        "from shepherd.daemons.sessiond import main; raise SystemExit(main())",
        "--expected-schema-version",
        str(EXPECTED_SCHEMA_VERSION),
    )
    SPAWNS.append(argv)
    return subprocess.Popen(
        list(argv), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


# ----- small readers ----------------------------------------------------------


def await_true(predicate: object, message: str, ceiling_s: float = CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def get_json(port: int, path: str) -> Mapping[str, object]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=CEILING_S)
    try:
        connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        assert response.status == 200
        decoded: Mapping[str, object] = json.loads(response.read().decode("utf-8"))
        return decoded
    finally:
        connection.close()


def raw_stop_records(log_dir: Path) -> list[Any]:
    """The log as bytes on disk, read without Shepherd's own decoder.

    Deliberately not `read_stop_records`: this is the *independent* reading, so
    a decoder that silently dropped every record could not make the population
    look empty-and-therefore-fine.
    """
    directory = log_dir / STOP_PREFIX
    if not directory.is_dir():
        return []
    return [
        json.loads(line)
        for path in sorted(directory.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ----- the one live run -------------------------------------------------------


@dataclass(frozen=True)
class LiveStop:
    """One real `claude -p` run, and everything the five checks read from it."""

    throwaway: Throwaway
    entry: HookEntry
    controld: controld.Controld
    completed: subprocess.CompletedProcess[str]
    log_dir: Path
    diff_dir: Path
    records: tuple[Any, ...]
    engine_session_id: str

    def tree_row(self) -> Any | None:
        """This run's row on the fleet page's tree, found by cwd.

        By `cwd`, never by position and never by a count: the lane runs against
        the user's real config dir and their own sessions are in the same
        registry (F10).
        """
        data = self.controld_data("/api/fleet/tree")
        workspaces = data["workspaces"]
        assert isinstance(workspaces, list)
        rows = [
            row
            for workspace in workspaces
            for row in workspace["sessions"]
            if row["cwd"] == str(self.throwaway.workdir)
        ]
        return rows[0] if len(rows) == 1 else None

    def store_row(self) -> Any | None:
        """This run's row in `controld`'s own store, by engine session id.

        **M3 moved the answer for the two checks that used to read the tree.**
        `signals/discovery_loop.py::reconcile_sdk_cli` (T21, DP2 option 2) marks
        a hooked `claude -p` run's row `ephemeral` on the next sweep, and
        `Store.fleet()` is `WHERE s.ephemeral = 0` — so the row is deliberately
        **off** the fleet page. It is not deleted, and its verdict columns are
        exactly where they were; the tree is simply no longer where a `-p` run
        can be read. Measured, not assumed: the row this lane produced is
        `origin=external, ownership=attached, ephemeral=True`, with `stop_reason`
        and `outcome` set. See BLOCKER T24-2.
        """
        return self.controld.store.get_session_by_engine_id(self.engine_session_id)

    def controld_data(self, path: str) -> Any:
        body = get_json(self.controld.port, path)
        data = body["data"]
        assert isinstance(data, dict)
        narrowed: Mapping[str, object] = data
        return narrowed

    def transcript(self) -> Path | None:
        """The engine's own transcript for this run, under its real config dir.

        Located by session id through `locate_transcript`, which globs — the
        project-directory slug is lossy and is never reversed. Read-only, and
        nothing in this module opens any other file under `~/.claude`.
        """
        return locate_transcript(transcript_root(), self.engine_session_id)


@pytest.fixture(scope="module")
def live_stop(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveStop]:
    """Start the two daemons, install the hook into a throwaway settings file,
    spawn **one** `claude -p`, and hold it all open for the five checks.

    Module-scoped so the lane costs one live run in total, not one per test.
    The per-test settings guard in `conftest.py` still wraps every test.
    """
    root = tmp_path_factory.mktemp("t19")
    patch = pytest.MonkeyPatch()
    try:
        for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            patch.setenv(name, str(root / name.lower()))
        patch.setenv("XDG_RUNTIME_DIR", str(root / "run"))
        # `MacHost` reads `TMPDIR`, not `XDG_RUNTIME_DIR`. This one goes in the
        # **process** environment because `start_sessiond` below inherits it and
        # has to agree with the injected host about where the sockets are.
        patch.setenv("TMPDIR", str(root / "run"))

        # `HOME` deliberately does **not** go in the process environment: this
        # fixture spawns a real `claude`, and a throwaway `HOME` hides the
        # account record (`Not logged in · Please run /login`). Shepherd's own
        # directories arrive by injection instead — which is what `log_root`'s
        # docstring means by "a test relocates both by handing in a host".
        #
        # Until that injection existed, `log_dir` below resolved to the real
        # `~/Library/Application Support/Shepherd/logs/stops/` and stop records
        # **accumulated across runs**. `test_exactly_one_engine_session_is_in_the_log`
        # and its four siblings passed on a clean machine, then failed with one
        # extra engine_session_id per live run and got permanently worse.
        shepherd_home = root / SHEPHERD_HOME_DIRNAME
        shepherd_home.mkdir(parents=True, exist_ok=True)
        host = throwaway_host(shepherd_home)
        for directory in (host.dirs().data_dir, host.dirs().runtime_dir):
            assert root in directory.parents, f"{directory} escaped the throwaway"

        workdir = root / "work"
        workdir.mkdir()
        settings = root / "settings.json"
        settings.write_text("{}\n", encoding="utf-8")
        throwaway = Throwaway(workdir=workdir, settings=settings)
        log_dir = log_root(host)

        ingest = host.control_socket(INGEST_SOCKET_NAME)
        entry = build_hook_entry(ingest, host.hook_dispatch(ingest))
        assert entry.available, f"this host cannot dispatch a hook: {entry.reason}"
        installed = install_hooks(settings, entry)
        assert installed.refused_reason is None, installed.refused_reason
        assert installed.events_installed == len(SUBSCRIBED_EVENTS)
        assert installed.warnings == ()

        started = controld.start(host=host, port=0, engine_config_dir=None)
        daemon = start_sessiond(root)
        try:
            await_true(ingest.path.exists, "sessiond never bound its ingest socket")
            completed = run_recorded(throwaway.argv(PROMPT), cwd=workdir)
            # **The run succeeded** — asserted here, before anything reads a
            # population, because a lane whose engine died and whose counters
            # are therefore zero is the false green this task exists to avoid.
            assert completed.returncode == 0, completed.stderr
            assert MARKER in completed.stdout, completed.stdout
            assert "Not logged in" not in completed.stdout + completed.stderr

            await_true(
                lambda: len(raw_stop_records(log_dir)) >= len(STOP_FAMILY_EVENTS),
                f"fewer than {len(STOP_FAMILY_EVENTS)} stop records reached "
                f"{log_dir / STOP_PREFIX} after a successful run",
            )
            records = tuple(raw_stop_records(log_dir))
            engine_ids = {record["evidence"]["engine_session_id"] for record in records}
            assert len(engine_ids) == 1, engine_ids
            yield LiveStop(
                throwaway=throwaway,
                entry=entry,
                controld=started,
                completed=completed,
                log_dir=log_dir,
                diff_dir=log_dir / DIFF_DIRNAME,
                records=records,
                engine_session_id=str(engine_ids.pop()),
            )
        finally:
            controld.stop(started)
            daemon.terminate()
            daemon.wait(timeout=CEILING_S)
    finally:
        patch.undo()


# ----- 1. a real stop, a real transcript, a real verdict ----------------------


def test_a_real_session_stop_produces_a_verdict(live_stop: LiveStop) -> None:
    """The claim the unit seams cannot make, in four parts.

    The order is deliberate: the process succeeded, then the population is
    non-empty, and only then is anything asserted about its contents.
    """
    assert live_stop.completed.returncode == 0
    assert live_stop.records, "a successful run left no stop record at all"

    # (a) a real `Stop` fired — on the engine's own evidence, not on ours.
    transcript = live_stop.transcript()
    assert transcript is not None, "the engine wrote no transcript for this run"
    summaries = [
        entry
        for entry in read_transcript(transcript)
        if entry.get("subtype") == STOP_HOOK_SUMMARY
    ]
    assert summaries, "the transcript records no Stop hook: no Stop ever fired"
    commands = {
        info["command"]
        for summary in summaries
        for info in summary["hookInfos"]
        if isinstance(info, dict)
    }
    assert live_stop.entry.command in commands, commands

    # (b) the transcript's last `assistant` entry ended the turn.
    assert last_assistant_stop_reason(transcript) == "end_turn"

    # (c) a verdict decided by the heuristic split, off that ending.
    ended = [
        record
        for record in live_stop.records
        if record["evidence"]["tail"]["ending"] == "ended_turn"
    ]
    assert ended, "no stop record ever saw the turn end (A9's append race, unbounded)"
    verdict = ended[-1]["verdict"]
    assert verdict["decided_by"] == "heuristic"
    assert verdict["stop_reason"] == "completed"
    assert verdict["bucket"] == "finished"
    assert verdict["confidence"] > 0.0

    # (d) the row carries the *last* record's verdict — because the lane applies
    # stops in arrival order and so does `replay`.
    #
    # **This used to read the fleet page's tree, and M3 made that the wrong
    # place.** `reconcile_sdk_cli` (T21, DP2 option 2) marks a hooked `-p` run
    # `ephemeral` on the next sweep and `Store.fleet()` excludes those, so the
    # tree is now empty of it by design. The claim is unchanged — the verdict
    # reached the row — and it is read where the row now is. Arrival first: the
    # row exists and its verdict columns are set, *then* the tree's emptiness is
    # asserted as the consequence rather than as the claim.
    row = live_stop.store_row()
    assert row is not None, "this run's session is not in controld's store at all"
    final = live_stop.records[-1]["verdict"]
    assert row.outcome == final["bucket"]
    assert row.stop_reason == final["stop_reason"]
    assert row.ended_at is not None

    assert row.ephemeral is True, (
        "DP2 option 2 did not fire: a hooked `-p` run is supposed to be marked "
        "ephemeral by the discovery sweep, and this row was not"
    )
    assert live_stop.tree_row() is None, (
        "a row DP2 marked ephemeral reached the fleet page anyway"
    )


def read_transcript(path: Path) -> list[Any]:
    """Every readable entry. A torn last line is skipped, never raised (D25)."""
    entries: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            decoded: object = json.loads(line)
        except ValueError:
            continue
        if isinstance(decoded, dict):
            entries.append(decoded)
    return entries


def last_assistant_stop_reason(path: Path) -> str | None:
    """`message.stop_reason` of the last `assistant` entry, read here directly.

    Independent of `read_tail` on purpose: an expected value re-derived by the
    code under test is a tautology, and this is the source of truth §8's rule
    is keyed on (data-schemas §Transcript JSONL, `message.stop_reason`).
    """
    reasons = [
        entry["message"]["stop_reason"]
        for entry in read_transcript(path)
        if entry.get("type") == "assistant" and isinstance(entry.get("message"), dict)
    ]
    settled = [reason for reason in reasons if isinstance(reason, str)]
    return settled[-1] if settled else None


# ----- 2. on disk, and replaying to the same columns (C-M2-7) -----------------


def test_the_stop_record_is_on_disk_and_replays_to_the_same_columns(
    live_stop: LiveStop,
) -> None:
    """C-M2-7 against a real log rather than a `tmp_path` one.

    The record survived a real process boundary — a hook process, `sessiond`,
    `controld`'s ingest thread, a rotating writer — and re-running **today's**
    classifier over it must land on the columns already stored.
    """
    found, stats = read_stop_records(live_stop.log_dir)
    assert stats.records >= 1, f"nothing readable under {live_stop.log_dir / STOP_PREFIX}"
    assert len(found) == stats.records == len(live_stop.records)
    assert stats.skipped_malformed == 0
    assert stats.skipped_version == 0
    assert stats.unreadable_files == 0
    assert stats.skipped_undated == 0

    report = replay(
        store=live_stop.controld.store,
        log_dir=live_stop.log_dir,
        since=None,
        apply=False,
        diff_dir=live_stop.diff_dir,
    )
    # The population first. A `replay` pointed at the wrong directory reports
    # `read 0` and every other counter zero, and every assertion below it would
    # then pass having checked nothing.
    assert report.read == stats.records, report
    assert report.reclassified == 1, report
    assert report.orphaned == 0
    assert report.classifier_failures == 0
    assert report.unreadable_files == 0
    # C-M2-7: today's rules disagree with the stored columns about nothing.
    assert report.changes == (), report.changes
    assert report.applied is False
    assert report.diff_path.is_file()
    assert report.diff_path.read_text(encoding="utf-8").strip() != ""


# ----- 3. `replay` in the process that owns the store (DP9) -------------------


def test_replay_inside_controld_is_idempotent(live_stop: LiveStop) -> None:
    """DP9. The command runs against `controld`'s own live `Store` — the single
    writer thread, the open connection, the running server — and twice.

    Idempotence is asserted on the **row**, not only on the report: a report
    that read nothing is idempotent too.
    """
    # The row, not the tree: M3's DP2 hides a hooked `-p` run from the fleet page
    # (see `store_row`'s note and BLOCKER T24-2), and a comparison of `None` with
    # `None` is idempotent for the wrong reason.
    before = live_stop.store_row()
    assert before is not None

    first = replay(**self_args(live_stop))
    assert first.read >= 1, f"replay read nothing from {live_stop.log_dir}: {first}"
    assert first.applied is True
    after_first = live_stop.store_row()

    second = replay(**self_args(live_stop))
    after_second = live_stop.store_row()

    assert after_first == before, "the first apply moved a column C-M2-7 says is settled"
    assert after_second == after_first, "the second apply was not a no-op"
    assert comparable(second) == comparable(first)
    assert second.diff_path == first.diff_path


def self_args(live_stop: LiveStop) -> dict[str, Any]:
    """The one spelling of this lane's `replay` call, so two runs cannot differ."""
    return {
        "store": live_stop.controld.store,
        "log_dir": live_stop.log_dir,
        "since": None,
        "apply": True,
        "diff_dir": live_stop.diff_dir,
    }


def comparable(report: ReplayReport) -> tuple[object, ...]:
    """Everything a second run must reproduce. `diff_path` is compared apart
    and the file itself is **appended** to by design, so it is not in here."""
    return (
        report.read,
        report.skipped_malformed,
        report.skipped_version,
        report.orphaned,
        report.reclassified,
        report.changes,
        report.unknown_rate_before,
        report.unknown_rate_after,
        report.unreadable_files,
        report.skipped_undated,
        report.classifier_failures,
        report.date,
    )


# ----- 4. P13, per test ------------------------------------------------------


def test_real_settings_file_is_untouched(
    live_stop: LiveStop, settings_guard: str, real_user_settings: SettingsObservation
) -> None:
    """P13/K3 asserted **per test** — M1's F10 lesson.

    A per-suite guard can say the file changed; it cannot say which test did
    it, and the one that did it is the only thing worth knowing. Four halves,
    because the digest alone would miss the backup half of the rule: the
    content, the siblings, the argv, and the file this run actually pointed the
    engine at.
    """
    now = observe_settings(real_config_dir())
    assert now.digest == settings_guard, "this test changed the real settings file"
    assert now.digest == real_user_settings.digest, "the suite changed it earlier"
    assert now.siblings == real_user_settings.siblings, (
        f"a file appeared or vanished beside {now.path}: {now.siblings}"
    )
    assert now.digest != "absent"

    real = real_config_dir() / "settings.json"
    assert live_stop.throwaway.settings != real
    assert not live_stop.throwaway.settings.is_relative_to(real_config_dir())
    for argv in SPAWNS:
        assert str(real) not in " ".join(argv), argv

    # …and the isolation was load-bearing rather than incidental: the hook the
    # live run dispatched through is in the **throwaway** file.
    written = live_stop.throwaway.settings.read_text(encoding="utf-8")
    assert live_stop.entry.command in written
    assert str(real) not in written


# ----- 5. no tmux, asserted rather than promised ------------------------------


def test_no_tmux_socket_is_touched(live_stop: LiveStop) -> None:
    """CLAUDE.md rules 1-4 and §18's 2026-09-12 incident, satisfied by absence.

    M2 needs no pty, so the honest scope is *do not touch it at all*. Asserted
    twice: over every argv this module handed the operating system, and over
    its own non-docstring literals, so a later edit cannot add one quietly.
    The ledger is checked non-empty first — a scan of nothing finds nothing.
    """
    assert SPAWNS, "no process was spawned: this check would pass vacuously"
    assert any(argv[0] == "claude" for argv in SPAWNS), SPAWNS
    for argv in SPAWNS:
        for word in argv:
            for token in FORBIDDEN_TOKENS:
                assert token not in word, argv

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert literals, "the scan found no literals at all: it is not reading this module"
    for literal in literals:
        for token in FORBIDDEN_TOKENS:
            assert token not in literal, literal

    # The one file this module wrote is the throwaway settings file. Nothing in
    # it may name a multiplexer either — that is what would become an argv.
    written = live_stop.throwaway.settings.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in written
