# Backlog — SD-09: sessions cannot reach Shepherd's tools (deferred 2026-09-27)

**Status:** deferred by the owner on 2026-09-27 ("Let's defer this for now"). Not in the qa6
rulings BUILD (`docs/plans/2026-09-27-qa6-rulings-plan.md`, phase P14 is out of scope).

## The gap

The README promises capability 3: "sessions message and spawn each other". It does not exist.
A Shepherd session is a plain `claude` process in a tmux pane, and nothing hands it a way to
call Shepherd's tool surface (`send_to_session`, `ask_session`, `spawn_session`, …). Only the
human (web UI, CLI) and the master can call tools today.

- qa6 scenario: **O12** (FAIL). Evidence: `.cc10x/qa/wf-20260923T182839Z-9adb11fc/report.md`
  §8 `### SD-09` (spec ref C-13).
- Interim: the README marks capability 3 as "not yet" (qa6 rulings plan, P1).

## Open decision (OD-1): how a session gets the channel

Both options route calls over the owner-only Unix RPC socket built for BC-05 (qa6 rulings
plan, P10). The caller is identified by the session's own id.

| Option | How | Trade-off |
|---|---|---|
| **A — per-session MCP server (recommended)** | Shepherd spawns each session with `--mcp-config` pointing at a small stdio MCP server that forwards to the RPC socket as the SESSION audience. Caller id from `CLAUDE_CODE_SESSION_ID` (captured in `docs/specs/data-schemas.md:3903-3943`). | Native tools with real return values; matches spec §11. More to build. |
| B — CLI over Bash | Session runs `shepherd send` / `shepherd spawn`; `SHEPHERD_SESSION_ID` in the pane env. | Simpler; the agent must remember to shell out, and replies are plain text. |
| C — hooks | — | Rejected: hooks are one-way and cannot return a result. |

## Prerequisites before building

1. BC-05 RPC socket shipped (qa6 rulings plan P10).
2. M4 plan Track C prerequisite 2: a per-caller scope property (handlers already receive
   `ctx`; the scope does not exist yet), and the G-M4-16 audience declarations corrected.
3. A new spec §3 row (D80 is reserved for it).
4. Re-verify qa6 waves 1, 4, 5 and 8 after it lands (spawn argv changes touch every spawn).
