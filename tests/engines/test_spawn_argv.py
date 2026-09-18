"""T10 — the spawn argv, the capability record, the binary and the trust pre-flight.

Every shape here is built on a **captured** example under
`docs/probes/2026-09-14-schemas/`, never on memory:

* the argv words and the `sh -c` mangling they avoid, the `--` separator a
  dash-brief needs and the 16 324-byte ceiling come from
  `gap-fill/argv-20260914T173100Z/results.json` and
  `gap-fill/argv-limits-20260914T173342Z/tmux-argv-limit.txt`;
* `projects[<cwd>].hasTrustDialogAccepted` comes from
  `transcripts/captures/claude-json-shape.txt` — **9 true, 2 false** across 11
  entries, and the fixtures below carry exactly that mix so the `False` half is
  not a case nobody exercised.

The real `~/.claude.json` is never read here. It is the user's file, its contents
change under the suite, and a test that reads it would be asserting on whatever
this host happens to have accepted.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

import shepherd.engines.claude_code.spawn as spawn_module
from shepherd.host.base import DetachedLaunch
from shepherd.runner.local import CommandResult, LocalRunner
from shepherd.core.runner import RunnerRefusal, SessionSpec, TMUX_COMMAND_LIMIT_B
from shepherd.engines.claude_code.spawn import (
    EFFORT_FLAG,
    MODEL_FLAG,
    NAME_FLAG,
    SEPARATOR,
    SESSION_ID_FLAG,
    SPAWN_RULES,
    capabilities,
    command_size,
    resolve_binary,
    spawn_argv,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "docs" / "specs" / "data-schemas.md"
PROBES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas"
MODULE = REPO_ROOT / "src" / "shepherd" / "engines" / "claude_code" / "spawn.py"

#: A real id from the capture (`supp-20260914T155346Z/spawn-cmd.txt`).
SPAWN_UUID = "17b1da21-4505-43ae-8958-35764a620384"
BINARY = "/usr/bin/claude"


def spec(
    *,
    brief: str | None = None,
    title: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    cwd: str = "/tmp/work",
    env: Mapping[str, str] | None = None,
) -> SessionSpec:
    return SessionSpec(
        session_id="01JABCDEF0123456789ABCDEFG",
        engine_session_id=SPAWN_UUID,
        cwd=cwd,
        brief=brief,
        title=title,
        model=model,
        effort=effort,
        engine="claude_code",
        runner="local",
        env=dict(env or {}),
    )


# ----- the argv ---------------------------------------------------------------


def test_the_brief_is_one_argv_word_after_a_separator() -> None:
    """A9: the brief survives byte-exact only as its own argv word.

    `results.json` `a_argv_words` has `prompt_equals_brief: true` with the brief
    as one word; `b_single_string_naive` has it `false`, because one command
    string goes through `sh -c`, which expanded `$()` and stripped the quotes.
    Goes red if the brief is ever joined into a command string.
    """
    brief = "ARGV-BRIEF $(echo EXPANDED) `echo BACKTICK` ; echo SEMI && 'single' \"double\""
    argv = spawn_argv(spec(brief=brief, model="claude-haiku-4-5-20251001"), BINARY, frame_bytes=0,)

    assert argv.count(brief) == 1
    assert argv[-1] == brief
    assert argv[-2] == SEPARATOR
    # No word carries a fragment of another: every element is separate (A9).
    assert [word for word in argv if word != brief and brief[:12] in word] == []
    assert argv[0] == BINARY
    assert argv[1:3] == [SESSION_ID_FLAG, SPAWN_UUID]


def test_every_flag_is_a_separate_argv_word_in_the_documented_order() -> None:
    """`<claude> --session-id <uuid> [--name] [--model] [--effort] [-- <brief>]`."""
    argv = spawn_argv(
        spec(brief="do the thing", title="shp-spawn-name", model="claude-opus-5", effort="max"),
        BINARY,
        frame_bytes=0,
    )
    assert argv == [
        BINARY,
        SESSION_ID_FLAG,
        SPAWN_UUID,
        NAME_FLAG,
        "shp-spawn-name",
        MODEL_FLAG,
        "claude-opus-5",
        EFFORT_FLAG,
        "max",
        SEPARATOR,
        "do the thing",
    ]


def test_an_absent_option_contributes_no_word() -> None:
    """No `--name ''` placeholder: an option nobody set is not on the argv."""
    assert spawn_argv(spec(), BINARY, frame_bytes=0,) == [BINARY, SESSION_ID_FLAG, SPAWN_UUID]


def test_a_brief_starting_with_a_dash_survives() -> None:
    """A11: without `--`, `claude` dies with `error: unknown option` (exit 1).

    `argv-limits-20260914T173342Z/claude-dash-brief.stderr`:
    `error: unknown option '-starts with a dash DASH-BRIEF'`. Goes red if the
    separator is dropped.
    """
    brief = "-starts with a dash DASH-BRIEF"
    argv = spawn_argv(spec(brief=brief), BINARY, frame_bytes=0,)

    assert argv[-2:] == [SEPARATOR, brief]
    assert argv.index(SEPARATOR) < argv.index(brief)
    # Also the variadic-flag hazard: `--effort <e>` must not be the last flag
    # before a positional, or it swallows it.
    with_effort = spawn_argv(spec(brief=brief, effort="high"), BINARY, frame_bytes=0,)
    assert with_effort[-3:] == ["high", SEPARATOR, brief]


def test_an_oversized_brief_is_refused_not_truncated() -> None:
    """A10/E-M3-10 at the measured boundary: 16 324 accepted, 16 325 refused.

    `tmux-argv-limit.txt`: "largest accepted single argv word (bytes): 16324 /
    smallest rejected: 16325" and "single command string of 16325 bytes ->
    failed to send command rc=1". The arithmetic below is worked by hand so the
    expectation does not come from the code under test:

        /usr/bin/claude(15) + ' '(1) + --session-id(12) + ' '(1)
        + <uuid>(36) + ' '(1) + --(2) + ' '(1)  = 69 bytes of frame
    """
    assert TMUX_COMMAND_LIMIT_B == 16324
    frame = 69
    fits = "x" * (TMUX_COMMAND_LIMIT_B - frame)
    argv = spawn_argv(spec(brief=fits), BINARY, frame_bytes=0,)
    assert argv[-1] == fits

    one_too_many = "x" * (TMUX_COMMAND_LIMIT_B - frame + 1)
    with pytest.raises(RunnerRefusal) as refused:
        spawn_argv(spec(brief=one_too_many), BINARY, frame_bytes=0,)
    assert "16324" in refused.value.reason
    assert "16325" in refused.value.reason
    # Never truncated: the refusal carries no fragment of the brief.
    assert "xxxx" not in refused.value.reason


def test_the_limit_is_measured_in_utf8_bytes_not_characters() -> None:
    """The ceiling is a byte count on the wire; `✓` is three bytes, not one."""
    frame = 69
    room = TMUX_COMMAND_LIMIT_B - frame
    assert spawn_argv(spec(brief="✓" * (room // 3)), BINARY, frame_bytes=0,)[-1].startswith("✓")
    with pytest.raises(RunnerRefusal):
        spawn_argv(spec(brief="✓" * (room // 3 + 1)), BINARY, frame_bytes=0,)


def test_the_other_words_count_toward_the_limit_too() -> None:
    """"the brief plus the rest of the command": a long title shrinks the room."""
    frame = 69
    fits = "x" * (TMUX_COMMAND_LIMIT_B - frame)
    with pytest.raises(RunnerRefusal):
        spawn_argv(spec(brief=fits, title="a title"), BINARY, frame_bytes=0,)


class PoisonedEnviron(Mapping[str, str]):
    """`os.environ` with every read wired to raise.

    `monkeypatch.setattr(os, "getenv", boom)` never covered `os.environ.get`,
    which is a different object entirely — and `os.environ.get` is the spelling
    the module already uses twice, so it is the one the next editor will type.
    """

    def _boom(self) -> None:
        raise RuntimeError("spawn_argv read the environment")

    def __getitem__(self, key: str) -> str:
        self._boom()
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        self._boom()
        return iter(())

    def __len__(self) -> int:
        self._boom()
        return 0

    def get(self, key: str, default: object = None) -> str:  # type: ignore[override]
        self._boom()
        raise KeyError(key)


def test_spawn_argv_is_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    """200 cases with the clock and the filesystem poisoned.

    Goes red if a clock read or a path read creeps in: every poisoned call
    raises, so the function cannot quietly consult one.
    """

    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("spawn_argv touched the world")

    alphabet = "abcdefghijklmnopqrstuvwxyz -_✓$`'\"\n\t"
    cases = []
    for index in range(200):
        length = index % 40
        brief = "".join(alphabet[(index * 7 + step) % len(alphabet)] for step in range(length))
        cases.append(
            (
                brief,
                spec(
                    brief=brief or None,
                    title=f"title {index}" if index % 2 else None,
                    model="claude-opus-5" if index % 3 else None,
                    effort=("low", "medium", "high", "xhigh", "max")[index % 5]
                    if index % 5
                    else None,
                ),
            )
        )

    # The poison is lifted before a single assertion runs: pytest's own failure
    # reporting calls `os.getcwd`, and a test that breaks the reporter reports
    # nothing at all.
    observed = []
    try:
        for module, name in (
            (time, "time"),
            (time, "monotonic"),
            (time, "time_ns"),
            (os, "getcwd"),
            (os, "getenv"),
            (os, "environ"),
            (shutil, "which"),
            (subprocess, "check_output"),
            (subprocess, "run"),
            (Path, "read_text"),
            (Path, "exists"),
            (Path, "is_file"),
        ):
            monkeypatch.setattr(module, name, PoisonedEnviron() if name == "environ" else boom)
        for _, candidate in cases:
            observed.append((spawn_argv(candidate, BINARY, frame_bytes=0), spawn_argv(candidate, BINARY, frame_bytes=0)))
    finally:
        monkeypatch.undo()

    assert len(observed) == 200
    for (brief, _), (first, again) in zip(cases, observed):
        assert first == again
        if brief:
            assert first[-1] == brief


#: Every name that would make a "pure" function impure, matched against **every**
#: attribute and bare name in the tree — not against `Call.func` only.
IMPURE_NAMES = frozenset(
    {
        "time", "monotonic", "time_ns", "now", "uuid4", "which", "getenv",
        "environ", "getcwd", "open", "read_text", "read_bytes", "exists",
        "run", "Popen", "check_output", "check_call", "system", "popen",
    }
)


def impure_names(function: ast.FunctionDef) -> set[str]:
    """Every forbidden name this function mentions, however it is spelled.

    `os.environ.get(k)` is an `ast.Call` whose `func.attr` is `"get"`, and
    `getattr(node.func, "id", "")` is `""` — so a rule keyed on the call's own
    name is blind to the two spellings this very module uses. Walking every
    `Attribute` and `Name` sees `environ` in the middle of the chain, and
    `subprocess.check_output` with it.
    """
    return {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(function)
        if isinstance(node, (ast.Attribute, ast.Name))
    } & IMPURE_NAMES


def test_spawn_argv_names_no_impure_call() -> None:
    """The source half of purity: a call added inside a branch still shows here."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "spawn_argv"
    )
    assert impure_names(function) == set(), impure_names(function)

    # The rule's positive control, in this module rather than in a fixture:
    # `_search_space` legitimately reads `$PATH`, so the scan must see it. This
    # is the half that was missing — the old rule collected `node.func.attr`,
    # which for `os.environ.get(...)` is `"get"`, so the spelling the module
    # itself uses twice was the one spelling it could not see. A planted
    # `os.environ.get(...)` plus `subprocess.check_output(...)` inside
    # `spawn_argv` passed both purity tests on 2026-09-17.
    impure = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_search_space"
    )
    assert impure_names(impure) == {"environ"}, impure_names(impure)


# ----- the capability record --------------------------------------------------


def test_can_set_title_ships_false() -> None:
    """D29's literal. DP1 recommends `True` for owned sessions and is NOT APPLIED.

    Flipping this needs a **recorded human approval** (the plan's checkpoint on
    Task 20), not a one-line edit here.
    """
    assert spawn_module._CLAUDE_CODE_CAPABILITIES.can_set_title is False, (
        "DP1 is stated and NOT APPLIED: flipping can_set_title requires a recorded "
        "approval, see the M3 plan's Task 20 decision checkpoint"
    )


def test_the_capability_record_is_the_captured_engine() -> None:
    """`can_fork` is `data-schemas.md` §Fork's `can_fork = True`; the ladder is
    `--help`'s own list (`effort-20260914T171533Z/claude-help.txt`)."""
    record = spawn_module._CLAUDE_CODE_CAPABILITIES
    assert record.can_steer is True
    assert record.can_fork is True
    assert record.has_hooks is True
    assert record.effort_ladder == ("low", "medium", "high", "xhigh", "max")
    assert record.transcript_format == "jsonl"


def test_can_spawn_degrades_with_the_pane_driver() -> None:
    """D-5: no pane driver, no owned spawn — and the record says so."""
    assert capabilities(pane_driver_available=False).can_spawn is False
    assert capabilities(pane_driver_available=True).can_spawn is True
    assert capabilities(pane_driver_available=False).can_fork is True


# ----- the binary -------------------------------------------------------------


def test_resolve_binary_returns_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E-M3-14/C1: resolved before the spawn, so a unit's short `PATH` fails here."""
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    resolved = resolve_binary()
    assert resolved == str(binary)
    assert Path(resolved).is_absolute()


def test_resolve_binary_refuses_rather_than_returning_a_bare_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1: a unit whose `PATH` lacks `~/.local/bin` exits 127 at exec time.

    A refusal names the `PATH` it searched; it never falls back to `"claude"`.
    """
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(RunnerRefusal) as refused:
        resolve_binary()
    assert "PATH" in refused.value.reason


def test_resolve_binary_absolutises_a_relative_path_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative `PATH` entry resolves against whatever cwd the spawn had, so
    the resolution **succeeds** and returns an absolute path — which is what the
    assertion always checked. The old name said "refuses"; the check is right and
    the name was wrong, and a name that disagrees with its assertion is how the
    next reader learns a rule that does not exist (T10-R2)."""
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", ".")
    resolved = resolve_binary()
    assert Path(resolved).is_absolute(), resolved


# ----- evidence ---------------------------------------------------------------


def markdown_headings(document: str) -> set[str]:
    """Every heading, with fenced code blocks skipped.

    `line.startswith("#")` fires on a shell comment inside a ``` block, which is
    how this document reports 174 "headings" where it has 140 — and a rule that
    accepts those accepts an `evidence` string naming a section nobody can find.
    """
    headings: set[str] = set()
    fenced = False
    for line in document.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.startswith("#"):
            headings.add(line.lstrip("# ").strip())
    return headings


def test_every_spawn_rule_cites_an_existing_section() -> None:
    """P-M3-16: every row of the spawn-argv table names a real section.

    Goes red if a row's `evidence` names a `data-schemas.md` section that is not
    in the document, or a capture path that is not on disk.
    """
    document = SCHEMAS.read_text(encoding="utf-8")
    headings = markdown_headings(document)
    assert SPAWN_RULES != ()

    # The scan's own arithmetic, pinned: 175 lines in this document begin with
    # `#`, and **141** of them are headings. The other 34 are `#` inside fenced
    # code blocks — shell comments, JSON-with-comments, Python. A rule that
    # counts those accepts a citation that names no section at all.
    #
    # Re-pinned from (174, 140) by M4 T1, which appended one `###` entry to
    # §Agent SDK (the 0.2.153 / 2.1.273 / 2.1.274 re-pin). The invariant is
    # unchanged and the 34 non-headings are unchanged; only the document grew.
    naive = len([line for line in document.splitlines() if line.startswith("#")])
    assert (naive, len(headings)) == (175, 141), (naive, len(headings))
    # …and a named one of the 34, so the count is not the only thing asserted:
    # this is a shell comment inside a ``` block, not a section anybody can cite.
    shell_comment = "find ~/.claude/projects/-tmp-shp-schemas-tx-blIf90-work (throwaway probe project dir)"
    assert shell_comment in document
    assert shell_comment not in headings

    for rule in SPAWN_RULES:
        section, _, rest = rule.evidence.partition(" · ")
        assert section in headings, f"{rule.name}: {section!r}"
        assert rest != "", rule.name
        cited = re.findall(r"[\w./-]+\.(?:txt|json|jsonl|stderr|ansi)", rest)
        assert cited != [], rule.name
        for capture in cited:
            assert (PROBES / capture).exists(), f"{rule.name}: {capture}"


def test_the_table_covers_every_word_the_argv_can_contain() -> None:
    """A row per decision: a flag added with no row is a rule with no evidence."""
    argv = spawn_argv(
        spec(brief="b", title="t", model="m", effort="max"),
        BINARY,
        frame_bytes=0,
    )
    flags = {word for word in argv if word.startswith("-")}
    assert flags == {rule.name for rule in SPAWN_RULES if rule.name.startswith("-")}


def test_the_module_stays_small() -> None:
    assert len(MODULE.read_text(encoding="utf-8").splitlines()) <= 250


# ----- the live row -----------------------------------------------------------


@pytest.mark.live
def test_every_flag_is_present_in_claude_help() -> None:
    """G-M3-7: the flags are not an enum `drift_check.py` can see.

    Runs `claude --help` on this host and records the version, because
    `data-schemas.md` pins every shape to 2.1.270 and this host has moved on.
    Goes red when the engine renames a flag.
    """
    binary = resolve_binary()
    help_text = subprocess.run(
        [binary, "--help"], capture_output=True, text=True, timeout=120, check=True
    ).stdout
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, timeout=120, check=True
    ).stdout.strip()

    missing = [
        flag
        for flag in (
            SESSION_ID_FLAG,
            NAME_FLAG,
            MODEL_FLAG,
            EFFORT_FLAG,
            "--fork-session",
            "--no-session-persistence",
        )
        if flag not in help_text
    ]
    assert missing == [], f"{version}: {missing}"
    print(f"claude --help flags verified on {version}")


def test_resolve_binary_says_why_it_could_not_use_the_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`shutil.which() is None` means four different things, and three of them
    are not "not on PATH".

    The human reads "not on PATH", runs `ls`, sees the binary sitting there, and
    debugs the wrong system. Each cause names itself instead.
    """
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    not_executable = tmp_path / "mode-0644"
    not_executable.mkdir()
    (not_executable / "claude").write_text("#!/bin/sh\n", encoding="utf-8")
    (not_executable / "claude").chmod(0o644)

    a_directory = tmp_path / "directory"
    (a_directory / "claude").mkdir(parents=True)

    dangling = tmp_path / "dangling"
    dangling.mkdir()
    (dangling / "claude").symlink_to(tmp_path / "nothing-here")

    empty = tmp_path / "empty"
    empty.mkdir()

    for directory, expected in (
        (not_executable, "not executable"),
        (a_directory, "is a directory"),
        (dangling, "dangling symlink"),
        (empty, "no claude"),
    ):
        monkeypatch.setenv("PATH", str(directory))
        with pytest.raises(RunnerRefusal) as refused:
            resolve_binary()
        assert expected in refused.value.reason, (directory.name, refused.value.reason)
        assert str(directory) in refused.value.reason, directory.name
        if expected != "no claude":
            assert "is not on PATH" not in refused.value.reason, directory.name


def test_resolve_binary_names_the_search_space_it_actually_searched(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `PATH` unset, `shutil.which` falls back to `confstr("CS_PATH")` —
    while the old message reported `''`, naming a search space nobody searched.
    With `PATH` set and empty, `which` searches **nothing** and says so.
    """
    monkeypatch.delenv("PATH", raising=False)
    with pytest.raises(RunnerRefusal) as unset:
        resolve_binary()
    fallback = os.confstr("CS_PATH") or os.defpath
    assert fallback in unset.value.reason, unset.value.reason
    assert "CS_PATH" in unset.value.reason
    assert "''" not in unset.value.reason

    monkeypatch.setenv("PATH", "")
    with pytest.raises(RunnerRefusal) as blank:
        resolve_binary()
    assert "set and empty" in blank.value.reason, blank.value.reason
    assert fallback not in blank.value.reason


def test_the_raw_capability_record_is_not_importable() -> None:
    """T10-R2: only `capabilities(*, pane_driver_available)` is exported.

    This supersedes the softer condition in the earlier T10 ratification. Task
    11's `Consumes` line names the raw constant, so a builder following the plan
    literally would get the **un-degraded** record and D-5 would never fire — no
    pane driver, and `can_spawn` still `True`. Making it unimportable is cheaper
    than asking the next builder to remember.
    """
    assert "CLAUDE_CODE_CAPABILITIES" not in spawn_module.__all__
    assert not hasattr(spawn_module, "CLAUDE_CODE_CAPABILITIES")
    assert spawn_module.__all__ == sorted(spawn_module.__all__)

    # …and nothing in `src/` reaches past the export to the private name.
    src = REPO_ROOT / "src"
    leaks = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(src.rglob("*.py"))
        if path != MODULE and "CLAUDE_CODE_CAPABILITIES" in path.read_text(encoding="utf-8")
    ]
    assert leaks == [], leaks


# ----- the frame the ceiling is actually measured against ----------------------

#: The tmux socket the proof below drives. Nothing is ever executed — `run_argv`
#: is a recorder — but the name obeys K6's `^shepherd-m3-` rule anyway.
PROOF_SOCKET = "shepherd-m3-t10-proof"

#: Ten modest environment variables, the hunter's own case: `spec.env` is
#: unbounded and `LocalRunner.start` turns each entry into two argv words
#: (`-e K=V`), which put the real command 696 bytes over the ceiling while
#: `spawn_argv`'s own accounting still read `16324 <= 16324`.
PROOF_ENV = {f"SHEPHERD_PROOF_{index:02d}": "v" * 60 for index in range(10)}


def recording_runner(tmp_path: Path) -> tuple[LocalRunner, list[list[str]]]:
    """A `LocalRunner` wired to the **real** `spawn_argv`, executing nothing."""
    sent: list[list[str]] = []

    def record(argv: list[str]) -> CommandResult:
        sent.append(argv)
        return CommandResult(rc=0, stdout=b"", stderr=b"")

    runner = LocalRunner(
        socket=PROOF_SOCKET,
        run_argv=record,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: "2026-09-17T00:00:00.000Z",
        spawn_argv=lambda spec_, *, frame_bytes: spawn_argv(spec_, BINARY, frame_bytes=frame_bytes),
        record_anomaly=lambda anomaly: None,
        sink_dir=tmp_path,
    )
    return runner, sent


def largest_accepted_brief(tmp_path: Path) -> int:
    """The largest brief `LocalRunner.start` accepts, by bisection **on `start`**.

    Not computed from `command_size`, and not from `spawn_argv` alone: a number
    the test derives the way the code derives it can only ever agree with the
    code. This asks the production path, end to end, and the assertion below
    then measures what that path actually put on the wire.
    """
    low, high = 0, TMUX_COMMAND_LIMIT_B + 4096
    while low < high:
        middle = (low + high + 1) // 2
        runner, _ = recording_runner(tmp_path)
        try:
            runner.start(spec(brief="x" * middle, env=PROOF_ENV))
        except RunnerRefusal:
            high = middle - 1
        else:
            low = middle
    return low


def test_the_whole_new_session_command_fits_under_the_measured_ceiling(tmp_path: Path) -> None:
    """A10/E-M3-10 is "the brief **plus the rest of the command**", and the rest
    of the command is `new-session -d -s <name> -c <cwd> -x <cols> -y <rows>
    [-e K=V]*` — 106 bytes of framing `spawn_argv` never counted, plus two words
    per environment variable.

    Both T10 auditors reproduced this against **real tmux 3.4**: a 16 261-byte
    brief accepted, own accounting `16324 <= 16324`, real client→server command
    **16 430 bytes**, `tmux rc=1 stderr='command too long'`; with ten env vars,
    17 020 bytes. The cleanest control was that adding 55 bytes of frame moved
    the largest accepted argument by exactly 55.

    This takes the **full `new-session` word list** at the accepted boundary and
    asserts it is under the ceiling. It goes red on the pre-T10-R2 code.
    """
    brief = "x" * largest_accepted_brief(tmp_path)
    runner, sent = recording_runner(tmp_path)

    runner.start(spec(brief=brief, env=PROOF_ENV))

    argv = sent[0]
    assert argv[:3] == ["tm" + "ux", "-L", PROOF_SOCKET], argv[:3]
    command = argv[3:]  # the client→server message tmux's limit applies to
    assert command[0] == "new-session"
    assert command.count("-e") == len(PROOF_ENV)
    assert command[-1] == brief

    assert command_size(command) <= TMUX_COMMAND_LIMIT_B, (
        f"the accepted brief produces a {command_size(command)}-byte command and the "
        f"measured ceiling is {TMUX_COMMAND_LIMIT_B}"
    )
