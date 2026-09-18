"""T3 — the transcript tail reader, over the 19 real captured transcripts.

**The fixtures ARE Claude Code.** Every assertion below is against bytes a real
`claude` wrote, copied read-only into `docs/probes/.../transcripts/copies/`.
Where a shape has no capture (a `null` `stop_reason`, a torn trailing line, a
non-UTF-8 byte) the test **composes** the case in `tmp_path` and says so — a
composed fixture is honest; editing a capture to make a test pass is not.

P-M2-15: nothing here opens a path under `~/.claude/`. The copies are the only
legal transcript fixtures.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.stops import TurnEnding
from shepherd.engines.claude_code import transcript_tail
from shepherd.engines.claude_code.transcript_tail import (
    TAIL_BYTES,
    TAIL_ENTRIES,
    locate_transcript,
    read_tail,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COPIES = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "transcripts" / "copies"

#: One real transcript per shape this reader has to survive, named by the fact
#: it carries rather than by its session id.
GROUPED_BLOCKS = COPIES / "-tmp-shp-schemas-fork-RgNHRN-work/76d51cc7-3b32-4274-9ee4-e08f21f79042.jsonl"
SYNTHETIC_ONLY = COPIES / "-tmp-shp-schemas-tx-blIf90-work/89b8683f-b2ea-4874-934a-9cadbb6cb276.jsonl"
METADATA_TAIL = COPIES / "-tmp-shp-schemas-tx-blIf90-work/7c27bb7f-5390-48b0-8b2e-cf4004113d09.jsonl"
HELD_TOOL_CALL = COPIES / "-tmp-shp-schemas-reg-Jv4MTo-work/ea5a5348-c427-4438-b6f1-23a46e260b59.jsonl"

#: Big enough to read any of the copies whole — the bounded window is the
#: subject of its own tests, and every other test states which it is using.
WHOLE_FILE = 4 * 1024 * 1024


def all_copies() -> list[Path]:
    """The 15 main transcripts. Subagent transcripts live a level deeper and
    are `transcript.py`'s job (T13, M1), not this reader's."""
    return sorted(COPIES.glob("*/*.jsonl"))


def copy_into(tmp_path: Path, source: Path) -> Path:
    target = tmp_path / source.name
    shutil.copy(source, target)
    return target


def compose(tmp_path: Path, entries: list[dict[str, object]], name: str = "composed.jsonl") -> Path:
    """A transcript with no capture behind it. Named `compose` so a reader can
    see at the call site that this shape is constructed, not observed."""
    target = tmp_path / name
    target.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    return target


def assistant(
    message_id: str,
    stop_reason: str | None,
    blocks: list[dict[str, object]],
    block_index: int = 0,
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, object]:
    return {
        "type": "assistant",
        "apiBlockIndex": block_index,
        "message": {
            "id": message_id,
            "model": model,
            "stop_reason": stop_reason,
            "content": blocks,
        },
    }


def user(blocks: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "user", "message": {"content": blocks}}


# ----- the eight rules, each against a capture --------------------------------


def test_tail_filters_by_entry_type_before_counting() -> None:
    """E25 / E-M2-15: metadata is re-appended, so it clusters in the tail.

    This file's last two lines are `system` and `last-prompt`. A line-count
    tail of three returns bookkeeping; a type-filtered tail returns the turn.
    """
    lines = [line for line in METADATA_TAIL.read_text(encoding="utf-8").splitlines() if line.strip()]
    naive = [str(json.loads(line)["type"]) for line in lines[-3:]]
    assert naive == ["assistant", "system", "last-prompt"]  # the capture, as it is

    tail, anomalies = read_tail(METADATA_TAIL, limit=3, max_bytes=WHOLE_FILE)

    assert tail.entry_count == 3
    assert tail.ending is TurnEnding.ENDED_TURN
    assert tail.last_assistant_text == "FORKED"
    assert not any(anomaly.kind is AnomalyKind.MALFORMED_PAYLOAD for anomaly in anomalies)


def test_blocks_of_one_message_are_grouped() -> None:
    """E-M2-14: one API message is split across entries, one per content block,
    with a repeated `usage` and an increasing `apiBlockIndex`.

    In this capture, message `egiSk1` is `apiBlockIndex` 0 (a `thinking` block)
    and 1 (the `text` block "OK"). Reading the last *entry* would return an
    empty text; reading the last *group* returns the message.
    """
    entries = [
        json.loads(line)
        for line in GROUPED_BLOCKS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    grouped = [e for e in entries if e.get("type") == "assistant" and e.get("apiBlockIndex") == 1]
    assert grouped, "the capture no longer has a split message — re-probe before editing"

    tail, _ = read_tail(GROUPED_BLOCKS, limit=TAIL_ENTRIES, max_bytes=WHOLE_FILE)
    assert tail.last_assistant_text == "PINEAPPLE-42"
    assert tail.ending is TurnEnding.ENDED_TURN


def test_held_tool_call_is_not_a_finished_turn(tmp_path: Path) -> None:
    """ADR-M2-3: `tool_use` means the model stopped holding an unexecuted call,
    which is `stalled_pending_tool` and not a finished turn.

    The capture confirms the *spelling* is live — `tool_use` appears 26 times
    across the copies — but no captured transcript's **last** group is one, so
    the ending itself is exercised on a composed file.
    """
    tail, _ = read_tail(HELD_TOOL_CALL, limit=2, max_bytes=WHOLE_FILE)
    assert tail.ending is TurnEnding.ENDED_TURN  # this file's last turn ended

    path = compose(
        tmp_path,
        [
            user([{"type": "text", "text": "go"}]),
            assistant("m1", "tool_use", [{"type": "tool_use", "id": "t1", "name": "Bash"}]),
        ],
    )
    held, _ = read_tail(path, max_bytes=WHOLE_FILE)
    assert held.ending is TurnEnding.HELD_TOOL_CALL
    assert [use.name for use in held.tool_uses] == ["Bash"]


def test_hit_token_cap_is_its_own_ending(tmp_path: Path) -> None:
    """`max_tokens` -> `TRUNCATED`. **Composed**: the corpus's one truncation
    arrives as `StopFailure.error = max_output_tokens` with no `Stop` at all
    (E-M2-2), so the transcript spelling has no capture here."""
    path = compose(
        tmp_path, [assistant("m1", "max_tokens", [{"type": "text", "text": "half a sen"}])]
    )
    tail, _ = read_tail(path, max_bytes=WHOLE_FILE)
    assert tail.ending is TurnEnding.HIT_TOKEN_CAP


def test_synthetic_entry_is_not_a_turn_ending(tmp_path: Path) -> None:
    """E-M2-18: `<synthetic>` is client-generated — no API call, no turn ending.

    This capture's **only** assistant entry is synthetic and carries
    `stop_sequence`. Honouring it would invent a turn ending out of a client
    -side banner; excluding it leaves the window with nothing that ended a
    turn, which is `ABSENT` and is counted.
    """
    target = copy_into(tmp_path, SYNTHETIC_ONLY)
    tail, anomalies = read_tail(target, limit=TAIL_ENTRIES, max_bytes=WHOLE_FILE)

    assert tail.ending is TurnEnding.ABSENT
    assert AnomalyKind.TRANSCRIPT_TAIL_ABSENT in {anomaly.kind for anomaly in anomalies}
    assert tail.entry_count == 2  # the synthetic entry is still *in* the window


def test_the_only_two_stop_sequence_captures_are_synthetic() -> None:
    """DP7's evidence, recorded rather than assumed.

    §8 and the plan treat `stop_sequence` as the live fourth spelling. Both of
    its occurrences in the 19 copies sit on `<synthetic>` entries, so no
    capture exercises a *real* `stop_sequence`. That is why the `OTHER` case
    below is composed and says so, and why the gap is in the blocker file.
    """
    found = [
        (path.name, message.get("model"))
        for path in all_copies()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
        for entry in [_loads(line)]
        if isinstance(entry, dict) and entry.get("type") == "assistant"
        for message in [entry.get("message")]
        if isinstance(message, dict) and message.get("stop_reason") == "stop_sequence"
    ]
    assert len(found) == 2
    assert {model for _, model in found} == {"<synthetic>"}


def test_unknown_stop_reason_spelling_is_other_and_counted(tmp_path: Path) -> None:
    """DP7 — a spelling no member claims becomes `OTHER`, counted, never guessed.

    **Composed:** every captured `stop_sequence` is synthetic (above), so a
    real one has no fixture. The rule under test is the narrowing itself, and
    the count is what tells you to add a member.
    """
    path = compose(
        tmp_path,
        [
            user([{"type": "text", "text": "go"}]),
            assistant("m1", "stop_sequence", [{"type": "text", "text": "halted"}]),
        ],
    )
    tail, anomalies = read_tail(path, max_bytes=WHOLE_FILE)

    assert tail.ending is TurnEnding.OTHER
    assert AnomalyKind.STOP_UNMAPPED_VALUE in {anomaly.kind for anomaly in anomalies}
    assert "stop_sequence" in " ".join(anomaly.detail for anomaly in anomalies)


def test_ending_walks_back_over_null_stop_reason(tmp_path: Path) -> None:
    """E-M2-13: a lone `thinking` block can carry `stop_reason: null`.

    **Composed** — every captured `thinking` entry carries its message's real
    `stop_reason`. The rule is that a null decides nothing, so the reader walks
    back to the most recent group that decided something.
    """
    path = compose(
        tmp_path,
        [
            user([{"type": "text", "text": "go"}]),
            assistant("m1", "end_turn", [{"type": "text", "text": "done"}]),
            assistant("m2", None, [{"type": "thinking", "thinking": "hmm"}]),
        ],
    )
    tail, _ = read_tail(path, max_bytes=WHOLE_FILE)
    assert tail.ending is TurnEnding.ENDED_TURN


def test_all_null_stop_reasons_are_absent_not_guessed(tmp_path: Path) -> None:
    path = compose(
        tmp_path,
        [assistant("m1", None, [{"type": "thinking", "thinking": "hmm"}])],
    )
    tail, anomalies = read_tail(path, max_bytes=WHOLE_FILE)
    assert tail.ending is TurnEnding.ABSENT
    assert AnomalyKind.TRANSCRIPT_TAIL_ABSENT in {anomaly.kind for anomaly in anomalies}


def test_tool_uses_and_failures_are_collected() -> None:
    """Rules 6 and 7, counted over all 15 captured main transcripts.

    `Write` twice and four `is_error` results is what the corpus holds; those
    two numbers are heuristics 3 and 4's entire input, so they are asserted
    against the capture rather than against the reader's own arithmetic.
    """
    names: list[str] = []
    failures = 0
    for path in all_copies():
        tail, _ = read_tail(path, limit=100, max_bytes=WHOLE_FILE)
        names.extend(use.name for use in tail.tool_uses)
        failures += len(tail.failures)

    assert names.count("Write") == 2
    assert names.count("Bash") == 8
    assert names.count("Agent") == 3
    assert failures == 4


def test_a_failure_is_paired_back_to_its_tool_by_id() -> None:
    """E-M2-17: the tool's *name* lives on the assistant entry that issued the
    call, not on the result that failed."""
    tail, _ = read_tail(GROUPED_BLOCKS, limit=100, max_bytes=WHOLE_FILE)
    assert len(tail.failures) == 1
    failure = tail.failures[0]
    assert failure.name == "Bash"
    assert failure.tool_use_id == "toolu_01Te4G4F86V1UF8hZrZz6gu5"
    assert any(use.tool_use_id == failure.tool_use_id for use in tail.tool_uses)


def test_unpairable_error_result_is_counted_not_attributed(tmp_path: Path) -> None:
    """A result whose call fell outside the window keeps `name=None`.

    Attributing it to the nearest tool would be a guess that reads like a fact.
    """
    path = compose(
        tmp_path,
        [
            user([{"type": "tool_result", "tool_use_id": "toolu_orphan", "is_error": True}]),
            assistant("m1", "end_turn", [{"type": "text", "text": "done"}]),
        ],
    )
    tail, anomalies = read_tail(path, max_bytes=WHOLE_FILE)

    assert len(tail.failures) == 1
    assert tail.failures[0].name is None
    assert tail.failures[0].tool_use_id == "toolu_orphan"
    assert AnomalyKind.TOOL_RESULT_UNPAIRED in {anomaly.kind for anomaly in anomalies}


def test_malformed_trailing_line_is_skipped(tmp_path: Path) -> None:
    """D25 / E-M2-11: a daemon killed mid-write leaves exactly one torn line."""
    target = copy_into(tmp_path, METADATA_TAIL)
    with target.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "assistant", "message": {"id": "torn", "stop_rea')

    tail, anomalies = read_tail(target, limit=3, max_bytes=WHOLE_FILE)

    assert tail.skipped_lines == 1
    assert AnomalyKind.MALFORMED_PAYLOAD in {anomaly.kind for anomaly in anomalies}
    # …and the tail is otherwise the same one the intact file gives.
    intact, _ = read_tail(METADATA_TAIL, limit=3, max_bytes=WHOLE_FILE)
    assert tail.ending is intact.ending
    assert tail.last_assistant_text == intact.last_assistant_text


def test_tail_reader_never_raises(tmp_path: Path) -> None:
    """P-M2-7, over 200+ corruptions of a real transcript.

    Truncated at every byte of its last line, empty, absent, a directory, and
    non-UTF-8 bytes. Each returns a record and counts; none raises, because a
    transcript is the *observed* system and reading it may never cost a fold
    (C-M2-6, principle 4).
    """
    source = SYNTHETIC_ONLY.read_bytes()
    # Every byte boundary of the tail — which spans the last entry and part of
    # the one before it, so the 200 the property names are real cuts and not a
    # number rounded up to meet it.
    cases = 0

    for cut in range(len(source) - 260, len(source)):
        target = tmp_path / "cut.jsonl"
        target.write_bytes(source[:cut])
        tail, _ = read_tail(target, max_bytes=WHOLE_FILE)
        assert tail.entry_count >= 0
        cases += 1
    assert cases >= 200, f"only {cases} truncations — the fixture got smaller"

    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")
    assert read_tail(empty)[0].ending is TurnEnding.ABSENT

    absent, anomalies = read_tail(tmp_path / "not-here.jsonl")
    assert absent.ending is TurnEnding.ABSENT
    assert AnomalyKind.TRANSCRIPT_TAIL_ABSENT in {anomaly.kind for anomaly in anomalies}

    directory = tmp_path / "a-directory.jsonl"
    directory.mkdir()
    assert read_tail(directory)[0].ending is TurnEnding.ABSENT

    binary = tmp_path / "binary.jsonl"
    binary.write_bytes(b"\xff\xfe\x00not utf-8 at all\n")
    tail, _ = read_tail(binary)
    assert tail.ending is TurnEnding.ABSENT
    assert tail.skipped_lines == 1


def test_tail_read_is_bounded(tmp_path: Path) -> None:
    """A4 / r3 — this runs on `controld`'s single ingest thread.

    A full-file scan per stop against a transcript of thousands of entries
    delays the next hook's frame, and "the observer never harms the observed"
    is the one clause M2 may not trade. The assertion is on **bytes read**, not
    on the wall clock, so it cannot go quiet on a fast machine.
    """
    assert TAIL_BYTES == 256 * 1024

    big = tmp_path / "big.jsonl"
    filler = json.dumps({"type": "system", "pad": "x" * 4000})
    tail_entries = [
        json.dumps(user([{"type": "text", "text": "go"}])),
        json.dumps(assistant("m1", "end_turn", [{"type": "text", "text": "done"}])),
    ]
    big.write_text("\n".join([filler] * 400 + tail_entries) + "\n", encoding="utf-8")
    assert big.stat().st_size > TAIL_BYTES

    read_bytes = _bytes_read_by(big, lambda: read_tail(big))
    assert read_bytes <= TAIL_BYTES
    assert read_bytes < big.stat().st_size

    tail, anomalies = read_tail(big)
    assert tail.ending is TurnEnding.ENDED_TURN
    assert tail.truncated is True
    assert AnomalyKind.TRANSCRIPT_TAIL_TRUNCATED in {anomaly.kind for anomaly in anomalies}


def test_first_partial_line_of_the_window_is_discarded(tmp_path: Path) -> None:
    """A mid-line seek is not a malformed line, and must not be counted as one."""
    path = tmp_path / "window.jsonl"
    entries = [
        json.dumps(assistant("m0", "end_turn", [{"type": "text", "text": "x" * 500}])),
        json.dumps(user([{"type": "text", "text": "go"}])),
        json.dumps(assistant("m1", "end_turn", [{"type": "text", "text": "done"}])),
    ]
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")

    whole, _ = read_tail(path, max_bytes=WHOLE_FILE)
    assert whole.truncated is False
    assert whole.skipped_lines == 0

    # A window that lands in the middle of the first entry.
    windowed, _ = read_tail(path, max_bytes=len(entries[2]) + len(entries[1]) + 40)
    assert windowed.truncated is True
    assert windowed.skipped_lines == 0, "a mid-line seek is not a torn line"
    assert windowed.ending is TurnEnding.ENDED_TURN
    assert windowed.last_assistant_text == "done"


def test_truncated_window_is_flagged_and_counted(tmp_path: Path) -> None:
    """Principle 5: a shorter tail is honest, a silent one is not."""
    path = tmp_path / "w.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(assistant(f"m{index}", "end_turn", [{"type": "text", "text": "y" * 300}]))
            for index in range(20)
        )
        + "\n",
        encoding="utf-8",
    )
    full, full_anomalies = read_tail(path, max_bytes=WHOLE_FILE)
    assert full.truncated is False
    assert AnomalyKind.TRANSCRIPT_TAIL_TRUNCATED not in {a.kind for a in full_anomalies}

    short, short_anomalies = read_tail(path, max_bytes=1500)
    assert short.truncated is True
    assert short.entry_count < full.entry_count
    assert AnomalyKind.TRANSCRIPT_TAIL_TRUNCATED in {a.kind for a in short_anomalies}


def test_tail_is_found_by_session_id_glob(tmp_path: Path) -> None:
    """The project-directory slug is lossy and hash-suffixed past 200 UTF-16
    units, so the session id is the only key. Never reverse the slug."""
    projects = tmp_path / "projects"
    (projects / "-a-lossy-slug").mkdir(parents=True)
    wanted = projects / "-a-lossy-slug" / "abc-123.jsonl"
    shutil.copy(METADATA_TAIL, wanted)

    assert locate_transcript(projects, "abc-123") == wanted
    assert locate_transcript(projects, "no-such-session") is None

    # …and the module contains no slug arithmetic at all.
    source = Path(transcript_tail.__file__).read_text(encoding="utf-8")
    assert "replace(" not in source or "slug" not in source


def test_promise_is_unjudged_without_a_predicate(tmp_path: Path) -> None:
    """The promise *vocabulary* is T8's. This reader supplies the ordering fact
    and says `None` — "there was no promise to judge" — when nobody asked."""
    path = compose(
        tmp_path,
        [
            assistant("m1", "tool_use", [{"type": "tool_use", "id": "t1", "name": "Bash"}]),
            assistant("m2", "end_turn", [{"type": "text", "text": "Now I will run the tests."}]),
        ],
    )
    unjudged, _ = read_tail(path, max_bytes=WHOLE_FILE)
    assert unjudged.promise_followed_by_tool_use is None

    broken, _ = read_tail(path, max_bytes=WHOLE_FILE, promise=lambda text: "I will" in text)
    assert broken.promise_followed_by_tool_use is False

    kept_path = compose(
        tmp_path,
        [
            assistant("m1", "end_turn", [{"type": "text", "text": "Now I will run the tests."}]),
            assistant("m2", "tool_use", [{"type": "tool_use", "id": "t1", "name": "Bash"}]),
        ],
        name="kept.jsonl",
    )
    kept, _ = read_tail(kept_path, max_bytes=WHOLE_FILE, promise=lambda text: "I will" in text)
    assert kept.promise_followed_by_tool_use is True


# ----- the module's own boundaries --------------------------------------------


def test_tail_reader_only_reads() -> None:
    """Principle 4 / C-M2-6 — nothing we install may harm Claude Code."""
    tree = ast.parse(Path(transcript_tail.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {
                "write_text",
                "write_bytes",
                "unlink",
                "mkdir",
                "rmdir",
                "remove",
                "rename",
                "touch",
            }, ast.dump(node.func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print"
    source = Path(transcript_tail.__file__).read_text(encoding="utf-8")
    assert '"w"' not in source and "'w'" not in source
    assert "settings.json" not in source


def test_the_reader_reads_no_hook_payload_stop_reason() -> None:
    """P-M2-5 / D46, stated precisely.

    The `Stop` **hook payload** has no `stop_reason` field — not in 26
    captures, not in the CLI's own schema. The transcript's
    `message.stop_reason` is a different object on a different surface, and
    reading it is exactly what D46 says to do instead. So the assertion is not
    "the token is absent" (prose has to be able to explain the rule) but
    "there is exactly one **code** read of it, and it is out of a message".
    """
    source = Path(transcript_tail.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    code_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert code_literals.count("stop_reason") == 1
    assert 'message.get("stop_reason")' in source


def test_no_fixture_reads_the_real_claude_dir() -> None:
    """P-M2-15 — the copies are the only legal transcript fixtures."""
    # Built at runtime so this guard does not trip over its own spelling.
    engine_dir = "." + "claude"
    home_call = "Path.home" + "()"
    forbidden = (f"/root/{engine_dir}", f"{engine_dir}/projects", home_call)
    own = Path(__file__).read_text(encoding="utf-8")
    for needle in forbidden:
        assert needle not in own, needle
    for path in all_copies():
        assert "probes" in str(path)
        assert path.is_relative_to(REPO_ROOT)


def test_the_window_constants_are_the_plans(tmp_path: Path) -> None:
    assert TAIL_ENTRIES == 20
    assert TAIL_BYTES == 256 * 1024
    # The largest single captured entry is 410 665 bytes (§Transcript JSONL),
    # so the window is not sized to hold every line — the counter is the honesty.
    assert TAIL_BYTES < 410_665


def _bytes_read_by(target: Path, run: object) -> int:
    """How many bytes of `target` a call actually pulled off disk.

    Instrumenting the file object rather than timing the call: a wall-clock
    assertion goes quiet on a fast machine, and the claim is about the read.
    """
    import builtins
    from typing import Any, Callable, cast

    counted = [0]
    real_open = builtins.open

    def counting_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        handle = real_open(file, *args, **kwargs)
        if Path(str(file)) != target:
            return handle
        inner = handle.read

        def read(*size: Any) -> Any:
            chunk = inner(*size)
            counted[0] += len(chunk)
            return chunk

        handle.read = read  # type: ignore[method-assign]
        return handle

    builtins.open = counting_open  # type: ignore[assignment]
    try:
        cast(Callable[[], object], run)()
    finally:
        builtins.open = real_open  # type: ignore[assignment]
    return counted[0]


def _loads(line: str) -> object:
    try:
        return json.loads(line)
    except ValueError:
        return None


@pytest.mark.parametrize("path", all_copies(), ids=lambda path: path.name[:8])
def test_every_captured_transcript_reads_without_an_exception(path: Path) -> None:
    """The whole corpus, one call each, at the *default* window — which is the
    configuration `controld` will actually run."""
    tail, anomalies = read_tail(path)
    assert isinstance(tail.entry_count, int)
    assert tail.entry_count <= TAIL_ENTRIES
    assert all(anomaly.detail for anomaly in anomalies)
