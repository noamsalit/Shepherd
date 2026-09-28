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
import time
from collections.abc import Mapping
from pathlib import Path

from shepherd.runner.tmux_cmd import DEFAULT_SOCKET, is_server_teardown

from .. import hostprobe, paths, realclaude, teardown, tmuxctl
from ..mutations import active
from ..sandbox import TMP_CANONICAL, RunContext
from ..scenario import scenario
from ..verdict import Recorder

Q6_SOCKET = re.compile(r"^shepherd-m3-q6(\d+)-(\d+)$")
Q6_PROJECT = re.compile(r"shq6-(\d+)-")
#: The binary's name, assembled (the reason is `tests/boundaries/test_tmux_blast_radius.py`'s own
#: `TMUX`): `PLANTED_ARGV` names the user's socket on purpose, as data Z2's judge must refuse, and
#: a literal would read to that module's scan as an argv reaching `shepherd`. It is never executed.
TMUX = "tm" + "ux"
#: The one planted line Z2's mutation appends to the argv list it evaluates (never run).
PLANTED_ARGV = [TMUX, "-L", "shepherd", "list-sessions"]
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


#: A sidecar being rewritten is re-read this many times, SIDECAR_RETRY_S apart, before it is unknown (M4).
SIDECAR_READS = 5
SIDECAR_RETRY_S = 0.2


def read_sidecar(path: Path) -> dict[str, object] | None:
    """The sidecar whole, re-read while a live writer is mid-rewrite; `None` = still unreadable."""
    for attempt in range(SIDECAR_READS):
        try:
            decoded: object = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            if attempt + 1 < SIDECAR_READS:
                time.sleep(SIDECAR_RETRY_S)  # a bounded re-read, not readiness
            continue
        return {str(k): v for k, v in decoded.items()} if isinstance(decoded, dict) else {}
    return None


def unreadable_run_sidecars(run: RunContext, pids: Mapping[int, str]) -> list[str]:
    """Sidecars (`<pid>.json`) still unreadable after the re-reads whose pid is one of this run's engines."""
    directory = paths.REAL_CLAUDE_DIR / "sessions"
    unknown: list[str] = []
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        stem = path.stem
        engine = stem.isdigit() and any(word in pids.get(int(stem), "") for word in ("pane", "claude", "master_cli"))
        if engine and read_sidecar(path) is None:
            unknown.append(path.name)
    return unknown


def run_sidecars(run: RunContext, pids: Mapping[int, str]) -> list[dict[str, object]]:
    """Sidecars in the real ~/.claude/sessions that belong to this run (by pid or by cwd)."""
    found: list[dict[str, object]] = []
    directory = paths.REAL_CLAUDE_DIR / "sessions"
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        decoded = read_sidecar(path)
        if not decoded:
            continue  # gone, or still unreadable: `unreadable_run_sidecars` counts this run's as unknown
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


def engine_version(run: RunContext) -> str | None:
    resolution = read_json(run.run_dir / realclaude.RESOLUTION_FILE)
    path = resolution.get("path") if resolution else None
    return os.path.basename(path) if isinstance(path, str) else None


def local_tree_clause(run: RunContext, rec: Recorder, baseline: Mapping[str, object] | None) -> None:
    """Review finding 3: ~/.local/{bin, share/claude, state/claude} as at run START, after every lane and now.

    Names, kinds, mtimes and link targets (lstat/readlink only). The dangling
    `~/.local/bin/claude` is part of the START state, not a change. A lock file
    for a version other than this run's engine, added or removed, is the user's
    own session and is attributed, not counted (`hostprobe.local_tree_changes`).
    """
    start = baseline.get("local_tree") if baseline else None
    if not isinstance(start, dict):
        rec.block("files.local_tree_unchanged", "no local_tree in baseline.json (not a runner run of this build)")
        return
    version = engine_version(run)
    checked: dict[str, object] = {}
    attributed: dict[str, object] = {}
    unknown: list[str] = []
    snapshots = {f"after:{path.stem}": read_json(path) for path in sorted((run.run_dir / "host-after").glob("*.json"))}
    snapshots["now"] = {"local_tree": hostprobe.local_tree()}
    for label, snapshot in snapshots.items():
        tree = snapshot.get("local_tree") if snapshot else None
        if not isinstance(tree, dict):
            unknown.append(label)
            continue
        changes, seen = hostprobe.local_tree_changes(start, tree, version)
        if changes:
            checked[label] = changes
        attributed.update(seen)
    rec.record("files.local_tree_attributed_to_the_users_sessions", attributed)
    if unknown:
        rec.block("files.local_tree_snapshots_readable", f"snapshots with no local_tree (unknown is not clean): {unknown}")
    rec.check("files.local_tree_unchanged", not checked,
              "~/.local/{bin, share/claude, state/claude} as at run start in every snapshot and now "
              f"({len(start)} entries; the run-start ~/.local/bin/claude link included as it was)",
              {"changed": checked, "snapshots": len(snapshots)})


def daemons_alive_at_baseline(baseline: Mapping[str, object] | None) -> list[int]:
    raw = baseline.get("shepherd_daemons") if baseline else None
    pids = [entry[0] for entry in raw if isinstance(entry, list) and entry and isinstance(entry[0], int)] if isinstance(raw, list) else []
    return [pid for pid in pids if pid_alive(pid)]


def listing_clause(rec: Recorder, clause: str, key: str, baseline: Mapping[str, object] | None,
                   after: Mapping[str, object] | None) -> None:
    """H7: the user's real Shepherd dirs, baseline vs after-teardown: same names and, unless the
    user's own Shepherd daemon (alive at baseline and still) explains it, the same mtimes."""
    before_listing = baseline.get(key) if baseline else None
    after_listing = after.get(key) if after else None
    if not isinstance(before_listing, dict) or not isinstance(after_listing, dict):
        rec.block(clause, f"{key} missing from baseline.json or after-teardown.json (unknown is not clean)")
        return
    delta = hostprobe.listing_delta(before_listing, after_listing)
    users = daemons_alive_at_baseline(baseline)
    names_same = not delta["added"] and not delta["removed"]
    mtimes_ok = not delta["mtime_moved"] or bool(users)
    rec.check(clause, names_same and mtimes_ok,
              f"{key}: the same names" + (" (mtimes may move: the user's Shepherd daemon(s) "
                                          f"{users} were running at baseline and still are)" if users else
                                          " and mtimes as at baseline"),
              {**delta, "user_daemons_alive": users})


@scenario("Z1")
def test_z1_user_claude_settings_and_projects_as_they_were(qa6_run: RunContext, rec: Recorder) -> None:
    run = qa6_run
    mode = live_auth_mode(run)
    rec.record("given.live_auth_mode", mode)
    checks = settings_checks(run, rec)
    expected = paths.expected_settings_sha()  # the run-start sha the runner exported (owner's value when unset)
    mismatched = {name: sha for name, sha in checks.items() if sha != expected}
    rec.check("files.settings_sha", not mismatched and "now" in checks,
              f"sha256 == {expected} at every check",
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
    unknown = unreadable_run_sidecars(run, pids)
    if unknown:
        rec.block("files.run_sidecars_readable", f"sidecars of this run's engine pids unreadable after "
                  f"{SIDECAR_READS} reads (unknown is not clean): {unknown}")
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
    local_tree_clause(run, rec, baseline)
    after = read_json(run.run_dir / "host-after" / "after-teardown.json")
    for key, clause in (("shepherd_data", "files.real_shepherd_data_unchanged"),
                        ("real_tmpdir_shepherd", "files.real_tmpdir_shepherd_unchanged")):
        listing_clause(rec, clause, key, baseline, after)
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


def pane_tmux_log(run: RunContext) -> tuple[list[dict[str, object]], str]:
    """In-pane tmux calls (`{"argv", "tmux"}`), from the runner's ledger, else wave 8's copy, else the live file."""
    for source in (run.run_dir / "ledgers" / "pane-tmux-argv.log", run.run_dir / "wave8-ledgers" / "pane-tmux-argv.log",
                   run.pane_tmux_argv_log):
        if source.exists():
            return jsonl(source), str(source)
    return [], "absent (no tmux call was made inside a pane)"


def off_run_socket_argvs(lines: list[list[str]], run: RunContext) -> list[list[str]]:
    """Every product argv whose effective socket (tmux's own getopt rules) is not this run's."""
    return tmuxctl.product_argv_offenders(lines, run.pid)


def named_user_socket(argv: list[str]) -> bool:
    """The argv's effective socket (not its spelling at a fixed position) is the user's."""
    return tmuxctl.effective_socket(argv, None) in paths.USER_TMUX_SOCKETS


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
        violations = off_run_socket_argvs(evaluated, run)
        rec.check("tmux.argv", not violations, "every argv but `tmux -V` has effective socket shepherd-m3-q6<pid>-<k>",
                  {"violations": violations[:10], "lines": len(evaluated)})
        user = [argv for argv in evaluated if named_user_socket(argv)]
        rec.equal("tmux.no_user_socket_named", [], user[:10])
        kill_servers = [argv for argv in evaluated if any(is_server_teardown(w) for w in argv)
                        and not tmuxctl.socket_allowed(str(tmuxctl.effective_socket(argv, None)), run.pid)]
        rec.equal("tmux.kill_server_ours_only", [], kill_servers)
    pane_entries, pane_source = pane_tmux_log(run)
    rec.record("files.pane_log_source", {"source": pane_source, "entries": len(pane_entries)})
    pane_bad = tmuxctl.pane_argv_offenders(pane_entries, run.pid)
    rec.check("tmux.pane_argv_effective_socket", not pane_bad,
              "every tmux call made inside a pane (the real engine's; $TMUX set) resolves -S, -L, else $TMUX to "
              "shepherd-m3-q6<pid>-<k>", {"violations": pane_bad[:10], "entries": len(pane_entries)})
    unseeded = argv_lines(run.run_dir / "ledgers" / "unseeded-tmux-argv.log")
    rec.record("tmux.unseeded_log", {"lines": len(unseeded),
                                     "sockets": sorted({str(tmuxctl.effective_socket(a, None)) for a in unseeded})})
    rec.equal("tmux.unseeded_no_user_socket", [], [a for a in unseeded if named_user_socket(a)])
    # Review N3: the unseeded reconcile is excused for exactly `list-sessions` on the product's
    # default runner socket; any other verb there (or any other foreign socket) is a violation.
    unexcused = [a for a in unseeded if tmuxctl.argv_violation(a, None, run.pid) is not None
                 and not tmuxctl.unseeded_excused(a, DEFAULT_SOCKET)]
    rec.equal("tmux.unseeded_only_list_sessions_on_the_default_runner", [], unexcused[:10])
    rec.finish()


# ===== Z3 ===================================================================================================


def daemons_under_root(run: RunContext) -> list[dict[str, object]]:
    listed = hostprobe.run_pid_probe([str(paths.PS_BIN), "-A", "-o", "pid=,command="])
    if listed is None:
        raise hostprobe.ProbeUnknown("ps -A answered nothing (unknown is not clean)")
    found: list[dict[str, object]] = []
    for line in listed.splitlines():
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
    after = read_json(run.run_dir / "host-after" / "after-teardown.json")
    process_clauses(run, rec, baseline, after)
    rec.finish()


def attribution(pid: int, run: RunContext) -> str:
    """Whose a pid is, from its argv and cwd now: `ours`, `other qa6 run <pid>`, `gone`, `unknown: …`
    (a `ps`/`lsof` that could not answer — never read as gone, hunter N6), or `unattributed`."""
    try:
        command = hostprobe.process_args(pid)
        if command is None:
            return "gone"
        cwd = hostprobe.process_cwd(pid) or ""
    except hostprobe.ProbeUnknown as unknown:
        return f"unknown: {unknown}"
    if f"shepherd-m3-q6{run.pid}-" in command or under_run_root(command, run) or under_run_root(cwd, run):
        return "ours"
    if (m := re.search(r"shepherd-m3-q6(\d+)-|shq6-(\d+)-", f"{command} {cwd}")) and int(m.group(1) or m.group(2)) != run.pid:
        return f"other qa6 run {m.group(1) or m.group(2)}"
    return f"unattributed: {command[:160]}"


def process_clauses(run: RunContext, rec: Recorder, baseline: Mapping[str, object] | None,
                    after: Mapping[str, object] | None) -> None:
    """H7 / review N5: the user's Shepherd daemons and tmux SERVERS, baseline vs after-teardown,
    and the direct oracle — no pid the runner's teardown signalled was alive at baseline.

    A baseline daemon or tmux server gone after teardown is a failure (the run may have signalled
    the user's own process); a new one fails unless it is attributable to another live qa6 run.
    tmux CLIENT processes (`tmux attach`, `tmux ls` the user runs) come and go with the user's
    own terminals: their delta is recorded, never failed (a server is a tmux with parent launchd).
    """
    signalled_file = run.run_dir / teardown.SIGNALLED_FILE
    signalled = read_json(signalled_file)
    raw = signalled.get("signalled") if signalled else None
    if baseline is None or not isinstance(raw, list):
        rec.block("proc.teardown_signalled_no_baseline_pid",
                  f"no baseline.json or no {teardown.SIGNALLED_FILE} (the runner's teardown writes it; "
                  "unknown is not clean)")
    else:
        hit = hostprobe.signalled_baseline_pids(list(raw), baseline)
        rec.check("proc.teardown_signalled_no_baseline_pid", not hit,
                  "no pid the teardown signalled was alive at baseline (the user's processes)",
                  {"signalled": raw[:50], "at_baseline": hit})
    before_clients = baseline.get("tmux_pids") if baseline else None
    after_clients = after.get("tmux_pids") if after else None
    if isinstance(before_clients, list) and isinstance(after_clients, list):
        rec.record("proc.tmux_processes_delta_not_judged", hostprobe.pid_delta(before_clients, after_clients))
    for key, clause in (("shepherd_daemons", "proc.shepherd_daemons_unchanged"),
                        ("tmux_server_pids", "proc.tmux_servers_unchanged")):
        before = baseline.get(key) if baseline else None
        now = after.get(key) if after else None
        if not isinstance(before, list) or not isinstance(now, list):
            rec.block(clause, f"{key} missing from baseline.json or after-teardown.json (unknown is not clean)")
            continue
        delta = hostprobe.pid_delta(before, now)
        new = {str(pid): attribution(pid, run) for pid in delta["new"]}
        unknown = {pid: who for pid, who in new.items() if who.startswith("unknown")}
        bad_new = {pid: who for pid, who in new.items() if not who.startswith(("other qa6 run", "gone", "unknown"))}
        if unknown and not delta["gone"] and not bad_new:
            rec.block(clause, f"new {key} pid(s) whose owner could not be probed (unknown is not clean): {unknown}")
            continue
        rec.check(clause, not delta["gone"] and not bad_new,
                  f"every baseline {key} pid still running and no new one (except another qa6 run's)",
                  {"gone": delta["gone"], "new": new})
