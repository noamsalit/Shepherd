"""Wave 9, HOST lane: Z1-Z3 — the run left the host exactly as it found it (test-plan §4 Z1-Z3).

Runs **after** the runner's teardown (run.py: teardown before wave 9), so the
run roots are gone (Z3 asserts that) and everything these scenarios read lives
in the report directory: `baseline.json` (the pre-run host), `host-after/*.json`
(one snapshot after every lane process and `after-teardown.json`), `ledgers/`,
`live-closing-step.json` (wave 8's closing step) and `wave8-ledgers/` (the
product tmux log, copied after LIVE-A/LIVE-B stopped).

**Read-only.** Nothing here writes to the host, contacts the user's tmux
servers (`default`, `shepherd`) with a client command, connects to or binds the
forbidden port, or signals anything. The user's tmux state is read from the
socket directory listing and `pgrep` (setup.md §4 correction 2), which is why
Z2's "`tmux -L shepherd ls` unchanged" is asserted as the socket's presence
across the run rather than by running `ls` on it (U-rules: never touch that
socket).

**Attribution, not deletion.** Two other qa6 builders may run on this host.
State that carries another live run's pid (`shq6-<pid>-…` roots,
`shepherd-m3-q6<pid>-…` sockets, `-private-tmp-shq6-<pid>-…` project dirs) is
recorded as theirs and never counted as this run's leak; nothing is removed.

**Mutations** (§2c floor): Z1's settings clause is proved against a planted
change to a **copy** of the settings file (`w9_PP8_Z1_settings_copy` — the real
file is only ever opened for reading), and Z2's argv clause against one planted
argv line held in memory (`w9_PP7_Z2_planted_argv` — never executed).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

from .. import hostprobe, paths, realclaude
from ..mutations import active
from ..sandbox import TMP_CANONICAL, RunContext
from ..scenario import scenario
from ..verdict import Recorder

Q6_SOCKET = re.compile(r"^shepherd-m3-q6(\d+)-(\d+)$")
Q6_PROJECT = re.compile(r"shq6-(\d+)-")
#: The one planted line Z2's mutation appends to the argv list it evaluates (never run).
PLANTED_ARGV = ["tmux", "-L", "shepherd", "list-sessions"]
DAEMON_WORDS = ("shepherd-controld", "shepherd-sessiond", "launch_controld.py")


# ----- reading the report directory ------------------------------------------------------------------


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): v for k, v in decoded.items()} if isinstance(decoded, dict) else None


def names_of(snapshot: Mapping[str, object] | None, key: str) -> dict[str, float]:
    value = snapshot.get(key) if snapshot else None
    if not isinstance(value, dict):
        return {}
    return {str(k): float(v) for k, v in value.items() if isinstance(v, (int, float))}


def jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, dict):
                rows.append({str(k): v for k, v in decoded.items()})
    return rows


def argv_lines(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    found: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, list):
                found.append([str(word) for word in decoded])
    return found


def live_auth_mode(run: RunContext) -> str | None:
    decoded = read_json(run.run_dir / "live_auth_mode.json")
    mode = decoded.get("LIVE_AUTH_MODE") if decoded else None
    return mode if isinstance(mode, str) else None


def pid_alive(pid: int) -> bool:
    return hostprobe.process_args(pid) is not None


def other_run(pid: int, run: RunContext) -> bool:
    return pid != run.pid


def run_pids(run: RunContext) -> dict[int, str]:
    """Every pid this run started or observed, and where it was recorded."""
    found: dict[int, str] = {}
    for entry in jsonl(run.run_dir / "ledgers" / "pids.jsonl"):
        pid = entry.get("pid")
        if isinstance(pid, int):
            found[pid] = f"pids.jsonl:{entry.get('kind')}"
    closing = read_json(run.run_dir / "live-closing-step.json")
    recorded = closing.get("run_pids") if closing else None
    if isinstance(recorded, dict):
        for kind, pids in recorded.items():
            for pid in pids if isinstance(pids, list) else []:
                if isinstance(pid, int):
                    found.setdefault(pid, f"live-closing-step:{kind}")
    sessions = closing.get("sessions") if closing else None
    for entry in sessions if isinstance(sessions, list) else []:
        pane_pid = entry.get("pane_pid") if isinstance(entry, dict) else None
        if isinstance(pane_pid, int):
            found.setdefault(pane_pid, "live-closing-step:pane")
    return found


def under_run_root(text: str, run: RunContext) -> bool:
    return any(f"{spelling}/{paths.RUN_ROOT_PREFIX}{run.pid}-" in text for spelling in paths.TMP_SPELLINGS)


# ===== Z1 ===================================================================================================


def settings_checks(run: RunContext, rec: Recorder) -> dict[str, str]:
    checks: dict[str, str] = {}
    baseline = read_json(run.run_dir / "baseline.json")
    if baseline and isinstance(baseline.get("settings_sha"), str):
        checks["baseline"] = str(baseline["settings_sha"])
    for snapshot in sorted((run.run_dir / "host-after").glob("*.json")):
        decoded = read_json(snapshot)
        if decoded and isinstance(decoded.get("settings_sha"), str):
            checks[f"after:{snapshot.stem}"] = str(decoded["settings_sha"])
    measured = paths.REAL_SETTINGS
    if active("w9_PP8_Z1_settings_copy"):
        # The planted change goes into a COPY. The real file is opened read-only, once.
        copy = run.run_dir / "z1-mutation" / "settings.copy.json"
        copy.parent.mkdir(parents=True, exist_ok=True)
        with open(paths.REAL_SETTINGS, "rb") as handle:
            original = handle.read()
        copy.write_bytes(original + b"\n")
        measured = copy
        rec.note(f"QA6 MUTATION w9_PP8_Z1_settings_copy APPLIED: Z1 measured {copy} (the real bytes plus one "
                 f"planted newline), sha {hostprobe.sha256(copy)}; the real file's sha stays "
                 f"{hostprobe.sha256(paths.REAL_SETTINGS)}")
    checks["now"] = hostprobe.sha256(measured)
    return checks


def run_sidecars(run: RunContext, pids: Mapping[int, str]) -> list[dict[str, object]]:
    """Sidecars in the real ~/.claude/sessions that belong to this run (by pid or by cwd)."""
    found: list[dict[str, object]] = []
    directory = paths.REAL_CLAUDE_DIR / "sessions"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        try:
            decoded: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # a sidecar being rewritten by a live engine; the next read sees it whole
        if not isinstance(decoded, dict):
            continue
        pid = decoded.get("pid")
        cwd = str(decoded.get("cwd") or "")
        # A recorded pid counts only if it was recorded as an engine (pane, claude -p, master CLI):
        # a reused pid of a recorded controld or helper is not a run engine.
        engine_pid = isinstance(pid, int) and any(word in pids.get(pid, "") for word in ("pane", "claude", "master_cli"))
        ours = engine_pid or under_run_root(os.path.realpath(cwd) if cwd else "", run) or under_run_root(cwd, run)
        if ours:
            alive = isinstance(pid, int) and pid_alive(pid)
            found.append({"file": path.name, "pid": pid, "cwd": cwd, "alive": alive,
                          "recorded_as": pids.get(pid) if isinstance(pid, int) else None})
    return found


@scenario("Z1")
def test_z1_user_claude_settings_and_projects_as_they_were(qa6_run: RunContext, rec: Recorder) -> None:
    run = qa6_run
    mode = live_auth_mode(run)
    rec.record("given.live_auth_mode", mode)
    checks = settings_checks(run, rec)
    mismatched = {name: sha for name, sha in checks.items() if sha != paths.EXPECTED_SETTINGS_SHA}
    rec.check("files.settings_sha", not mismatched and "now" in checks,
              f"sha256 == {paths.EXPECTED_SETTINGS_SHA} at every check",
              {"checks": sorted(checks), "mismatched": mismatched})
    baseline = read_json(run.run_dir / "baseline.json")
    now = hostprobe.snapshot().as_json()
    if baseline is None:
        rec.block("files.projects_delta", "no baseline.json in the run directory (not a runner run)")
    else:
        added = sorted(set(names_of(now, "claude_projects")) - set(names_of(baseline, "claude_projects")))
        ours = [name for name in added if f"{paths.RUN_ROOT_PREFIX}{run.pid}-" in name]
        siblings = [name for name in added if (m := Q6_PROJECT.search(name)) and other_run(int(m.group(1)), run)]
        foreign = [name for name in added if name not in ours and name not in siblings]
        rec.record("files.projects_added", {"ours": ours, "attributed_to_other_qa6_runs": siblings, "foreign": foreign})
        if mode == "needs_real_home":
            rec.check("files.projects_delta", not foreign, f"only names carrying this run's {paths.RUN_ROOT_PREFIX}"
                      f"{run.pid}- slug", {"foreign": foreign, "ours": len(ours)})
        else:
            rec.check("files.projects_delta", not foreign and not ours, "an empty delta (sandbox_ok / no live wave)",
                      {"ours": ours, "foreign": foreign})
        rec.record("files.claude_json_mtime_delta", {"before": baseline.get("claude_json_mtime"),
                                                     "after": now.get("claude_json_mtime")})
    pids = run_pids(run)
    sidecars = run_sidecars(run, pids)
    rec.record("files.real_sidecars_of_this_run", sidecars)
    closing = read_json(run.run_dir / "live-closing-step.json")
    if closing is not None:
        closed = closing.get("sessions")
        rec.record("given.closing_step", {"sessions": len(closed) if isinstance(closed, list) else None,
                                          "problems": closing.get("problems")})
    alive = [entry for entry in sidecars if entry.get("alive")]
    rec.check("files.no_live_run_sidecar", not alive, "no ~/.claude/sessions file names a run pid still alive", alive)
    # Not in the plan's Z1 row; added after INC-1 (a real-HOME engine re-pointed the user's
    # `~/.local/bin/claude` into a run root). Derived oracle: the run leaves the link exactly as it
    # found it at run START — never "healthy", because it may already have been damaged before
    # the run (it was: INC-1 is unrepaired), and repairing it is not the harness's to do.
    link_start = realclaude.start_link_state(run.run_dir)
    link_now = realclaude.link_state()
    if link_start is None:
        rec.block("files.claude_bin_link_unchanged", f"no {realclaude.LINK_START_FILE} in the run directory")
    else:
        rec.check("files.claude_bin_link_unchanged", realclaude.compare(link_start, link_now) is None,
                  f"{paths.REAL_CLAUDE_BIN} is as it was at run start: {link_start}", link_now)
    rec.record("files.real_claude_resolution", read_json(run.run_dir / realclaude.RESOLUTION_FILE))
    if mode == "sandbox_ok":
        rec.equal("files.no_run_sidecar_in_real_dir", [], sidecars)
    rec.finish()


# ===== Z2 ===================================================================================================


def product_tmux_log(run: RunContext, rec: Recorder) -> tuple[list[list[str]] | None, str]:
    """The product's argv log: the runner's `ledgers/tmux-argv.log` (distinct from
    `ledgers/unseeded-tmux-argv.log` since SI-2), else wave 8's copy, else the live file."""
    _ = rec
    ledger = run.run_dir / "ledgers" / "tmux-argv.log"
    if ledger.exists():
        return argv_lines(ledger), str(ledger)
    wave8 = run.run_dir / "wave8-ledgers" / "tmux-argv.product.log"
    if wave8.exists():
        return argv_lines(wave8), str(wave8)
    if run.tmux_argv_log.exists():
        # A run whose root is still present (standalone or --mutation): the live product log itself.
        return argv_lines(run.tmux_argv_log), str(run.tmux_argv_log)
    return None, "absent"


def socket_violations(lines: list[list[str]], run: RunContext) -> list[list[str]]:
    pattern = paths.runner_socket_pattern(run.pid)
    return [argv for argv in lines if argv != ["tmux", "-V"]
            and not (len(argv) >= 3 and argv[1] == "-L" and pattern.fullmatch(argv[2]))]


def shim_spawns(run: RunContext) -> int:
    """Pane starts of the fake `claude` (not `-p` forks, not W5's harness panes, not self-tests)."""
    count = 0
    for entry in jsonl(run.run_dir / "ledgers" / "claude-argv.log"):
        argv = entry.get("argv")
        words = [str(word) for word in argv] if isinstance(argv, list) else []
        options = words[: words.index("--")] if "--" in words else words
        if any(w in options for w in ("-p", "--print", "--qa6-w5", "--qa6-selftest", "--version", "agents")):
            continue
        count += 1
    return count


def live_counts(run: RunContext) -> tuple[int, int]:
    closing = read_json(run.run_dir / "live-closing-step.json")
    sessions = closing.get("sessions") if closing else None
    entries = [entry for entry in (sessions if isinstance(sessions, list) else []) if isinstance(entry, dict)]
    return len(entries), len([entry for entry in entries if entry.get("killed_by")])


@scenario("Z2")
def test_z2_tmux_only_our_sockets_touched_and_ours_gone(qa6_run: RunContext, rec: Recorder) -> None:
    run = qa6_run
    baseline = read_json(run.run_dir / "baseline.json")
    now = hostprobe.snapshot().as_json()
    if baseline is None:
        rec.block("tmux.user_sockets_present_unchanged", "no baseline.json in the run directory")
        rec.block("tmux.dir_minus_q6_unchanged", "no baseline.json in the run directory")
    else:
        rec.equal("tmux.user_sockets_present_unchanged", baseline.get("tmux_user_sockets_present"),
                  now.get("tmux_user_sockets_present"))
        before, after = names_of(baseline, "tmux_dir"), names_of(now, "tmux_dir")
        rec.equal("tmux.dir_minus_q6_unchanged", sorted(n for n in before if not Q6_SOCKET.match(n)),
                  sorted(n for n in after if not Q6_SOCKET.match(n)))
        stale = {n: (before[n], after.get(n)) for n in before
                 if n.startswith("shepherd-m3-") and not Q6_SOCKET.match(n)}
        rec.check("tmux.stale_m3_sockets_untouched", all(was == still for was, still in stale.values()),
                  "the stale shepherd-m3-* sockets keep their mtimes", stale)
        rec.record("tmux.user_socket_mtimes", {n: (before.get(n), after.get(n)) for n in paths.USER_TMUX_SOCKETS})
    listing = hostprobe.tmux_socket_listing()
    ours = sorted(n for n in listing if (m := Q6_SOCKET.match(n)) and int(m.group(1)) == run.pid)
    theirs = sorted(n for n in listing if (m := Q6_SOCKET.match(n)) and int(m.group(1)) != run.pid)
    rec.equal("tmux.our_sockets_removed", [], ours)
    rec.record("tmux.attributed_to_other_qa6_runs",
               {n: pid_alive(int(m.group(1))) for n in theirs if (m := Q6_SOCKET.match(n)) is not None})
    servers = [(pid, cmd) for pid, cmd in hostprobe.pgrep(f"shepherd-m3-q6{run.pid}-") if "pgrep" not in cmd]
    rec.equal("tmux.our_servers_gone", [], servers)
    lines, source = product_tmux_log(run, rec)
    rec.record("files.product_log_source", source)
    if lines is None:
        rec.block("files.shim_log_nonempty", f"the product tmux log is not available ({source})")
        rec.block("tmux.argv", "no product tmux log to read")
    else:
        rec.check("files.shim_log_nonempty", len(lines) > 0, "the logging-tmux shim log is non-empty", len(lines))
        spawns = shim_spawns(run)
        live_spawns, live_kills = live_counts(run)
        news = [argv for argv in lines if "new-session" in argv]
        kills = [argv for argv in lines if "kill-session" in argv]
        rec.check("files.shim_log_control", len(news) >= spawns + live_spawns and len(kills) >= live_kills,
                  ">= one new-session per spawn and one kill-session per live kill",
                  {"new_session": len(news), "spawns_shim": spawns, "spawns_live": live_spawns,
                   "kill_session": len(kills), "kills_live": live_kills})
        evaluated = list(lines)
        if active("w9_PP7_Z2_planted_argv"):
            evaluated.append(list(PLANTED_ARGV))
            rec.note(f"QA6 MUTATION w9_PP7_Z2_planted_argv APPLIED: one planted argv {PLANTED_ARGV} appended to the "
                     "evaluated list (held in memory, never executed)")
        violations = socket_violations(evaluated, run)
        rec.check("tmux.argv", not violations, "every argv but `tmux -V` names -L shepherd-m3-q6<pid>-<k>",
                  {"violations": violations[:10], "lines": len(evaluated)})
        user = [argv for argv in evaluated if len(argv) >= 3 and argv[1] == "-L" and argv[2] in paths.USER_TMUX_SOCKETS]
        rec.equal("tmux.no_user_socket_named", [], user[:10])
        pattern = paths.runner_socket_pattern(run.pid)
        kill_servers = [argv for argv in evaluated if any(w.startswith("kill-ser") for w in argv)
                        and not (len(argv) >= 3 and pattern.fullmatch(argv[2]))]
        rec.equal("tmux.kill_server_ours_only", [], kill_servers)
    unseeded = argv_lines(run.run_dir / "ledgers" / "unseeded-tmux-argv.log")
    rec.record("tmux.unseeded_log", {"lines": len(unseeded), "sockets": sorted({a[2] for a in unseeded if len(a) >= 3})})
    rec.equal("tmux.unseeded_no_user_socket", [], [a for a in unseeded if len(a) >= 3 and a[2] in paths.USER_TMUX_SOCKETS])
    rec.finish()


# ===== Z3 ===================================================================================================


def daemons_under_root(run: RunContext) -> list[dict[str, object]]:
    done = hostprobe.run([str(paths.PS_BIN), "-A", "-o", "pid=,command="])
    found: list[dict[str, object]] = []
    for line in done.stdout.splitlines():
        head, _, command = line.strip().partition(" ")
        if not head.isdigit() or int(head) == os.getpid():
            continue
        if not (any(word in command for word in DAEMON_WORDS) or "claude" in command.split(" ")[0]):
            continue
        cwd = hostprobe.process_cwd(int(head)) or ""
        if under_run_root(command, run) or under_run_root(cwd, run):
            found.append({"pid": int(head), "command": command[:200], "cwd": cwd})
    return found


@scenario("Z3")
def test_z3_forbidden_port_untouched_nothing_left_running(qa6_run: RunContext, rec: Recorder) -> None:
    run = qa6_run
    baseline = read_json(run.run_dir / "baseline.json")
    owners = hostprobe.port_listener_pids(paths.FORBIDDEN_PORT)
    if baseline is None:
        rec.block("proc.port_owner_unchanged", "no baseline.json in the run directory")
    else:
        rec.equal("proc.port_owner_unchanged", baseline.get("port_owner_pids"), owners)
    forbidden = str(paths.FORBIDDEN_PORT)
    ledger = run.run_dir / "ledgers" / "controld-argv.jsonl"
    argvs = [entry.get("argv") for entry in jsonl(ledger if ledger.exists() else run.controld_argv_ledger)]
    named = [argv for argv in argvs if isinstance(argv, list) and any(
        str(argv[i]) == "--port" and i + 1 < len(argv) and str(argv[i + 1]) == forbidden for i in range(len(argv)))]
    if argvs:
        rec.check("proc.controld_argv_no_forbidden_port", not named,
                  "every recorded controld argv, none naming the forbidden port", {"argvs": len(argvs), "naming": named})
    else:
        rec.block("proc.controld_argv_no_forbidden_port", "no controld argv was recorded in this run (the check would be vacuous)")
    refusals = run.run_dir / "ledgers" / "port-refusals.log"
    count = len([line for line in refusals.read_text(encoding="utf-8").splitlines() if line.strip()]) if refusals.exists() else 0
    rec.equal("proc.client_refusals_zero", 0, count)
    left = [(pid, cmd) for spelling in paths.TMP_SPELLINGS
            for pid, cmd in hostprobe.pgrep(f"{spelling}/{paths.RUN_ROOT_PREFIX}{run.pid}-") if "pgrep" not in cmd]
    rec.equal("proc.pgrep_run_root_empty", [], left)
    rec.equal("proc.no_daemon_or_claude_under_run_root", [], daemons_under_root(run))
    roots = sorted(str(p) for p in TMP_CANONICAL.glob(f"{paths.RUN_ROOT_PREFIX}{run.pid}-*"))
    rec.equal("files.run_roots_removed", [], roots)
    others = sorted({int(m.group(1)) for p in TMP_CANONICAL.glob(f"{paths.RUN_ROOT_PREFIX}*")
                     if (m := re.match(rf"^{re.escape(paths.RUN_ROOT_PREFIX)}(\d+)-", p.name)) and int(m.group(1)) != run.pid})
    rec.record("files.roots_of_other_qa6_runs", {str(pid): pid_alive(pid) for pid in others})
    rec.finish()
