"""NEGATIVE CONTROL for `test_engine_config_is_read_only.py`.

The rule needs a fixture proving it stays **quiet**, not only one proving it
fires (M3 T2/T3: "a scan needs a negative control proving it stays quiet").
Every write below builds a `.claude.json` under a `tmp_path` — which is what
`tests/engines/test_trust_state.py` legitimately does on every case — and none
of them is the engine's file. Taint has to follow the *home*, not the filename.

Never imported, never executed: `scanned_files()` excludes `fixtures/`.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILENAME = ".claude.json"


def a_fixture_config_under_a_tmp_path(tmp_path: Path) -> Path:
    (tmp_path / ".claude.json").write_text(json.dumps({"projects": {}}), encoding="utf-8")
    return tmp_path


def the_same_through_a_module_constant(tmp_path: Path) -> None:
    home = tmp_path / "case-0"
    home.mkdir()
    (home / CONFIG_FILENAME).write_bytes(b"{}")


def reading_the_real_one_is_untouched() -> str:
    return (Path.home() / CONFIG_FILENAME).read_text(encoding="utf-8")


def listing_beside_the_real_one_is_untouched() -> list[str]:
    return sorted(child.name for child in Path.home().iterdir())
