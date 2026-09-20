"""T10 — the trust pre-flight: has the workspace-trust dialog been accepted?

Split out of `spawn.py` at T10-R2 (the fifth time this repo has answered a
250-line collision with a split rather than a raised cap). Trust *reading* and
argv *building* are two jobs: this module reads one JSON file the engine owns
and **writes nothing anywhere** (K3).

`trusted is None` is an **unknown**, never a `False` (principle 5): a `-p`
session creates no `projects[]` entry at all, so "absent" means nobody has been
asked, not "refused". Every failure is an unknown *with a distinct `source`* —
and the sources are what make schema drift self-announcing. `data-schemas.md`
pins every shape to **2.1.270** and this host already runs **2.1.273**, so a
`projects` that is suddenly a list, or an entry that is suddenly a string, is
the live case and not a hypothesis. Each of those says so in its own words; a
shared "no projects object" would report drift as absence.

**`$CLAUDE_CONFIG_DIR/.claude.json` is inferred, not captured.** The probe cited
for the shape (`probe_claude_json.py:7`) hardcodes `expanduser('~/.claude.json')`
and never reads the variable; what the probes actually drove through
`CLAUDE_CONFIG_DIR` was user-scope **settings**, a different file. Under this
project's binding rule — no data shape asserted without a real captured example
— the redirect is therefore **unverified** and recorded as such in
`data-schemas.md` §Not verified. **The degrade if it is wrong:** a host that sets
`CLAUDE_CONFIG_DIR` would make `trust_state` answer `unknown` forever, because
the real file is still at `~/.claude.json` and this module would be looking
somewhere else. That is a counted unknown with a source naming the path it
looked at, which is the failure mode principle 5 exists to make visible.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CONFIG_DIR_ENV",
    "CONFIG_FILENAME",
    "PROJECTS_KEY",
    "TRUST_KEY",
    "TrustState",
    "config_file",
    "trust_state",
]

#: The engine's own config file. `$CLAUDE_CONFIG_DIR/.claude.json` when the
#: variable is set (**inferred** — see the module docstring), else
#: `~/.claude.json`, which is a **sibling** of `~/.claude`, not inside it.
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
CONFIG_FILENAME = ".claude.json"

PROJECTS_KEY = "projects"
TRUST_KEY = "hasTrustDialogAccepted"

#: Distinguishes "the key is absent" from "the key is there and holds `null`".
#: `dict.get(k)` collapses the two, and collapsing them is how a drifted schema
#: gets reported as an empty one.
_ABSENT: object = object()


@dataclass(frozen=True)
class TrustState:
    """`trusted is None` is an **unknown**, not a `False` (principle 5), and
    `source` always says where the answer came from — including when there is
    none, and *which* kind of none it is."""

    trusted: bool | None
    source: str


def config_file(engine_config_home: Path | None) -> Path | None:
    """Where the engine's config file is, or `None` when it cannot be named.

    `engine_config_home` is **required at the call site** (T10-R2): its old
    default was the user's real `~/.claude.json`, and the first caller to forget
    it was the test written beside it — which is how a planted mutation came to
    write the user's live 97 KB config (T10-R1). Passing `None` is now a
    decision somebody typed.

    A `$CLAUDE_CONFIG_DIR` that is **set and empty** is a misconfiguration, not
    an unset variable: falling back to the real home would silently read a file
    the operator told us not to. It names no file at all.
    """
    if engine_config_home is not None:
        return engine_config_home / CONFIG_FILENAME
    configured = os.environ.get(CONFIG_DIR_ENV)
    if configured is None:
        return Path.home() / CONFIG_FILENAME
    if configured == "":
        return None
    return Path(configured) / CONFIG_FILENAME


def _kind(value: object) -> str:
    """What a JSON value *is*, in the document's own vocabulary."""
    if value is None:
        return "null"
    return {
        bool: "a boolean",
        int: "a number",
        float: "a number",
        str: "a string",
        list: "an array",
        dict: "an object",
    }.get(type(value), type(value).__name__)


def trust_state(cwd: str, engine_config_home: Path | None) -> TrustState:
    """Has the workspace-trust dialog been accepted for `cwd`? Read-only.

    The key is the **raw absolute cwd**, not the project slug, looked up
    verbatim: a normalised lookup would answer for a directory the engine never
    recorded.

    Every exit is a `TrustState`; nothing escapes. `UnicodeDecodeError` is a
    `ValueError` and **not** an `OSError`, so it needs its own clause — the
    engine writes this file with `JSON.stringify`, which does not escape
    non-ASCII, so a torn tail (D25) lands mid-sequence and would otherwise
    escape out of a function whose whole contract is "every failure is an
    unknown with a source".
    """
    path = config_file(engine_config_home)
    if path is None:
        return TrustState(
            trusted=None,
            source=f"${CONFIG_DIR_ENV} is set and empty, so no config file can be named",
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return TrustState(trusted=None, source=f"absent: {path}")
    except UnicodeDecodeError as error:
        return TrustState(trusted=None, source=f"undecodable: {path}: {error}")
    except OSError as error:
        return TrustState(trusted=None, source=f"unreadable: {path}: {error}")

    try:
        document: object = json.loads(raw)
    except ValueError as error:
        return TrustState(trusted=None, source=f"malformed: {path}: {error}")

    if not isinstance(document, dict):
        return TrustState(
            trusted=None, source=f"the document is not an object but {_kind(document)}: {path}"
        )

    projects: object = document.get(PROJECTS_KEY, _ABSENT)
    if projects is _ABSENT:
        return TrustState(trusted=None, source=f"no {PROJECTS_KEY} key at all: {path}")
    if not isinstance(projects, dict):
        return TrustState(
            trusted=None,
            source=f"{PROJECTS_KEY} is not an object but {_kind(projects)}: {path}",
        )

    entry: object = projects.get(cwd, _ABSENT)
    if entry is _ABSENT:
        return TrustState(trusted=None, source=f"no entry for {cwd}: {path}")
    if not isinstance(entry, dict):
        return TrustState(
            trusted=None,
            source=f"the entry for {cwd} is not an object but {_kind(entry)}: {path}",
        )

    value: object = entry.get(TRUST_KEY, _ABSENT)
    if value is _ABSENT:
        return TrustState(trusted=None, source=f"no {TRUST_KEY} for {cwd}: {path}")
    if not isinstance(value, bool):
        return TrustState(
            trusted=None,
            source=f"{TRUST_KEY} for {cwd} is not a boolean but {_kind(value)}: {path}",
        )
    return TrustState(trusted=value, source=f"{PROJECTS_KEY}[{cwd}].{TRUST_KEY}: {path}")
