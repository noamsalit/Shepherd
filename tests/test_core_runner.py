"""T2: the runner and engine vocabulary — enums, frozen types, constant table.

Every count here is **derived from the type**, never written beside it. A literal
`== 6` next to an enum is a literal that falls behind the enum the first time a
member is appended; the totality product below cannot, because it is built from
the same enums T13's write-policy table is built from.
"""

from __future__ import annotations

import itertools
import random

import pytest
from shepherd.core.states import Ownership, SessionState


def test_pane_kind_is_the_six_the_captures_show() -> None:
    """T13 keys a **total** table on `SessionState x PaneKind x Ownership x
    input_empty`. The plan's key count is 96; a seventh `PaneKind` silently makes
    the table partial, so the product — not a `len()` beside the enum — is what
    this pins.
    """
    from shepherd.core.runner import PaneKind

    key_space = list(
        itertools.product(SessionState, PaneKind, Ownership, (True, False))
    )
    assert len(key_space) == 96  # the plan's number, Task 13
    assert len(set(key_space)) == len(key_space)

    # The other three factors are pinned by their own tests (T1); this is the
    # arithmetic that makes 96 a statement about `PaneKind` and not about them.
    assert len(key_space) == len(SessionState) * len(PaneKind) * len(Ownership) * 2

    # The wire values are the plan's words, in the plan's order.
    assert [kind.value for kind in PaneKind] == [
        "trust_dialog",
        "permission_dialog",
        "prompt_ready",
        "busy",
        "dead",
        "unreadable",
    ]


def test_write_decision_is_the_six_a_key_can_map_to() -> None:
    """Three *named* refusals, because a UI renders them differently, plus the
    `C-u` clearing form (capture-proven, `01b-after-ctrl-u.txt`). A seventh with
    no key mapping to it is a value nothing can return.
    """
    from shepherd.core.runner import PaneKind, WriteDecision

    assert [decision.value for decision in WriteDecision] == [
        "send_now",
        "clear_then_send",
        "queue",
        "refuse_dialog",
        "refuse_no_pty",
        "refuse_input_not_empty",
    ]
    assert len(WriteDecision) == len({d.value for d in WriteDecision})

    # `WriteDecision` is the value space and is NOT a factor of the totality key.
    assert WriteDecision not in (SessionState, PaneKind, Ownership)


def test_runner_handle_round_trips_and_refuses_an_ambiguous_field() -> None:
    """1 000 generated handles, plus the one case that must not round-trip.

    `session.runner_handle` is one TEXT column, so `to_text` is the only thing
    standing between a field containing the separator and a handle that parses
    back as a *different* handle.
    """
    from shepherd.core.runner import HANDLE_SEPARATOR, RunnerHandle

    alphabet = "abcdefgh-_.0123456789 "
    assert HANDLE_SEPARATOR not in alphabet
    rng = random.Random(20260917)
    for _ in range(1000):
        parts = [
            "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 24)))
            for _ in range(3)
        ]
        handle = RunnerHandle(runner=parts[0], socket=parts[1], session_name=parts[2])
        text = handle.to_text()
        assert text.count(HANDLE_SEPARATOR) == 2
        assert RunnerHandle.from_text(text) == handle

    # The separator in any field is an error, not a silently re-parsed handle.
    for field in ("runner", "socket", "session_name"):
        ambiguous = RunnerHandle(
            **{"runner": "r", "socket": "s", "session_name": "n", field: f"a{HANDLE_SEPARATOR}b"}
        )
        with pytest.raises(ValueError):
            ambiguous.to_text()

    # …and a text with the wrong number of parts is refused rather than padded.
    with pytest.raises(ValueError):
        RunnerHandle.from_text("r|s")
    with pytest.raises(ValueError):
        RunnerHandle.from_text("r|s|n|extra")


def test_the_frozen_types_have_exactly_the_plan_s_fields_in_order() -> None:
    """The field lists are compared **against the dataclasses**, not kept beside
    them: M1 shipped a hand-maintained list mirroring a dataclass that nothing
    ever compared, and it fell behind silently. Order matters for `PaneFields`
    and for every positional construction downstream.
    """
    import ast
    import dataclasses

    from shepherd.core import runner as mod

    def normalised(annotation: object) -> str:
        """`from __future__ import annotations` stores the *unparsed* AST, so a
        string comparison would be about quote style. Compare the syntax."""
        assert isinstance(annotation, str), annotation
        return ast.unparse(ast.parse(annotation, mode="eval"))

    expected: dict[str, list[tuple[str, str]]] = {
        "RunnerHandle": [("runner", "str"), ("socket", "str"), ("session_name", "str")],
        "ProcState": [
            ("alive", "bool"),
            ("pid", "int | None"),
            ("exit_code", "int | None"),
            # `#{pane_dead_signal}` was EMPTY even after SIGTERM
            # (`14-list-sessions-after-sigterm.txt`), so this stays `None` on
            # this evidence rather than being invented.
            ("exit_signal", "int | None"),
            ("observed_at", "str"),
        ],
        "PaneFields": [
            ("alternate_on", "bool"),
            ("pane_dead", "bool"),
            ("pane_dead_status", "int | None"),
            ("pane_title", "str | None"),
            ("width", "int"),
            ("height", "int"),
            ("pane_pid", "int | None"),
        ],
        "PaneState": [
            ("kind", "PaneKind"),
            ("fields", "PaneFields"),
            # Draft text only — ghost text is a separate field by construction
            # (E-M3-5), so no caller can mistake a placeholder for input.
            ("input_text", "str"),
            ("ghost_text", "str | None"),
            ("dialog_text", "str | None"),
        ],
        "SessionSpec": [
            ("session_id", "str"),
            ("engine_session_id", "str"),
            ("cwd", "str"),
            ("brief", "str | None"),
            ("title", "str | None"),
            ("model", "str | None"),
            ("effort", "str | None"),
            ("engine", "str"),
            ("runner", "str"),
            ("env", "Mapping[str, str]"),
        ],
        "EngineCapabilities": [
            ("can_spawn", "bool"),
            ("can_steer", "bool"),
            ("can_fork", "bool"),
            ("can_set_title", "bool"),
            ("has_hooks", "bool"),
            ("effort_ladder", "tuple[str, ...]"),
            ("transcript_format", 'Literal["jsonl", "sqlite", "none"]'),
        ],
        "TerminalFrame": [
            ("kind", 'Literal["snapshot", "live", "closed"]'),
            ("data", "bytes"),
            # A `closed` frame always carries a reason (E-M3-29).
            ("reason", "str | None"),
        ],
    }
    for name, fields in expected.items():
        declared = getattr(mod, name)
        assert dataclasses.is_dataclass(declared), name
        assert declared.__dataclass_params__.frozen is True, name
        actual = [(f.name, normalised(f.type)) for f in dataclasses.fields(declared)]
        assert actual == [(n, normalised(t)) for n, t in fields], name

    # The dataclasses in the module are exactly these — a new one added without
    # a row here is not silently unpinned.
    in_module = {
        name
        for name, value in vars(mod).items()
        if isinstance(value, type) and dataclasses.is_dataclass(value)
    }
    assert in_module == set(expected)


def test_runner_refusal_is_an_exception_carrying_a_reason() -> None:
    from shepherd.core.runner import RunnerRefusal

    assert issubclass(RunnerRefusal, Exception)
    error = RunnerRefusal("no live terminal")
    assert error.reason == "no live terminal"
    assert str(error) == "no live terminal"


def test_caps_match_the_spec_numbers() -> None:
    """Each constant is compared to the **document that states it**, not to a
    number typed twice. A drift in either place is then a failure, which is the
    whole point of pinning a measured value.
    """
    import re
    from pathlib import Path

    from shepherd.core import runner as mod

    repo = Path(__file__).resolve().parents[1]
    platform_spec = (repo / "docs" / "specs" / "orchestrator-platform.md").read_text(
        encoding="utf-8"
    )
    schemas = (repo / "docs" / "specs" / "data-schemas.md").read_text(encoding="utf-8")

    def spec_int(text: str, pattern: str) -> int:
        found = re.findall(pattern, text)
        assert len(set(found)) == 1, (pattern, found)
        return int(found[0])

    # §11's recursion caps, read out of §11.
    assert mod.MAX_SESSION_DEPTH == spec_int(platform_spec, r"max_session_depth\s+=\s+(\d+)")
    assert mod.MAX_CHILDREN_PER_SESSION == spec_int(
        platform_spec, r"max_children_per_session\s+=\s+(\d+)"
    )
    assert mod.MAX_TOTAL_OWNED_SESSIONS == spec_int(
        platform_spec, r"max_total_owned_sessions\s+=\s+(\d+)"
    )
    # §8's own number for the spawn timeout.
    assert mod.SPAWN_TIMEOUT_S == float(
        spec_int(platform_spec, r"`SPAWN_TIMEOUT_S` \((\d+)\)")
    )
    # The MEASURED largest accepted argv word, not a round number — and the
    # capture's next byte is the one that failed.
    assert mod.TMUX_COMMAND_LIMIT_B == spec_int(
        schemas, r"largest accepted single argv word \(bytes\): (\d+)"
    )
    assert mod.TMUX_COMMAND_LIMIT_B + 1 == spec_int(schemas, r"smallest rejected: (\d+)")

    # The poll interval has no spec line; it is the plan's number and is pinned
    # here as one, with the invariant that matters stated beside it.
    assert mod.SPAWN_POLL_INTERVAL_S == 0.25
    assert mod.SPAWN_POLL_INTERVAL_S < mod.SPAWN_TIMEOUT_S


def _string_literals(source: str) -> list[str]:
    """Every string constant in the source, docstrings included — they are what
    a reader learns the vocabulary from, so a leak there is still a leak."""
    import ast

    return [
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


#: The pane driver's own words. They live in `runner/` (L2); a literal one layer
#: down would make `core/` speak a particular multiplexer.
RUNNER_WORDS = ("tmux", "send-keys", "capture-pane", "-L")


def _runner_word_hits(source: str) -> list[str]:
    """Flag-shaped words match **case-sensitively** — a socket flag is always
    written `-L`, and matching it case-insensitively would fire on the `-l` in
    an ordinary hyphenated word like "handle-less"."""
    hits: list[str] = []
    for literal in _string_literals(source):
        for word in RUNNER_WORDS:
            found = word in literal if word.startswith("-") else word.lower() in literal.lower()
            if found:
                hits.append(literal)
    return hits


def test_no_runner_word_appears_in_core() -> None:
    """One allowed occurrence, named: `AnomalyKind.TMUX_UNAVAILABLE`'s value.

    The plan mandates that member (`doctor` must be able to say *what* is
    unavailable), and it is the wire word a stored count is keyed by, so it
    cannot be spelled neutrally. It is allowed **by identity** — this asserts the
    exact file and the exact literal — rather than by an exemption rule that
    would also silence the next leak. ADR-1: an exemption is how boundaries die.
    """
    from pathlib import Path

    core_dir = Path(__file__).resolve().parents[1] / "src" / "shepherd" / "core"
    paths = sorted(core_dir.rglob("*.py"))
    assert paths, core_dir
    hits = {
        (path.name, literal)
        for path in paths
        for literal in _runner_word_hits(path.read_text(encoding="utf-8"))
    }
    assert hits == {("anomalies.py", "tmux_unavailable")}

    # …and that one literal really is the anomaly member's value, not a comment
    # someone parked in `anomalies.py`.
    from shepherd.core.anomalies import AnomalyKind

    assert AnomalyKind.TMUX_UNAVAILABLE.value == "tmux_unavailable"

    # self-check: the scan bites on each banned word, in a docstring and in a
    # value, and stays quiet on an identifier that merely contains one.
    assert _runner_word_hits('"""Starts a tmux server."""\n') != []
    assert _runner_word_hits('X = "send-keys"\n') != []
    assert _runner_word_hits('X = "capture-pane -p"\n') != []
    assert _runner_word_hits('X = ["-L", "shepherd"]\n') != []
    assert _runner_word_hits("TMUX_COMMAND_LIMIT_B = 16324\n") == []
    assert _runner_word_hits('X = "a handle-less row"\n') == []
    assert _runner_word_hits('"""A TMUX server."""\n') != []


def _anomaly_claims(source: str) -> tuple[set[str], set[str]]:
    """(member names read off `AnomalyKind`, bare strings handed to `bump_anomaly`).

    `Store.bump_anomaly(kind: str)` accepts **anything**, so a bare `str` kind
    fails nowhere: it is counted only after it first fires and `doctor` never
    shows it as `0`, which is the state principle 5 forbids. This is the only
    gate that can see it.
    """
    import ast

    members: set[str] = set()
    bare: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "AnomalyKind":
                members.add(node.attr)
        if isinstance(node, ast.Call):
            target = node.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name == "bump_anomaly" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    bare.add(first.value)
    return members, bare


def test_every_anomaly_claim_names_a_member() -> None:
    """Every anomaly the product counts resolves to an `AnomalyKind` member."""
    from pathlib import Path

    from shepherd.core.anomalies import AnomalyKind

    src = Path(__file__).resolve().parents[1] / "src" / "shepherd"
    names = {member.name for member in AnomalyKind}
    values = {member.value for member in AnomalyKind}

    seen_members: set[str] = set()
    for path in sorted(src.rglob("*.py")):
        members, bare = _anomaly_claims(path.read_text(encoding="utf-8"))
        unknown = sorted(m for m in members if m not in names)
        assert unknown == [], f"{path.name}: {unknown}"
        assert sorted(b for b in bare if b not in values) == [], path.name
        seen_members |= members

    # The scan is not vacuous: the shipped code really does name members.
    assert seen_members, "no AnomalyKind member is referenced anywhere in src/"

    # self-check: both forms bite.
    assert _anomaly_claims("AnomalyKind.NOT_A_MEMBER\n")[0] == {"NOT_A_MEMBER"}
    assert _anomaly_claims('store.bump_anomaly("orphaned_pane")\n')[1] == {"orphaned_pane"}
    assert _anomaly_claims("store.bump_anomaly(kind.value)\n") == (set(), set())
