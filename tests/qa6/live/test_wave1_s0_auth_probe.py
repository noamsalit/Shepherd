"""S0 — the environment-truth probe that binds `LIVE_AUTH_MODE` (test-plan §4 S0; C-10).

Does real `claude` (the CLI) and the SDK master authenticate under a sandboxed
`CLAUDE_CONFIG_DIR` + `HOME` on this Mac? Four sub-probes:

* (a) CLI, sandboxed — always runs;
* (b) CLI, real HOME — runs if (a) is not `ok`, or under the completion rule;
* (c) SDK master, sandboxed SUB instance — always runs;
* (d) SDK master, real HOME, through the launcher — runs if (c) is not `ok`, or
  under the completion rule.

Each ends `ok | auth_missing | error | skipped`; a timeout or network error is
retried once. The 3x3 table binds exactly one value (total over the pairs).
After **each** sub-probe the real settings sha is re-read (U2): a change is
S0's FAIL and the runner stops the run. U1 pre-authorises real `claude`.

Writes `<run_dir>/live_auth_mode.json` and puts `LIVE_AUTH_MODE=<v>` first in
the evidence, which the runner's wave-8 stop-if reads.

The engine is the run's `<run0>/bin/claude` (realclaude.py: `QA6_REAL_CLAUDE`
→ `which claude` → the newest `~/.local/share/claude/versions/*`; INC-1), never
the user's `~/.local/bin/claude`. Both probe envs come from `probe_envs`: the
real-HOME one carries no `XDG_*` and `DISABLE_AUTOUPDATER=1` (SI-1), which
`test_harness_guards.py::test_proof_host_safe_envs` checks.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field

from pathlib import Path

from .. import hostprobe, paths, realclaude
from ..httpclient import Client, as_dict
from ..instance import Controld, app_state, seed_db, start_launcher
from ..pool import InstancePool
from ..sandbox import InstanceRoot, RunContext, checked_env, mint_instance, real_home_env, sandbox_env
from ..scenario import live_scenario
from ..sse_rig import Frame, Subscriber, subscribe
from ..verdict import Blocked, Recorder

PROMPT = "Reply with exactly: QA6-PONG"
MARKER = "QA6-PONG"
CLI_TIMEOUT_S = 120.0
MASTER_BOUND_S = 180.0
AUTH_WORDS = ("not logged in", "/login", "log in", "login", "authenticat", "unauthor", "api key", "oauth")


@dataclass
class Probe:
    name: str
    result: str = "skipped"
    detail: dict[str, object] = field(default_factory=dict)


def classify_cli(rc: int, stdout: str, stderr: str) -> str:
    text = f"{stdout}\n{stderr}"
    if rc == 0 and MARKER in stdout:
        return "ok"
    if "Not logged in" in text or "/login" in text:
        return "auth_missing"
    return "error"


def probe_envs(run: RunContext, root: InstanceRoot) -> tuple[dict[str, str], dict[str, str]]:
    """(sandboxed, real-HOME) envs for the CLI probes (a) and (b)."""
    return sandbox_env(run, root, path_mode="bare"), real_home_env(run, root, path_mode="bare")


def cli_probe(name: str, engine: Path, env: dict[str, str], cwd: str, settings: str) -> Probe:
    argv = [str(engine), "-p", PROMPT, "--model", "haiku", "--settings", settings,
            "--no-session-persistence"]
    probe = Probe(name)
    for attempt in (1, 2):
        try:
            done = subprocess.run(argv, env=checked_env(env, f"S0 {name}"), cwd=cwd, capture_output=True, text=True,
                                  timeout=CLI_TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            probe.detail[f"attempt{attempt}"] = f"timeout after {CLI_TIMEOUT_S}s"
            probe.result = "error(network)"
            continue
        except OSError as error:
            raise Blocked(f"claude cannot be executed at all: {error}") from error
        probe.detail.update(rc=done.returncode, stdout=done.stdout[-1500:], stderr=done.stderr[-1500:],
                            argv=argv, attempts=attempt)
        probe.result = classify_cli(done.returncode, done.stdout, done.stderr)
        network = "ECONNREFUSED" in done.stderr or "ENOTFOUND" in done.stderr or "network" in done.stderr.lower()
        if probe.result == "error" and network and attempt == 1:
            continue
        return probe
    return probe


def turn_frames(sub: Subscriber, turn_id: str) -> list[Frame]:
    return [frame for frame in sub.snapshot() if frame.kind.startswith("master.") and frame.data.get("turn_id") == turn_id]


def master_probe(name: str, controld: Controld) -> Probe:
    probe = Probe(name)
    client = Client(controld.port, refusals_log=controld.run.port_refusals, allow_master_send=True)
    for attempt in (1, 2):
        sub = subscribe(f"S0{name}", controld.port)
        try:
            response = client.post("/api/master/send", {"text": PROMPT})
            probe.detail["send_status"] = response.status
            probe.detail["send_body"] = response.text[:600]
            data = as_dict(response.json().get("data")) if response.json().get("ok") is True else {}
            turn_id = data.get("turn_id")
            probe.detail["api_started"] = data.get("started")
            if not isinstance(turn_id, str):
                probe.result = "error"
                return probe
            deadline = time.monotonic() + MASTER_BOUND_S
            end: Frame | None = None
            while time.monotonic() < deadline and end is None:
                for frame in turn_frames(sub, turn_id):
                    if frame.kind in ("master.turn_ended", "master.error"):
                        end = frame
                        break
                time.sleep(0.25)
            frames = turn_frames(sub, turn_id)
            text = "".join(str(f.data.get("text") or "") for f in frames if f.kind == "master.text")
            probe.detail.update(kinds=[f.kind for f in frames], text=text[-800:], attempts=attempt,
                                end=(end.kind, str(end.data.get("text"))[:600]) if end else None)
            if end is None:
                probe.result = "error(network)"
                continue
            if end.kind == "master.turn_ended" and MARKER in text:
                session = app_state(controld.db, "master_session_id")
                probe.detail["master_session_id"] = session
                probe.result = "ok" if isinstance(session, str) and session else "error"
                return probe
            error_text = str(end.data.get("text") or "").lower()
            probe.result = "auth_missing" if end.kind == "master.error" and any(w in error_text for w in AUTH_WORDS) else "error"
            return probe
        finally:
            sub.close()
    return probe


def subject(first: Probe, second: Probe) -> str:
    if first.result == "ok":
        return "sandbox"
    if second.result == "ok":
        return "real_home"
    return "none"


def bind(cli: str, master: str, b: Probe, d: Probe) -> str:
    """The 3x3 table (test-plan S0), total: exactly one row matches."""
    if cli == "none" or master == "none":
        return "unavailable"
    if cli == "sandbox" and master == "sandbox":
        return "sandbox_ok"
    if cli == "real_home" and master == "real_home":
        return "needs_real_home"
    if cli == "sandbox" and master == "real_home":
        return "needs_real_home" if b.result == "ok" else "unavailable"
    return "needs_real_home" if d.result == "ok" else "unavailable"


class ShaWatch:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec

    def after(self, probe: str) -> None:
        sha = hostprobe.sha256(paths.REAL_SETTINGS)
        self.rec.equal(f"files.settings_sha.after_{probe}", paths.EXPECTED_SETTINGS_SHA, sha)


def real_claude_snapshot() -> dict[str, object]:
    return {"projects": hostprobe.listing(paths.REAL_CLAUDE_DIR / "projects"),
            "claude_json_mtime": hostprobe.mtime(paths.REAL_CLAUDE_JSON)}


def delta(before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
    was = before.get("projects")
    now = after.get("projects")
    was_map = was if isinstance(was, dict) else {}
    now_map = now if isinstance(now, dict) else {}
    return {
        "projects_added": sorted(set(now_map) - set(was_map)),
        "projects_changed": sorted(n for n in set(now_map) & set(was_map) if now_map[n] != was_map[n]),
        "claude_json_mtime_changed": before.get("claude_json_mtime") != after.get("claude_json_mtime"),
    }


@live_scenario("S0")
def test_s0_bind_live_auth_mode(qa6_run: RunContext, pool: InstancePool, rec: Recorder) -> None:
    engine = realclaude.require(qa6_run)
    resolution = realclaude.load(qa6_run)
    rec.record("given.real_claude", {**resolution.as_json(), "exposed_as": str(engine)})
    if resolution.inc1_fallback:
        rec.note(f"INC-1: the user's claude link is unusable; the engine is the fallback {resolution.path} ({resolution.why})")
    watch = ShaWatch(rec)
    watch.after("start")
    root = mint_instance(qa6_run)
    settings = root.root / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    sandbox, real = probe_envs(qa6_run, root)
    probes = {name: Probe(name) for name in "abcd"}
    deltas: dict[str, object] = {}

    def run_b() -> None:
        before = real_claude_snapshot()
        probes["b"] = cli_probe("b", engine, real, str(root.cwd), str(settings))
        deltas["b"] = delta(before, real_claude_snapshot())
        watch.after("b")

    def run_d() -> None:
        before = real_claude_snapshot()
        d_root = mint_instance(qa6_run)
        seed_db(d_root, runner_socket=qa6_run.runner_socket(d_root.k))
        launcher = start_launcher(qa6_run, d_root)
        pool.adopt(launcher)
        launcher.wait_ready()
        probes["d"] = master_probe("d", launcher)
        launcher.stop()
        deltas["d"] = delta(before, real_claude_snapshot())
        watch.after("d")

    probes["a"] = cli_probe("a", engine, sandbox, str(root.cwd), str(settings))
    watch.after("a")
    if probes["a"].result != "ok":
        run_b()
    c_instance = pool.ready(path_mode="live")
    probes["c"] = master_probe("c", c_instance)
    c_instance.stop()
    watch.after("c")
    if probes["c"].result != "ok":
        run_d()

    cli, master = subject(probes["a"], probes["b"]), subject(probes["c"], probes["d"])
    # The completion rule: under needs_real_home every engine process runs with
    # the real HOME, so both subjects must be proven to authenticate there.
    if cli == "sandbox" and master == "real_home" and probes["b"].result == "skipped":
        run_b()
    if cli == "real_home" and master == "sandbox" and probes["d"].result == "skipped":
        run_d()
    mode = bind(cli, master, probes["b"], probes["d"])

    results = {name: {"result": probe.result, **probe.detail} for name, probe in probes.items()}
    rec.note(f"LIVE_AUTH_MODE={mode} (cli={cli}, master={master})")
    rec.note(json.dumps({"S0_RESULTS": {k: v["result"] for k, v in results.items()}, "real_claude_deltas": deltas}))
    rec.record("proc.sub_probes", {k: v["result"] for k, v in results.items()})
    rec.record("files.real_claude_deltas", deltas)
    rec.check("binding.total", mode in ("sandbox_ok", "needs_real_home", "unavailable"),
              "exactly one of sandbox_ok / needs_real_home / unavailable", mode)
    for name in ("c", "d"):
        detail = probes[name].detail
        if probes[name].result == "ok":
            rec.equal(f"api.{name}_started", True, detail.get("api_started"))
    (qa6_run.run_dir / "live_auth_mode.json").write_text(
        json.dumps({"LIVE_AUTH_MODE": mode, "cli": cli, "master": master, "S0_RESULTS": results,
                    "real_claude_deltas": deltas}, indent=1, default=str),
        encoding="utf-8",
    )
    (qa6_run.run_dir / "s0-detail.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    left = [hit for spelling in paths.TMP_SPELLINGS
            for hit in hostprobe.pgrep(f"claude.*{spelling}/{paths.RUN_ROOT_PREFIX}{qa6_run.pid}-{root.k}")]
    rec.check("proc.no_claude_left", not left, "no claude child left under S0's root", left[:5])
    # S0 Cleanup: its instances are stopped by the pool; its root goes with the run root.
    rec.finish()
