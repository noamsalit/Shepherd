<!-- Surface: linux-process-git. Evidence folder: docs/probes/2026-09-14-schemas/linux-process-git/
     All captures: claude --version = 2.1.270 (Claude Code); host Ubuntu 24.04.4 LTS, Linux 6.8.0-117-generic x86_64,
     systemd 255, git 2.43.0, Python 3.12.3, uid 0 (root). Captured 2026-09-14 16:16–16:26 UTC.
     Paths below are relative to docs/probes/2026-09-14-schemas/linux-process-git/ unless absolute.
     Throwaway sessions only (haiku); the user's live claude processes were only read, and appear as redacted shapes
     (flag names, env var NAMES, cgroup) under "others" in captures/proc-*-snapshot.json.
     Audited 2026-09-14: all 16 fenced examples traced as ordered byte-for-byte excerpts of the cited capture files;
     no user-session content in examples; Status/alignment wording corrected where the evidence did not reach. -->

## `/proc/<pid>/stat` of a claude process (starttime, comm, ppid)

> **Sanitised 2026-09-20.** One ticket-shaped identifier (a branch/worktree name
> created under `mktemp -d`) was substituted with a `PROJ-` prefix at the owner's
> instruction — the original carried a former employer's project prefix. Nothing
> else in this write-up or its captures was altered, and `probe_git.sh` was
> renamed to match, so re-running the probe reproduces the captures as written.

- **Produced by:** Linux kernel 6.8.0-117-generic procfs, for Claude Code 2.1.270 processes
- **Consumed by:** §5 process topology and §8 `state`/`stopped` ("observed process exit", spec line 938; "process exit ≠ 0", line 964), §9 LocalRunner, D1 (attached sessions), D14, M1 (attached liveness), M3 (owned sessions)
- **Probe:** `probe_proc.sh` (uses `proc_snapshot.py`, `hook_capture.py`, `sessiond_sim.py`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/proc-C-snapshot.json`, interactive throwaway session in tmux)
```json
   "stat_raw": "4049158 (claude) R 4049157 4049158 4049158 34820 4049158 4194304 69500 28569 0 0 334 32 24 13 20 0 9 0 544014506 5696491520 78486 18446744073709551615 ... 0",
   "stat_field_count": 52,
   "stat_named_fields": {
    "1:pid": "4049158",
    "2:comm": "claude",
    "3:state": "R",
    "4:ppid": "4049157",
    "5:pgrp": "4049158",
    "6:session": "4049158",
    "7:tty_nr": "34820",
    "8:tpgid": "4049158",
...
    "20:num_threads": "9",
    "22:starttime": "544014506",
...
   "starttime_epoch_s": 1789402889.06,
```
`clk_tck` and `btime` from the same file: `"clk_tck": 100,` / `"btime": 1783962744,`.

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| 1 `pid` | int | always | | |
| 2 `comm` | string in parens | always | `claude` (4/4 own snapshots A–D + 4/4 user processes); **`2.1.270` when launched by full path** | Max 15 bytes. Parse with `rindex(")")`, not `split()` |
| 3 `state` | char | always | `S`, `R` | |
| 4 `ppid` | int | always | `timeout` (A/B/D), `tmux: server` (C), `bash` (all 4 user processes) | |
| 5–8 `pgrp`,`session`,`tty_nr`,`tpgid` | int | always | print mode: `tty_nr 0`, `tpgid -1`; interactive in tmux: `tty_nr 34820`, own session leader | Distinguishes a pty-attached TUI from a `-p` run |
| 20 `num_threads` | int | always | `9` | Thread comms: `claude`, `JSCWarmUp`, `mi-scavenger`, `JITWorker`, `Bun Pool 0`, `Bun Pool 1`, `HTTP Client`, `HeapHelper`, `fs.watch` |
| 22 `starttime` | int (clock ticks since boot) | always | `544014506` | Wall clock = `btime + starttime / CLK_TCK` (CLK_TCK = 100). **Equals the registry's `procStart` string in 24/24 hook deliveries** (next schema) |
| total fields | | always | 52 | |

**Variants and edge cases:**
- **`comm` is not reliably `claude`.** The same binary started as `/root/.local/share/claude/versions/2.1.270` has `comm: 2.1.270`, `status Name: 2.1.270`, `argv0: /root/.local/share/claude/versions/2.1.270` (`captures/comm-fullpath.txt`). Identify claude processes by `readlink /proc/<pid>/exe` matching `*/claude/versions/*`, not by `comm`.
- The user's live processes (redacted shapes, `captures/proc-A-snapshot.json` "others"): 4 processes, `exe` basenames `2.1.269` (1) and `2.1.270` (3). A process keeps running the old versioned binary after an auto-update.
- Readable by a different uid (`runuser -u nobody`): `cmdline`, `comm`, `stat`, `status`. Denied: `environ`, `cwd`, `exe`, `fd` (`captures/proc-nobody-A.txt`, `captures/proc-nobody-C.txt`). `hidepid` is not set (`/proc` mount options `rw,nosuid,nodev,noexec,relatime`); `kernel.yama.ptrace_scope = 1`. Same-uid reads all succeeded.

**Spec alignment:** the spec relies on "observed process exit" (line 938) and "process exit ≠ 0" (line 964), but the `session` table (§7, lines 640–698) has no `pid` or process-start column. Without `(pid, starttime)` there is no way to observe exit for an `attached` session, and no guard against pid reuse. An exit code is not observable at all for a process that is not our child. The spec says `exit_code` is `owned` only, which is consistent with that. Reality: `(pid, starttime)` is available and stable (`captures/proc-peercred.jsonl`).

## `/proc/<pid>/{cmdline,exe,cwd,environ,cgroup}` of a claude process

- **Produced by:** Linux procfs, for Claude Code 2.1.270
- **Consumed by:** §8 attached-session registration (lines 881, 926–927), §7.0 `session.cwd`/`brief`, D1, D22 (cwd binding), M1
- **Probe:** `probe_proc.sh` + `proc_snapshot.py`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/proc-C-snapshot.json`)
```json
   "exe": "/root/.local/share/claude/versions/2.1.270",
   "argv": [
    "claude",
    "--model",
    "claude-haiku-4-5-20251001",
    "--session-id",
    "159b556e-eb7e-4cbe-b303-efcc8f5d08a5",
    "--name",
    "shp lpg probe",
    "--allowedTools",
    "Bash(sleep *)"
   ],
   "cwd": "/tmp/shp-lpg-proc.vpBd05/real/repo",
...
   "cgroup": "0::/user.slice/user-0.slice/user@0.service/tmux-spawn-37d8f7d4-3ea6-4cda-a6c8-9f1dc5736877.scope",
   "parent": {
    "pid": 4049157,
    "comm": "tmux: server"
   },
...
   "environ_link": {
    "CLAUDE_PID_present": true,
    "CLAUDE_PID_equals_this_pid": false,
    "CLAUDE_CODE_SESSION_ID_present": true,
    "CLAUDE_CODE_SESSION_ID_equals_a_marker_of_this_session": false,
    "PWD_equals_proc_cwd": false
   },
```
The `--resume` form (full capture: `captures/proc-B-snapshot.json`):
```json
    "--resume",
    "bf3b6fd8-3e12-42de-b62a-02535a996554",
```
A user's live session, redacted to its shape (full capture: `captures/proc-A-snapshot.json`, "others"):
```json
   "argv_shape": [
    "--resume",
    "<redacted>",
    "--remote-control",
    "<redacted>"
   ],
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `cmdline` | NUL-separated argv | always | `claude -p <prompt> --model … --session-id <uuid> …`; `--resume <uuid>` as two separate elements; user processes: `--resume <r> --remote-control <r>` (3), no args (1) | The session id is in argv only when `--session-id`, `--resume` or a similar flag was passed. A bare `claude` has no id in argv. **The `-p` prompt text is in argv and readable by any uid** |
| `exe` | symlink | always | `/root/.local/share/claude/versions/2.1.270`, `…/2.1.269` | Same-uid only |
| `cwd` | symlink | always | `/tmp/shp-lpg-proc.vpBd05/real/repo` | **Physical path.** Launched from `…/link/repo` (a symlink), it resolves to `…/real/repo` |
| `environ` | NUL-separated | always | own sessions: 41–42 names when launched from inside Claude Code, 6 names with `env -i` (`HOME LANG PATH PWD TERM XDG_RUNTIME_DIR`); user processes: 41 names (3), 22 names (1) | This is the **exec-time** environment. Claude Code sets nothing in its own environ |
| `CLAUDE_PID`, `CLAUDE_CODE_SESSION_ID` in environ | string | sometimes (A/B/C and 3/4 user processes; not D, not 1/4 user) | never equal to this process's own pid/session (A, B, C) | **Inherited from the Claude Code session that launched it.** Never use a claude process's own environ to learn its session id |
| `cgroup` | `0::/…` | always | own: `user@0.service/tmux-spawn-<uuid>.scope`; user: `user@0.service/tmux-spawn-<uuid>.scope` (3), `session-10905.scope` (1) | Shows whether the process lives under the user manager or under a login session scope |

**Variants and edge cases:**
- `PWD` in environ is the logical path (`…/link/repo`) and differs from the `cwd` symlink (`PWD_equals_proc_cwd: false` in all 4 own snapshots).
- The environ names of the user's Remote Control sessions include `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `TMUX`, `TMUX_PANE` (names only; values not read).
- `fd` of a live session includes `/tmp/claude-0/-tmp-shp-lpg-proc-vpBd05-real-repo/<session_id>/tasks` (C) and `.../<session_id>/tasks` (A, B, D), a directory that contains the session id. This is a second, undocumented pid→session hint. It was not relied on.

**Spec alignment:** spec lines 926–927 say a hand-launched session "registers itself on its first turn with no filesystem polling". That still holds for sessions started after hooks exist. For a session already running, `/proc` gives cwd and sometimes an argv id, but not reliably a session id. The registry (next schema) is the source for that. The spec names neither. Not probed on this surface: whether a session that was already running when hooks were installed ever fires `SessionStart` later (for example on `/clear`, compaction or a settings reload). The gap above is about the window before that, and it does not depend on the answer.

## Hook process ancestry and environment (which claude owns this hook?)

- **Produced by:** Claude Code 2.1.270 when it runs a `type: command` hook
- **Consumed by:** §8 "Hook installation: one dispatcher" (hookd.py, lines 893–930), §5 (UDS, line 312), D37, M1
- **Probe:** `probe_proc.sh` with `hook_capture.py` registered for SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop and SessionEnd in `<tmpdir>/real/repo/.claude/settings.json` (`captures/proc-settings.json`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh`
- **Status:** verified live 2026-09-14 (4 sessions × 6 events = 24 hook runs)

**Real example** (trimmed; full capture: `captures/proc-hooks.jsonl`, session C `SessionStart`)
```json
{"_event": "SessionStart", "_captured_at": "2026-09-14T16:21:38.957Z", "_claude_version": "2.1.270 (Claude Code)", "_hook_pid": 4049200, "_claude_pid": 4049158, "_ancestry": [{"pid": 4049200, "ppid": 4049199, "comm": "python3", ... "exe": "/usr/bin/python3.12"}, {"pid": 4049199, "ppid": 4049158, "comm": "sh", "cmdline": ["/bin/sh", "-c", "SHP_CLAUDE_VERSION='2.1.270 (Claude Code)' python3 ... "exe": "/usr/bin/dash"}, {"pid": 4049158, "ppid": 4049157, "comm": "claude", "cmdline": ["claude", "--model", "claude-haiku-4-5-20251001", "--session-id", "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "--name", "shp lpg probe", "--allowedTools", "Bash(sleep *)"], "exe": "/root/.local/share/claude/versions/2.1.270"}, {"pid": 4049157, "ppid": 1, "comm": "tmux: server"}], ... "_env_selected": {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_PROJECT_DIR": "/tmp/shp-lpg-proc.vpBd05/real/repo", "PWD": "/tmp/shp-lpg-proc.vpBd05/link/repo", ... "XDG_RUNTIME_DIR": "/run/user/0"}, "_env_link": {"CLAUDE_PID_present": true, "CLAUDE_PID_equals_owning_claude_pid": true, "CLAUDE_CODE_SESSION_ID_present": true, "CLAUDE_CODE_SESSION_ID_equals_payload_session_id": true, "CLAUDE_PROJECT_DIR_equals_payload_cwd": true, "PWD_equals_payload_cwd": false}, "payload": {"session_id":"159b556e-eb7e-4cbe-b303-efcc8f5d08a5","transcript_path":"/root/.claude/projects/-tmp-shp-lpg-proc-vpBd05-real-repo/159b556e-eb7e-4cbe-b303-efcc8f5d08a5.jsonl","cwd":"/tmp/shp-lpg-proc.vpBd05/real/repo", ...}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| ancestry `hook → sh → claude` | process chain | always (24/24) | `python3` → `sh` (`/bin/sh -c <command>`, exe `/usr/bin/dash`) → `claude` | The hook's **grandparent** is the owning claude. There is a `/bin/sh -c` in between |
| ancestors above claude | chain | always | A/B/D: `timeout, bash, bash, timeout, bash, claude, bash, tmux: server`; C: `tmux: server` (ppid 1) | A/B/D ran nested under another Claude Code session. **The nearest claude ancestor is the owner; a second claude further up is the launcher** |
| env `CLAUDE_PID` | string | always (24/24) | equals the owning claude pid in 24/24 | Set by claude for its hook children. Its own environ does not have it (previous schema) |
| env `CLAUDE_CODE_SESSION_ID` | string | always (24/24) | equals payload `session_id` in 24/24 (A, B with `--resume`, C, D) | |
| env `CLAUDE_PROJECT_DIR` | string | always | equals payload `cwd` in 24/24 (physical path) | |
| env `PWD` | string | always | logical path `…/link/repo`; ≠ payload `cwd` in 24/24 | Inherited, not reset |
| env `CLAUDE_CODE_ENTRYPOINT` | string | always | `sdk-cli` (`-p`), `cli` (interactive) | |
| env `CLAUDE_ENV_FILE` | string | sometimes | `SessionStart` only | name only recorded |
| env `COLUMNS`, `LINES` | string | sometimes | interactive (C) only | |
| env `CLAUDE_CODE_MESSAGING_SOCKET`, `…_TOKEN` | string | sometimes | absent from `SessionEnd` hook env (A, B, D, C) | names only |

**Variants and edge cases:**
- The hook's own env carries both ids, so hookd can stamp `claude_pid` onto the frame without walking `/proc`. The ancestry walk is the fallback, and it must match `exe` rather than `comm` (see the first schema).
- cc10x confound: with `"enabledPlugins": {"cc10x@cc10x": false}` the stream-json `init` reported `plugins: []` and the only `hook_started` event was our `SessionStart:startup` (or `SessionStart:resume`) (`captures/proc-A-stream.jsonl`, `proc-B-stream.jsonl`, `proc-D-stream.jsonl`). No cc10x hooks fired.

**Spec alignment:** spec lines 900–906 (hookd.py) read stdin and forward it without any process identity. That is aligned with the payload (the payload carries `session_id`). Gap: the pid needed for liveness (see the `/proc/<pid>/stat` schema) is free in the hook env as `CLAUDE_PID` (`captures/proc-hooks.jsonl`), and the spec never mentions it.

## pid ↔ session_id linkage: `~/.claude/sessions/<pid>.json` `procStart` = `/proc/<pid>/stat` field 22

- **Produced by:** Claude Code 2.1.270 (registry file) + Linux procfs
- **Consumed by:** §8 lines 881 and 926–927 (register attached sessions), D1, D24 liveness, M1
- **Probe:** `probe_proc.sh` (`sessiond_sim.py` joins SO_PEERCRED → /proc → registry per hook frame); `probe_print_registry.sh` (does `-p` register?). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_proc.sh && bash docs/probes/2026-09-14-schemas/linux-process-git/probe_print_registry.sh`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `captures/proc-peercred.jsonl`, one frame from session C)
```json
{"peercred": {"pid": 4049200, "uid": 0, "gid": 0}, "walk": [{"pid": 4049200, "comm": "python3", "ppid": 4049199}, {"pid": 4049199, "comm": "sh", "ppid": 4049158}, {"pid": 4049158, "comm": "claude", "ppid": 4049157}], "claude_pid": 4049158, "claude_stat_starttime": 544014506, "claude_start_epoch_s": 1789402889.06, "registry": {"sessionId": "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "procStart": "544014506", "startedAt": 1789402898892, "pid": 4049158}, "walk_ms": 0.24, "payload_session_id": "159b556e-eb7e-4cbe-b303-efcc8f5d08a5", "payload_event": "SessionStart", "payload_bytes": 453}
```
A print-mode session's registry file (trimmed; full capture: `captures/proc-A-registry.json`)
```json
    "pid": 4048575,
    "sessionId": "bf3b6fd8-3e12-42de-b62a-02535a996554",
    "cwd": "/tmp/shp-lpg-proc.vpBd05/real/repo",
    "startedAt": 1789402841533,
    "procStart": "544009686",
...
    "kind": "interactive",
    "entrypoint": "sdk-cli",
...
    "tmux": "main:@0.%0",
    "messagingSocketPath": "/run/user/0/cc-socks/4048575.sock",
    "name": "repo-ce",
    "nameSource": "derived",
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| registry `pid` | number | always | = file name = `/proc` pid | |
| registry `procStart` | string | always | equals `/proc/<pid>/stat` field 22 in 24/24 frames (4 distinct processes) | Join key `(pid, procStart)` guards against pid reuse |
| registry `startedAt` | epoch ms | always | +0.67 s (A), +0.72 s (D), +9.83 s (C, time spent in the trust dialog) after `btime + starttime/100` | **Not process start**; roughly registration time |
| registry `sessionId` | uuid | always | = hook payload `session_id` in 24/24 | With `--resume` (B) the same id, new pid and new `procStart` |
| registry `kind` / `entrypoint` | string | always | `-p`: `interactive` / `sdk-cli` (6 files); TUI: `interactive` / `cli` | `kind` does not distinguish print mode |
| registry `tmux` | string | sometimes | `lpgprobe:@0.%0` (C); `main:@0.%0` for `-p` runs that inherited `TMUX` (A, `print-registry-*-inherited.json`); absent with `env -i` | **No socket name.** For A it names the launching session's pane, not a pane A owns |
| registry `bridgeSessionId` | string | sometimes | C only | |
| SO_PEERCRED walk | | always (24/24) | 0.22–1.04 ms | with hook waiting for a 1-byte ack |

**Variants and edge cases:**
- **Print-mode (`-p`) sessions DO write the registry file** in 2.1.270: 4/4 in `captures/print-registry.txt` (text and stream-json output, inherited and `env -i` env), plus A and D (`proc-meta.txt`, `proc-A-registry.json`, `proc-D-registry.json`) and B (`registry` non-null in `proc-peercred.jsonl`). The file is deleted on exit in 4/4 (`after_exit_registry_file=none`). This contradicts `docs/probes/2026-09-14-schemas/transcripts/SECTION.md` ("`-p` sessions never write one").
- In the recorded run the registry file was still present when the interactive session's `SessionEnd` hook connected (`proc-peercred.jsonl`, last line). An earlier run of the same probe, whose captures were overwritten and are **not** in evidence, saw `"registry": null` at that point. Treat the ordering as racy and do not read the registry at `SessionEnd`.
- A launcher's `tmux` can leak into the registry of a child session (A above), so the `tmux` field is not proof of ownership.

**Spec alignment:** the spec has no pid/registry linkage at all. Lines 926–927 (self-registration on the first turn) miss running-at-install sessions, as the transcripts surface already recorded (that behaviour was not re-probed here). This surface adds that `(pid, procStart)` is the stable key joining the hook env (`CLAUDE_PID`), `/proc` and the registry (`captures/proc-peercred.jsonl`).

## Unix domain socket at mode 0600 + `SO_PEERCRED`

- **Produced by:** Linux 6.8 AF_UNIX via CPython 3.12.3 `socket`
- **Consumed by:** §5 line 312 (hookd→sessiond UDS 0600), §13 line 2044 ("Both Unix sockets at mode 0600"), §15 line 2219 (`$XDG_RUNTIME_DIR/shepherd/` mode 0700), D37, M1
- **Probe:** `probe_socket.py`; live use in `sessiond_sim.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/linux-process-git/probe_socket.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/socket.txt`)
```text
## 1. file modes (stat)
srwxr-xr-x 755 socket root:root /tmp/shp-lpg-sock.mvu8empc/plain.sock
srw------- 600 socket root:root /tmp/shp-lpg-sock.mvu8empc/sessiond.sock
drwx------ 700 directory root:root /tmp/shp-lpg-sock.mvu8empc/shepherd
srw------- 600 socket root:root /tmp/shp-lpg-sock.mvu8empc/shepherd/sessiond.sock
...
## 2. SO_PEERCRED
getsockopt raw bytes: a3c53d000000000000000000 len 12
peer (pid, uid, gid): (4048291, 0, 0) | Popen child pid: 4048291 | match: True
socket.SO_PEERCRED constant: 17 | hasattr(socket,'SCM_CREDENTIALS'): True
peer exited BEFORE accept(): SO_PEERCRED pid = 4048292 | child pid: 4048292 | /proc/<pid> exists now: False

## 3. connect as uid nobody (runuser -u nobody)
plain.sock (umask 022 default): PermissionError [Errno 13] Permission denied
sessiond.sock (0600): PermissionError [Errno 13] Permission denied
0600 sock inside 0700 dir: PermissionError [Errno 13] Permission denied

## 4. sun_path length limit
path len 107 bytes: bind ok
path len 108 bytes: OSError: AF_UNIX path too long
...
connect as nobody to abstract name: connected
...
connect to stale path: ConnectionRefusedError: [Errno 111] Connection refused
re-bind same path without unlink: OSError: [Errno 98] Address already in use
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| socket mode | st_mode | always | umask 0177 at `bind()` → `srw-------` (0600); default umask 022 → 0755 | Set umask before `bind()`; there is no chmod window |
| `SO_PEERCRED` | 12 bytes `struct ucred {pid,uid,gid}` (`"3i"`) | always | pid matched the connecting child's pid | `socket.SO_PEERCRED == 17` |
| peer pid after the peer exited | int | always | still returned; `/proc/<pid>` gone | **Credentials are captured at `connect()`.** Walking `/proc` from them races the hook's exit |
| other-uid connect | errno | always | `EACCES` for 0600, 0755 (no `w`) and 0600-in-0700 | Connecting needs write permission on the socket inode |

**Variants and edge cases:**
- `sun_path` holds at most 107 bytes plus NUL. `/run/user/0/shepherd/sessiond.sock` is 34 bytes. A deep path like the evidence folder would fail.
- An abstract-namespace socket (`\0name`) has no file mode, and uid `nobody` connected to it. Do not use one.
- A stale socket file after a crash gives `ECONNREFUSED` to clients and `EADDRINUSE` on re-bind. sessiond must unlink before bind.
- In the live probe, a hook that waited for a 1-byte ack let the listener walk `/proc` in 0.22–1.04 ms (`captures/proc-peercred.jsonl`), inside hookd's 250 ms budget (spec line 312).

**Spec alignment:** aligned. Spec line 2044 (sockets 0600) and line 2219 (dir 0700) are achievable and effective against another uid. Addition: the spec's hookd (lines 900–906) does not wait for any reply. A sessiond that wants `SO_PEERCRED` → `/proc` must read `/proc` before the hook exits, or rely on `CLAUDE_PID` carried in the frame.

## systemd user manager, transient unit `Restart=always`, and journal lines

- **Produced by:** systemd 255 (255.4-1ubuntu8.17), user manager `user@0.service`
- **Consumed by:** §15 lines 2209–2226 (two user units, `Restart=always`, linger), D39, §7 migrations line 860, M6 packaging (out of M1–M4 scope, but D39 constrains M1 daemons)
- **Probe:** `probe_systemd_xdg.sh` (one transient unit, stopped and reset-failed; no unit files written; linger untouched). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/systemd-xdg.txt`)
```text
## systemctl --user with XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS removed
Failed to connect to bus: No medium found
rc=1
...
## env -i systemctl --user --machine=root@.host
Failed to connect to bus: No medium found
rc=1

## env -i with XDG_RUNTIME_DIR=/run/user/$uid only
running
rc=0
...
Running as unit: shp-lpg-probe-1789402661.service; invocation ID: bb57f6bcfa4240bfb71dbd9e6930297a
systemd-run rc=0
t+01s MainPID=4047993 Result=success NRestarts=0 ExecMainStatus=0 ActiveState=active SubState=running 
t+02s MainPID=0 Result=exit-code NRestarts=0 ExecMainStatus=1 ActiveState=activating SubState=auto-restart 
t+03s MainPID=4048010 Result=success NRestarts=1 ExecMainStatus=0 ActiveState=active SubState=running 
...
t+10s MainPID=0 Result=exit-code NRestarts=5 ExecMainStatus=1 ActiveState=failed SubState=failed 
...
Restart=always
RestartUSec=500ms
...
StartLimitIntervalUSec=10s
StartLimitBurst=5
StartLimitAction=none
...
2026-09-14T16:17:41+00:00 finops-mitm-lab systemd[1014041]: Started shp-lpg-probe-1789402661.service - shepherd schema probe (throwaway).
2026-09-14T16:17:41+00:00 finops-mitm-lab (sh)[4047993]: shp-lpg-probe-1789402661.service: Invalid environment variable name evaluates to an empty string: DBUS_SESSION_BUS_ADDRESS-<unset>, XDG_CONFIG_HOME-<unset>, XDG_DATA_HOME-<unset>, XDG_RUNTIME_DIR-<unset>
...
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Main process exited, code=exited, status=1/FAILURE
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Failed with result 'exit-code'.
2026-09-14T16:17:42+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Scheduled restart job, restart counter is at 1.
...
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Scheduled restart job, restart counter is at 5.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Start request repeated too quickly.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: shp-lpg-probe-1789402661.service: Failed with result 'exit-code'.
2026-09-14T16:17:49+00:00 finops-mitm-lab systemd[1014041]: Failed to start shp-lpg-probe-1789402661.service - shepherd schema probe (throwaway).
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `systemctl --user` reachability | exit code + stderr | always | works with inherited env; `No medium found` rc=1 without `XDG_RUNTIME_DIR` (also `env -i`, also `--machine=root@.host`); works with only `XDG_RUNTIME_DIR=/run/user/0` | The one variable that matters is `XDG_RUNTIME_DIR` |
| `show -p` states | `Key=Value` lines | always | `active/running` → `activating/auto-restart` → … → `failed/failed` | `NRestarts` counts up to 5 |
| `StartLimitBurst` / `StartLimitIntervalUSec` | defaults | always | `5` / `10s` | With `Restart=always` a crash loop ends in `failed` after 5 restarts in 10 s |
| journal lines | `journalctl --user -u` short-iso | always | `Started …`, `Main process exited, code=exited, status=1/FAILURE`, `Scheduled restart job, restart counter is at N.`, `Start request repeated too quickly.` | Unit stdout lines are tagged `sh[<pid>]`. `journalctl _SYSTEMD_USER_UNIT=` in the system view returned `-- No entries --` |
| transient unit file | path | always | `/run/user/0/systemd/transient/shp-lpg-probe-1789402661.service` | Gone after `stop` + `reset-failed` (`LoadState=not-found`) |
| unit env names | list | always | `DBUS_SESSION_BUS_ADDRESS … HOME INVOCATION_ID JOURNAL_STREAM … PATH PWD SHELL SSH_AUTH_SOCK SYSTEMD_EXEC_PID USER XDG_DATA_DIRS XDG_RUNTIME_DIR` | No `XDG_DATA_HOME`/`XDG_CONFIG_HOME`; `PWD=/root` |

**Variants and edge cases:**
- systemd expands `${VAR-…}` and `$$` inside `ExecStart=` itself, before `/bin/sh` runs: `start pid=$ XDG_RUNTIME_DIR= …` plus the "Invalid environment variable name" warning. A unit file that passes shell syntax must write `$${VAR}`.
- `~/.config/systemd/user` does not exist on this host yet.
- The user's live Remote Control claude processes run in `user@0.service/tmux-spawn-*.scope` cgroups, which belong to the user manager (`captures/proc-A-snapshot.json` "others"). Not verified: what happens to them on logout with `Linger=no`. Logging out was not attempted.

**Spec alignment:**
- Spec lines 2215–2216 say `Restart=always`, and reality is that `Restart=always` alone gives up after 5 starts in 10 s: `Start request repeated too quickly.` → `failed` (`captures/systemd-xdg.txt`). The probe unit set `RestartSec=500ms` and exited 1 after about 1 s; the `StartLimitBurst=5` / `StartLimitIntervalUSec=10s` defaults were left unchanged. A daemon that crash-loops that fast ends in `failed` and is not restarted again. The spec should state the intended start-limit policy: `StartLimitIntervalSec=0` or a longer `RestartSec=` to keep retrying, or accept `failed`. For the migration refuse-to-start rules (spec lines 855–862), ending in `failed` may be the desired outcome, since it stops a futile loop. Either way, it is a choice the spec does not make.
- Spec lines 2223–2224 (`shepherd install` checks `loginctl`) are aligned. But `shepherd install` and any `systemctl --user` call fail with `Failed to connect to bus: No medium found` when `XDG_RUNTIME_DIR` is unset. This was observed with `env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS` and with `env -i`; cron, `su` and ssh command contexts were not probed. The spec does not mention this dependency.

## `loginctl show-user` (Linger)

- **Produced by:** systemd-logind 255
- **Consumed by:** §15 lines 2221–2226, D39 ("lingering required"), principle 4
- **Probe:** `probe_systemd_xdg.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14 (read-only; linger was not changed)

**Real example** (trimmed; full capture: `captures/systemd-xdg.txt`)
```text
## loginctl
UID USER LINGER STATE
  0 root no     active

1 users listed.
UID=0
Name=root
RuntimePath=/run/user/0
Service=user@0.service
Slice=user-0.slice
State=active
Linger=no
linger dir: 
logind KillUserProcesses: #KillUserProcesses=no 
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `Linger` | `yes`/`no` | always | `no` | `/var/lib/systemd/linger/` is empty |
| `State` | enum | always | `active` | (`lingering` is the value with no login session but linger on; not observed) |
| `RuntimePath` | path | always | `/run/user/0` | tmpfs `mode=700`, `size=391156k` |
| `Service` | unit | always | `user@0.service` | |
| `KillUserProcesses` | logind.conf | always | commented default `no` | Login-scope processes survive logout; the user manager itself does not without linger |

**Variants and edge cases:** `-p Name -p UID …` output order follows systemd's order, not the order of the `-p` arguments (`UID` printed before `Name`).

**Spec alignment:** aligned. Linger is off on the target host, exactly the case spec lines 2221–2226 guard against. `shepherd install` will have to prompt.

## XDG base directories (this shell vs systemd user manager)

- **Produced by:** pam_systemd / ssh login session; systemd 255 user manager
- **Consumed by:** §15 lines 2213–2219, §7 logs line 830 (`$XDG_DATA_HOME/shepherd`), §13 line 2049 (`$XDG_CONFIG_HOME/shepherd/`), D39, M1 (daemons create these dirs)
- **Probe:** `probe_systemd_xdg.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_systemd_xdg.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/systemd-xdg.txt`)
```text
## this shell: XDG values
XDG_RUNTIME_DIR=/run/user/0
XDG_DATA_HOME=<unset>
XDG_CONFIG_HOME=<unset>
XDG_STATE_HOME=<unset>
XDG_CACHE_HOME=<unset>
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
XDG_SESSION_ID=10905
XDG_SESSION_CLASS=user
shell_is_login: no
...
XDG_DATA_HOME -> /root/.local/share (default)
XDG_CONFIG_HOME -> /root/.config (default)
XDG_RUNTIME_DIR -> /run/user/0
...
## user manager environment (names; XDG_*/DBUS values)
...
XDG_RUNTIME_DIR=/run/user/0
XDG_DATA_DIRS=/usr/local/share/:/usr/share/:/var/lib/snapd/desktop
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `XDG_DATA_HOME` | path | never (shell, user manager, unit) | | Must default to `~/.local/share` |
| `XDG_CONFIG_HOME` | path | never | | Must default to `~/.config` |
| `XDG_STATE_HOME`, `XDG_CACHE_HOME` | path | never | | |
| `XDG_RUNTIME_DIR` | path | shell: yes; user manager: yes; unit env: yes; hook env: yes (`/run/user/0`); `env -i`: no | `/run/user/0` | No default exists. Claude Code uses it as well (registry `messagingSocketPath: /run/user/0/cc-socks/<pid>.sock`) |
| `DBUS_SESSION_BUS_ADDRESS` | string | shell, user manager, unit | `unix:path=/run/user/0/bus` | |

**Variants and edge cases:**
- This shell is a non-login shell, yet it has `XDG_RUNTIME_DIR` because it inherits from an ssh login session (`XDG_SESSION_ID=10905`). A claude launched with a scrubbed environment would presumably not pass it to hookd. This is inferred and was not provoked: all 24 captured hook envs had `XDG_RUNTIME_DIR=/run/user/0`, including session D, because the `env -i` launch passed it explicitly.
- `/run/user/0` is a tmpfs that logind creates per user. Without linger it is removed when the last session ends, which also removes any socket placed in it. Inferred from logind docs, not provoked here.

**Spec alignment:** spec lines 2217–2219 are aligned for the data and config paths, as long as the implementation applies the XDG defaults, because neither variable is ever set on this host. Line 2219 (`$XDG_RUNTIME_DIR/shepherd/`): hookd runs inside the claude process's environment, not under systemd. hookd should derive `/run/user/<uid>` when `XDG_RUNTIME_DIR` is absent, otherwise it cannot find the socket. The spec gives no fallback (`captures/systemd-xdg.txt`, `env -i` case). The hookd failure itself is inferred and was not observed (see the edge case above).

## Credential store availability (Secret Service vs 0600 file)

- **Produced by:** host packages / D-Bus session bus (dbus-daemon, `busctl`)
- **Consumed by:** §13 line 2049 ("Which one this host has is recorded in data-schemas.md"), D2/D39 `Credentials` seam, M4 (credential_ref), M4.5
- **Probe:** `probe_secrets_runtime.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`
- **Status:** partially verified. Availability was verified live 2026-09-14: this host has no Secret Service, and the 0600-file fallback works. The Secret Service driver path (`secret-tool` store/lookup/clear, locked collection under a headless user service) is not verifiable here, because no keyring is installed and nothing was installed.

**Real example** (trimmed; full capture: `captures/secrets-runtime.txt`)
```text
secret-tool                  <not found>
gnome-keyring-daemon         <not found>
kwalletd5                    <not found>
kwalletd6                    <not found>
...
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/0/bus
srw-rw-rw- 1 root root 0 Jul 27 14:55 /run/user/0/bus
...
$ busctl --user list | grep -i -E 'secret|keyring|kwallet'
<no secret/keyring/kwallet names on the session bus, including activatable>
$ busctl --user call org.freedesktop.secrets /org/freedesktop/secrets org.freedesktop.DBus.Peer Ping
Call failed: The name org.freedesktop.secrets was not provided by any .service files
[rc=1]
...
store/lookup round trip: SKIPPED (secret-tool absent or no org.freedesktop.secrets on the session bus)
...
drwx------ 700 root:root <tmpdir>/shepherd
-rw------- 600 root:root <tmpdir>/shepherd/credentials.json
nobody read: cat: <tmpdir>/shepherd/credentials.json: Permission denied
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `secret-tool` (libsecret-tools) | binary | never | not installed | |
| keyring daemons | binary | never | gnome-keyring, kwalletd5/6, pass, keyctl: none | |
| D-Bus session bus | socket | always | `/run/user/0/bus`, owned by the user manager (PID 1014041) | |
| `org.freedesktop.secrets` | bus name | never | not owned and not activatable | |
| Python `secretstorage` / `keyring` | module | never | `ModuleNotFoundError` | |
| 0600 file fallback | file mode | always | `-rw-------` in a `drwx------` dir; `nobody` denied | |

**Variants and edge cases:** not verified: a host that has gnome-keyring. Under a systemd user service with no graphical login, the default collection is normally locked. Nothing here could exercise that.

**Spec alignment:** aligned. Spec line 2049's fallback is the driver this host needs: **this host has no Secret Service; `Credentials` uses the mode-0600 file under `$XDG_CONFIG_HOME/shepherd/` (defaulting to `~/.config/shepherd/`)**.

## Runtime toolchain (Python, SQLite, venv/pip, Node/TypeScript)

- **Produced by:** Ubuntu 24.04.4 packages on this host
- **Consumed by:** §5 Stack lines 404–411 (Python 3.12, SQLite WAL, `claude-agent-sdk`, `tsc`), principle 6 line 168 (`mypy --strict`), §7 line 570 ("a raw `sqlite3` shell"), §15 line 2209 (`shepherd install` creates a venv), D26, M1–M4
- **Probe:** `probe_secrets_runtime.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_secrets_runtime.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/secrets-runtime.txt`)
```text
python3                      /usr/bin/python3
Python 3.12.3
...
sqlite3.sqlite_version: 3.45.1
journal_mode=WAL: [('wal',)]
json1 json_extract: [(2,)]
jsonb (3.45+): [('blob',)]
CHECK enum: []
STRICT table (3.37+): []
RETURNING (3.35+): [(1, 'running')]
conditional UPDATE rowcount path: [(1,)]
compile_options (FTS5/JSON): [('ENABLE_FTS5',), ('THREADSAFE=1',)]
$ sqlite3 (CLI)
sqlite3                      <not found>
$ python3 -m pip --version
/usr/bin/python3: No module named pip
[rc=1]
...
$ python3 -m venv <tmp>/with-pip
The virtual environment was not created successfully because ensurepip is not
available.  On Debian/Ubuntu systems, you need to install the python3-venv
package using the following command.
...
[rc=1]
$ python3 -m venv --without-pip <tmp>/nopip
[rc=0]
...
node                         <not found>
nodejs                       <not found>
npm                          <not found>
npx                          <not found>
tsc                          <not found>
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| Python | version | always | 3.12.3 (`/usr/bin/python3 -> python3.12`); no 3.11/3.13 | matches spec |
| SQLite (Python module) | version | always | 3.45.1; WAL, JSON1, `jsonb`, STRICT, RETURNING, FTS5 all work | |
| `sqlite3` CLI | binary | never | | |
| pip / ensurepip | module | never | `No module named pip` / `ensurepip` | `python3-venv`, `python3.12-venv`, `python3-pip` not installed |
| `venv` | stdlib | sometimes | fails with pip (rc=1); `--without-pip` rc=0 | |
| pipx / uv / virtualenv / mypy | binary | never | | |
| node / npm / npx / tsc / corepack / bun / deno | binary | never | also absent in a login shell | `claude` is a 223,981,040-byte ELF (bundled runtime, no system node) |
| tmux / git | version | always | tmux 3.4, git 2.43.0 | |

**Variants and edge cases:** none beyond the table. Nothing was installed.

**Spec alignment:**
- Spec line 2209 says "`shepherd install` creates a venv", and reality is that `python3 -m venv` fails on this host (no `ensurepip`). Only `--without-pip` works, and then nothing can install `claude-agent-sdk` (spec line 406) without apt `python3.12-venv` or a bootstrap (`captures/secrets-runtime.txt`).
- Spec line 411 says "no bundler beyond `tsc`", and reality is that no node, npm or tsc is installed. The frontend cannot be built on this host as-is. The spec does not say whether the build runs on the target host or ships prebuilt JS, so this is an unstated host prerequisite rather than a contradiction.
- Host notes, not spec misalignments: `mypy` (principle 6, line 168) is not installed. That is a development tool, and it becomes installable once the venv/pip gap above is fixed. There is also no `sqlite3` CLI. Line 570 is a readability rationale for TEXT enums and does not require the CLI. The stdlib `python3 -m sqlite3` shell exists in 3.12, but that was not captured here. SQLite features for §7 (WAL, CHECK, JSON, STRICT, RETURNING) are aligned.

## `git rev-parse` outputs for cwd → repo binding

- **Produced by:** git 2.43.0
- **Consumed by:** §7 `repo.root_path` line 632 ("absolute, canonicalized, UNIQUE. The longest-prefix key"), `workspace.root_path` line 621 (`discover_repos`), §8 line 881, §13 line 2113, D22, M1 (discovery and binding)
- **Probe:** `probe_git.sh` (throwaway repos in `mktemp -d`; read-only on `/root/Shepherd`, `/root/src/cc10x-qa`). Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/git.txt`)
```text
$ git -C /root/Shepherd rev-parse --show-toplevel --git-common-dir --git-dir --is-bare-repository --is-inside-work-tree
/root/Shepherd
.git
.git
false
true
[rc=0]
...
$ git -C /root/Shepherd/docs/specs rev-parse --show-toplevel --show-prefix --git-common-dir
/root/Shepherd
docs/specs/
../../.git
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/src) git rev-parse --path-format=absolute --show-toplevel --git-common-dir --git-dir
/tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1
/tmp/shp-lpg-git.YD7ktR/main/.git
/tmp/shp-lpg-git.YD7ktR/main/.git/worktrees/PROJ-1
[rc=0]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/bare.git rev-parse --show-toplevel
fatal: this operation must be run in a work tree
[rc=128]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/plain/dir rev-parse --show-toplevel
fatal: not a git repository (or any of the parent directories): .git
[rc=128]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main/vendor/inner/deep) git rev-parse --show-toplevel --show-superproject-working-tree
/tmp/shp-lpg-git.YD7ktR/main/vendor/inner
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/main/mods/sub) git rev-parse --show-toplevel --show-superproject-working-tree --path-format=absolute --git-common-dir
/tmp/shp-lpg-git.YD7ktR/main/mods/sub
/tmp/shp-lpg-git.YD7ktR/main
/tmp/shp-lpg-git.YD7ktR/main/.git/modules/mods/sub
[rc=0]
...
$ (cd /tmp/shp-lpg-git.YD7ktR/link-to-main/src) git rev-parse --show-toplevel --show-cdup
/tmp/shp-lpg-git.YD7ktR/main
../
[rc=0]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/foreign rev-parse --show-toplevel
fatal: detected dubious ownership in repository at '/tmp/shp-lpg-git.YD7ktR/foreign'
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `--show-toplevel` | abs path, one line | sometimes | work tree root, **physical path** (symlink resolved) | rc=128 in a bare repo, inside `.git`, outside a repo, or on dubious ownership |
| `--git-common-dir` | path | always in a repo | **relative** by default (`.git`, `../../.git`); absolute in a linked worktree (`…/main/.git`) | Use `--path-format=absolute` (git ≥ 2.31) |
| `--git-dir` | path | always in a repo | `.git` at the root; absolute `…/main/.git` from a subdir (`src/pkg`); `…/main/.git/worktrees/PROJ-1` in a worktree; `…/.git/modules/mods/sub` in a submodule | Relative or absolute depending on cwd; use `--path-format=absolute` |
| `--show-prefix` | rel path + `/` | always in a work tree | `docs/specs/`, `src/pkg/` | |
| `--show-superproject-working-tree` | abs path or empty | sometimes | submodule → `…/main`; nested plain repo → no line | A nested non-submodule repo does not know its parent |
| `--is-bare-repository` | `true`/`false` | always | | |
| multi-flag output | one line per flag, in flag order | always | | Empty values print no line, so line position is not stable |

**Variants and edge cases:**
- Nested repo: innermost toplevel wins (`…/main/vendor/inner`). The outer repo sees it as untracked `?? vendor/`.
- Symlink: running from `…/link-to-main/src` returns `…/main`, the same physical form Claude Code puts in hook `cwd` and `/proc/<pid>/cwd` (`captures/proc-cwd-forms.txt`: `rev-parse --show-toplevel (from logical cwd): /tmp/shp-lpg-proc.vpBd05/real/repo`).
- A repo owned by another uid fails with `detected dubious ownership` rc=128 unless `-c safe.directory=<path>` is given.
- No commits: `rev-parse HEAD` rc=128 while `--show-toplevel` works.

**Spec alignment:**
- Spec line 632 ("canonicalized") is aligned if canonicalization is `realpath`. Hook `cwd`, `/proc` cwd and `rev-parse` all return physical paths. Only `PWD` is logical (`captures/proc-hooks.jsonl`).
- D22 (line 126, "resolves nested repos to the innermost") matches git's own behavior (aligned).
- Mismatch: D22 binds a session by longest-prefix of `cwd` against registered `root_path`s. A linked worktree reports `--show-toplevel` = the worktree path and lives outside the repo root. The spec's own layout (line 1374, `<repo>-wt/<KEY>/`, a **sibling** of `<repo>`) never prefix-matches, so a worker session in a worktree gets `repo_id = null`. `--git-common-dir --path-format=absolute` (→ `<repo>/.git`) is the key that maps a worktree back to its repo (`captures/git.txt` §D). This bites M1 as soon as a user runs claude in a hand-made worktree, before M5 creates any. The spec is also internally inconsistent here: Appendix A (lines 2426 and 2431) shows a queue-worker session with `repo_id: rep_b2` (`reporting-service`) and `cwd: …/reporting-service-wt/PROJ-81711`, a binding that longest-prefix matching cannot produce. An owned session could have `repo_id` set at spawn, but `repos_touched` (§7, from `FileChanged` paths) and attached sessions have no such escape.

## `git remote get-url` forms (`repo.vcs_remote`)

- **Produced by:** git 2.43.0
- **Consumed by:** §7 `repo.vcs_remote` line 633 ("null for non-git"), Appendix A line 2408, §13 redaction lines 2052–2053, D22, M1
- **Probe:** `probe_git.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/git.txt`)
```text
$ git -C /root/Shepherd remote get-url origin
error: No such remote 'origin'
[rc=2]
...
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url origin
/tmp/shp-lpg-git.YD7ktR/origin-src
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-ssh
git@github.com:example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-sshurl
ssh://git@github.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gh-https
https://github.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url gl-https-noext
https://gitlab.com/example-org/sub-group/example-repo
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url with-cred
https://oauth2:FAKE_TOKEN_NOT_REAL@gitlab.com/example-org/example-repo.git
[rc=0]
$ git -C /tmp/shp-lpg-git.YD7ktR/main remote get-url rewritten
git@github.com:example-org/example-repo.git
[rc=0]
(config value vs get-url for the insteadOf remote)
$ git -C /tmp/shp-lpg-git.YD7ktR/main config --get remote.rewritten.url
gh:example-org/example-repo.git
[rc=0]
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| stdout | one URL line | sometimes | scp-like `git@host:org/repo.git`; `ssh://git@host/org/repo.git`; `https://host/org/repo(.git)`; nested groups `org/sub-group/repo`; local path | No normalization. The same repo has several spellings |
| rc | int | always | 0; **2** with `error: No such remote '<name>'` | `/root/Shepherd` has no remote |
| userinfo in URL | string | sometimes | `oauth2:FAKE_TOKEN_NOT_REAL@` returned verbatim | Secrets can live in the URL |
| `insteadOf` | config | sometimes | `get-url` returns the rewritten URL; `config --get` returns the raw `gh:` alias | |

**Variants and edge cases:** a bare repo's `get-url origin` works (a local path from `clone --bare`). A repo may have many remotes, and git has no notion of which one is canonical. `/root/src/cc10x-qa` has `origin` = an https GitHub URL (`captures/git.txt` §A).

**Spec alignment:**
- Spec line 633 says `vcs_remote` is "null for non-git", and reality is that it is also absent for a git repo with no remote (rc=2, `/root/Shepherd` itself) and ambiguous with several remotes. The spec does not say which remote, or that `get-url` expands `insteadOf`.
- §13 lines 2052–2053 apply redaction only to `action_log.args` and `work_item.raw`, and reality is that `remote get-url` returns embedded credentials verbatim (`https://oauth2:<token>@…`). Storing that raw in `repo.vcs_remote`, which the UI and the agent's context can read, would leak a token (`captures/git.txt` §B).

## `git worktree list --porcelain` and a linked worktree's `.git` file

- **Produced by:** git 2.43.0
- **Consumed by:** D22 (lazy per-(work item, repo) worktrees, revises D15), §10 worker loop line 1374, §11 `local_destructive` "remove worktree" line 1631, §7 `session.worktree_path` line 665, M1 (discovery/binding of existing worktrees), M5
- **Probe:** `probe_git.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `captures/git.txt`)
```text
$ cat /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/.git
gitdir: /tmp/shp-lpg-git.YD7ktR/main/.git/worktrees/PROJ-1
[file type: regular file]
...
$ cat .git/worktrees/PROJ-1/gitdir
/tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1/.git
$ cat .git/worktrees/PROJ-1/commondir
../..
$ cat .git/worktrees/PROJ-1/HEAD
ref: refs/heads/feat/PROJ-1
$ cat .git/worktrees/locked/locked
probe lock reason

$ git -C /tmp/shp-lpg-git.YD7ktR/main worktree list --porcelain
worktree /tmp/shp-lpg-git.YD7ktR/main
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/main

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/PROJ-1
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/PROJ-1

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/detached
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
detached

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/gone
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/gone
prunable gitdir file points to non-existent location

worktree /tmp/shp-lpg-git.YD7ktR/main-wt/locked
HEAD 03f9ec10bdc1ab0f9b790e3ea489e6eb5ac20f9a
branch refs/heads/feat/locked
locked probe lock reason

[rc=0]
...
worktree /tmp/shp-lpg-git.YD7ktR/bare.git
bare
...
worktree /tmp/shp-lpg-git.YD7ktR/noremote
HEAD 0000000000000000000000000000000000000000
branch refs/heads/main
...
fatal: cannot remove a locked working tree, lock reason: probe lock reason
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `worktree <abs path>` | line, starts a record | always | main tree first, then linked trees sorted by path | Records are separated by a blank line |
| `HEAD <40-hex>` | line | always except bare | all zeros in a repo with no commits | |
| `branch refs/heads/<name>` | line | sometimes | `refs/heads/main`, `refs/heads/feat/PROJ-1` | Full ref, not the short name |
| `detached` | bare keyword | sometimes | linked `--detach` tree; main tree after `checkout --detach` | Replaces `branch` |
| `bare` | bare keyword | sometimes | bare repo record (no `HEAD`) | |
| `locked [<reason>]` | line | sometimes | `locked probe lock reason` | `worktree remove` refuses it (rc=128) |
| `prunable <reason>` | line | sometimes | `prunable gitdir file points to non-existent location` | Directory deleted by hand; still listed until `worktree prune` |
| `-z` | NUL terminators | option | `worktree …\0HEAD …\0branch …\0\0` | Use `-z` for paths containing newlines |
| worktree `.git` | **regular file** | always for linked worktrees and submodules | `gitdir: <abs path>/.git/worktrees/<name>`; submodule: `gitdir: ../../.git/modules/mods/sub` (relative) | A discovery walk that tests `isdir(".git")` misses both |
| `.git/worktrees/<name>/{gitdir,commondir,HEAD,locked}` | files | always (`locked` sometimes) | back-pointer `…/main-wt/PROJ-1/.git`; `../..`; `ref: refs/heads/feat/PROJ-1` | |

**Variants and edge cases:**
- The same list is printed from inside any linked worktree (`git -C …/main-wt/PROJ-1 worktree list --porcelain` gives an identical record set).
- A worktree of a bare repo: `rev-parse --show-toplevel` = `…/bare-wt/main2`, `--git-common-dir` = `…/bare.git`.
- A detached worktree: `symbolic-ref -q --short HEAD` rc=1 with no output, and `rev-parse --abbrev-ref HEAD` prints `HEAD`.
- The worktree name is the basename (`PROJ-1`). Two worktrees with the same basename get a suffix. Not provoked here.

**Spec alignment:** see the `git rev-parse` schema: the `<repo>-wt/<KEY>/` layout (line 1374) is outside `<repo>`, so longest-prefix binding (D22, lines 126 and 632) cannot bind worktree sessions. The binding must also accept `worktree list --porcelain` paths or `--git-common-dir` as a repo alias. Discovery (line 621, `discover_repos`) must treat a `.git` **file** as a repo marker (`captures/git.txt` §D, §I). Also, Appendix A (lines 2399–2432) uses macOS paths (`/Users/noamsalit/Git/...`) for a platform that D39 (line 143) fixed as Linux.
