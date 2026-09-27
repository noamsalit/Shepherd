"""P11 REM-FIX 1: the digest that binds an answer to the dialog a human read.

**Pure.** Text in, a hex string out. It is its own module because it has two
callers on two sides of one wire, and they must agree byte for byte:
`toolsurface/tools_terminal.py::get_decision` stamps the digest on the card it
serves, and `dialogs.py::answer_permission` recomputes it over the pane it
re-reads before any key is sent. Two copies of one hash call would be two
places for that agreement to drift.

**Why a digest, when the gate already matches the option set.** The option set
is a *shape*: two permission dialogs asking about different commands have the
same three options at the same three positions, so a card left open on the
first one would answer the second. The digest is over the whole dialog text
the card was built from — the command included — so a pane asking anything
else is refused, never answered on the strength of an older read.
"""

from __future__ import annotations

import hashlib

__all__ = ["DIALOG_CHANGED", "digest_of"]

#: The refusal a stale card is given. It names the next move, not only the gap.
DIALOG_CHANGED = (
    "the dialog changed since it was shown — nothing was sent; read it again before answering"
)


def digest_of(dialog_text: str | None) -> str | None:
    """sha256 hex of the dialog text exactly as the pane gave it, as UTF-8.

    `None` when the pane shows no dialog: there is nothing to bind an answer
    to, and an empty string's digest would be a binding to nothing.
    """
    if not dialog_text:
        return None
    return hashlib.sha256(dialog_text.encode("utf-8")).hexdigest()
