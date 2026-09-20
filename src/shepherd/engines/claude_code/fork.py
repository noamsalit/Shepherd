"""T15 — the engine's `-p` fork surface: the argv out, and the result object back.

A **sibling** of `spawn.py`, not a section of it, for the reason this repo has
taken six times now: `spawn.py` is at its 250-line artifact cap and the fork argv
is a second job — `spawn.py` answers *how an owned session is started*, this
answers *how one question is asked of a session already running*. The plan's
Files/Surfaces names `spawn.py`; the cap is doing its job and the split is the
answer the router has given at `db.py`, `rows.py`, `stops.py`, `reads.py`,
`writes.py` and `admission.py`.

**The result object lives here, not in `orchestration/ask.py` where the plan's
`Produces` put it.** §5.0: the engine's own spelling stays in its adapter, and
`result` / `session_id` / `is_error` / `subtype` are Claude Code's field names,
not Shepherd's. Keeping them here also keeps `ask()` under the artifact cap the
plan set, which is what forced the question — the split answers both.

Pure: no clock, no path, no process, and no `--settings` of ours.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from shepherd.core.runner import RunnerRefusal
from shepherd.engines.claude_code.spawn import SEPARATOR, SESSION_ID_FLAG

__all__ = [
    "FORK_RULES",
    "FORK_SESSION_FLAG",
    "JSON_OUTPUT",
    "NO_PERSISTENCE_FLAG",
    "OUTPUT_FORMAT_FLAG",
    "PRINT_FLAG",
    "RESUME_FLAG",
    "ForkResult",
    "ForkRule",
    "fork_argv",
    "parse_fork_result",
]


@dataclass(frozen=True)
class ForkRule:
    """One field of the `-p` result object, and where a real example of it is.

    `evidence` is `<data-schemas.md section> · <what backs it>`, the shape
    `SpawnRule` uses, and `test_every_ask_rule_cites_an_existing_section` asserts
    the section really is in the document and the capture really is on disk (K1:
    no data shape asserted without a real captured example).
    """

    name: str
    evidence: str


_FORK_SECTION = "Fork (`--resume <id> --fork-session`) — the basis of `ask()`"
_P2 = "2026-09-17-m3-tmux/p2-fork-20260917T110431Z"

FORK_RULES: tuple[ForkRule, ...] = (
    ForkRule(
        name="result",
        evidence=(
            f"{_FORK_SECTION} · the assistant's final text, PINEAPPLE-M3, the codeword "
            f"given only to the base session: {_P2}/02-fork-with-session-id.stdout.json"
        ),
    ),
    ForkRule(
        name="session_id",
        evidence=(
            f"{_FORK_SECTION} · the fork's own id, equal to the requested uuid when "
            f"--session-id is passed: {_P2}/02-fork-with-session-id.argv.txt, "
            f"{_P2}/results.json"
        ),
    ),
    ForkRule(
        name="is_error",
        evidence=(
            f"{_FORK_SECTION} · false on all four captured runs: "
            f"{_P2}/05-result-object-shape.json"
        ),
    ),
    ForkRule(
        name="subtype",
        evidence=(
            f"{_FORK_SECTION} · success on all four captured runs: "
            f"{_P2}/03-fork-nsp-with-session-id.stdout.json"
        ),
    ),
)


@dataclass(frozen=True)
class ForkResult:
    """The four fields of the `-p --output-format json` result object this reads.

    Every one has a row in `ASK_RULES` and a real example in `data-schemas.md`
    §Fork's field table, which P2 appended (A25, K1).
    """

    result: str | None
    session_id: str
    is_error: bool
    subtype: str


def parse_fork_result(stdout: bytes) -> ForkResult | None:
    """The result object, or `None`. **Never raises.**

    A `-p` run that printed something unreadable is an *unknown answer*, not a
    crash of the asker: the caller is told `text=None` with a refusal, and the
    row still gets a verdict. `session_id` is the one required field — without it
    nothing can be bound and no residue can be looked for.
    """
    try:
        document: object = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    session_id: object = document.get("session_id")
    if not isinstance(session_id, str):
        return None
    result: object = document.get("result")
    return ForkResult(
        result=result if isinstance(result, str) else None,
        session_id=session_id,
        is_error=document.get("is_error") is True,
        subtype=str(document.get("subtype", "")),
    )

PRINT_FLAG = "-p"
OUTPUT_FORMAT_FLAG = "--output-format"
JSON_OUTPUT = "json"
RESUME_FLAG = "--resume"
FORK_SESSION_FLAG = "--fork-session"
NO_PERSISTENCE_FLAG = "--no-session-persistence"


def fork_argv(
    *, binary: str, engine_session_id: str, question: str, fork_session_id: str | None
) -> list[str]:
    """The argv `ask()` forks the target with. Pure: no clock, no path, no process.

    **Every word is P2's, in P2's order** — the probe's own argv capture is
    `docs/probes/2026-09-17-m3-tmux/p2-fork-20260917T110431Z/03-fork-nsp-with-session-id.argv.txt`,
    and `tests/orchestration/test_ask.py` parses the flags out of that file rather
    than retyping them. Two words the probe passed are deliberately absent:
    `--model`, which the probe pinned to haiku for cost, and `--settings`, which
    production never passes (§16 spawns no queue workers at M3).

    `--session-id` is optional because P2 ran a control without it and the engine
    then generated the id; it is passed in production because P2 proved it is
    **accepted and returned verbatim**, which makes the fork's transcript name
    predictable and therefore sweepable for residue.

    `--no-session-persistence` is what makes the normal path leave nothing behind
    (BLOCKER-T1-2). It is not an optimisation and it has no flag of its own here:
    a fork without it leaves `<newId>.jsonl` in the target's project dir, which
    Shepherd may not delete.

    **A question that could be read as a flag is refused, never repaired.** The
    spawn argv has a captured `--` separator (A11); this argv does **not** —
    nothing in P2 or the 2026-09-14 runs put one here — so K1 forbids inventing
    one, and a leading `-` is a refusal with the reason named.
    """
    if question.startswith("-"):
        raise RunnerRefusal(
            f"a fork question may not begin with '-' ({question[:24]!r}): the engine would "
            f"read it as a flag, and unlike the spawn argv this one has no captured "
            f"{SEPARATOR!r} separator to put it behind — rephrase it rather than have "
            f"Shepherd guess a separator no probe has seen"
        )
    argv = [
        binary,
        PRINT_FLAG,
        OUTPUT_FORMAT_FLAG,
        JSON_OUTPUT,
        RESUME_FLAG,
        engine_session_id,
        FORK_SESSION_FLAG,
    ]
    if fork_session_id is not None:
        argv += [SESSION_ID_FLAG, fork_session_id]
    return [*argv, NO_PERSISTENCE_FLAG, question]
