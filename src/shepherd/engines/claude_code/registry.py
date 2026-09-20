"""The live-session registry — discovery that needs no hooks (Decision pressure 5).

Claude Code writes one sidecar per **trusted, running** session at
`<config_dir>/sessions/<pid>.json` and deletes it on exit (data-schemas
§"Live-session registry `~/.claude/sessions/<pid>.json`"). That file is the only
discovery source that works on a machine where no hook is installed, which is
the machine M1 exists to serve.

Three rules this module exists to hold:

* **`entrypoint` is the discriminator, never `kind`.** `kind` is `"interactive"`
  for a `-p` run too (`docs/probes/2026-09-16-registry-and-version-drift.md`
  Finding 1), so code that branches on it flickers every `-p` run through the
  fleet page.
* **The sibling `<pid>.<64hex>.key` file is never opened** — it holds a peer
  token (E32). The glob is `*.json`, which cannot reach it.
* **Absence is "not running or not trusted", never "finished"** (E29). Nothing
  here infers a stop; liveness is `(pid, procStart)` through `HostPlatform`.

Impure/pure split: `parse_sidecar` is pure and carries every shape assertion;
`scan_registry` and `agents_json_fallback` are the thin adapters that do I/O.
Every subprocess call is an argv list — never `shell=True` (§13).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind

#: `<config_dir>/sessions/` — the directory the engine writes sidecars into.
SESSIONS_DIRNAME = "sessions"

#: Where **the engine** keeps its state. This is deliberately not
#: `HostDirs.config_dir`, which is *Shepherd's* own (`~/.config/shepherd`,
#: ADR-2): a live proof against this host scanned Shepherd's directory, found no
#: sessions, and fell through to the `claude agents --json` fallback — on the one
#: machine the hookless path exists to serve.
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
DEFAULT_CONFIG_DIRNAME = ".claude"

#: `*.json` never matches the `<pid>.<64hex>.key` sibling (E32, P15).
SIDECAR_GLOB = "*.json"

#: `entrypoint` values. `cli` is an attached interactive session; `sdk-cli` is a
#: `-p` run, which this path skips and counts (RD9). Both carry
#: `kind: "interactive"`, which is why `kind` is read and never branched on.
CLI_ENTRYPOINT = "cli"
SDK_CLI_ENTRYPOINT = "sdk-cli"

#: `nameSource` values, ranked by D29's title ratchet (`user > engine > brief`).
USER_NAME_SOURCE = "user"
DERIVED_NAME_SOURCE = "derived"

#: The one-shot fallback. It forks a `claude` process per call and lacks
#: `procStart`, `entrypoint`, `tmux` and `nameSource`, so it is strictly weaker
#: than the sidecar and is never put on a timer (E33, G11).
AGENTS_ARGV: tuple[str, ...] = ("claude", "agents", "--json")
AGENTS_TIMEOUT_S = 5.0

#: What the fallback cannot tell us. An entry carrying it is never registered.
UNKNOWN_FIELD = ""

#: The two `needs_you` reasons this source can produce, composed **here** rather
#: than in `signals/`: engine-sourced text belongs to the engine adapter (r4),
#: and `tests/signals/test_normalise.py` holds that rule mechanically. The idle
#: wording is §8's `idle_prompt` row restated for a human; the blocked wording is
#: the fallback used only when a `waiting` sidecar carries no `waitingFor`.
IDLE_REASON = "idle — waiting for your next instruction"
BLOCKED_REASON = "waiting for you"


@dataclass(frozen=True)
class RegistryEntry:
    """One sidecar, parsed. Field names follow data-schemas' table exactly.

    `status` and `name_source` are `str`, **not** `Literal`: the values listed in
    the schema are *observed*, not closed, and the shapes were verified at engine
    2.1.270 while this host runs 2.1.273 (G12). A `Literal` is a typecheck, not a
    runtime guard — it could not even *construct* the unrecognised-status entry
    the mapping site is required to keep the prior state for (r5).
    """

    session_id: str
    pid: int
    proc_start: str
    cwd: str
    kind: str
    entrypoint: str
    status: str
    waiting_for: str | None
    name: str | None
    name_source: str | None
    started_at_ms: int
    updated_at_ms: int
    status_updated_at_ms: int
    version: str
    tmux: str | None
    pid_domain: str | None


@dataclass(frozen=True)
class SidecarProblem:
    """A sidecar that could not be read as one. Counted, never raised (D25)."""

    reason: str


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_sidecar(raw: str) -> RegistryEntry | SidecarProblem:
    """Pure: one sidecar's JSON text → an entry, or the reason it is not one.

    A daemon killed mid-write leaves a truncated trailing file, so a parse
    failure is a value here rather than an exception (D25, principle 5).
    """
    try:
        decoded: object = json.loads(raw)
    except ValueError as error:
        return SidecarProblem(reason=f"unparsable json: {error}")
    if not isinstance(decoded, dict):
        return SidecarProblem(reason=f"expected an object, got {type(decoded).__name__}")

    fields: dict[str, object] = {str(key): value for key, value in decoded.items()}
    session_id = _text(fields.get("sessionId"))
    pid = _whole(fields.get("pid"))
    proc_start = _text(fields.get("procStart"))
    cwd = _text(fields.get("cwd"))
    started_at_ms = _whole(fields.get("startedAt"))
    if session_id is None or pid is None or cwd is None or started_at_ms is None:
        return SidecarProblem(reason="missing one of sessionId, pid, cwd, startedAt")

    status_updated = _whole(fields.get("statusUpdatedAt"))
    updated = _whole(fields.get("updatedAt"))
    return RegistryEntry(
        session_id=session_id,
        pid=pid,
        # `procStart` is the pid-reuse guard; without it the entry is still
        # readable, but nothing may claim the pid is the same process.
        proc_start=proc_start if proc_start is not None else UNKNOWN_FIELD,
        cwd=cwd,
        kind=_text(fields.get("kind")) or UNKNOWN_FIELD,
        entrypoint=_text(fields.get("entrypoint")) or UNKNOWN_FIELD,
        status=_text(fields.get("status")) or UNKNOWN_FIELD,
        waiting_for=_text(fields.get("waitingFor")),
        name=_text(fields.get("name")),
        name_source=_text(fields.get("nameSource")),
        started_at_ms=started_at_ms,
        updated_at_ms=updated if updated is not None else started_at_ms,
        status_updated_at_ms=(
            status_updated
            if status_updated is not None
            else (updated if updated is not None else started_at_ms)
        ),
        version=_text(fields.get("version")) or UNKNOWN_FIELD,
        tmux=_text(fields.get("tmux")),
        pid_domain=_text(fields.get("pidDomain")),
    )


def claude_config_dir() -> Path:
    """`$CLAUDE_CONFIG_DIR`, or `~/.claude`. Read-only: nothing here ever writes."""
    configured = os.environ.get(CONFIG_DIR_ENV)
    return Path(configured) if configured else Path.home() / DEFAULT_CONFIG_DIRNAME


def is_attached_interactive(entry: RegistryEntry) -> bool:
    """`entrypoint == "cli"`. NEVER reads `.kind` — it is `interactive` for `-p` too."""
    return entry.entrypoint == CLI_ENTRYPOINT


def scan_registry(config_dir: Path) -> tuple[list[RegistryEntry], tuple[Anomaly, ...]]:
    """Every readable sidecar under `<config_dir>/sessions/`. Read-only, no clock.

    The directory is missing on a host where no session has ever accepted the
    trust dialog. That is the one place the `claude agents --json` fallback is
    consulted — once, never on a timer (E33, G11).
    """
    directory = config_dir / SESSIONS_DIRNAME
    if not directory.is_dir():
        return agents_json_fallback()

    entries: list[RegistryEntry] = []
    anomalies: list[Anomaly] = []
    for path in sorted(directory.glob(SIDECAR_GLOB)):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as error:
            anomalies.append(_malformed(f"{path.name}: unreadable: {error}"))
            continue
        parsed = parse_sidecar(raw)
        if isinstance(parsed, SidecarProblem):
            anomalies.append(_malformed(f"{path.name}: {parsed.reason}"))
            continue
        entries.append(parsed)
    return entries, tuple(anomalies)


def agents_json_fallback(
    timeout_s: float = AGENTS_TIMEOUT_S,
) -> tuple[list[RegistryEntry], tuple[Anomaly, ...]]:
    """One shot of `claude agents --json`. Never scheduled, never on a timer.

    It is a projection of the same sidecars and lacks `procStart`, `entrypoint`,
    `tmux` and `nameSource`, so its entries carry `UNKNOWN_FIELD` for the
    discriminator and the pid-reuse guard — which means `is_attached_interactive`
    refuses them and the discovery pass counts them rather than registering a
    session it cannot check liveness for. See BLOCKER T7b-2.
    """
    try:
        completed = subprocess.run(
            list(AGENTS_ARGV),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return [], (_malformed(f"agents fallback failed: {error}"),)
    if completed.returncode != 0:
        return [], (_malformed(f"agents fallback exited {completed.returncode}"),)

    try:
        decoded: object = json.loads(completed.stdout)
    except ValueError as error:
        return [], (_malformed(f"agents fallback returned no json: {error}"),)
    if not isinstance(decoded, list):
        return [], (_malformed("agents fallback returned a non-list"),)

    entries: list[RegistryEntry] = []
    anomalies: list[Anomaly] = []
    for item in decoded:
        if not isinstance(item, dict):
            anomalies.append(_malformed("agents fallback entry is not an object"))
            continue
        parsed = parse_sidecar(json.dumps(item))
        if isinstance(parsed, SidecarProblem):
            anomalies.append(_malformed(f"agents fallback entry: {parsed.reason}"))
            continue
        entries.append(parsed)
    return entries, tuple(anomalies)


def _malformed(detail: str) -> Anomaly:
    return Anomaly(
        kind=AnomalyKind.MALFORMED_PAYLOAD, detail=detail, engine_session_id=None
    )
