# Progress

## Current Workflow

PLAN — M1 (foundation + visibility) of the Shepherd orchestrator platform.

## Tasks

Not yet created.

## Completed

- Read `docs/specs/orchestrator-platform.md` in full (2381 lines, §1–§19 + Appendix A).
- Established environment ground truth (Python/SQLite/tmux/claude/network/no-node).
- Recovered and analysed the §18 hook-payload probe from a prior session.
- Resolved scope (M1–M4), platform (cross-platform, Linux live), and credential posture with the user.

## Verification

- `FULL OUTER JOIN` probe (spec §18): SQLite 3.45.1 — **SUPPORTED**.
- Dependency probe: `pytest` 9.1.1, `mypy`, `claude-agent-sdk` 0.2.152 install cleanly into a venv.
- Hook-event probe: 77 real events captured across 12 event types; 12 registered event types
  never fired.

## M3 Task 10 — `engines/claude_code/spawn.py` (2026-09-17)

`claude --version`: **2.1.273 (Claude Code)** — `data-schemas.md` pins every shape to 2.1.270
(G-M3-7). `tmux -V`: 3.4. `claude --help` on this host, the six flags M3 spawns with:

```text
 --effort <level>                Effort level for the current session
 --fork-session                  When resuming, create a new session ID
 --model <model>                 Model for the current session. Provide
 -n, --name <name>               Set a display name for this session
 --no-session-persistence        Disable session persistence - sessions
 --session-id <uuid>             Use a specific session ID for the
```

No flag has drifted. `tests/engines/test_spawn_argv.py::test_every_flag_is_present_in_claude_help`
(`-m live`) asserts this on every live run and prints the version it saw.

## Last Updated

2026-09-12
