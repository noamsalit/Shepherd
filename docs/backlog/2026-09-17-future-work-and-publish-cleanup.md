# Backlog: future work + pre-publish cleanup

**Written:** 2026-09-17
**Updated:** 2026-09-20 — F1–F5 and F9 applied; the scrub applied in part; the
rest is open with the decisions named.

---

## Status, 2026-09-20

| | Item | State |
|---|---|---|
| F1 | D56 — `Runner` is a terminal seam, `EngineAdapter` a CLI-harness seam | **done** — decision row + §17 bullet |
| F2 | §15 rewritten for three deployment shapes | **done** — 15.1 macOS · 15.2 systemd user · 15.3 container |
| F3 | §5.0 extracted to `logical-architecture.md` | **done** — §5.0 is now a pointer + summary table |
| F4 | commit `layer-map.html` | **done, but the original was lost** — the reboot took the `/tmp` copy, exactly as this file predicted. Rebuilt from the extracted document, not recovered |
| F5 | layer map updated and pinned | **done** — seven seams, L6, D56 |
| F6 | drop the systemd user-unit installer? | **open — decision** (recorded in §15.2) |
| F7 | remote deployment with auth | **open — decision**, and deliberately not started |
| F8 | test `MacHost` on a real Mac | **in progress elsewhere** — a session on the owner's Mac is running it |
| F9 | delete the stale 2026-09-13 M1 plan | **done** |
| F10 | commit strategy | **overtaken** — see "What the push actually did" below |
| 2a | employer-associated identifiers | **done** — 109 refs, every tracked file, no exceptions |
| F11 | cc10x installed from a local checkout | **still open** — PR #91 was still `OPEN` when checked on 2026-09-20 |

### Three corrections this pass made to the spec itself

Found while doing the above, and recorded rather than quietly fixed:

1. **§6 was titled "The six seams" and listed six**, with no `HostPlatform` block —
   D55 added the seventh on 2026-09-16 and §6 never caught up. Fixed, and the
   seam's eight members are now written out.
2. **`MasterRuntime` has six members, not five.** M4 added `close()` as a
   *flagged* deviation (`core/master.py`, DP9) because a runtime that owns a
   subprocess and a connection cannot be shut down without one. The flag is now
   promoted into §6.
3. **§5.0 said five layers; the enforced map has had six since ADR-1.**
   `tests/boundaries/_imports.py` carries `"shepherd.daemons": 6`. For four
   milestones the document and the test disagreed about how many layers exist.
   The test was right; `logical-architecture.md` now documents L6.

### What the push actually did (F10, overtaken by events)

The first real commit and push happened on **2026-09-18, before any of Part 2
was applied**, and `noamsalit/Shepherd` is **public**. So the sequence in §2f was
not followed, and the scrub below is now a *working-tree* scrub rather than a
pre-publish one. What that changes:

- **`git history` still contains every unscrubbed string.** A rename today is
  visible in the current tree only.
- **No secrets were exposed.** Re-verified 2026-09-20: every API-key-shaped
  string in the repo is a deliberate fake, and a scan for real key shapes across
  all tracked files returns nothing.
- **The owner's email is in the history regardless** — it is the commit author
  address on every commit, so scrubbing it from twelve JSONL files does not
  un-publish it.
- Whether to rewrite history is an **open decision**, and it is blocked on two
  things: `main`'s branch protection disables force-pushes, and a second session
  currently holds a working clone.

### What was scrubbed, and what was deliberately left

**Superseded the same day.** An earlier pass on 2026-09-20 scrubbed only
`docs/specs/` and `docs/plans/`, and deliberately kept three things: the ticket
id inside a verbatim probe capture, the frozen corpora under `docs/probes/` and
`docs/reviews/`, and the fixture strings in `src/` and `tests/`. The reasoning
was that a sanitised capture is a fabricated one, and that a second session was
editing the source trees.

**The owner overrode that: the name goes everywhere, with no exceptions.** That
decision is theirs to make, and it is the right trade — the evidence is
*regenerable* (the probe script was renamed alongside its capture, so a re-run
reproduces it), which was the only property the frozen-corpus rule was actually
protecting. See §2a below for what was replaced and the two consequences.

The remaining "left deliberately" items are unchanged and unrelated to the name:

- **The hostname and the `/root/` paths stay.** They appear inside verbatim
  command output and disclose only that the machine had a name and ran as root.
- **`docs/reviews/`'s session transcripts stay.** They carry the owner's email
  and subscription type, which are in the commit metadata regardless.

---

**Original document follows.**

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

### 2a. Employer-associated identifiers — **removed 2026-09-20**

**Status: done, and done completely.** The owner's instruction was that the
former employer's name must not appear anywhere in the documentation or the
repository. It does not. The old strings are deliberately not reproduced in this
file either, because a cleanup note that quotes what it cleaned up leaves the
string in the repository.

What was in scope: a ticket-id prefix, four repo names, a GitLab group in one
`vcs_remote` example, and a workspace name used in path examples. They were
illustrative filler written into the spec's ASCII mockups and Appendix A during
the design dialogue, plus one probe script that named a throwaway `/tmp` branch
to mimic a queue worker's worktree. **No employer data was ever on this
machine** — nothing was cloned, mirrored, or read from a live system — so this
was never a disclosure problem. It was that a reader would reasonably assume the
names came from somewhere internal.

**109 references, every tracked file, replaced:**

| Was | Now |
|---|---|
| the ticket prefix | `PROJ-<same digits>` — numbers preserved, so every cross-reference still resolves |
| repo name 1 | `payments-api` |
| repo name 2 | `billing-api` |
| repo name 3 | `scanner-cli` |
| repo name 4 | `data-loader` |
| the GitLab group in `repo.vcs_remote` | `acme` |
| the workspace name in `/work/<name>` examples | `acme` |

Covered `docs/specs/`, `docs/plans/`, `docs/probes/`, `docs/reviews/`, `src/`,
`tests/` and `.cc10x/`. Verified by a case-insensitive scan over every tracked
file that returns nothing.

**Three consequences, all recorded rather than hidden:**

1. **The probe captures are no longer verbatim.** `docs/probes/` is frozen
   evidence, and the rule in `CLAUDE.md` is that it is read-only — because a
   capture edited to look tidy stops being evidence. That rule was overridden
   here **explicitly and on the owner's instruction**, which is the only way it
   may be overridden. The affected captures carry a notice saying which token
   was substituted and that the rest of the output is unmodified, so no later
   reader mistakes a sanitised capture for raw output. The probe script was
   renamed to match, so **re-running it reproduces the sanitised capture** — the
   evidence is regenerable, which is the property that mattered.
2. **ASCII mockups were re-aligned.** The new names are different lengths, so box
   borders and the `[→]` action columns were repadded. One pre-existing
   misalignment in `2026-09-17-m4-orchestrator-plan.md` (a dependency graph that
   was never aligned) was left alone rather than "fixed" under cover of this
   change.

3. **D38's byte-freeze on `web/`/`cli/` went red, correctly.** One comment in
   `web/static/rail.js` quoted a rail row using an old repo name, and Gate A
   exists to fail exactly that. The one permitted re-base was spent by T24 on
   2026-09-18, so regenerating the manifest under T24's name would have
   attributed a 2026-09-20 publish scrub to a task that ran two days earlier.
   Instead the gate gained a **third block**, `post_milestone.edits`: D38's
   sentence is about *completing L4*, and that milestone is closed, so a later
   edit is outside what it claims — but it still may not pass unnoticed. Each
   entry names a path, a date, an agent and a reason; the paths must be disjoint
   from `rebase.regenerated_paths`, so the block can never relaunder a path T24
   already moved; and the drift equality now covers both lists. `baseline` is
   still never rewritten and `rebase` is still T24's, spent once. Proved with
   three planted mutations — an overlapping path, an undeclared move, and a
   declaration for a file that did not move — each red, restoration verified by
   `sha256sum -c`.

**Four base64 blobs inside probe JSONL happen to contain the two letters as a
substring** of an opaque token. They are random encoded bytes, not the name, and
editing them would corrupt the capture for no gain. Named here so the scan's
result is explainable rather than surprising.


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
