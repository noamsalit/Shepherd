"""The neutral field readers — one literal key each, and nothing else (K12).

Ten functions with one rule between them: **each reads exactly one literal key
out of `Signal.fields`, spelled inline at the call to `.get`.** There is
deliberately no `_field(signal, key)` helper. A computed key is a key no test
can check and no scan can read, so `tests/boundaries/test_engine_vocabulary.py`
fails closed on one — even when the "computation" is a module constant.

They lived in `signals/rules.py` until this task, and they moved for the reason
that module's own header gives for the cap: `rules.py` reached ADR-1's 600-line
limit exactly, and T10-2's disposition adds a cell to Table B's `TURN_STOPPED`
row. The cap is a proxy for "this file is doing too much", so the answer was to
move a coherent unit out rather than to raise the number. These ten are that
unit: one rule, one shape, one reason to change — a new neutral key in
`SIGNAL_FIELD_KEYS` — and none of Table B's rows had to be touched to move them.

**Reading is all they do.** Nothing here interprets a value: `read_refusal`
returns the neutral word, and the map from that word to an `AnomalyKind` stays
beside the rule that counts it. The engine's own vocabulary is never spelled in
this package (§5.0) — `SIGNAL_FIELD_KEYS` is the closed set these keys come
from, and the adapter is what projects an engine field onto one of them.
"""

from __future__ import annotations

from shepherd.core.signals import Signal

__all__ = [
    "read_ask",
    "read_changed_paths",
    "read_failure_note",
    "read_model",
    "read_next_cwd",
    "read_prompt",
    "read_refusal",
    "read_start_source",
    "read_subagent_id",
    "read_task_id",
]


def read_ask(signal: Signal) -> str | None:
    value = signal.fields.get("ask")
    return value if isinstance(value, str) and value else None


def read_prompt(signal: Signal) -> str | None:
    value = signal.fields.get("prompt")
    return value if isinstance(value, str) and value else None


def read_next_cwd(signal: Signal) -> str | None:
    value = signal.fields.get("next_cwd")
    return value if isinstance(value, str) and value else None


def read_model(signal: Signal) -> str | None:
    value = signal.fields.get("model")
    return value if isinstance(value, str) and value else None


def read_subagent_id(signal: Signal) -> str | None:
    value = signal.fields.get("subagent_id")
    return value if isinstance(value, str) and value else None


def read_task_id(signal: Signal) -> str | None:
    value = signal.fields.get("task_id")
    return value if isinstance(value, str) and value else None


def read_refusal(signal: Signal) -> str | None:
    value = signal.fields.get("refusal")
    return value if isinstance(value, str) and value else None


def read_failure_note(signal: Signal) -> str | None:
    value = signal.fields.get("failure_note")
    return value if isinstance(value, str) and value else None


def read_changed_paths(signal: Signal) -> tuple[str, ...]:
    value = signal.fields.get("changed_paths")
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def read_start_source(signal: Signal) -> str | None:
    value = signal.fields.get("start_source")
    return value if isinstance(value, str) and value else None
