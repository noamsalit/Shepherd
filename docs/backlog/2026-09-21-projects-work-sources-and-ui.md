# Forward work — projects, work sources, and the UI redesign

**Written 2026-09-21.** This is the register for everything decided on
2026-09-21 that is **not built**. It supersedes nothing; it is the milestone
plan that D57–D64 and the UI redesign do not otherwise have.

Nothing here has been implemented. `git diff` for 2026-09-21 touches
documentation only, plus one test-fixture repair (see W0).

---

## Where the decisions live

| | |
|---|---|
| **D57–D64** | `docs/specs/orchestrator-platform.md` §3 — projects, lifecycle, `Unassigned`, repo↔project many-to-many, delete semantics, discovery switches, work sources, provider-declared filters |
| **UI** | `docs/design/ui-decisions.md` — U1–U15, plus the two artifact links |
| **Harness** | `docs/specs/harness-contract.md` — deferred, decided in outline, six open questions |
| **Auth** | `docs/specs/credentials-and-auth.md` — four questions, **none answered** |
| **Sandboxing** | spec §17 — none exists today; the container plan is recorded there |

## W0 — done on 2026-09-21

- **The Linux-only test failure is fixed.** `tests/engines/test_hook_dispatch_delivery.py::test_the_wedge_fixture_really_wedges_an_unbounded_writer`
  asserted that an unbounded writer wedges against a hung peer. It passed on
  macOS and failed on Linux for a real reason: `LARGE_FRAME` is 40 KB and
  Linux's `/proc/sys/net/core/wmem_default` is **212,992**, so the write landed
  entirely in the socket buffer and returned. macOS's default is ~8 KB, so
  there it wedged. The negative control now uses its own `WEDGE_FRAME` of 1 MB,
  sized clear of both rather than probed — a test that reads the tunable it
  depends on can be made to pass by changing the machine.

## W1 — Projects backend (D57–D61)

The largest piece, and **not a UI change**. It can land without touching
`web/static/` at all, which keeps the D38 byte-freeze out of it entirely.

1. **Migration 004** — `workspace.root_path` dropped; `workspace.description`
   added; `repo.workspace_id` replaced by a repo↔project join table (D60).
2. **`admission.py`** — the allowlist becomes the registered repo paths alone.
   Drop the workspace-root branch (and with it the T11-1 special case).
3. **`upsert_workspace`'s match-on-name goes.** Identity is `workspace.id`.
   This closes a live defect: today `/work/api` and `/personal/api` collapse
   into one project and the second silently overwrites the first's path.
4. **Five verbs**, registered as `ToolDef`s so the master and the HTTP API share
   them: `create_project`, `rename_project`, `delete_project`, `add_repo`,
   `remove_repo`. `create_project`, `add_repo` and `delete_project` are
   `blast_class=local_destructive`.
5. **`list_repos` gets a tool and a route.** It exists in the store today and
   nothing exposes it, so the UI cannot see a project's repos at all.
6. **`Unassigned`** (D59) — a reserved project, and the policy lives in
   `bind_cwd_to_repo`, the one function both discovery lanes already call.
7. **Delete** (D61) forgets, cascading to sessions; running sessions force a
   three-way choice rather than being killed silently.

**Route it through cc10x as PLAN first, not BUILD.** Migration plus a schema
change plus five gated verbs plus a policy change both discovery lanes hit is
exactly the scope where the plan-review gate earns its keep.

## W2 — Discovery switches (D62)

Three independent gates, all shipping **on**:

1. `discovery_pass` **inside** `run_discovery_loop` — not the thread. The
   thread also owns the liveness sweep and M3's mailbox pass, so killing it
   silently loses the demotion that stops a wedged session claiming `running`.
2. D47's accept-the-first-event-of-any-kind, which is what makes the hook lane
   a second discovery source.
3. `bind_cwd_to_repo`'s auto-create, which is D59's policy.

**One sub-question is deliberately open:** with (2) off, a hook event from an
unregistered session must either be **dropped** — losing the stop reason for a
session the scan is showing — or **accepted without registering**, which means
holding state for a session we decided not to track. Neither is free. Answer it
when a switch is actually needed.

## W3 — Work sources (D63, D64)

Arrives with M5's `queue` table, or earlier as configuration-only.

1. Queue configuration moves **onto the project**; Settings keeps health
   (`last_sync_at`, `last_sync_error`, drain state).
2. `WorkItemCapabilities` gains a **filter declaration** — per field: key,
   label, kind (`single_select` / `multi_select` / `text`), and how options are
   fetched. The UI renders the declaration and never learns a query language.
3. The raw provider query stays as an explicit **Advanced** field.
4. **Saving validates and reports the match count.** A typo returning zero is
   otherwise indistinguishable from a correct filter over an empty backlog —
   neither is an error, nobody is told, and the queue quietly does nothing.
5. `queue.enabled` stays `FALSE` by default. *Connected but paused* is a normal
   state the page renders plainly, not a warning.

## W4 — The UI

Blocked on nothing technical; the owner gates it. See
`docs/design/ui-decisions.md` for the settled list and, more importantly, for
**U1–U4 and U15, which must be answered before implementing.** The two that
matter most:

- the **Needs-You rail** has no home in the new design, and it is the element
  the whole product is built around;
- the **autonomy toggle** is Settings-only, against §12's *"visible at all
  times"*.

## W5 — Not started, ordered by when they bite

- **Queues and Kanban pages** — placeholders in the design, never discussed.
- **Model and engine per session (U15)** — proposed three-level precedence, not
  decided.
- **Bring your own harness** — `harness-contract.md`, six open questions.
- **Credentials** — `credentials-and-auth.md`, four open questions, none
  answered. Needed only when Shepherd stops being one person on one machine.
- **Real sandboxing** — spec §17. Same trigger as credentials.


## W6 — Documentation debt found by the 2026-09-21 audit

Two read-only audits compared every factual claim in the specs against `src/`. Most
findings were corrected the same day; these were left, deliberately, because each is a
section rewrite rather than a sentence fix. **Each is a real inaccuracy, not a nitpick.**

1. **§6's `Runner` Protocol lists 8 members; `runner/base.py` ships 12** — the eight plus
   `pane()`, `list_owned_panes()`, `attached_clients()`, `clear_input()`. `snapshot()`'s
   second parameter is `scrollback`, not `lines`. A status comment now says so in §6;
   the member list itself was not rewritten.
2. **§7 omits ten shipped columns.** `session` carries `observed_at`,
   `live_subagent_ids`, `created_task_ids`, `completed_task_ids`, `pid`, `proc_start`,
   `auto_compact_at`, `quota_notice_at`; `repo` carries `owner_id` and `git_common_dir`.
   `git_common_dir` matters most — it is D48's binding key and §7 points at `root_path`
   instead.
3. **§16's M4 row still says "the two MCP exporters".** One shipped. §11 now carries the
   correction; §16 does not.
4. **§14 names `ScriptedWorkItemProvider` and `ScriptedEngine`**, which do not exist, and
   omits `ScriptedHost`, which does. Flagged in place, list not rewritten.
5. **§8's hook-dispatcher code sample is the shape that was rejected.** Flagged in place;
   the real one-liner lives in §15 and in `hookd_command.py`.
6. **Appendix A needs a rewrite** (C22): `repo_id` values contradict D48, and the
   `workspace` row is built on `root_path`, which D57 removes.
7. **§12's ASCII mockups took damage in the 2026-09-20 scrub** — box borders at the
   fleet-page mockup no longer align after the substitutions changed string widths.

**Method note, worth keeping.** Both audits were told to *verify every numeric and
symbolic claim against the source* rather than to read for plausibility. That is what
found them: the counts a reader trusts most (105 boundary rules, 127 mypy files, 140
lines, 20 stop reasons, 64 decisions) were all **correct**, and the errors were in prose
that looked settled.

## Still open from before 2026-09-21

Carried forward so this file is a complete register. Detail in
`docs/plans/m4-blockers/router-decisions.md` and
`docs/plans/m1-m4-qa/fixes.md`.

1. **`fleet_summary` exceeds §11's "~40 lines regardless of fleet size"** —
   measured 92 lines at 5 sessions, 127 at 25, 428 at 200. Two viable repairs.
2. **`shepherd status` is blind to a running daemon** — needs a transport
   decision *and* a second Gate A re-base, which must be taken together.
3. **§T25-8** — a worker released at shutdown meets a closed store.
   **Deterministic, not racy**; the QA pass measured it 20/20.
4. **Track C's reversal condition** — every handler now receives a
   `CallerContext`, but `caller_id` is an **unauthenticated self-stamp**. Scope
   is expressible; identity is not.
5. **F6** — drop the systemd user-unit installer?
6. **License** — none chosen. Default copyright applies on a public repo.
7. **`MacHost` is unverified** (`verified() == False`). A macOS port landed on
   2026-09-20 and the suite passes there, but the five G1 captures the spec asks
   for are not in the tree.
8. **The browser UI has never been opened by a human.** HANDOFF's manual
   checklist is outstanding, including the no-JavaScript degrade.
9. **Appendix A of the spec is stale** (C22) — and now doubly so, because D57
   removes the `root_path` its example row is built on.
