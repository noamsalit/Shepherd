"""Planted violation: production writing into the engine's own config directory.

P-M3-14/K3. The user's rule is absolute — Shepherd reads `~/.claude`, and Claude
Code owns every byte under it. A write here is how M1's `settings.json` incident
class starts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def install() -> None:
    target = config_dir() / "settings.json"
    target.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
