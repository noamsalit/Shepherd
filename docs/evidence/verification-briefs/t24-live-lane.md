# T24 — the live lane: one real owned session, end to end

Your spec is **`docs/plans/2026-09-17-m3-owned-sessions-plan.md`, section "### Task 24"**, verbatim
and binding. Read it in full before anything else. Then read, in this order:

1. `CLAUDE.md` — tmux safety, and §18 "Incident 2026-09-12" in
   `docs/specs/orchestrator-platform.md`, which is what these rules cost.
2. `docs/plans/2026-09-17-m3-BLOCKERS.md` — the milestone's decision ledger. **Read the tail.**
   BLOCKER-T1-1..T1-4 are live-probe findings you inherit; the "T19 — verified by the router" entry
   tells you which half of clause 10 is yours.
3. `docs/specs/data-schemas.md` — **no data shape may be asserted without a real example in here.**
4. `docs/specs/implementation-constraints.md` — all of it.
5. `docs/specs/orchestrator-platform.md` §3 (the 54 decisions), §5.0 (the layers).
6. `tests/e2e/conftest.py` and the shipped live tests — the isolation you are composing on top of.

## The blast-radius rules. These are absolute.

- **Never run `tmux kill-server` without `-L`.** Pass `-L` explicitly on **every** tmux invocation,
  including teardown, including from inside tmux (a command run inside tmux inherits `$TMUX` and
  resolves to that session's socket, so a bare `kill-server` from an isolated socket still kills it).
- **The user has live sessions on socket `shepherd`.** Never name that
  socket. Your socket is **`shepherd-m3-live`** and nothing else.
- **Never put `:` in a tmux session name** — tmux reserves it as the `session:window` separator and
  silently rewrites the name. Use `shepherd_<id>`.
- **Never write anywhere under `~/.claude/`.** `~/.claude/settings.json` must stay byte-identical at
  sha256 `375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac` — the autouse per-test
  guard asserts it before and after every test in the lane and you keep that. Never read
  `<pid>.<64hex>.key` sidecars (they are peer tokens).
- Do not `git commit`. Do not `rm -rf` anything under the repo except `__pycache__` and your own
  scratchpad. `docs/probes/` is read-only frozen evidence.

**Before your first live run**, print the complete set of tmux argvs the lane will issue and the
teardown sequence, and check each one against `check_tmux_argv`. The plan marks this
`Checkpoint Type: human_verify` for exactly this reason. If any argv names a socket that is not
`^shepherd-m3-`, stop and report rather than adjusting it.

## What the lane must not be allowed to be

A live test that **cannot fail** is worse than no live test. The plan records the precedent: revision
1's `test_a_spawn_registers_exactly_one_row` asserted `count == 1` in a world spawned with
`--settings {}`, where the second writer could never run — a vacuous pass, and the acceptance clause
it served was simply false. Hence `installed_settings`, and hence the rule: **assert the ingest count
actually moved before asserting anything about the row.** Apply that shape to all six tests: each one
asserts **arrival** — that the real thing happened — before it asserts the property.

A live test that fails is **investigated, never retried into green**. No timing assertions.

## Scope discipline

- `CLAUDE_CONFIG_DIR` is out (M1 Finding 3: it breaks authentication).
- Asserting a session **count** against the real config dir is out (M1's F10: the user's own sessions
  are visible).
- Do **not** delete `test_no_tmux_is_invoked_at_all` — T5 already moved its rule into
  `tests/boundaries/`. You add the **narrower live second check**,
  `test_every_tmux_call_in_the_live_lane_names_a_throwaway_socket`, observed through the lane's
  `make_run_argv` and **not scanned from source**. Source-scanning and call-observing catch different
  things, which is why both exist.
- **Mutation proof required on the boundaries rule:** plant `-L shepherd` in a live test **in your
  shadow tree** and confirm red. Never plant that in the real tree.

## Your files — you are the only writer of these

`tests/e2e/conftest.py`, `tests/e2e/test_live_owned_session.py` (new),
`tests/e2e/test_live_ask_fork.py` (new), `tests/e2e/test_live_attached_session.py` (extended),
and an append at the end of `docs/plans/2026-09-17-m3-BLOCKERS.md` and of the plan's Progress notes.
`tests/e2e/test_live_rename.py` is T20's — read it, do not rewrite it.

## Mutation discipline

Plant only in **`scratchpad/t24/shadow/`** — `cp -a src tests pyproject.toml docs` into it, strip
`__pycache__`, run pytest with `cwd=` the shadow. Shadow **both** `src/` and `tests/`; boundary rules
resolve the repo root from the test file. Never plant in the real tree, and never in a path whose
default target is a real user file — that mistake once wrote to the user's real `~/.claude.json`.
Prove restoration with a command whose **exit code decides** (`sha256sum -c`), never a printed hash.

## Exit criteria

M1's 7 and M2's 5 live tests still pass; M3's **7** (your six plus T20's) pass; `tmux -L
shepherd-m3-live ls` reports **no server**; `tmux -L shepherd ls` shows the same sessions at the end
of your run as at the start (**read them, never hard-code them**); `~/.claude/settings.json` still
`375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac`; the default run
(`.venv/bin/pytest`) still green and `mypy --strict src` clean.

## Report back

Every live test with what it actually observed (the real exit code, the real dialog, the real bytes
— quote them). The tmux argvs the lane issued. The mutation proofs with red/survived — **report
survivors, a survivor is information**. Anything in the plan you found false of this tree. The
before/after `~/.claude/settings.json` hashes and the `tmux -L shepherd ls` output.
