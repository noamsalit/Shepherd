"""Hook frames and named-sessiond readiness, shared by every module that drives the hook lane.

* **The dispatch argv is the product's own.** `install_hooks` writes a sandbox
  settings file for *this* instance's sessiond socket (the H1 code path), the
  command is read back from the file, split at ` || `, and `shlex.split` —
  argv, no shell (test-plan H6/C6/D12 Given). The `|| true` half is L4's.
* **Frames are real captures** from
  `docs/probes/2026-09-14-schemas/hooks/live/*/events.jsonl` (read-only), with
  `session_id`, `cwd` and `transcript_path` substituted; a value with no live
  capture is a captured frame of the same event with that one field
  substituted (test-plan §6 "Hook frames"; G13).
* **Readiness of a named sessiond is exactly one probe frame**: a real-shape
  `SessionStart` naming the module's seeded target, delivered through the
  dispatch argv, observed as the target row's `last_event_at` changing (the
  column the hook lane folds). Every `delivered=` oracle subtracts it
  (env-plan §1 "sessiond instances"). Its latency is the positive control for
  later FAIL(bound) waits on the same channel.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.engines.claude_code.hooks_config import install_hooks
from shepherd.host.mac import MacHost

from . import paths
from .instance import Controld, SessiondManager, SessiondRun
from .sessions import session_row
from .verdict import Blocked, await_env

#: A captured transcript whose last assistant message ends `end_turn`
#: (docs/probes, read-only; copied, never edited).
COMPLETED_TRANSCRIPT = (
    paths.PROBES / "2026-09-17-m4-sdk" / "p4-plugins-20260917T214517Z" / "setting-sources-empty"
    / "transcript-332441dc-ff6f-42d7-8c54-cf7e30d73f3b.jsonl"
)
SEND_TIMEOUT_S = 10.0
PROBE_BOUND_S = 5.0


def captured(directory: str, event: str, index: int = 0) -> dict[str, object]:
    """The `index`-th `payload` of `event` in a live capture directory."""
    found: list[dict[str, object]] = []
    for line in (paths.HOOKS_LIVE / directory / "events.jsonl").read_text(encoding="utf-8").splitlines():
        record: object = json.loads(line)
        if isinstance(record, dict) and record.get("_event") == event and isinstance(record.get("payload"), dict):
            found.append({str(k): v for k, v in record["payload"].items()})
    if len(found) <= index:
        raise Blocked(f"capture {directory} has no {event} #{index}")
    return found[index]


def frame(payload: Mapping[str, object], *, session_id: str, cwd: str, transcript_path: str | None = None,
          **overrides: object) -> dict[str, object]:
    body = dict(payload)
    body["session_id"] = session_id
    body["cwd"] = cwd
    if transcript_path is not None:
        body["transcript_path"] = transcript_path
    body.update(overrides)
    return body


def copy_transcript(cfg: Path, engine_session_id: str, slug: str = "-qa6-hooks") -> Path:
    """Copy the captured completed transcript to `<cfg>/projects/<slug>/<id>.jsonl`."""
    target = cfg / "projects" / slug / f"{engine_session_id}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(COMPLETED_TRANSCRIPT, target)
    return target


def dispatch_argv(controld: Controld) -> tuple[list[str], Path]:
    """Install hooks for this instance's sessiond socket; return the argv and the file."""
    root = controld.root
    host = MacHost(environ={"HOME": str(root.home), "TMPDIR": str(root.tmpdir)})
    plan = host.control_socket("sessiond")
    entry = build_hook_entry(plan, host.hook_dispatch(plan))
    settings = root.root / "hooks" / "settings.json"
    settings.parent.mkdir(exist_ok=True)
    result = install_hooks(settings, entry)
    if result.refused_reason is not None:
        raise Blocked(f"the product refused to install hooks into the sandbox file: {result.refused_reason}")
    decoded: object = json.loads(settings.read_text(encoding="utf-8"))
    hooks = decoded.get("hooks") if isinstance(decoded, dict) else None
    groups = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    command: object = None
    if isinstance(groups, list) and groups and isinstance(groups[0], dict):
        inner = groups[0].get("hooks")
        if isinstance(inner, list) and inner and isinstance(inner[0], dict):
            command = inner[0].get("command")
    if not isinstance(command, str):
        raise Blocked(f"no SessionStart dispatch command in {settings}")
    return shlex.split(command.split(" || ")[0]), settings


@dataclass(frozen=True)
class Sent:
    rc: int | None
    elapsed_s: float
    stderr: bytes
    signalled: int | None


def send(argv: list[str], env: Mapping[str, str], payload: Mapping[str, object] | bytes,
         timeout_s: float = SEND_TIMEOUT_S) -> Sent:
    """Run the dispatch argv with the payload on stdin (no shell)."""
    data = payload if isinstance(payload, bytes) else json.dumps(dict(payload)).encode("utf-8")
    started = time.monotonic()
    try:
        done = subprocess.run(argv, input=data, env=dict(env), capture_output=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return Sent(rc=None, elapsed_s=time.monotonic() - started, stderr=b"(timed out)", signalled=None)
    elapsed = time.monotonic() - started
    signalled = -done.returncode if done.returncode < 0 else None
    return Sent(rc=done.returncode, elapsed_s=elapsed, stderr=done.stderr, signalled=signalled)


def last_event_at(controld: Controld, engine_session_id: str) -> object:
    row = session_row(controld, engine_session_id)
    return row.get("last_event_at") if row else None


def start_ready_sessiond(
    manager: SessiondManager,
    name: str,
    *,
    argv: list[str],
    target_engine_id: str,
    target_cwd: str,
    schema: int = 4,
) -> tuple[SessiondRun, float]:
    """Start a named sessiond and prove it relays with exactly one probe frame."""
    run = manager.start(name, schema=schema)
    manager.wait_socket(run)
    before = last_event_at(manager.controld, target_engine_id)
    probe = frame(captured("S01_startup_tools", "SessionStart"), session_id=target_engine_id, cwd=target_cwd)
    started = time.monotonic()
    sent = send(argv, manager.controld.env, probe)
    if sent.rc != 0:
        raise Blocked(f"{name}: the probe dispatch exited {sent.rc}: {sent.stderr[:200]!r}")
    await_env(lambda: last_event_at(manager.controld, target_engine_id) != before or None, PROBE_BOUND_S,
              f"{name}: the probe frame changed {target_engine_id}'s last_event_at")
    return run, max(time.monotonic() - started, 1e-3)
