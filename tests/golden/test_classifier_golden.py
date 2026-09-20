"""T17 lane 1 — the classifier over the real captures, and nothing else.

**No mocking of Claude Code: the fixtures ARE Claude Code.** Every verdict in
this file is derived from bytes a real hook wrote to a real stdin, or from a
real transcript the engine wrote to disk, and the only thing that is ours is
which of the two a fixture pairs with (`stops.py`, "the composition").

Adding a missed case is: capture the signals, drop in a fixture, fix the rule,
re-run. Nothing here builds a payload.
"""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path

import pytest

from golden.corpus import (
    EXPECTED_EVENT_COUNT,
    REPO_ROOT,
    EXPECTED_GAPFILL_EVENT_COUNT,
    EXPECTED_GAPFILL_FILE_COUNT,
    EXPECTED_GAPFILL_MARKERS,
    EXPECTED_GAPFILL_PTY_FILE_COUNT,
    EXPECTED_GAPFILL_SESSION_COUNT,
    EXPECTED_SESSION_COUNT,
    EXPECTED_TRANSCRIPT_COPIES,
    GAPFILL_HOOK_GLOBS,
    GAPFILL_MARKER_LABEL,
    GAPFILL_ROOT,
    gapfill_files,
    load_corpus,
    load_gapfill_corpus,
    parse,
    transcript_copies,
)
from golden.stops import (
    EXPECTED_CORPUS_ONE_STOPS,
    EXPECTED_CORPUS_TWO_STOPS,
    EXPECTED_CURATED,
    EXPECTED_FIXTURE_COUNT,
    EXPECTED_VERDICTS,
    MAX_UNKNOWN_RATE,
    StopFixture,
    composed,
    load_stop_fixtures,
    load_verdicts,
    unknown_rate,
    verdict_table,
    write_verdicts,
)
from shepherd.core.signals import MalformedPayload
from shepherd.core.stops import StopReason
from shepherd.signals.verdict import classify

#: P-M2-12's three. No M2 code path produces any of them, and the two corpora
#: are the widest input this build can put through the classifier.
UNREACHABLE = (StopReason.CRASHED, StopReason.KILLED, StopReason.DERAILED)


@pytest.fixture(scope="module")
def fixtures() -> list[StopFixture]:
    return load_stop_fixtures()


# ----- the two corpora --------------------------------------------------------


def test_both_corpora_load() -> None:
    """429 + 239, and corpus 1 has **no** malformed capture.

    Corpus 2's 23 refusals are the probe harness's own `MARKER` lines, which
    carry no `hook_event_name` and were never hook stdin. They are asserted by
    exact count and by label, so a genuinely torn capture appearing among them
    is a failure rather than a rounding error.
    """
    corpus_one = load_corpus()
    corpus_two = load_gapfill_corpus()

    assert len(corpus_one) == EXPECTED_EVENT_COUNT
    assert len({event.session_id for event in corpus_one}) == EXPECTED_SESSION_COUNT
    assert [parse(e) for e in corpus_one if isinstance(parse(e), MalformedPayload)] == []

    assert len(corpus_two) == EXPECTED_GAPFILL_EVENT_COUNT
    refused = [event for event in corpus_two if isinstance(parse(event), MalformedPayload)]
    assert len(refused) == EXPECTED_GAPFILL_MARKERS
    assert {event.label for event in refused} == {GAPFILL_MARKER_LABEL}
    assert all(event.payload == {} for event in refused)
    accepted = {
        event.session_id for event in corpus_two if not isinstance(parse(event), MalformedPayload)
    }
    assert len(accepted) == EXPECTED_GAPFILL_SESSION_COUNT


def test_the_pidfd_capture_is_loaded() -> None:
    """A5, r3 — `pty-hooks.jsonl` is not `hooks.jsonl`.

    A glob that silently matches nothing is how an evidence gap becomes
    invisible, so every glob is asserted against an **exact** count and the
    pidfd run's own file is named, not hoped for.
    """
    files = gapfill_files()
    assert len(files) == EXPECTED_GAPFILL_FILE_COUNT

    pty = sorted(GAPFILL_ROOT.glob(GAPFILL_HOOK_GLOBS[1]))
    assert len(pty) == EXPECTED_GAPFILL_PTY_FILE_COUNT
    assert [path.name for path in pty] == ["pty-hooks.jsonl"]
    assert set(pty) <= set(files), "the pty capture is not in the loaded corpus"

    # …and its events really arrive, rather than the file merely being listed.
    scenarios = {event.scenario for event in load_gapfill_corpus()}
    assert {path.parent.name for path in pty} <= scenarios

    assert len(transcript_copies()) == EXPECTED_TRANSCRIPT_COPIES


# ----- every stop capture, and the table ---------------------------------------


def test_every_stop_capture_produces_a_verdict(fixtures: list[StopFixture]) -> None:
    """All 99 of corpus 1's stops (26 `Stop`, 23 `StopFailure`, 50 `SessionEnd`),
    all 70 of corpus 2's, and the curated compositions — each one classified,
    and each one classified as the fixture **declared** before the classifier
    ran. The declaration comes from §8's table, not from re-running the rule.
    """
    assert len(fixtures) == EXPECTED_FIXTURE_COUNT
    assert (
        EXPECTED_CORPUS_ONE_STOPS + EXPECTED_CORPUS_TWO_STOPS + EXPECTED_CURATED
        == EXPECTED_FIXTURE_COUNT
    )
    wrong = [
        (fixture.name, fixture.expected.value, classify(fixture.evidence).stop_reason.value)
        for fixture in fixtures
        if classify(fixture.evidence).stop_reason is not fixture.expected
    ]
    assert wrong == []


def test_verdicts_match_the_expected_table(
    fixtures: list[StopFixture], request: pytest.FixtureRequest
) -> None:
    """The checked-in table, regenerated only by `--update-golden` (M1's shape).

    Compared key by key so a diff names the fixture that moved rather than
    printing two 174-row dictionaries.
    """
    actual = verdict_table(fixtures)
    if bool(request.config.getoption("--update-golden")):
        write_verdicts(actual)
        pytest.skip("golden verdict table rewritten")
    expected = load_verdicts()
    assert len(actual) == EXPECTED_FIXTURE_COUNT
    assert sorted(expected) == sorted(actual)
    differing = {
        name: (expected[name], actual[name])
        for name in actual
        if expected[name] != actual[name]
    }
    assert differing == {}


def test_replay_of_the_golden_lane_is_byte_identical() -> None:
    """Twice, from scratch, the same bytes — M1's own discipline.

    A fixture set built from a `set` iteration order, a `tmp_path` name or a
    clock would pass every other test in this file and fail this one.
    """
    first = json.dumps(verdict_table(load_stop_fixtures()), indent=2, sort_keys=True)
    second = json.dumps(verdict_table(load_stop_fixtures()), indent=2, sort_keys=True)
    assert first == second
    assert first == EXPECTED_VERDICTS.read_text(encoding="utf-8").rstrip("\n")


def test_corpus_unknown_rate_is_under_20_percent(fixtures: list[StopFixture]) -> None:
    """P-M2-14 — DP8's defer working, over the stop-fixture population.

    The two `unknown`s that remain are both honest: the engine's own `unknown`
    error value, and C13's observed exit with no obtainable exit code.
    """
    assert len(fixtures) == EXPECTED_FIXTURE_COUNT, "the ceiling is meaningless over a short set"
    rate = unknown_rate(fixtures)
    assert rate < MAX_UNKNOWN_RATE, f"{rate:.1%} of the stop fixtures are unknown"

    unknown = [f for f in fixtures if classify(f.evidence).stop_reason is StopReason.UNKNOWN]
    assert unknown, "no fixture is unknown, so the rate is not being measured"
    assert sorted(f.name for f in unknown) == [
        "composed:c13/observed-process-exit",
        "real:S08_mock_http400/0003",
    ]


def test_benign_auto_compaction_does_not_fire_context_exhausted(
    fixtures: list[StopFixture],
) -> None:
    """The coverage table's unnamed row, which is the one that must NOT fire.

    `autocompact-real-*` captured a session that compacted and carried on. §8's
    rule is bounded by *death*, so the two sessions that survived a compaction
    end `completed`, and the one in `lifecycle-end-*` that was killed
    mid-compaction — `PreCompact{auto}` with no `PostCompact`, then
    `SessionEnd` — is the only `context_exhausted` in either corpus.
    """
    exhausted = [
        fixture.name
        for fixture in fixtures
        if classify(fixture.evidence).stop_reason is StopReason.CONTEXT_EXHAUSTED
    ]
    assert exhausted == ["real:lifecycle-end-20260914T175238Z/0017"]
    benign = [f for f in fixtures if f.name.startswith("composed:autocompact-real-")]
    assert len(benign) == 8
    assert {classify(f.evidence).stop_reason for f in benign} == {StopReason.COMPLETED}


def test_unreachable_reasons_are_unreachable(fixtures: list[StopFixture]) -> None:
    """P-M2-12 over both corpora: `crashed`, `killed`, `derailed` (G-M2-2/4/6)."""
    assert len(fixtures) == EXPECTED_FIXTURE_COUNT
    produced = {classify(fixture.evidence).stop_reason for fixture in fixtures}
    assert len(produced) > 1, "one verdict over 174 fixtures is not an assertion"
    assert produced.isdisjoint(UNREACHABLE)
    assert {fixture.expected for fixture in fixtures}.isdisjoint(UNREACHABLE)


# ----- the two rules that make the fixtures auditable -------------------------


def test_composed_fixtures_name_their_captures(fixtures: list[StopFixture]) -> None:
    """K1, mechanically: no shape without a capture.

    Every fixture names the capture files it is made of and **every named path
    exists on disk**; a composed one — a real stop record paired with a real
    tail from another session — names at least two, because the pairing is the
    part that is ours and it has to be auditable.
    """
    assert any(composed(fixture) for fixture in fixtures), "nothing is composed; the guard is idle"
    missing: list[str] = []
    for fixture in fixtures:
        assert fixture.sources, f"{fixture.name} names no capture"
        for source in fixture.sources:
            assert not Path(source).is_absolute(), f"{fixture.name}: {source} is not repo-relative"
            if not (REPO_ROOT / source).is_file():
                missing.append(f"{fixture.name}: {source}")
        if composed(fixture):
            assert len(fixture.sources) >= 2, f"{fixture.name} is composed but names one capture"
    assert missing == []


def test_no_fixture_reads_the_real_claude_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """P-M2-15, as an observation rather than a promise.

    424 of the 429 corpus payloads name a `transcript_path` that still exists
    on this host. Reading one would make the suite non-hermetic and dependent
    on a directory the user may clear at any moment — and it would pass. So the
    whole fixture build runs with `open` instrumented, and every path it
    touches is recorded and checked.
    """
    opened: list[str] = []
    real_open = builtins.open

    def record(file: object, *args: object, **kwargs: object) -> object:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(builtins, "open", record)
    fixtures = load_stop_fixtures()
    monkeypatch.undo()

    assert fixtures, "nothing was built, so nothing was observed"
    # The same directory `tests/conftest.py` guards: `$CLAUDE_CONFIG_DIR`, or
    # `~/.claude`. Re-derived rather than imported, because `tests/` is not a
    # package and its `conftest` name is already taken in this directory.
    forbidden = str(Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))
    offenders = [path for path in opened if path.startswith(forbidden) or "/.claude/" in path]
    assert offenders == [], f"a fixture read the engine's own directory: {offenders[:3]}"
    assert any("docs/probes" in path for path in opened), "no capture was read at all"

    named = [source for fixture in fixtures for source in fixture.sources]
    assert [source for source in named if "/.claude/" in source] == []
