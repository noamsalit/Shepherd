"""`python -m shepherd.daemons` — the control daemon.

The console entry points (`shepherd-controld`, `shepherd-sessiond`) are the
supported spelling; this exists so a source checkout with nothing installed can
still start the thing.
"""

from __future__ import annotations

from shepherd.daemons.controld import main

if __name__ == "__main__":  # pragma: no cover - the process entry point
    raise SystemExit(main())
