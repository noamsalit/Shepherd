# Backlog: future work + pre-publish cleanup

**Written:** 2026-09-17
**Status:** nothing here is actioned. Do not start until the implementation
session (M1–M3) has finished — several items touch documents it is reading right now.

This file is new and is not referenced by the spec or any plan, so creating it
cannot affect a running session.

---

## Part 1 — Future work for Shepherd

### Spec edits (cheap, no code impact)

| # | Item | Why | Size |
|---|---|---|---|
| F1 | **Add D56**: `Runner` is a *terminal* seam and `EngineAdapter` is a *CLI-harness* seam by design. A harness-less API-loop session is a **third session class** alongside `owned` / `attached` — not a `Runner` driver. Add matching §17 deferred bullet. | Both seams were validated against three CLI-shaped engines (Claude Code, Codex, Antigravity). That is D9's own warning one level up. Writing it down is the difference between "anticipated" and "discovered in month four". | 1 decision row + 1 bullet |
| F2 | **Rewrite §15 Packaging for three deployment shapes.** It still opens "Linux, single user, no root (D39)" and describes only systemd. D55 revised D39 the next day and named three shapes; §15 never caught up. | A session reading §15 alone builds the Linux installer and misses macOS and the container. | 3 subsections |
| F3 | **Extract §5.0 into `docs/specs/logical-architecture.md`**, referenced from the spec the way `data-schemas.md` is. | The logical architecture is currently buried at line 217 of a 2,700-line file. | ~150 lines moved |
| F4 | **Commit `layer-map.html` into `docs/specs/`.** | Its only on-disk copy is in this session's `/tmp` scratchpad. One reboot from gone, and not in git. | copy |
| F5 | **Update the layer-map artifact** — it says six seams; there are seven since `HostPlatform` (D55). Pin it to the sidebar. | Phone-readable architecture view is stale. | small |

### Product decisions to take

| # | Item | Notes |
|---|---|---|
| F6 | **Consider dropping the systemd user-unit installer.** Keep the Linux *driver* (the container needs it), but treat Linux-local as "dev mode: run in the foreground". The foreground supervision driver already has to exist for the container, so this costs zero extra code. | Saves a chunk of M6 plus the `loginctl enable-linger` footgun that silently kills agent sessions on logout. Two real targets are Mac-laptop and remote-container. |
| F7 | **Remote deployment with a proper UI and authentication.** Owner has plans for this; later phase. Needs the auth seam (deferred in §13) and the multi-user path (D2). | Must be taken explicitly, never as a side effect of shipping a Dockerfile. §13's "127.0.0.1 only, no knob to bind wider" holds until then. |
| F8 | **Test `MacHost` on a real Mac after M4.** The driver is written and passes the `HostPlatform` contract suite — but that suite runs on Linux. It proves the shape, not the behaviour. | Likeliest first failures, both probed as real: macOS has no `/run/user/<uid>`, and `sun_path` is 103 bytes vs Linux's 107 — a socket path that binds here can fail there. Peer credentials use a different call (`LOCAL_PEERCRED` / `getpeereid`). All inside the seam, so fixes stay in `host/mac.py`. |

### Housekeeping

| # | Item |
|---|---|
| F9 | **Delete `docs/plans/2026-09-13-m1-foundation-visibility-plan.md`** — superseded by `2026-09-16-m1-foundation-visibility-plan.md`, and it predates D35–D55. |
| F10 | **Nothing is committed since baseline `22d9ef2`.** Decide the commit strategy before publishing. |
| F11 | **cc10x**: installed from the local directory `/root/src/cc10x-qa` (branch `feat/qa-route-clean`, commit `6ff8ae4` = PR #91), so it will not auto-update. When #91 merges upstream: `claude plugin marketplace remove cc10x && claude plugin marketplace add romiluz13/cc10x`. |

---

## Part 2 — Pre-publish cleanup

**Order matters: scrub BEFORE the first real commit.** Git history is permanent,
and rewriting it later is far more expensive. Nothing is pushed anywhere today —
no remotes, no `gh` auth, no credential helper.

### 2a. The "OX" references — cosmetic, not a leak

**Verified: there is no employer data on this machine.** No `ox-ai-agent`,
`reporting-service`, `vibesec` or `factor` repo exists on disk (`/root` holds
only `AIVisor`, `Finopsera_poc`, `Shepherd`, `src`, `shots`, `snap`). Nothing was
cloned, mirrored, or read from a live system.

The strings are illustrative filler written into the spec's ASCII mockups and
Appendix A during the design dialogue, plus one probe script that names a
throwaway `/tmp` branch `feat/OXDEV-1` to mimic a queue worker's worktree.

The problem is not disclosure — it is that **a reader would reasonably assume it
came from somewhere internal.** Rename to neutral placeholders
(`OXDEV-71937` → `PROJ-123`, `ox-ai-agent` → `payments-api`, etc.).

#### `OXDEV-*` — 108 refs across 10 files

| File | Count | Kind |
|---|---|---|
| `docs/specs/orchestrator-platform.md` | 27 | Appendix A + UI mockups |
| `docs/probes/2026-09-14-schemas/linux-process-git/captures/git.txt` | 27 | synthetic `/tmp` repo capture |
| `docs/specs/data-schemas.md` | 19 | worked examples |
| `docs/probes/2026-09-14-schemas/linux-process-git/SECTION.md` | 18 | probe write-up |
| `docs/probes/2026-09-14-schemas/linux-process-git/probe_git.sh` | 7 | creates `feat/OXDEV-1` in `/tmp` |
| `docs/reviews/.../plan-vs-spec/spec-diff.patch` | 3 | evidence |
| `docs/reviews/.../arch-in-spec/spec-uncommitted-diff.txt` | 3 | evidence |
| `tests/signals/conftest.py` | 2 | fixture string |
| `tests/signals/test_discovery.py` | 1 | fixture string |
| `docs/reviews/.../arch-in-spec/spec-quotes.txt` | 1 | evidence |

#### Internal-looking repo names — 35 refs across 14 files

`ox-ai-agent`, `reporting-service`, `vibesec`, `factor`

| File | Count |
|---|---|
| `docs/specs/orchestrator-platform.md` | 18 |
| `docs/reviews/.../plan-vs-spec/spec-diff.patch` | 3 |
| `docs/reviews/.../arch-in-spec/spec-uncommitted-diff.txt` | 3 |
| `docs/specs/data-schemas.md` | 2 |
| `tests/test_core_runner.py` | 1 |
| `tests/signals/test_hook_lane.py` | 1 |
| `tests/engines/test_hookd_runtime.py` | 1 |
| `src/shepherd/web/static/rail.js` | 1 |
| `src/shepherd/core/runner.py` | 1 |
| `docs/probes/2026-09-16-hookd-latency.md` | 1 |
| `docs/probes/2026-09-14-schemas/linux-process-git/SECTION.md` | 1 |
| `docs/plans/2026-09-17-m2-signals-engine-plan.md` | 1 |
| `docs/plans/2026-09-16-m1-BLOCKERS.md` | 1 |
| `.cc10x/cc10x-hook-events.log` | 1 |

### 2b. Real identifying data — must be scrubbed or excluded

#### Machine hostname `finops-mitm-lab` — 64 refs across 6 files

| File | Count |
|---|---|
| `docs/probes/2026-09-14-schemas/linux-process-git/captures/systemd-xdg.txt` | 43 |
| `docs/specs/data-schemas.md` | 9 |
| `docs/probes/2026-09-14-schemas/linux-process-git/SECTION.md` | 9 |
| `docs/reviews/.../probe-env-provenance/env-readings.txt` | 1 |
| `docs/probes/.../tmux-tui/run-20260914T154946Z/01-trust-dialog-fmt.txt` | 1 |
| `docs/probes/.../tmux-tui/run-20260914T154946Z/01b-list-sessions-after-refuse.txt` | 1 |

#### Owner email `nsalit@gmail.com` — 3 files

All under `docs/reviews/2026-09-14-m1-plan-review/evidence/probe-transcripts/fresh-probe-copies/`.
These are **full session JSONL transcripts**. Highest-risk content in the repo.

#### `/root/` absolute paths — 155 refs in shipped files

| File | Count |
|---|---|
| `docs/specs/data-schemas.md` | 127 |
| `docs/plans/2026-09-16-m1-foundation-visibility-plan.md` | 9 |
| `docs/plans/2026-09-17-m2-signals-engine-plan.md` | 8 |
| `docs/plans/2026-09-17-m3-owned-sessions-plan.md` | 5 |
| `docs/plans/2026-09-17-m3-BLOCKERS.md` | 4 |
| `docs/plans/2026-09-16-m1-BLOCKERS.md` | 2 |
| `docs/plans/2026-09-13-m1-foundation-visibility-plan.md` | 2 |
| `docs/specs/orchestrator-platform.md` | 1 |
| `docs/specs/implementation-constraints.md` | 1 |

(Plus many more inside `docs/probes/` and `docs/reviews/`, which are proposed for exclusion anyway.)

### 2c. No secrets found

Every API-key-shaped string in the repo is a deliberate fake:
`sk-ant-api03-shp-fake-key…`, in 14 probe files. No `.env`, no `.pem`, no
credential files, no real tokens.

### 2d. Proposed publish set

```
publish
  docs/specs/          spec, data-schemas, implementation-constraints
  docs/plans/          current M1–M3 plans (minus the stale 2026-09-13 one)
  docs/methodology/    20K — the parallel-QA experiment write-up
  src/  tests/
  README, LICENSE, .gitignore      (none of the three exists yet)

exclude
  docs/probes/         17M — raw session captures, hook payloads, transcripts
  docs/reviews/        2.0M — includes full JSONL transcripts with the owner's email
  .cc10x/              284K — plugin state
  .venv/
```

~5 MB published instead of 48 MB, and the excluded material is the part that is
recordings of real working sessions rather than design output.

**Note:** `docs/probes/` is cited throughout the spec as evidence (D41). If it is
excluded, either accept the dangling references or add a line saying the raw
captures are kept locally.

### 2e. Authentication — when the time comes

- **Best:** `gh auth login` → GitHub.com → HTTPS → **login with a web browser** (device flow).
  Token lands in the OS keychain. Never typed into chat, never in a file.
- **Alternative:** SSH key (`ssh-keygen -t ed25519`), public half added to GitHub.
- **Avoid:** pasting a PAT into the conversation — it would be in the transcript
  permanently. If a PAT is unavoidable, use a **fine-grained** one, scoped to this
  repo only, `Contents: read/write`, with an expiry.
- **Never** share the token with the assistant. Once `gh`/SSH is authenticated,
  `git push` needs nothing further.

### 2f. Suggested sequence

1. Implementation session finishes M1–M3.
2. Apply F1–F5 (spec edits) and F9 (delete stale plan).
3. Write `.gitignore`, `LICENSE`, `README.md`.
4. Scrub 2a and 2b; review the diff.
5. Owner runs `gh auth login`.
6. First real commit, then `gh repo create --public` and push.

---

## Out of scope — personal machine note

Not part of this repo and never publishable, but present in `/root/`:
`finops-data-dump.sql`, `Finopsera_poc/`, `setup-remote-docker.sh`,
`session-1211127-scrollback-20260912.txt`, `pre-orchestrator-backup-20260720/`.
Flagged only because this is meant to be a clean personal machine.
