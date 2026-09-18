"""Session state vocabulary and the fleet's sort order (§16).

M1 has three live states; the full seven-bucket palette lands in M2.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

#: §7.1's `title_source` ratchet, ranked `user` > `engine` > `brief` (D29).
#: It lives in `core/` rather than in `store/models.py` because both the fold's
#: delta and the store's row are typed by it, and `core/` is the only package
#: both may import (BLOCKER T7b-3).
TitleSource = Literal["user", "engine", "brief"]

#: The rank the ratchet compares. Total over `TitleSource`, so a lookup can
#: never fall off the end.
TITLE_SOURCE_RANK: dict[TitleSource, int] = {"user": 2, "engine": 1, "brief": 0}


class SessionState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    NEEDS_YOU = "needs_you"
    STOPPED = "stopped"


class Ownership(StrEnum):
    """§7 `session.ownership` (D1). `class` was the original name — a reserved word."""

    OWNED = "owned"
    ATTACHED = "attached"


class Origin(StrEnum):
    """§7 `session.origin`."""

    ORCHESTRATOR = "orchestrator"
    QUEUE_WORKER = "queue_worker"
    USER_UI = "user_ui"
    EXTERNAL = "external"
    ASK_FORK = "ask_fork"


#: §16: `needs_you` first, then `running`, then `stopped`. `starting` is live but
#: has produced nothing to act on yet, so it sorts between running and stopped.
#: Total over `SessionState`, so a sort key can never fall off the end.
FLEET_STATE_ORDER: tuple[SessionState, ...] = (
    SessionState.NEEDS_YOU,
    SessionState.RUNNING,
    SessionState.STARTING,
    SessionState.STOPPED,
)
