"""NEGATIVE FIXTURE for `test_engine_config_is_read_only.py`.

Four spellings of a write to `~/.claude.json` — the engine's config **file**,
which is a *sibling* of `~/.claude` and so matched none of the directory
literals the rule taints. The first is the one that was actually planted into
`trust_state` on 2026-09-17 and survived the whole 35-test boundary suite
(T10-R1/T10-R2); the others are the spellings the next editor would reach for.

Never imported, never executed: `scanned_files()` excludes `fixtures/`.
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_FILENAME = ".claude.json"
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


def config_file(engine_config_home: Path | None) -> Path:
    if engine_config_home is not None:
        return engine_config_home / CONFIG_FILENAME
    return Path.home() / CONFIG_FILENAME


def a_round_trip_through_the_resolver(home: Path | None) -> None:
    path = config_file(home)
    path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def a_literal_sibling_of_the_config_dir() -> None:
    (Path.home() / ".claude.json").write_text("{}", encoding="utf-8")


def the_filename_through_a_module_constant() -> None:
    target = Path.home() / CONFIG_FILENAME
    target.write_text("{}", encoding="utf-8")


def through_the_environment_variable() -> None:
    configured = os.environ.get(CONFIG_DIR_ENV)
    home = Path(configured) if configured else Path.home()
    with open(home / CONFIG_FILENAME, "w", encoding="utf-8") as handle:
        handle.write("{}")
