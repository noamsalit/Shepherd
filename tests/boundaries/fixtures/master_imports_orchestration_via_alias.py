"""Planted violation, frozen as a fixture: D19's breach behind an alias (P-M4-8).

`import shepherd.orchestration.wake as w` binds one letter, and every later use
reads `w.drain`. A rule matching the text `from shepherd.orchestration import` —
or reading the *bound name* rather than the module the alias came from — reports
this file clean. That is M3's K16 lesson: three tmux rules each fell to exactly
one line of indirection.

Inert. Nothing imports this module; the reference below sits inside a function
that is never invoked, and the module body performs no call at all.
"""

from __future__ import annotations

import shepherd.orchestration.wake as w


def drain_the_wake_set() -> object:
    return w.drain
