"""`Frame` — L1: the ingest listener produces it and the relay consumes it, so a
shared L1 type keeps T10 and T10b independent rather than circular."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    payload: bytes
    received_at: str
    peer_pid: int | None
