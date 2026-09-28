# qa6 rulings BUILD — incidents

## 2026-09-27 ~18:50 IDT — API session limit (HTTP 429)
Five agents stopped mid-run: P5 builder (14 files changed, uncommitted), P10 builder (7 files),
P11 REM-FIX (12 files), P6 verifier, P7 verifier (both read-only). Limit reset 19:10 IDT. Router
re-dispatched each with "resume from the uncommitted worktree state" at 19:11. No work lost.
