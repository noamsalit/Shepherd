"""The one source-file reader in the boundary package.

Its own module so that `_imports` (the rules' vocabulary) and `_taint` (the
value-following analysis the field-level rules need) can share it without an
import cycle, and so there is exactly one place that opens a file: a scan that
cannot raise on a missing path is a scan that never opened one (B1).
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def parsed(path: Path) -> ast.Module:
    """The module's AST. Reading is never conditional on the caller's package."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
