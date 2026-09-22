"""`shepherd replay` — the command and the tool (T12, D19/D35, DP9, D38.1).

Seam: `main(argv)` → `invoke()`, the same seam as the rest of `tests/cli/`.
`cli/` is an L5 consumer: it reaches the replay engine through one registered
tool and it may not import `signals/`, open a store, or touch a log. Three of
the tests below are about exactly that, because the honest failure of a
standalone `shepherd` process — *this process has no such capability* — is the
behaviour DP9 asks for, and a second store opened "just for replay" is the trap
it names.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from cli.conftest import register_tools, scripted_host

from shepherd.core.states import Origin, Ownership
from shepherd.core.stops import (
    STOP_RECORD_VERSION,
    Bucket,
    DecidedBy,
    StopEvidence,
    StopReason,
    TranscriptTail,
    TurnEnding,
    Verdict,
)
from shepherd.cli.main import EXIT_FAILURE, EXIT_OK, EXIT_USAGE, main
from shepherd.logs.jsonl import RotatingJsonlLog
from shepherd.logs.stops import StopLog
from shepherd.store.db import Store
from shepherd.toolsurface.registry import registered_tools
from shepherd.toolsurface.tools_replay import REPLAY_TOOL, register_replay_tool
from shepherd.toolsurface.types import Audience, BlastClass

CLI_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "cli"

STAMP = "2026-09-17T01:04:18.671Z"
DAY = "2026-09-17"


def seed_stop(store: Store, log_dir: Path, name: str, stamp: str = STAMP) -> str:
    """One stopped session whose column says `unknown` and whose record does not."""
    workspace = store.create_project(name=name, description=None)
    session = store.register_session(
        engine_session_id=f"engine-{name}",
        workspace_id=workspace.id,
        repo_id=None,
        cwd=f"/tmp/{name}",
        started_at=stamp,
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
    stale = Verdict(
        stop_reason=StopReason.UNKNOWN,
        bucket=Bucket.ERROR,
        why="what the rules said at the time",
        confidence=0.0,
        decided_by=DecidedBy.MECHANICAL,
        next_actions=(),
        waiting_on=None,
        missing=(),
    )
    store.apply_stop_verdict(session.id, stale, stamp, None)
    evidence = StopEvidence(
        record_version=STOP_RECORD_VERSION,
        session_id=session.id,
        engine_session_id=f"engine-{name}",
        received_at=stamp,
        mechanical=None,
        mechanical_detail=None,
        tail=TranscriptTail(
            ending=TurnEnding.ENDED_TURN,
            last_assistant_text="DONE",
            entry_count=3,
            tool_uses=(),
            failures=(),
            promise_followed_by_tool_use=None,
            skipped_lines=0,
            truncated=False,
        ),
        tasks_total=0,
        tasks_done=0,
        brief="ship the thing",
        auto_compact_pending=False,
        quota_notice=False,
        process_exit_observed=False,
        exit_code=None,
    )
    log = StopLog(RotatingJsonlLog(log_dir, "stops"))
    assert log.append(evidence, stale) is True
    log.close()
    return session.id


def run(
    argv: list[str], *, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> int:
    return main(
        argv,
        out=out,
        err=err,
        host=scripted_host(runtime_dir=tmp_path / "run"),
        correlation_id="fixed",
    )


def test_replay_prints_counts_and_unknown_rate(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    session_id = seed_stop(store, log_dir, "s1")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    code = run(["replay"], tmp_path=tmp_path, out=out, err=err)
    printed = out.getvalue()

    assert code == EXIT_OK, err.getvalue()
    assert "read 1 records" in printed
    assert "reclassified 1 sessions" in printed
    assert "changed 1" in printed
    assert "unknown → completed" in printed
    assert "unknown rate: 100.0% → 0.0%" in printed
    assert f"diff: {diff_dir / f'{DAY}.log'}" in printed
    # RD7: without --apply the columns are untouched, and the command says so.
    assert "--apply" in printed
    session = store.get_session(session_id)
    assert session is not None and session.stop_reason == "unknown"


def test_replay_apply_writes_the_columns(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    session_id = seed_stop(store, log_dir, "s1")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    code = run(["replay", "--apply"], tmp_path=tmp_path, out=out, err=err)

    assert code == EXIT_OK, err.getvalue()
    session = store.get_session(session_id)
    assert session is not None and session.stop_reason == "completed"


def test_replay_since_narrows_the_read_without_emptying_it(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Two records in, one out — a *narrowing*, not an empty read.

    This test used to assert `read 0 records` against `--since 2027-01-01`,
    which is the same output an unvalidated `--since 30d` produced. An
    assertion on the empty answer cannot tell the filter working from the
    filter refusing everything, and it enshrined the second as the spec.
    """
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    seed_stop(store, log_dir, "old", stamp="2026-09-15T01:04:18.671Z")
    seed_stop(store, log_dir, "new")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    code = run(["replay", "--since", DAY], tmp_path=tmp_path, out=out, err=err)

    assert code == EXIT_OK, err.getvalue()
    printed = out.getvalue()
    assert "read 1 records" in printed
    assert "reclassified 1 sessions" in printed
    assert "changed 1" in printed


def test_a_since_that_is_not_a_date_is_a_usage_error(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """§8's own example, `--since 30d`, read zero records and exited **0**.

    It is a usage error, and the message says the spelling rather than the
    thing a missing capability would say.
    """
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    session_id = seed_stop(store, log_dir, "s1")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    code = run(["replay", "--since", "30d", "--apply"], tmp_path=tmp_path, out=out, err=err)

    assert code == EXIT_USAGE
    complaint = err.getvalue()
    assert "YYYY-MM-DD" in complaint
    assert "control daemon" not in complaint, "the capability is present; it refused the value"
    session = store.get_session(session_id)
    assert session is not None and session.stop_reason == "unknown"
    assert not diff_dir.exists()


def test_replay_since_needs_a_value(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    assert run(["replay", "--since"], tmp_path=tmp_path, out=out, err=err) == EXIT_USAGE


def test_replay_in_a_standalone_process_says_so_and_exits_one(
    tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """DP9: no capability, no replay — and never a second store (§7 rule 3, D37)."""
    code = run(["replay"], tmp_path=tmp_path, out=out, err=err)

    assert code == EXIT_FAILURE
    complaint = err.getvalue()
    assert "replay did not answer" in complaint
    assert "control daemon" in complaint
    assert out.getvalue() == ""


#: Calls that would mean `cli/` reached the system itself. Matched against the
#: callee's **last name component**, so `sqlite3.connect(...)`, `db.open_store()`
#: and a bare `open_store()` are the same reach.
FORBIDDEN_CALLS = frozenset(
    {"open_store", "Store", "connect", "read_stop_records", "read_records", "replay"}
)


def calls_in(tree: ast.Module) -> set[str]:
    """The name of every function called, however it is spelled.

    Four of the six entries in this set used to be matched only against an
    `ast.Call` with an `ast.Name` func, so `sqlite3.connect(...)` — an
    `ast.Attribute` — could never fire one of them. A rule that cannot fire is
    not a rule.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            found.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            found.add(node.func.attr)
    return found


def test_replay_never_opens_a_store_from_cli() -> None:
    """An AST scan, not a promise: `cli/` opens no database and imports no store.

    `rglob`, not `glob` (the gotcha `patterns.md` already names): a
    non-recursive scan stops caring the day someone adds `cli/commands/`.
    """
    modules = sorted(CLI_ROOT.rglob("*.py"))
    assert len(modules) >= 4, "the scan found almost nothing — check the root"
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "sqlite3" not in imported, f"{module.name} imports a database driver"
        reaches = calls_in(tree) & FORBIDDEN_CALLS
        assert reaches == set(), f"{module.name} calls the system directly: {reaches}"


def test_the_scan_that_says_cli_opens_no_store_can_fail() -> None:
    """The self-check: the rule fires on the spelling the real code would use.

    `cli.read("replay", ...)` is an `ast.Attribute` call, which is exactly what
    the old scan could not see — so it reported success without checking.
    """
    leak = ast.parse("import sqlite3\ndef go():\n    sqlite3.connect('/tmp/x')\n")
    assert calls_in(leak) & FORBIDDEN_CALLS == {"connect"}
    assert calls_in(ast.parse("def go():\n    open_store('/tmp/x')\n")) & FORBIDDEN_CALLS == {
        "open_store"
    }
    assert calls_in(ast.parse("def go():\n    cli.say('hello')\n")) & FORBIDDEN_CALLS == set()


def test_replay_tool_is_local_destructive_and_human_only(
    store: Store, tmp_path: Path
) -> None:
    """D38.1's shape: the one M2 tool that can overwrite 412 verdicts."""
    register_replay_tool(store, tmp_path / "logs", tmp_path / "logs" / "replay")
    tools = registered_tools()

    assert REPLAY_TOOL in tools
    tool = tools[REPLAY_TOOL]
    assert tool.blast_class is BlastClass.LOCAL_DESTRUCTIVE
    assert tool.audiences == frozenset({Audience.HUMAN})


def test_replay_command_reaches_the_system_only_through_invoke(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The consumer boundary, asserted at the call rather than only in the scan."""
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    seed_stop(store, log_dir, "s1")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    seen: list[str] = []
    real = __import__("shepherd.toolsurface.registry", fromlist=["invoke"]).invoke

    def recording(name: str, args: object, ctx: object) -> object:
        seen.append(name)
        return real(name, args, ctx)  # type: ignore[arg-type]

    monkeypatch.setattr("shepherd.cli.commands.invoke", recording)
    assert run(["replay"], tmp_path=tmp_path, out=out, err=err) == EXIT_OK
    assert seen == [REPLAY_TOOL]


def test_recompute_no_longer_claims_m2_has_not_happened(
    store: Store, projects_root: Path, tmp_path: Path, out: io.StringIO, err: io.StringIO
) -> None:
    """Review finding A2: the stub's sentence became false the day this landed."""
    log_dir, diff_dir = tmp_path / "logs", tmp_path / "logs" / "replay"
    seed_stop(store, log_dir, "s1")
    register_tools(store, projects_root)
    register_replay_tool(store, log_dir, diff_dir)

    code = run(["recompute"], tmp_path=tmp_path, out=out, err=err)

    assert code == EXIT_OK
    assert "nothing in this build replays a session's history" not in err.getvalue()
    assert "reclassified 1 sessions" in out.getvalue()
    # The claim is gone from what the command *says*: the only surviving copy of
    # the old sentence is the comment recording why it was removed.
    from shepherd.cli.main import USAGE

    assert "lands in M2" not in USAGE
    assert "refused here" not in USAGE
    assert "alias of replay" in USAGE
