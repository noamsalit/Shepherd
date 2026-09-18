# Surface: gap-fill (claims no other surface probed)

Every capture on this surface was made on 2026-09-14 on Linux 6.8.0-117-generic with `claude --version` = `2.1.270 (Claude Code)` and `tmux 3.4`, unless a block names another binary (the Agent-SDK-bundled CLI `2.1.259`). Each capture folder has a `versions.txt`, or a `meta.json` with `claude_version` for the SDK runs.

**Evidence folder:** `docs/probes/2026-09-14-schemas/gap-fill/`. Re-run any probe from the repo root.

| Capture folder | Script | Covers |
|---|---|---|
| `systemd-tmux-20260914T170532Z/` | `bash .../gap-fill/probe_systemd_tmux.sh` | tmux server cgroup under a systemd user unit; stop/restart survival; user-manager PATH; `claude` inside a unit |
| `tmux-env-20260914T173859Z/` | `bash .../gap-fill/probe_tmux_env.sh` | which environment a new pane receives |
| `tmux-naming-20260914T170739Z/` | `bash .../gap-fill/probe_tmux_naming.sh` | `:` and `.` in session names, `-t` resolution, `$TMUX` inside a pane |
| `tmux-attach-keys-20260914T170850Z/` | `bash .../gap-fill/probe_tmux_attach_keys.sh` | second client versus `resize-window`; raw key bytes into a pane (`keydump.py`) |
| `keys-claude-20260914T180105Z/` | `python3 .../gap-fill/probe_keys_claude.py` | what the Claude Code TUI does with those bytes |
| `interrupt-20260914T172251Z/`, `interrupt-real-20260914T172811Z/` | `python3 .../gap-fill/probe_interrupt.py [--real]` | Esc / C-c / SIGINT during a turn |
| `argv-20260914T173100Z/`, `argv-limits-20260914T173342Z/` | `python3 .../gap-fill/probe_argv.py`; `bash .../gap-fill/probe_argv_limits.sh` | brief as argv through `tmux new-session` |
| `effort-20260914T171533Z/` | `python3 .../gap-fill/probe_effort.py` | `--effort` values, what reaches the Messages API, hook `effort` |
| `sdk-server_info-20260914T171112Z/`, `sdk-server_info-syscli-20260914T171115Z/` | `<venv>/bin/python .../gap-fill/sdk_probe.py server_info [--cli PATH]` | `models[]` in the initialize response |
| `sdk-approval_timeout-20260914T171126Z/`, `sdk-approval_timeout-syscli-20260914T171129Z/` | `<venv>/bin/python .../gap-fill/sdk_probe.py approval_timeout [--cli PATH]` | `can_use_tool` blocking for 630 s |
| `transcript-append-20260914T175435Z/` | `python3 .../gap-fill/probe_transcript_append.py` | transcript append-only / whole-line check |
| `config-scopes-20260914T173908Z/` | `python3 .../gap-fill/probe_config_scopes.py` | hooks hot-added to a running session; user-scope hooks with `_shepherd_managed`; `claude mcp add -s user`; MCP permission prompt |
| `mcp-perm-p-20260914T174121Z/` | `python3 .../gap-fill/probe_mcp_perm_p.py` | permission-rule spellings and sources for an MCP tool in `-p` |
| `mcp-add-env-20260914T181206Z/` | `bash .../gap-fill/probe_mcp_add_env.sh` | `claude mcp add -e` argument order |
| `pidfd-pty-20260914T175854Z/` | `python3 .../gap-fill/probe_pidfd_pty.py` | pidfd exit observation of a non-child; Claude Code TUI under `pty.fork` |
| `lifecycle-end-20260914T175238Z/`, `autocompact-real-20260914T174911Z/` | `python3 .../gap-fill/probe_lifecycle_end.py`; `python3 .../gap-fill/probe_autocompact_real.py` | auto compaction, kill during compaction, `SessionEnd.reason` resume/logout |
| `elicitation-tui-20260914T174206Z/` | `python3 .../gap-fill/probe_elicitation_tui.py` | MCP elicitation in the TUI |
| `cross-version-resume-20260914T175737Z/` | `bash .../gap-fill/probe_cross_version_resume.sh` | resume across 2.1.259 and 2.1.270 |
| `websocket-20260914T171610Z/` | `python3 .../gap-fill/probe_websocket.py` | WebSocket libraries; stdlib RFC 6455 handshake |
| `binary-context-20260914T174348Z/` | `python3 .../gap-fill/extract_binary_context.py` | binary text around values that could not be provoked |
| `cc10x-check-20260914T180206Z/` | `bash .../gap-fill/check_cc10x.sh` | whether cc10x hooks fired in the real-config runs |

(`...` stands for `docs/probes/2026-09-14-schemas`.) Helpers: `gaplib.py` (tmux wrapper that always passes `-L shp-gap*`; `MockEnv`; `Tui`), `capture_hook.sh` (copied from `tmux-tui/`; appends raw stdin, event name, our UTC timestamp, claude pid, and process ancestry), `mock_api2.py` (scriptable local Messages API), `mcp_stub.py` (stdio MCP server standing in for `shepherd-mcp`), `keydump.py`, `redact_account.py`, `redact_transcript.py`, `verify_examples.py`.

**Probe hygiene.**
- **tmux.** Every call passed `-L shp-gap-*`. Servers were started under `env -i`. Teardown was `kill-server` on those sockets only, or `kill-session -t =<name>` in the naming probe. A final check showed "no server running" on every `shp-gap-*` socket. The user's `shepherd` socket was never addressed.
- **systemd.** Only transient units named `shp-gap-*` were used, and all were stopped afterwards.
- **Isolated backends.** "Mock" runs used `CLAUDE_CONFIG_DIR=<mktemp>/cfg`, a fake `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL=http://127.0.0.1:<port>` served by `mock_api2.py`. The CLI binary, its hooks, dialogs and transcripts are real. Only the model replies are scripted.
- **Real-API runs.** These used `claude-haiku-4-5-20251001` with the user's login, in `/tmp/shp-gap-*` directories: `systemd-tmux` (one `-p` turn), `interrupt-real`, `autocompact-real`, `cross-version-resume`, and `sdk-*`.
- **cc10x.** It was disabled in every throwaway settings file. It did not fire: `cc10x-check-20260914T180206Z/counts.txt` shows `cc10x_occurrences=0` in every real-config transcript, and each Stop `hookCount` is 1, which is our capture hook.
- **User settings untouched.** `~/.claude/settings.json` has sha256 `375e5322…` both before and after (`config-scopes-*/real-user-settings-sha256-{before,after}.txt`). The real-API runs added trust entries to `~/.claude.json`, which the rules allow.
- **Privacy.**
  - No content from the user's own transcripts was read or copied. The only files under `~/.claude/projects` that were read belong to the throwaway sessions above.
  - The Agent SDK initialize response carries `account` (email, organization); `redact_account.py` replaced those values with `<redacted>`.
  - A real-config transcript copy was reduced by `redact_transcript.py`, because attachments can carry the user's global instructions.
  - The host name that tmux prints in its status line was replaced with `<redacted: host name>`.
  - A mistake during the probe: one exploratory `pkill -f` matched only the probe's own shell. No other process was signalled.

---

## tmux server cgroup under a systemd user unit (`sessiond` stand-in)

- **Produced by:** tmux 3.4 (built with systemd scope support) started from a transient systemd 255 user unit; Linux 6.8 cgroup v2
- **Consumed by:** D14 (spec line 117), §9 LocalRunner table line 1139 "the tmux server is its own process", D39/§15 unit files lines 2209-2219; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/q1-cgstop.txt`)
```text
KillMode=control-group
...
## pids: unit MainPID=4054469 tmux-server=4054473 pane0(claude)=4054474 pane1(sleep)=4054479
## /proc/<pid>/cgroup before stop
unit-main:   0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-sessiond-cgstop.service
tmux-server: 0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-sessiond-cgstop.service
pane-claude: 0::/user.slice/user-0.slice/user@0.service/app.slice/tmux-spawn-46d672a6-c748-4b3f-85eb-6c017b5d6d71.scope  comm=claude
...
## after stop (+4s)
...
tmux-server 4054473: dead
pane-claude 4054474: dead
pane-sleep  4054479: dead
## tmux -L shp-gap-sysd-a list-sessions
no server running on /tmp/tmux-0/shp-gap-sysd-a
```
Same launch with `KillMode=process` (`q1-procstop.txt`), and with the server started through `systemd-run --user --scope` from inside the unit (`q1-scopestop.txt`):
```text
KillMode=process
...
tmux-server 4054646: alive(tmux: server)
pane-claude 4054647: alive(claude)
```
```text
tmux-server: 0::/user.slice/user-0.slice/user@0.service/app.slice/shp-gap-tmuxsrv-scopestop.scope
...
tmux-server 4054726: alive(tmux: server)
pane-claude 4054727: alive(claude)
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| tmux server cgroup, first `new-session` run inside the unit | cgroup path | always (4/4 variants) | `.../app.slice/<unit>.service` | the server forks from the unit's client, so it stays in the unit cgroup |
| pane process cgroup | cgroup path | always | `.../app.slice/tmux-spawn-<uuid>.scope` | only pane children move out |
| server + panes after `systemctl --user stop` (control-group) | liveness | always | all `dead`; `no server running` | panes die because their pty master (the server) is gone |
| after `systemctl --user restart` (control-group) | liveness | always | old server and panes `dead`; the new ExecStart creates a **new** server with new pane pids (`pane_pid=4054598`) | the sessions are not preserved (`q1-cgrestart.txt`) |
| after stop with `KillMode=process` | liveness | always | server, claude, sleep `alive` | only MainPID is killed |
| after stop, server started in its own `--scope` | liveness | always | server, claude, sleep `alive` | server cgroup `shp-gap-tmuxsrv-scopestop.scope` |
| `SendSIGHUP` / `KillSignal` defaults | unit property | always | `SendSIGHUP=no`, `KillSignal=15` | |

**Variants and edge cases:**
- When `claude` is not on the unit's PATH, the pane command fails at once. tmux then exits and the unit's second tmux call logs `server exited unexpectedly` (`q1-nopath.txt`). See the next block.
- The `## journal` section of `q1-cgstop.txt` also shows lines from an earlier, discarded run that used the same unit name (a different tmpdir). They are not evidence for this run.
- A `claude` that starts inside a unit gets hook ancestry `capture_hook.sh → sh → claude → sh → systemd` (`systemd-tmux-*/hooks.jsonl`).

**Spec alignment:**
- Spec line 1139 says tmux survives a `sessiond` restart or upgrade because "the tmux server is its own process". In reality, a tmux server first started by `sessiond` inside `shepherd-sessiond.service` lives in that unit's cgroup. The default `KillMode=control-group` kills it, and every owned session with it, on `systemctl --user stop` and on `restart` (`q1-cgstop.txt`, `q1-cgrestart.txt`). Survival needs one of two measures, both verified. Start the server in its own scope (`systemd-run --user --scope tmux -L shepherd ...`, `q1-scopestop.txt`), or use `KillMode=process` (`q1-procstop.txt`). The §15 unit sketch (lines 2215-2216) has only `Restart=always`, and `Restart=always` alone brings the unit back with the sessions gone.
- D14 (line 117) says tmux "survives `sessiond` restarts". This holds only with the scope or KillMode measure above (same evidence).

## systemd user-manager environment: PATH, `claude` resolution and auth inside a unit; env handed to panes

- **Produced by:** systemd 255 user manager (`systemctl --user show-environment`), `systemd-run --user`, claude 2.1.270, tmux 3.4
- **Consumed by:** D39 (spec line 143), §15 lines 2209-2219, engine matrix line 547 (`claude -p`), §9 LocalRunner spawn; M3
- **Probe:** `probe_systemd_tmux.sh` (Q2). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_systemd_tmux.sh`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `systemd-tmux-20260914T170532Z/q2-user-manager-environment.txt`, `q2-unit-claude-resolve.txt`, `q2b-unit-claude-resolve-with-path.txt`, `q2c-unit-auth-turn.txt`)
```text
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/snap/bin
...
command -v claude -> 
claude --version -> /bin/sh: 1: claude: not found
...
claude auth status exit=127
```
```text
PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
command -v claude -> /root/.local/bin/claude
claude --version -> 2.1.270 (Claude Code)
claude auth status exit=0
```
```text
{'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'PONG', 'num_turns': 1}
```
Pane environment when the unit sets PATH (`q1-cgstop.txt`):
```text
PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TERM=tmux-256color
TMUX_PANE=%0
TMUX=/tmp/tmux-0/shp-gap-sysd-a,4054473,0
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| user manager `PATH` | string | always | `/usr/local/sbin:...:/snap/bin:/snap/bin` | no `~/.local/bin`, which is where the native installer puts `claude` |
| user manager variable names | list | always | `HOME LANG LOGNAME PATH SHELL USER XDG_RUNTIME_DIR XDG_DATA_DIRS DBUS_SESSION_BUS_ADDRESS GSM_SKIP_SSH_AGENT_WORKAROUND SSH_AUTH_SOCK` | values other than PATH/HOME/LANG/SHELL/XDG_RUNTIME_DIR redacted |
| `claude` in a unit without a PATH override | exit | always | `claude: not found`, exit 127 | |
| `claude auth status` in a unit with PATH set | exit | always | `0` | credentials resolve from `$HOME` without a login shell |
| `claude -p` turn from a unit | result | always | `success`, `PONG` | |
| pane env from a unit-started server | env | always | unit env + `TERM=tmux-256color`, `TMUX`, `TMUX_PANE`, plus `INVOCATION_ID`, `JOURNAL_STREAM`, `SYSTEMD_EXEC_PID`, `MEMORY_PRESSURE_*` | systemd variables leak into every claude pane |

**Variants and edge cases:**
- Setting `${TMUX-<unset>}` inside a `systemd-run` command line is unreliable, because systemd does its own `${}` expansion. The `TMUX= CLAUDECODE= TERM=` line in `q2-unit-claude-resolve.txt` is an artifact, not a value, and is not cited.

**Spec alignment:**
- D39 (line 143) and §15 (lines 2209-2219) imply that the daemons can run `claude` as a systemd user service. In reality the user manager's PATH does not contain `/root/.local/bin`, so a unit without `Environment=PATH=...` (or an absolute `claude` path) cannot find `claude`, and every owned spawn fails (`q2-unit-claude-resolve.txt`, `q1-nopath.txt`). With PATH set, auth and a `-p` turn work (`q2b-*`, `q2c-*`). The unit files in §15 need an explicit PATH or an absolute binary path. Neither is written today.

## Pane environment source: tmux server environment versus the calling client (`new-session -e`)

- **Produced by:** tmux 3.4
- **Consumed by:** §9 LocalRunner `Runner.start(spec)` (spec line 424), D11 per-session credential/engine env; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_env.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_env.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-env-20260914T173859Z/env.txt`; capture-pane wraps at 80 columns)
```text
## pane output of shepherd_e1: SHP_PROBE_VAR=from-first-client PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap-env,
## pane output of shepherd_e2: SHP_PROBE_VAR=from-first-client PATH=/opt/x:/usr/bin:/bin TMUX=/tmp/tmux-0/shp-g
## pane output of shepherd_e3: SHP_PROBE_VAR=from-dash-e PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap-env,406042
## pane output of shepherd_e4: SHP_PROBE_VAR=from-set-environment-g PATH=/usr/bin:/bin TMUX=/tmp/tmux-0/shp-gap
```

| Case | Client env | Pane saw | Notes |
|---|---|---|---|
| e1: first client starts the server | `SHP_PROBE_VAR=from-first-client`, `PATH=/usr/bin:/bin` | both from the client | the server env is copied from this client |
| e2: later client, no `-e` | `SHP_PROBE_VAR=from-second-client`, `PATH=/opt/x:/usr/bin:/bin` | `SHP_PROBE_VAR=from-first-client`, `PATH=/opt/x:...` | ordinary variables come from the **server**; PATH comes from the **client** |
| e3: `new-session -e SHP_PROBE_VAR=from-dash-e -e PATH=/opt/y:...` | `PATH=/usr/bin:/bin` | `SHP_PROBE_VAR=from-dash-e`, `PATH=/usr/bin:/bin` | `-e` works for ordinary variables; `-e PATH=` was overridden by the client's PATH |
| e4: `set-environment -g` then a new session | | `from-set-environment-g` | global env applies to later panes |
| `update-environment` default | | `DISPLAY KRB5CCNAME SSH_ASKPASS SSH_AUTH_SOCK SSH_AGENT_PID SSH_CONNECTION WINDOWID XAUTHORITY` | only these are refreshed from a client |

**Variants and edge cases:**
- This was found by accident. In `probe_config_scopes.py`, the first version passed the mock API port only in the client environment. Sessions created after the first one silently talked to the first session's (closed) port and ended in `StopFailure` `server_error` "Connection refused". That run was discarded, and `gaplib.Tui` now passes `-e`.

**Spec alignment:**
- The spec does not say how per-session environment (`CLAUDE_CONFIG_DIR`, credentials, and so on) reaches an owned session. Setting it on the `tmux` client process is silently ignored once the `shepherd` server exists. `new-session -e KEY=VAL` works for ordinary variables, and PATH must be set on the client (`env.txt`). This is a gap to write down, not a contradiction.

## tmux session-name rewriting and `-t` target resolution

- **Produced by:** tmux 3.4
- **Consumed by:** §18 incident, spec lines 2344-2358; §9 naming, line 1135 (`shepherd_<session_id>`); CLAUDE.md rule 4; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`
- **Status:** verified live 2026-09-14 (throwaway socket; no kill-server)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-naming-20260914T170739Z/naming.txt`)
```text
$ tmux -L shp-gap-name-a new-session -d -s shepherd:spike1 -x 80 -y 24 sleep 100000
[rc=0]
$ tmux -L shp-gap-name-a new-session -d -s shepherd.dot1 -x 80 -y 24 sleep 100000
[rc=0]
...
$ tmux -L shp-gap-name-a list-sessions -F #{session_name}|#{session_id}|windows=#{session_windows}
shepherd|$0|windows=2
shepherd_dot1|$2|windows=1
shepherd_ok-1|$3|windows=1
shepherd_spike1|$1|windows=1
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd:spike1 resolved: session=#{session_name} window=#{window_name} pane=#{pane_id}
resolved: session=shepherd window=spike1 pane=%1
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd.dot1 resolved(dot, no =): session=#{session_name} window=#{window_name}
resolved(dot, no =): session=shepherd window=sleep
...
$ tmux -L shp-gap-name-a display-message -p -t shepherd_ok resolved(prefix): session=#{session_name}
resolved(prefix): session=shepherd_ok-1
...
$ tmux -L shp-gap-name-a display-message -p -t =no_such_session: nonexistent: session=#{session_name}
nonexistent: session=
[rc=0]
...
$ tmux -L shp-gap-name-a send-keys -t =no_such_session: -l x
can't find session: no_such_session
[rc=1]
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `new-session -s` with `:` | rc / stored name | always | rc 0, stored as `shepherd_spike1` | silent rewrite |
| `new-session -s` with `.` | rc / stored name | always | rc 0, stored as `shepherd_dot1` | also rewritten |
| `-t shepherd:spike1` | resolution | always | session `shepherd`, window `spike1` | also with `=shepherd:spike1` |
| `-t shepherd.dot1` | resolution | always | session `shepherd` (window 0) | `.` is the pane separator |
| `-t shepherd_ok` (no `=`) | resolution | always | `shepherd_ok-1` | unique-prefix match |
| `has-session -t =shepherd_ok` | rc | always | 1, `can't find session: shepherd_ok` | `=` forces exact match |
| `has-session -t shep` (ambiguous prefix) | rc | always | 1 | |
| `display-message -p -t <missing>` | rc / output | always | **rc 0**, formats expand empty | also under `env -i` |
| `send-keys -t <missing>` | rc | always | 1 | |

**Variants and edge cases:**
- A prefix match could make `-t shepherd_ses_1` hit `shepherd_ses_12`. Always use `=name:`.
- Never use `display-message` as an existence check. Use `has-session -t =name`.

**Spec alignment:**
- Aligned with lines 2353-2358 (`:` is rewritten to `_`; `-t shepherd:spike1` resolves to session `shepherd`, window `spike1`). Line 2354 mentions only `:`. `.` is also rewritten, and a `.` in a target means a pane (`naming.txt`), so `session_id` values must exclude both `:` and `.`.

## `$TMUX` inheritance inside a pane

- **Produced by:** tmux 3.4
- **Consumed by:** §18 rule 2, spec lines 2349-2351; CLAUDE.md rule 3; M3
- **Probe:** `probe_tmux_naming.sh` (step 5). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_naming.sh`
- **Status:** verified live 2026-09-14

**Real example** (full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-naming-20260914T170739Z/inpane-output.txt`)
```text
inside pane: TMUX=/tmp/tmux-0/shp-gap-name-a,4055044,3
--- bare 'tmux display-message -p #{socket_path}|#{session_name}' (no -L):
/tmp/tmux-0/shp-gap-name-a|shepherd_ok-1
--- bare 'tmux list-sessions -F #{session_name}' (no -L):
shepherd
shepherd_dot1
shepherd_ok-1
shepherd_spike1
--- 'tmux -L shp-gap-name-b list-sessions' (explicit -L):
/tmp/tmux-0/shp-gap-name-b|shepherd_other
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `TMUX` in a pane | `socket_path,server_pid,session_index` | always | `/tmp/tmux-0/shp-gap-name-a,4055044,3` | |
| bare `tmux` command inside a pane | target socket | always | the pane's own socket | |
| `tmux -L other` inside a pane | target socket | always | `other` | `-L` overrides `$TMUX` |

**Spec alignment:** aligned with lines 2349-2351. Only read-only commands were run to show this; no destructive command.

## Second tmux client attaching to a session that `Runner.resize` sized

- **Produced by:** tmux 3.4 (nested client: an outer throwaway tmux pane runs `env -u TMUX tmux -L shp-gap-att-inner attach`)
- **Consumed by:** D14 "jump to terminal" (line 117), §9 line 1141, `[tmux attach]` line 1991, `Runner.resize` line 428; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh` (part A). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-attach-keys-20260914T170850Z/attach.txt`)
```text
## state: A0 created -x 160 -y 45, no client
inner window=160x45 pane=160x45 session_attached=0
inner window-size option:  (global: latest) aggressive-resize: off
...
## state: A1 Runner.resize (resize-window -x 120 -y 40), no client
inner window=120x40 pane=120x40 session_attached=0
inner window-size option: manual (global: latest) aggressive-resize: off
...
## state: A2 second client attached from a 100x30 terminal (plain attach)
inner window=120x40 pane=120x40 session_attached=1
inner window-size option: manual (global: latest) aggressive-resize: off
inner list-clients: /dev/pts/5 100x30 flags=attached,focused,UTF-8 session=shepherd_t1;
...
## state: A5 window-size set back to latest (the default) with the 90x25 client attached
inner window=90x24 pane=90x24 session_attached=1
...
## state: A6 Runner.resize (-x 150 -y 50) again after A5
inner window=150x50 pane=150x50 session_attached=1
inner window-size option: manual (global: latest) aggressive-resize: off
...
## state: A8 client attached with -f ignore-size,read-only from 100x30, window-size=latest
inner window=100x29 pane=100x29 session_attached=1
inner window-size option: latest (global: latest) aggressive-resize: off
inner list-clients: /dev/pts/5 100x30 flags=attached,focused,ignore-size,read-only,UTF-8 session=shepherd_t1;
...
## A10 typed 'RO' into the read-only client; keydump lines with hex: 0
```
What the 100x30 client sees of the 120x40 window (`A2-outer-client-view.txt`):
```text
keydump ready
...
[shepherd_0:python3*                                         [0,0] "<redacted: host name>" 17:08 14-Sep-26
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| global `window-size` | option | always | `latest` | tmux 3.4 default |
| `aggressive-resize` | option | always | `off` | |
| window `window-size` after `resize-window` | option | always | `manual` | `resize-window` silently switches the window to manual |
| window size with a smaller client attached, window-size manual | WxH | always | stays `120x40`; the client sees a panned viewport (`[0,0]`) | the browser's size wins |
| `resize-window` with a client attached | WxH | always | applied (`150x50`); the pane got SIGWINCH (keydump `sigwinch` lines) | |
| client terminal resize, window-size manual | WxH | always | window unchanged | |
| window-size `latest` with a client | WxH | always | client size minus the status line (`90x24`, `100x29`) | |
| `attach -f ignore-size` as the only client | WxH | observed once | window still followed the client (`100x29`) | `ignore-size` did not stop it when it was the only client |
| `client_flags` | list | always | `attached,focused,UTF-8`; `...,ignore-size,read-only,...` | |
| read-only client keystrokes | bytes to pane | always | none (`hex: 0`) | |

**Variants and edge cases:**
- Detaching the second client (A7) leaves the window at the last `resize-window` size.
- The attached terminal shows tmux's own status line, which includes the host name, unless `status off` is set on the Shepherd socket.

**Spec alignment:**
- Line 1141 ("`tmux -L shepherd attach -t shepherd_<id>` and you are driving it by hand") is aligned on attach itself. Two things are unspecified. First, after any `Runner.resize` (line 428) the window is `manual`, so a human attaching from a smaller terminal sees a clipped, panning view, and from a larger one sees dead space. Second, if Shepherd sets `window-size latest` instead, the browser and the human fight over size. The "exact" claim (line 117, line 1141) needs a chosen policy (`attach.txt`). Use `attach -r` for a view-only hand-off; it was verified that it delivers no keys.

## Raw key bytes delivered to a pane through tmux

- **Produced by:** tmux 3.4 `send-keys` / `paste-buffer` into a raw-mode pane program (`keydump.py`, which enables bracketed paste like the Claude TUI)
- **Consumed by:** §9 terminal fidelity lines 1150-1153, write policy lines 1171-1173, `Runner.write` line 427, D40; M3
- **Probe:** `probe_tmux_attach_keys.sh` (part B). Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_tmux_attach_keys.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/tmux-attach-keys-20260914T170850Z/keys-keydump.jsonl`)
```json
{"marker": "send-keys Escape", "t": 1789405745.571}
{"hex": "1b", "repr": "b'\\x1b'", "t": 1789405745.577}
{"marker": "send-keys C-c", "t": 1789405746.181}
{"hex": "03", "repr": "b'\\x03'", "t": 1789405746.188}
{"marker": "send-keys Up Down Left Right", "t": 1789405746.792}
{"hex": "1b5b411b5b421b5b441b5b43", "repr": "b'\\x1b[A\\x1b[B\\x1b[D\\x1b[C'", "t": 1789405746.799}
...
{"marker": "send-keys -H e2 9c 93 (UTF-8 check mark)", "t": 1789405749.848}
{"hex": "e29c93", "repr": "b'\\xe2\\x9c\\x93'", "t": 1789405749.854}
...
{"marker": "send-keys -l 'a\nb' (literal LF)", "t": 1789405751.071}
{"hex": "610a62", "repr": "b'a\\nb'", "t": 1789405751.078}
{"marker": "paste-buffer -p (bracketed, app enabled ?2004h)", "t": 1789405751.689}
{"hex": "1b5b3230307e6c696e65206f6e650d6c696e652074776f1b5b3230317e", "repr": "b'\\x1b[200~line one\\rline two\\x1b[201~'", "t": 1789405751.695}
{"marker": "paste-buffer (no -p)", "t": 1789405752.300}
{"hex": "6c696e65206f6e650d6c696e652074776f", "repr": "b'line one\\rline two'", "t": 1789405752.307}
...
{"marker": "printf XYZ > pane_tty (/dev/pts/4)", "t": 1789405753.529}
{"marker": "end", "t": 1789405754.335}
```

| Input | Bytes the pane read | Notes |
|---|---|---|
| `send-keys Escape` / `C-c` / `Enter` | `1b` / `03` / `0d` | |
| `send-keys Up Down Left Right` | `1b5b41 1b5b42 1b5b44 1b5b43` | normal cursor-key mode |
| `BSpace Tab BTab` | `7f 09 1b5b5a` | |
| `send-keys -H <hex>` | exactly those bytes (`1b5b41`, `03`, `e29c93`, a hand-built `1b5b3230307e...1b5b3230317e`) | an xterm.js `onData` string can be sent byte-exact |
| `send-keys -l` with ESC and LF | `1b5b41`; `610a62` | `-l` does not escape control bytes |
| `paste-buffer -p` | `1b5b3230307e ... 1b5b3230317e`, LF turned into CR | brackets are added only because the app enabled `?2004h` |
| `paste-buffer` (no `-p`) | LF turned into CR, no brackets | |
| write to `#{pane_tty}` | **nothing read**; `XYZ` appears on screen | the slave side is output, not input (`keys-pane-screen.txt`) |

**Spec alignment:**
- Line 1153 (`keystrokes: ──► write policy ──► pty`) is aligned in principle: arbitrary bytes reach the pane through `send-keys -H`. Writing to the pane's tty is **not** a way to type (`keys-pane-screen.txt`), so `Runner.write` must use `send-keys -H` (or `-l` for text), never the tty device.

## Key semantics in the Claude Code TUI (history, bracketed paste, Ctrl-C, Esc)

- **Produced by:** claude 2.1.270 TUI in tmux 3.4 (mock API backend)
- **Consumed by:** §9 lines 1171-1173, D40, UI line 1975; M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_keys_claude.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_keys_claude.py`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/keys-claude-20260914T180105Z/results.json`, `01-after-raw-up.txt`, `03-after-raw-ctrl-c-idle.txt`)
```json
 "raw_up_recalls_history": true,
 "bracketed_paste_prompt": "PASTE-LINE-ONE\nPASTE-LINE-TWO",
 "raw_ctrl_c_idle_screen_hint": [
  "Press Ctrl-C again to exit"
 ],
 "alive_after_one_ctrl_c": true,
 "esc_clears_input": false
```
```text
─── History 1/1 ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ FIRST-PROMPT-FOR-HISTORY
```

| Input (`send-keys -H`) | TUI effect | Notes |
|---|---|---|
| `1b 5b 41` (Up) at an empty prompt | recalls history (`History 1/1`) | |
| `paste-buffer -p` of two lines, then Enter | one prompt; `UserPromptSubmit.prompt` = `PASTE-LINE-ONE\nPASTE-LINE-TWO` | the newline survives; tmux's LF-to-CR does not split it |
| `03` at the idle prompt | hint `Press Ctrl-C again to exit`; session alive | a second one exits (not repeated here) |
| `1b` (Esc) with typed text, once or twice | text stays | Esc does not clear input |

**Variants and edge cases:**
- At startup the TUI enables kitty keyboard protocol flags (`^[[>5u`) and focus events (`?1004h`) (`pidfd-pty-*/pty-stream-head.cat-v.txt`). Under tmux with default `extended-keys off`, legacy bytes as above work.

**Spec alignment:** aligned with lines 1171-1173.

## Interrupting a running TUI turn: Esc, C-c, SIGINT

- **Produced by:** claude 2.1.270 TUI in tmux 3.4. Mock API for all four cases, plus a real-API (haiku) repeat of Esc during a tool call
- **Consumed by:** write-policy "explicit interrupt" line 1169, `interrupt_session` line 1231, `⎋ interrupt` line 1975, `Runner.signal` line 429, `killed` line 965, mailbox trigger on `Stop` line 1181; M3/M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py` and `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_interrupt.py --real`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/interrupt-20260914T172251Z/results.json`, `hooks.jsonl`, `esc_tool-transcript-delta.jsonl`, `sigint_tool-screen-after.txt`)
```json
 "esc_tool": {
  "how": "esc",
  "events": [
   "UserPromptSubmit",
   "PreToolUse(Bash)"
  ],
  "claude_alive": true,
```
Transcript entries written by Esc during the Bash call:
```json
{"parentUuid":"3d9ddbf6-6350-4f28-8a9e-e228e96d95af","isSidechain":false,"promptId":"4e064b61-5f19-48a8-940f-1472fa47c95a","type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP what you are doing and wait for the user to tell you how to proceed.","is_error":true,"tool_use_id":"toolu_mock_1789406576424"}]},"uuid":"eec46fb0-9200-408c-8a2c-5b3b53c45ea1","timestamp":"2026-09-14T17:22:59.301Z","toolUseResult":"User rejected tool use","toolDenialKind":"user-rejected",...}
{"parentUuid":"5f5cc4ef-1e9c-48dc-9834-0ea68a09e510","isSidechain":false,"promptId":"4e064b61-5f19-48a8-940f-1472fa47c95a","type":"user","message":{"role":"user","content":[{"type":"text","text":"[Request interrupted by user for tool use]"}]},"uuid":"25ee91a1-32b8-4f00-b821-60ddb7a35a87","timestamp":"2026-09-14T17:22:59.304Z","interruptedMessageId":"msg_mock_1789406576424",...}
```
SIGINT to the claude pid during the tool call (`hooks.jsonl`, `sigint_tool-screen-after.txt`):
```json
{"_event":"SessionEnd","_captured_at":"2026-09-14T17:23:41.803Z",...,"hook_event_name":"SessionEnd","reason":"other"}}
```
```text
Resume this session with:
claude --resume 12965b0b-2454-4673-bbce-c3d0635982f5
Pane is dead (status 0, Mon Sep 14 17:23:41 2026)
```

| Delivery | Hooks after the interrupt (8 s window) | Transcript | Session | Notes |
|---|---|---|---|---|
| `send-keys Escape` during a Bash tool call | **none**: no `PostToolUseFailure`, no `Stop` | `tool_result` `is_error:true` + `toolUseResult:"User rejected tool use"`, `toolDenialKind:"user-rejected"`; then user text `[Request interrupted by user for tool use]` with `interruptedMessageId` | alive; the next prompt gets a normal `Stop` | same with the real API (`interrupt-real-*/hooks.jsonl`: `PreToolUse`, then the next turn's `UserPromptSubmit`; `transcript-redacted.jsonl` line 23-25) |
| `send-keys C-c` during a Bash tool call | none | same two entries | alive | |
| `send-keys Escape` while the API request is in flight | none | **no marker at all** (only the user prompt entry) | alive; **the prompt text is put back in the input box** | the next typed text was appended to it: `UserPromptSubmit.prompt` = `INT-ESC-STREAMReply with only the word AFTER` |
| `kill -INT <claude pid>` during a tool call | `SessionEnd{reason:"other"}` | | **exits**, pane status 0 | prints `Resume this session with:` |
| `kill -INT <claude pid>` at the idle prompt | `SessionEnd{reason:"other"}` | | exits, status 0 | |
| `send-keys C-c` at the idle prompt | none | | alive, hint shown | |

**Variants and edge cases:**
- A foreground `sleep` as a real-API test failed twice. Haiku first set `run_in_background:true`, then refused ("safety block against standalone sleep"). The committed real run uses `python3 -c 'import time; time.sleep(40)'` (`interrupt-real-*/steps.log`).
- `PostToolUseFailure.is_interrupt` was never observed. The hook did not fire at all on interrupt.

**Spec alignment:**
- Line 429 (`Runner.signal`) and line 965 (`killed` = we sent the signal): a SIGINT to the pane process does not interrupt, it **terminates** Claude Code (`SessionEnd` `other`, exit 0). An interrupt must be `send-keys Escape` (`interrupt-*/results.json`).
- Line 1181 (mailbox delivery trigger is the `Stop` hook) and line 1169 (running → queue, deliver at next `Stop`): an interrupted turn emits **no `Stop`**, so queued messages would wait until the next completed turn. After an Esc during streaming, the previous prompt sits in the input box, and a programmatic write gets concatenated onto it (`interrupt-*/hooks.jsonl`).
- Line 938 (`stopped` on `Stop`/`StopFailure`/`SessionEnd`): after an Esc the session is idle but no stop-class event arrives. The only immediate signal is the pair of transcript entries above (in the 8 s window no hook fired; a later `Notification idle_prompt` was not waited for).

## Brief passed as argv through `tmux new-session` (`EngineAdapter.spawn_argv`)

- **Produced by:** tmux 3.4 + claude 2.1.270 (mock API)
- **Consumed by:** `spawn_argv` line 435, `spawn_session(project, brief, ...)` line 1377, "no `shell=True` anywhere; argv lists only" line 2112; M3/M5
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_argv.py`, `probe_argv_limits.sh`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_argv.py && bash docs/probes/2026-09-14-schemas/gap-fill/probe_argv_limits.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/argv-20260914T173100Z/results.json`, `argv-limits-20260914T173342Z/tmux-argv-limit.txt`, `claude-dash-brief.stderr`)
```json
 "a_argv_words": {
  "tmux_argv_words": 4,
...
  "pane_comm": "claude",
  "pane_cmdline": [
   "claude",
   "--model",
   "claude-haiku-4-5-20251001",
   "ARGV-BRIEF $(echo EXPANDED) `echo BACKTICK` ; echo SEMI && 'single' \"double\" \\back $HOME *\nsecond line\tTAB \u2713 end"
  ],
  "trust_dialog_shown": true,
  "hooks_before_trust": [],
  "events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "prompt_len": 112,
  "prompt_equals_brief": true,
```
```json
 "b_single_string_naive": {
  "tmux_argv_words": 1,
...
  "prompt_head": "ARGV-BRIEF EXPANDED BACKTICK ; echo SEMI && 'single' double \\back /root *\nsecond line\tTAB \u2713 end",
```
```text
largest accepted single argv word (bytes): 16324
smallest rejected: 16325 -> failed to send command rc=1 
```
```text
error: unknown option '-starts with a dash DASH-BRIEF'
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| positional prompt to interactive `claude` | behaviour | always (4/4 spawned) | **auto-submits**: `SessionStart`, `UserPromptSubmit`, `Stop` | |
| before trust is accepted | hooks | always | `[]` (trust dialog on screen) | the prompt is held and submitted after trust |
| `new-session ... claude --model M <brief>` (argv words) | pane process | always | `pane_comm` `claude` (no shell); cmdline byte-exact | `prompt_equals_brief: true` including `$()`, backticks, quotes, `\`, `*`, LF, TAB, UTF-8 |
| one command string with the brief in `"..."` | pane process | always | `sh -c` expanded `$()`, backticks and `$HOME`, and stripped quotes | `prompt_equals_brief: false` |
| one command string with `shlex.quote(brief)` | prompt | always | byte-exact | |
| brief starting with `-` | exit | always | pane dead status 1; `error: unknown option '-starts with a dash DASH-BRIEF'` | `claude ... -- "-brief"` works (`e_dash_brief_with_separator`) |
| brief size limit | bytes | always | tmux accepts ≤ 16324 bytes for the whole command in this test; 20 KiB and 100 KiB fail with `command too long`; 140 KiB fails earlier in execve (`E2BIG`) | the limit is on tmux's client→server message, not on Linux ARG_MAX |

**Variants and edge cases:**
- Variadic flags such as `--allowedTools a b` swallow a following positional prompt: `Error: Input must be provided either through stdin or as a prompt argument when using --print` (`mcp-perm-p-*/results.json`). Put `--` before the brief.

**Spec alignment:**
- Line 2112 (argv lists only) holds only if the tmux command is passed as separate argv words. A single command string goes through `sh -c` and mangles the brief (`b_single_string_naive`).
- Line 1377 `spawn_session(project, brief, ...)` with the brief on argv: briefs over about 16 KB cannot be passed this way at all, and a brief starting with `-` crashes the spawn unless `spawn_argv` emits `--` (`argv-limits-*`, `d_dash_brief_no_separator`). A large `build_brief()` (prior attempts plus the work item) needs another channel, such as `send-keys`/paste after start or a file.

## `--effort` flag: accepted values, invalid values, what reaches the API

- **Produced by:** claude 2.1.270 CLI (mock API logging the request body)
- **Consumed by:** engine matrix line 552, `ModelProvider.effort_ladder()` line 454, `EngineCapabilities.effort_ladder` line 498, `spawn_session(effort?)` line 1656; M3/M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_effort.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_effort.py`
- **Status:** verified live 2026-09-14 (request body from a local mock; no real API call)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/effort-20260914T171533Z/claude-help.txt`, `runs.jsonl`, `summary.jsonl`)
```text
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
```
```json
{"label": "effort=bogus haiku", ... "rc": 0, "stdout_summary": {"subtype": "success", "is_error": false, "result": "OK-MOCK"}, "stderr": "Warning: Unknown --effort value 'bogus' \u2014 ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.", "wall_s": 0.5}
{"label": "no effort claude-haiku-4-5-20251001", "model": "claude-haiku-4-5-20251001", "output_config": null, "thinking": {"budget_tokens": 31999, "type": "enabled", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": "<absent>"}}
{"label": "effort=xhigh claude-sonnet-5", "model": "claude-sonnet-5", "output_config": {"effort": "xhigh"}, "thinking": {"type": "adaptive", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": {"level": "xhigh"}}}
{"label": "effort=max claude-opus-5", "model": "claude-opus-5", "output_config": {"effort": "max"}, "thinking": {"type": "adaptive", "display": "omitted"}, ... "hook_effort": {"UserPromptSubmit": "<absent>", "Stop": {"level": "max"}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `--effort` accepted values | enum | always | `low, medium, high, xhigh, max` (help text and warning) | |
| invalid value (`bogus`, `auto`) | behaviour | always | exit 0, stderr warning, **default effort used** | no error |
| uppercase `MAX` | behaviour | always | accepted as `max` on sonnet (`output_config.effort: "max"`) | case-insensitive |
| request `output_config.effort` (sonnet-5, opus-5) | string | always | the level given; `high` when omitted or invalid | anthropic-beta includes `effort-2025-11-24` |
| request for haiku-4-5 | fields | always | `output_config: null`, `thinking: {budget_tokens: 31999, type: enabled}` for every level | effort is silently dropped for haiku |
| hook `effort` | object | sometimes | `Stop.effort = {level}` for sonnet/opus; absent on `UserPromptSubmit`; absent for haiku | matches the hooks surface |

**Spec alignment:** aligned with line 552 (the ladder is exactly `low·medium·high·xhigh·max`). A mistyped effort does not fail a spawn; it silently runs at `high`, and per-model support must come from `supportedEffortLevels` (next block).

## `ModelProvider.models()` source: initialize `models[]`

- **Produced by:** claude CLI 2.1.259 (SDK-bundled) and 2.1.270 via claude-agent-sdk 0.2.152 `ClaudeSDKClient.get_server_info()` (no model turn)
- **Consumed by:** `ModelProvider.models()` line 453 ("id, context, cost, release"), master runtime selection line 2287; M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py server_info`. Re-run: `/tmp/shp-sdk-9IOKNs/venv/bin/python docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py server_info --cli /root/.local/bin/claude` (any venv with claude-agent-sdk)
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/sdk-server_info-syscli-20260914T171115Z/server-info.json`; account values redacted in the file)
```json
 "models": [
  {
   "value": "default",
   "resolvedModel": "claude-opus-5[1m]",
   "displayName": "Default (recommended)",
   "description": "Opus 5 with 1M context \u00b7 Best for everyday, complex tasks",
   "supportsEffort": true,
   "supportedEffortLevels": [
    "low",
    "medium",
    "high",
    "xhigh",
    "max"
   ],
   "supportsAdaptiveThinking": true,
   "supportsFastMode": true,
   "supportsAutoMode": true
  },
...
   "value": "haiku",
   "resolvedModel": "claude-haiku-4-5-20251001",
   "displayName": "Haiku",
   "description": "Haiku 4.5 \u00b7 Fastest for quick answers"
  }
```

| Field | Type | Presence (5 models × 2 CLI versions) | Observed values | Notes |
|---|---|---|---|---|
| `value` | string | always | `default`, `opus[1m]`, `claude-fable-5-1[1m]`, `sonnet`, `haiku` | alias; `[1m]` suffix = 1M context |
| `resolvedModel` | string | always | `claude-opus-5[1m]`, `claude-fable-5-1`, `claude-sonnet-5`, `claude-haiku-4-5-20251001` | |
| `displayName` | string | always | `Default (recommended)`, `Opus (1M context)`, `Fable`, `Sonnet`, `Haiku` | |
| `description` | string | always | `Opus 5 with 1M context · Best for everyday, complex tasks`, … | context size only as prose |
| `supportsEffort` | bool | sometimes (4/5; absent for haiku) | `true` | |
| `supportedEffortLevels` | string[] | sometimes (4/5) | `["low","medium","high","xhigh","max"]` | |
| `supportsAdaptiveThinking` | bool | sometimes (4/5) | `true` | |
| `supportsFastMode` | bool | sometimes (2/5: default, opus[1m]) | `true` | |
| `supportsAutoMode` | bool | sometimes (4/5) | `true` | |
| context window (tokens) | int | **never** | | |
| cost / price | | **never** | | |
| release date | | **never** | | |

**Spec alignment:** spec line 453 says `models()` returns "id, context, cost, release". In reality the engine exposes id (`value`/`resolvedModel`), display name, description and effort capabilities. It does not expose context size (only a `[1m]` suffix and prose), cost, or release date (`server-info.json`, both CLI versions). Those must come from a static table, or context from `ResultMessage.modelUsage[].contextWindow` after a turn (agent-sdk-mcp surface).

## Transcript JSONL: append-only and whole-line writes

- **Produced by:** claude 2.1.270 TUI transcript writer (`<CLAUDE_CONFIG_DIR>/projects/<slug>/<session_id>.jsonl`), mock API
- **Consumed by:** `parse_transcript_delta(path, offset)` line 437, D24 (read transcript at stop); M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_transcript_append.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_transcript_append.py`
- **Status:** partially verified (no violation in 34 observed changes; a race cannot be proven absent by sampling)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/transcript-append-20260914T175435Z/results.json`, `observations.jsonl`, `transcript-outline.json`)
```json
 "observations": 34,
 "violations": 0,
 "partial_tail_observations": 0,
```
```json
{"t": 1789408482.0032, "phase": "turn_small", "file": "9242f47e-a0ba-4505-92cf-7e697e964216.jsonl", "size": 271, "prev_size": null, "ends_with_newline": true}
{"t": 1789408482.1068, "phase": "turn_small", "file": "9242f47e-a0ba-4505-92cf-7e697e964216.jsonl", "size": 243097, "prev_size": 271, "ends_with_newline": true}
```

| Action (phase) | File changes seen | Violations | Partial tails | Notes |
|---|---|---|---|---|
| small turn | 3 | 0 | 0 | first write is 271 bytes, then 243 KB in one step |
| 400 KiB assistant text | 3 | 0 | 0 | one line of 410665 bytes (`assistant len=410665`) appeared whole |
| tool call with large result (`seq 1 200000`) | 3 | 0 | 0 | the tool-result entry is `user len=39928`, far smaller than the ~1.3 MB command output |
| two Write-tool edits (file-history) | 3 + 2 | 0 | 0 | `file-history-delta`, `file-history-snapshot` entries are appended, not rewritten |
| `/rename` | 3 | 0 | 0 | `custom-title`/`agent-name` re-appended |
| manual `/compact` | 2 | 0 | 0 | `system/compact_boundary` appended; earlier bytes kept |
| `/rewind` (Restore conversation) | 0 during, 1 after | 0 | 0 | the dialog says "The conversation will be forked"; nothing rewritten |
| `/clear` | 5 across **two files** | 0 | 0 | a new `<session_id>.jsonl` is created; the old file only gets appends |
| `claude --resume <first id>` + turn | 3 | 0 | 0 | appends to the original file |

**Variants and edge cases:**
- The poller read every `*.jsonl` about every 2 ms and compared each new content with the previous bytes. Writes of up to 410 KB were seen only complete. That is evidence, not proof, that the writer uses whole-line appends.
- `/rewind` with "Restore code and conversation" was not exercised. The picker's selected point had no code changes, so the dialog offered conversation-only options (`screen-rewind-options.txt`).
- The cross-version resume block below also shows append-only across versions (prefix sha256 unchanged).

**Spec alignment:** aligned with line 437 for every action tried. `/clear` switches to a new file, so an offset reader keyed by path must follow `SessionStart{source:"clear"}` to the new `transcript_path`.

## Hooks written into a running session (attached-session registration)

- **Produced by:** claude 2.1.270 TUI (mock API, isolated CLAUDE_CONFIG_DIR)
- **Consumed by:** lines 925-927 ("a hand-launched session registers itself on its first turn"), `SessionStart` row line 881, `install_hooks()` line 440; M1
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py hot`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py hot`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/results.json`, `hot-local-hooks.jsonl`)
```json
 "hot": {
  "local_events_right_after_write": [],
  "local_events_after_turn2": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop"
  ],
  "user_events_right_after_write": [],
  "local_events_all": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "ConfigChange",
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "SessionEnd"
  ],
  "user_events_all": [
   "UserPromptSubmit",
   "MessageDisplay",
   "Stop",
   "SessionEnd"
  ],
```
```json
"payload":{"session_id":"6a75342c-7ef6-4553-9944-8f942479fe39",...,"hook_event_name":"ConfigChange","source":"user_settings","file_path":"/tmp/shp-gap-hot-q7dvx4xe/cfg/settings.json"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| hooks added to `.claude/settings.local.json` while running | fire on the next turn | always | `UserPromptSubmit`, `MessageDisplay`, `Stop` | no restart needed |
| hooks added to user-scope `settings.json` while running | fire on the next turn | always | same | |
| `SessionStart` for that already-running session | event | **never** | | the session never re-announces itself |
| `ConfigChange` for the user-scope write (seen by the local hooks) | event | always | `source:"user_settings"`, `file_path` | the local-file write could not be observed (no hooks were loaded yet) |

**Spec alignment:** lines 925-927 and 881 say a hand-launched session registers through `SessionStart` on its first turn. That holds only for sessions started **after** install. A session already running when `install_hooks()` writes settings begins sending `UserPromptSubmit`/`Stop` and so on, but never `SessionStart` (`hot-local-hooks.jsonl`, `hot-user-hooks.jsonl`). Registration must also accept the first event of any kind from an unknown `session_id` (all events carry `session_id`, `cwd` and `transcript_path`).

## User-scope hooks with `_shepherd_managed`, and the same command in two scopes

- **Produced by:** claude 2.1.270 `-p` (mock API; user scope = `CLAUDE_CONFIG_DIR/settings.json`)
- **Consumed by:** §15 lines 2230-2233, `install_hooks()`/`uninstall_hooks()` lines 440-441; M1
- **Probe:** `probe_config_scopes.py user`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py user`
- **Status:** verified live 2026-09-14 (in an isolated config dir standing in for `~/.claude`)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/user-user-settings.json`, `user-dup-hooks.jsonl`, `results.json`)
```json
  "SessionStart": [
   {
    "_shepherd_managed": true,
    "hooks": [
     {
      "type": "command",
```
```json
 "user": {
  "run": {
   "rc": 0,
...
  "dup_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "user_only_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
  "project_only_events": [
   "SessionStart",
   "UserPromptSubmit",
   "Stop"
  ],
...
  "user_settings_after_run_unchanged": true
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `_shepherd_managed: true` on the matcher group and on the hook entry | extra key | always | loads; hooks fire | no validation warning in `user-debug.log` |
| identical `command` string in user and project scope | executions per event | always | **1** (`dup_events` one line each) | deduplicated by command |
| user-only and project-only commands | executions | always | 1 each | scopes merge |
| user settings file after a run | content | always | unchanged | CLI did not rewrite it |

**Spec alignment:** aligned with lines 2230-2233. Because identical commands deduplicate, a Shepherd dispatcher registered in both user and project scope runs once. A slightly different command string (another path or env prefix) would run twice. Not tested: whether an editor such as `/hooks` or `/config` preserves the unknown key when the CLI rewrites `settings.json`.

## Tier-2 MCP server at user scope: `claude mcp add -s user`, pickup, permission rules

- **Produced by:** claude 2.1.270 (`claude mcp add|list|get`, TUI and `-p`), stdio server `mcp_stub.py`, mock API, isolated CLAUDE_CONFIG_DIR
- **Consumed by:** lines 1431-1433 (MCP over stdio is the tier-2 contract), 1695 (`shepherd-mcp`), 1700-1707 (SESSION_TOOLS), line 1540 (`mcp__shepherd__*` allowlist); M4
- **Probe:** `probe_config_scopes.py mcp`, `probe_mcp_perm_p.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_config_scopes.py mcp && python3 docs/probes/2026-09-14-schemas/gap-fill/probe_mcp_perm_p.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/mcp-add.txt`, `mcp-claude-json-after-add.json`, `mcp-list-get.txt`, `mcp-s2-permission-screen.txt`, `results.json`; `mcp-perm-p-20260914T174121Z/results.json`)
```json
 "mcpServers": {
  "shepherd": {
   "type": "stdio",
   "command": "/usr/bin/python3",
   "args": [
    "/root/Shepherd/docs/probes/2026-09-14-schemas/gap-fill/mcp_stub.py",
    "/root/Shepherd/docs/probes/2026-09-14-schemas/gap-fill/config-scopes-20260914T173908Z/mcp-stub-messages.jsonl"
   ],
   "env": {}
  }
 },
```
```text
shepherd:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
  Type: stdio
```
```text
 Tool use
   shepherd — Ping Tool: (MCP)
...
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don't ask again for shepherd — Ping commands in /tmp/shp-gap-mcp-rc4d_try/w
   3. No
```
```json
  "stderr": "Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has not been trusted. Run Claude Code interactively here once and accept the trust dialog, or set projects[\"/tmp/shp-gap-perm-proj-zcl84l32\"].hasTrustDialogAccepted: true in /tmp/shp-gap-perm-jotncm_2/cfg/.claude.json."
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| user-scope storage | JSON | always | top-level `mcpServers.<name>` in `<config dir>/.claude.json`: `{type:"stdio", command, args[], env{}}` | `mcp-add.txt` prints `File modified: .../cfg/.claude.json` |
| `claude mcp add -s user -e KEY=V name -- cmd` | parsing | always | `error: missing required argument 'commandOrUrl'` (rc 1): the variadic `-e` swallows the name | `claude mcp add -s user name -e KEY=V -- cmd` works and stores `"env": {"SHP_X": "1"}` (`mcp-add-env-20260914T181206Z/mcp-add-env.txt`) |
| session running **before** `mcp add` | tool list in the next API request | always | `tools_had_mcp_shepherd: [false]` | not picked up |
| session started after add, no allow rule | events | always | `PreToolUse`, `PermissionRequest`, `Notification[permission_prompt]`, then after "Yes" `PostToolUse` | the TUI asks per call |
| TUI, project settings `allow: ["mcp__shepherd__*"]` (trusted dir) | events | always | `PreToolUse`, `PostToolUse` (no prompt) | |
| `-p`, rule from `--allowedTools <x> --` or `--settings` file | outcome | always | `mcp__shepherd`, `mcp__shepherd__*`, `mcp__shepherd__ping` all **allow** (stub got `tools/call`) | 3 spellings × 2 sources |
| `-p`, rule in `.claude/settings.json` of an **untrusted** dir | outcome | always | **denied** (`permission_denials: ["mcp__shepherd__ping"]`) + stderr `Ignoring 1 permissions.allow entry ...` | trust gates project permissions in `-p` |
| client capabilities sent to the server | JSON | always | `{"roots":{"listChanged":true},"elicitation":{}}`, `protocolVersion` `2025-11-25` | `elicitation-tui-*/mcp-stub-messages.jsonl` |

**Spec alignment:**
- Lines 1431-1433 and 1695 (forced stdio binding) are aligned: user-scope stdio servers load in every project.
- A server added while tier-2 sessions run is invisible to them until restart (`results.json` `mcp_s1_running_before_add`).
- A worktree spawn (D15/D22) is a new, untrusted directory. Permission rules written into its `.claude/settings.json` are **ignored**, and in an interactive session every `mcp__shepherd__*` call prompts. Pass rules through `--settings` or `--allowedTools ... --`, or pre-accept trust (`mcp-perm-p-*/results.json`). The spec does not say where the tier-2 allow rule lives.

## Observed process exit for a process Shepherd did not spawn (pidfd)

- **Produced by:** Linux 6.8 `pidfd_open(2)`/`poll(2)`/`waitid(P_PIDFD)` via Python 3.12, tmux 3.4 `pane_dead_status`
- **Consumed by:** `stopped` rule "observed process exit" line 938, `crashed` line 964, `Runner.probe` line 430, `exit_code` owned-only line 693; M2/M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py` (part pidfd). Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/results.json`)
```json
 "pidfd_exit_via_trust_refusal": {
  "pid": 4063896,
  "ppid": 4063895,
  "comm": "claude",
  "starttime": 544599077,
  "is_our_child": false,
  "parent_comm": "tmux: server",
  "pidfd_send_signal_0": "ok",
  "poll_before": [],
  "poll_after_ms": 38.5,
  "poll_events": [
   [
    4,
    1
   ]
  ],
  "waitid_P_PIDFD": "ChildProcessError: errno=10 [Errno 10] No child processes",
  "pidfd_send_signal_0_after": "ok",
  "proc_exists_after": true,
  "tmux_pane_after": "dead=1 status=1 signal="
 },
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `pidfd_open` on a non-child | fd | always (3/3) | works (tmux pane claude; setsid'd sleep under pid 1) | no ptrace or parent relation needed |
| `poll` POLLIN on exit | event | always | `[[fd, 1]]` within 37-39 ms of a claude exit; 0.4 ms for SIGTERM on sleep | fires at exit (zombie), before the reap |
| `waitid(P_PIDFD)` for a non-child | exit status | always | `ChildProcessError errno=10` | the exit code is **not** obtainable by a non-parent |
| `/proc/<pid>` right after POLLIN | exists | sometimes | `true` while the zombie is unreaped (remain-on-exit pane; pid 1 not yet reaped); `false` after `kill-session` | do not use /proc existence as the signal |
| exit code through tmux (owned) | `pane_dead_status` | always with `remain-on-exit on` | `status=1` (trust refused) | |
| identity against pid reuse | `/proc/<pid>/stat` field 22 | always | `starttime` read before the exit | pair with the pid when opening |

**Spec alignment:** aligned with line 938 and line 693 (`exit_code` is owned-only). For attached sessions, pidfd gives exit *time* but no exit *code*, so `crashed` (line 964, "process exit ≠ 0") cannot be decided for attached sessions. Owned sessions get the code from tmux `pane_dead_status` only if `remain-on-exit` is on.

## Auto compaction: `PreCompact{trigger:auto}` / `PostCompact`, and death mid-compaction

- **Produced by:** claude 2.1.270 TUI. Real API (haiku) for natural auto compaction; mock API to hang the summarisation request and kill the session
- **Consumed by:** `context_exhausted` line 966, next action line 1087, context events line 921; M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_autocompact_real.py`, `probe_lifecycle_end.py compact`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_autocompact_real.py && python3 docs/probes/2026-09-14-schemas/gap-fill/probe_lifecycle_end.py compact`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/autocompact-real-20260914T174911Z/results.json`, `hooks.jsonl`; `lifecycle-end-20260914T175238Z/results.json`, `hooks.jsonl`)
```json
 "window100k_pct1": {
  "env": [
   "CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000",
   "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1"
  ],
  "events": [
   "SessionStart[source=startup]",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "MessageDisplay",
   "Stop",
   "SubagentStop",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "MessageDisplay",
   "Stop",
   "SubagentStop",
   "UserPromptSubmit",
   "PreCompact[trigger=auto]",
   "SubagentStop",
   "SessionStart[source=compact]",
   "PostCompact[trigger=auto]",
   "MessageDisplay",
   "Stop"
  ]
```
```json
"payload":{"session_id":"b658c86c-1ecd-4bac-bc26-d5dd73a20709",...,"hook_event_name":"PreCompact","trigger":"auto","custom_instructions":null}}
```
Killed (`tmux kill-session`) while the summarisation request hung at the mock:
```json
 "compact_b_killed_mid_compaction": {
  "events": [
   "UserPromptSubmit@f78d612e",
   "MessageDisplay@f78d612e",
   "Stop@f78d612e",
   "UserPromptSubmit@f78d612e",
   "PreCompact[trigger=auto]@f78d612e",
   "SessionEnd[reason=other]@f78d612e"
  ],
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `PreCompact.trigger` | string | always | `auto` | `custom_instructions: null` |
| `PostCompact.trigger` / `compact_summary` | string | sometimes | `auto` / the summary text (`TWO`, `OK-MOCK`) | |
| `SessionStart.source` between them | string | always when compaction completes | `compact` | |
| `PreCompact{auto}` **without** a later `PostCompact` in a healthy session | pattern | observed 2/3 turns (real API), 1/2 (mock) | the turn then ends with a normal `Stop`, no compaction | |
| kill during compaction | events | always | `PreCompact{auto}` → `SessionEnd{reason:"other"}`, no `PostCompact` | |
| summarisation request (mock log) | request | always | last user text begins `CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.` | `lifecycle-end-*/life-mock-requests.jsonl` |
| trigger knobs | env | | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` + `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=1` compacts; the PCT override alone did not (3 turns); a mock `usage.input_tokens=190000` alone did not | binary text in `binary-context-*/context.txt` |

**Spec alignment:** line 966 (`context_exhausted` = `PreCompact{auto}` with no `PostCompact` before death) matches the kill case. It will also classify as `context_exhausted` any session that dies after a benign, non-compacting `PreCompact{auto}` (observed twice in a healthy real session, `autocompact-real-*/results.json`). The rule needs a time bound (for example, "the most recent `PreCompact{auto}` was followed by no `Stop` or `PostCompact`").

## `SessionEnd.reason` = `resume` and `logout`

- **Produced by:** claude 2.1.270 TUI (mock API, fake API key, isolated CLAUDE_CONFIG_DIR)
- **Consumed by:** `logged_out` line 969, `resumed_elsewhere` line 970; M2
- **Probe:** `probe_lifecycle_end.py resume logout`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_lifecycle_end.py resume logout`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/gap-fill/lifecycle-end-20260914T175238Z/hooks.jsonl`)
```json
"payload":{"session_id":"30fce1e3-7010-4baf-bb5d-cadf207dfab1",...,"hook_event_name":"SessionEnd","reason":"resume"}}
"payload":{"session_id":"4734f21d-7203-4a04-b398-2fd12e081d26",...,"hook_event_name":"SessionStart","source":"resume","model":"claude-haiku-4-5-20251001","seconds_since_last_response":12,"context_tokens":30,"prompt_cache_likely_expired":false,"estimated_cache_write_usd":0}}
"payload":{"session_id":"ceec3e0f-a9b9-481c-b4a9-60c2fad20f1e",...,"hook_event_name":"SessionEnd","reason":"logout"}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `SessionEnd.reason` after `/resume <other id>` in a running TUI | string | always | `resume` | the old `session_id` ends |
| next `SessionStart` | object | always | `source:"resume"`, **the other session's id**, same process and pane | extra fields `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd` |
| `SessionEnd.reason` after `/logout` | string | always | `logout`; the process exits | fake API key auth in an isolated config |

**Spec alignment:**
- Lines 969-970: the values `logout` and `resume` are aligned. The field is `reason`, not `end_reason` (lines 967-970).
- `resumed_elsewhere` is misnamed. The same pane continues as a different `session_id`, so a pane-keyed owned session must rebind its `engine_session_id` rather than stop (`hooks.jsonl`).

## MCP elicitation in the TUI: `Notification.notification_type`

- **Produced by:** claude 2.1.270 TUI + stdio `mcp_stub.py` (`elicitation/create`, form and url modes), mock API
- **Consumed by:** `needs_you` rule line 937; M2
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_elicitation_tui.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_elicitation_tui.py`
- **Status:** partially verified (`elicitation_dialog` live; `elicitation_url_dialog`, `agent_needs_input` not provokable here)

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/elicitation-tui-20260914T174206Z/hooks.jsonl`, `mcp-stub-messages.jsonl`, `form-dialog-screen.txt`)
```json
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"Elicitation","mcp_server_name":"shepherd","message":"Which queue should the probe use?","mode":"form","requested_schema":{"type":"object","properties":{"queue":{"type":"string"}},"required":["queue"]}}}
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"Notification","message":"Claude Code needs your input","notification_type":"elicitation_dialog"}}
"payload":{"session_id":"48422ae5-49d3-4a59-a625-87569be30bed",...,"hook_event_name":"ElicitationResult","mcp_server_name":"shepherd","mode":"form","action":"accept","content":{"queue":"alpha"}}}
```
```text
  MCP server “shepherd” requests your input
  Which queue should the probe use?
  ❯ * queue: Type something…
    Accept    Decline
```
```json
{"t": 1789407744.441, "pid": 4061613, "dir": "in", "msg": {"jsonrpc": "2.0", "id": "elicit-2", "error": {"code": -32602, "message": "MCP error -32602: Client does not support URL-mode elicitation requests"}}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| order for a form elicitation | events | always | `PreToolUse` → `Elicitation{mode:form}` → `Notification{elicitation_dialog}` → (answer) → `ElicitationResult{action:accept, content}` → `Notification{elicitation_response}` → `PostToolUse` | |
| `Notification.message` | string | always | `Claude Code needs your input` | |
| url-mode `elicitation/create` from a stdio server | response | always | JSON-RPC error `-32602 Client does not support URL-mode elicitation requests`; no hooks, no dialog | client capability is `elicitation: {}` |
| `elicitation_url_dialog` | notification_type | **not observed** | | binary emits it for URL-mode dialogs (`binary-context-*/context.txt`) |
| `agent_needs_input` | notification_type | **not observed** | | binary emits it for background-agent/teammate "blocked" states and several setup dialogs (`binary-context-*/context.txt`); not tried (needs agent teams or background sessions) |

**Spec alignment:** line 937: `elicitation_dialog` is verified as a needs-you signal. `elicitation_url_dialog` cannot come from the stdio `shepherd-mcp` binding in 2.1.270, which rejects URL mode (`mcp-stub-messages.jsonl`). `agent_needs_input` and `worker_permission_prompt` remain binary-only.

## Resume across Claude Code versions (2.1.259 ↔ 2.1.270)

- **Produced by:** claude 2.1.259 (claude-agent-sdk 0.2.152 bundled binary) and 2.1.270 (system), `-p`, real API (haiku)
- **Consumed by:** `resume=state.master_session_id` line 1535, lines 1552-1553 ("across restarts, reboots, and upgrades"); M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_cross_version_resume.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/gap-fill/probe_cross_version_resume.sh`
- **Status:** verified live 2026-09-14 (one version pair, both directions)

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/cross-version-resume-20260914T175737Z/A-resume.json`, `A-versions-after-resume.json`, `A-ids.txt`, `B-resume.json`)
```json
{"type": "result", "subtype": "success", "is_error": false, "result": "KIWI-259", "session_id": "96f23b30-2d25-4979-a875-7b461721ebcb", "num_turns": 1}
```
```json
{"ai-title|None": 3, "assistant|2.1.259": 2, "assistant|2.1.270": 2, "atis-latch|None": 4, "attachment|2.1.259": 10, "attachment|2.1.270": 3, "last-prompt|None": 3, "mode|None": 1, "queue-operation|None": 4, "user|2.1.259": 1, "user|2.1.270": 1}
```
```text
size_before_resume=164824 sha256_before=086a7f8fb131f7064b3ee27accaf6e18d08190d8b9ee187ae42d6812260fa4ea
resume exit=0
size_after_resume=274374 prefix_unchanged=086a7f8fb131f7064b3ee27accaf6e18d08190d8b9ee187ae42d6812260fa4ea
```
```json
{"type": "result", "subtype": "success", "is_error": false, "result": "MELON-270", "session_id": "8ccb9276-4c04-4323-923f-8ddfc9ecace0", "num_turns": 1}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| resume 2.1.259 → 2.1.270 | result | always | recalled the code word; same `session_id` | |
| resume 2.1.270 → 2.1.259 (downgrade) | result | always | recalled; same `session_id` | |
| per-entry `version` | string | sometimes | mixed `2.1.259` and `2.1.270` in one file; metadata entries have none | |
| earlier bytes after resume | sha256 of the old prefix | always | unchanged | append-only across versions |

**Spec alignment:** aligned with lines 1552-1553 for this adjacent version pair. A large version jump or a schema migration was not tested.

## `can_use_tool` blocking longer than `await_decision(timeout_s=600)`

- **Produced by:** claude-agent-sdk 0.2.152 with CLI 2.1.259 (bundled) and 2.1.270 (`--cli`), real API (haiku)
- **Consumed by:** `authorize()` lines 1725-1749 (`await_decision(approval, timeout_s=600)`; "a timeout denies with a message the agent can act on"); M4
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py approval_timeout`. Re-run: `/tmp/shp-sdk-9IOKNs/venv/bin/python docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py approval_timeout [--cli /root/.local/bin/claude]`
- **Status:** verified live 2026-09-14

**Real example** (full captures: `docs/probes/2026-09-14-schemas/gap-fill/sdk-approval_timeout-syscli-20260914T171129Z/can-use-tool.jsonl`, `progress.jsonl`, `handler-calls.jsonl`, `meta.json`)
```json
{"_ts": "2026-09-14T17:11:33.047+00:00", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T17:22:03.147+00:00", "phase": "returning allow", "after_s": 630.1}
```
```json
{"_ts": "2026-09-14T17:22:03.160+00:00", "tool": "kill_session", "received": {"id": "ses_slow"}}
```
```json
{"_ts": "2026-09-14T17:22:04.581+00:00", "since_query_s": 633.0, "class": "ResultMessage"}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| CLI/SDK timeout on a pending `can_use_tool` control request | seconds | never observed | callback returned after 630.1 s; the tool ran; `ResultMessage` `success` | both CLI versions |
| messages during the wait | stream | never | first message after the query is the `UserMessage` tool result at 631.6 s | no keep-alive surfaced to the SDK caller |

**Spec alignment:** aligned with lines 1737-1749. Neither CLI version imposes a control-request timeout below 630 s, so the 600 s timeout and its deny message are Shepherd's own. Durations above 630 s were not tested.

## Browser terminal transport: WebSocket on the "stdlib HTTP + SSE" stack

- **Produced by:** Python 3.12.3 (system), stdlib `http.server`, `socket`, `hashlib`, `base64`
- **Consumed by:** §9 diagram line 1150 (`browser ──WS──► sessiond`), §5 stack line 406 ("stdlib HTTP + SSE"); M3
- **Probe:** `docs/probes/2026-09-14-schemas/gap-fill/probe_websocket.py`. Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_websocket.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/websocket-20260914T171610Z/imports.json`, `handshake.json`)
```json
 "websockets": "ModuleNotFoundError: No module named 'websockets'",
 "wsproto": "ModuleNotFoundError: No module named 'wsproto'",
 "aiohttp": "ModuleNotFoundError: No module named 'aiohttp'",
...
 "_pip": "/usr/bin/python3: No module named pip"
```
```json
 "response_head": "HTTP/1.1 101 Switching Protocols\r\nServer: BaseHTTP/0.6 Python/3.12.3\r\nDate: Mon, 14 Sep 2026 17:16:10 GMT\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: e1dFrKT8fv/yzhkYZ+5wPsDLWK4=\r\n\r\n",
 "expected_accept": "e1dFrKT8fv/yzhkYZ+5wPsDLWK4=",
 "accept_matches": true,
 "client_frame_hex": "8183b10402d1aa5f43",
 "server_frame_header_hex": "8108",
 "server_payload": "echo:\u001b[A",
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| WebSocket libraries on system python3 | import | never | `websockets`, `wsproto`, `aiohttp`, `tornado`, `simple_websocket` all missing; no pip | the agent-sdk-mcp surface installed packages only into a venv made with get-pip |
| stdlib 101 upgrade from `BaseHTTPRequestHandler` | response | always | `101 Switching Protocols`, correct `Sec-WebSocket-Accept` | |
| masked client text frame → unmasked server frame | frames | always | `81 83 <mask> ...` in; `81 08 echo:ESC[A` out | a keystroke round-trip works |

**Spec alignment:** line 1150 (WS) against line 406 ("stdlib HTTP + SSE"): not a contradiction in feasibility, since about 60 lines of stdlib code complete an RFC 6455 handshake and frame exchange (`handshake.json`). But the stack line does not list WebSocket, and `ThreadingHTTPServer` gives one thread per open terminal. Either name the hand-rolled WebSocket in §5, or use SSE down plus POST up for keystrokes.

## Fallback `PtyRunner`: the Claude Code TUI under Python `pty.fork`

- **Produced by:** claude 2.1.270 TUI under Python 3.12 `pty.fork` (mock API)
- **Consumed by:** lines 1144-1145 (fallback `PtyRunner`), `Runner` protocol lines 423-430; M3
- **Probe:** `probe_pidfd_pty.py` (part pty). Re-run: `python3 docs/probes/2026-09-14-schemas/gap-fill/probe_pidfd_pty.py`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/gap-fill/pidfd-pty-20260914T175854Z/results.json`, `pty-stream-head.cat-v.txt`, `pty-stream.bin`)
```text
^[7^[[r^[8^[[?25h^[[?25l^[[?2004h^[[?2031h^[[?1004h^[[<u^[[>5u^[[>4;2m^M^M
...
^[[2G^[[38;5;220m^[[1mAccessing^[[12Gworkspace:^[[22m^[[39m^M^M
```
```json
 "pty_turn_and_exit": {
  "initial_bytes": 1323,
  "trust_dialog": "timeout",
  "bytes_after_resize_100x30": 1445,
  "after_trust": "found",
  "turn": "found",
  "exit": {
   "read_end": "EIO",
   "waitpid_status": 0,
   "exitstatus": 0
  },
```
```json
 "pty_master_closed": {
  "ready": "found",
  "waitpid": [
   4063992,
   0
  ],
  "decoded": "exitcode=0",
  "seconds": 0.1,
  "hooks": [
   "SessionStart",
   "SessionEnd[other]"
  ]
 }
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| DEC private modes the TUI toggles | list | always | `?25` cursor, `?1049` alt screen, `?2004` bracketed paste, `?1004` focus, `?1000/1002/1003/1006` mouse, `?2031` colour-scheme reports; plus kitty keyboard `CSI > 5 u` / `CSI < u` | the full set a `PtyRunner` terminal must handle |
| raw-byte text search | behaviour | always | `trust this folder` not found: words are laid out with cursor moves (`Is^[[25Gthis^[[30Ga...`) | screen-state detection needs a terminal emulator |
| `TIOCSWINSZ` + SIGWINCH | redraw | always | 1445 bytes after 120x36 → 100x30 | |
| `/exit` | exit | always | read returns `EIO`; `waitpid` status 0; `SessionEnd{prompt_input_exit}` | |
| close master fd while idle | exit | always | exit 0 within 0.1 s; `SessionEnd{other}` | hang-up is indistinguishable from a normal exit by code |

**Spec alignment:** aligned with lines 1144-1145 ("degraded (no late-attach resync)"). The raw stream cannot be searched for dialog text without a server-side terminal emulator, so the trust-dialog detector from the tmux-tui surface (`capture-pane` text) has no `PtyRunner` equivalent (`pty-stream.bin`).

---

## Not verified on this surface

- **`agent_needs_input`, `worker_permission_prompt`, `elicitation_url_dialog` notifications.** URL mode was attempted and rejected by the client (`-32602`). The other two need agent teams or background sessions, which were not set up. The binary context is in `binary-context-20260914T174348Z/context.txt`.
- **`/rewind` "Restore code and conversation".** The chosen rewind point had no code changes, so only conversation options were offered.
- **Whether Claude Code rewrites `settings.json` and drops `_shepherd_managed`** when the user edits settings through `/hooks` or `/config`. Not attempted.
- **The real `~/.claude/settings.json` and `~/.claude.json`.** Not touched, by rule. User scope was tested through `CLAUDE_CONFIG_DIR`.
- **`can_use_tool` waits longer than 630 s,** and version pairs other than 2.1.259 ↔ 2.1.270.
- **A second tmux client typing into a session while the browser writes.** Only key delivery and the read-only client were checked.
