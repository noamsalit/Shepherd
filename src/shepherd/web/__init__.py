"""`web/` — the loopback HTTP+SSE surface (L5).

The static assets are shipped as package data (`pyproject.toml`'s
`[tool.setuptools.package-data]`), so the one function here answers "where are
they" in the way that works from a source tree *and* from an installed wheel:
beside this module, whatever that turns out to be.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIRNAME = "static"


def static_root() -> Path:
    """The directory `index.html` and the modules are served from."""
    return Path(__file__).resolve().parent / STATIC_DIRNAME
