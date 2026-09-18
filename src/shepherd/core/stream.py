"""`StreamEvent` — L1 so `signals/` can return one and `toolsurface/` can ring it
without either importing the other (ADR-4, F5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    session_id: str | None
    payload: Mapping[str, object]
    occurred_at: str
