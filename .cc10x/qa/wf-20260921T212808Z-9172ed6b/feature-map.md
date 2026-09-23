# Feature Map: Projects backend + dark-only web UI redesign (Shepherd / Flock / Projects / Settings)

**Workflow:** wf:wf-20260921T212808Z-9172ed6b · **Sources consolidated:** 3 lanes
**Status:** consolidated · **Revision:** `r4` · **Tree:** branch `integration`, HEAD `c243773`
**Written by the router, inline, after all three researchers returned.**

> **`r4` amendment, 2026-09-22 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap
> reached). `r4` is a **preflight-driven environment amendment**: `qa-preflight` measured the host
> and returned five corrections, **all five against `env-plan.md`** and all classed `wrong-guess`.
> **Exactly one of them turns on a fact restated in this file** — §5's **B9**, whose premise said
> *"the scratchpad path alone is 88"*. Measured: the scratchpad **root** is **76**, 88 is the
> *subdir* form, the suffix `/shepherd/controld.sock` is **23** and the budget is **107** (107
> BOUND, 108 REFUSED on real `AF_UNIX` binds), so the ceiling on `XDG_RUNTIME_DIR` is **84**.
> **B9's consequence is unchanged** and is corrected in place below. **Nothing else in this file
> changed**: no research claim, no input space, no blocker's consequence, and no new source was
> read. `r3` remains what pass 2 reviewed.

> **`r3` amendment, 2026-09-22 — UNREVIEWED BY A FRESH PASS.** Fresh-review passes: 2/2 (cap
> reached). Pass 2 returned five blocking findings against the test plan; **three** of them turn on
> a fact **restated in this file**, and those restatements are sharpened here rather than left to
> be mis-read again. They are marked **`r3`** inline: §4's `routes.py` boundary row (*"path-param-wins"*
> is true of `routes.py:250` but is **not** the guard a wire-level test observes, and naming it
> alone is what led the plan to send a body key that reached **neither** guard); §6's
> `#p-name`/`#p-desc`/`#p-new-path` value row (**duplicate name is a page-side warning, not a
> refusal** — `create_project` cannot refuse a name); and §6's `#p-new-path` keyboard row (the
> field exists in the dialog's **edit** mode only). **Nothing in §6's unreduced input space
> changes** — the space was right in `r1` and in `r2`, and it is right now; what the plan claimed
> to *drive* of it was not. No new lane was run and no new source was read: every `r3` note cites a
> file already cited here.

> **`r2` amendment, 2026-09-22.** A fresh review of the test plan and the environment plan returned
> six blocking findings; three of them corrected facts that are **restated in this file**, and those
> restatements are corrected here rather than left to disagree with the plan. They are marked
> **`r2`** inline: §5's B3 companion (a "non-zero box" is a one-pixel floor), §7's daemon-death chain
> (the four per-module unreachable sentences **do not exist**), §8's C-6 row and §9's S0 bullet
> (C-6 was resolvable by reading `store/reads.py:283-284` and
> `toolsurface/tools_projects_delete.py:128-136`; S0 confirms a reading rather than choosing between
> four live possibilities). Nothing in §6's **unreduced** input space changes — the space was right;
> what the plan claimed to cover of it was not.

---

## 0. Source coverage

| Lane | Coverage | Confidence | Note |
| --- | --- | --- | --- |
| `code` | partial | 86 | Read all 5 web python modules, all 9 shipped JS modules, index.html, the 4 projects toolsurface modules, compose.py and the tools_m1 projections. **Not read:** `app.css` (2490 lines) line by line, the 11 store verbs behind the lifecycle, full bodies of the 28 web test files. So every CSS-layout claim is second-hand from comments. |
| `spec_docs` | full | high | All eight authority documents plus `projects-ui-blockers/README.md`. **Deliberately excluded:** `docs/plans/recon/2026-09-21-backend-and-frontend-recon.md`, which the plan calls *"the measurement … outranks every other document"* (`plan:186`) but which was not in the lane's authority list — see G-12. Every recon-derived fact is reported as *the plan's claim about a measurement*, not as measured truth. |
| `cc10x_artifacts` | full | high | All memory files, the workflow JSON + events log, and `runs/qa3/report-qa3.md`. Confirmed the other lanes' artifacts were unfilled templates, so no cross-lane leak. |
| `tickets` | unavailable | — | Atlassian MCP present but unauthenticated. User confirmed repo docs are the authority. |

**Incidents:** two, both router-caused, both recorded in `qa.guard_observations`.
**G3** — the `cc10x_artifacts` and `spec_docs` lanes' reports overflowed the inline hand-back and the
harness spilled them to `/root/.claude/projects/.../tool-results/*.txt`, which matches the user-set
denied_read glob `/root/.claude/**`. The guard **denied the router's read**, correctly, on its first
real test. Not routed around; the lanes were re-asked for chunked inline hand-back.
**G4** — the router asked the `cc10x_artifacts` researcher to write its report into `.cc10x/`. It
**refused**, citing its read-only contract. The refusal was right and the router's request was the
error. No researcher wrote any file except `spec_docs.md`, written by the `spec_docs` lane before the
retraction reached it.

**One structural fact that dominates this map:** rounds 1–4 **never ran the QA route**. Only
`qa-executor` — the last of seven links — was dispatched, four times, with no feature map, no test
plan, no env plan, no preflight and no harness review. All 22 recorded defects came from a single
unreviewed executor. Round 5 is the first time this feature has been through the chain.

---

## 1. What the feature is

`controld` binds one stdlib `ThreadingHTTPServer` on `127.0.0.1` only and serves one HTML shell, static
JS/CSS, a table-driven JSON API, one SSE stream and one WebSocket upgrade. **There is no handler with
a body** — every route is a `path template -> tool name` pair resolved and handed to `invoke()`. The
shell ships **six** page roots; four are live (Shepherd, Flock, Projects, Settings) and two (Queues,
Kanban) are static "not built this milestone" stubs with no module. Behind them sit the projects
lifecycle verbs, migration 004's repo-project join table, a reserved `Unassigned` project, and a
delete that cascades inside the verb. Every user action is therefore assertable as exactly one
`invoke()` with a known argument set — which is the single most useful property this system has for
testing it.

---

## 2. Pipeline

| # | Leg | What happens | Sources that agree | Disagreement? |
| --- | --- | --- | --- | --- |
| 1 | browser → `FleetHandler` | Origin **and** Host checked before the body is read, on every POST and both streams; body capped at 1 MiB and must be a JSON object | code, spec | none |
| 2 | handler → `routes.py` | template match; undeclared query/body fields **dropped**; path parameter applied **last** so it always wins; static templates ordered first | code, spec | none |
| 3 | routes → `registry.invoke` + chokepoint | schema check, audience gate (`Audience.HUMAN`, `caller_id="web"`), audit sink; failures flattened to `GENERIC_ERROR` + correlation id | code, spec | none |
| 4 | handler → one store verb | arrange args, call one verb (or plan/kill/commit), project the record | code, spec | none |
| 5 | `announce()` | publishes **iff** the record's own positive key is True — a refusal announces nothing | code, spec(remfix) | **C-2** (spec §12 lists no `project.*` kind at all) |
| 6 | ring → `sse.envelope` | `session_id` / `project_id` promoted out of the payload; rest JSON-whitelisted | code, spec | none |
| 7 | `sse.frame()` | `id: <seq>`, **no `event:` name**, so an unknown type still reaches the page | code | uncorroborated (one lane) |
| 8 | `sse.js` → `app.js::onEnvelope` | single `message` listener → `refreshAll()`, coalesced to at most two passes, no timer | code | uncorroborated (one lane) |
| 9 | `add_repo` only: → git subprocess | `Path.resolve(strict)` + `probe_repo` + `repo_root` + `resolve_remote` at the **tool** layer, because `store/` does no filesystem I/O | code, spec | none |
| 10 | `delete_project` only: → kill path | kill runs **between** plan and commit, on the calling thread, **outside any transaction**; a raising kill is caught per session and counted as `stop_failed` | code, spec | none |

Legs 7 and 8 are described by the `code` lane alone. Nothing corroborates them; assertions there
carry less confidence than legs 1–6.

---

## 3. Contradictions

Only rows with a real test-design consequence are here. Documentation debt is in §8.

| C-n | What disagrees | Sources | Who wins, and why | **Changes what we test?** | Severity |
| --- | --- | --- | --- | --- | --- |
| **C-1** | **Three acceptance criteria are false of the tree.** AC-16 asserts `len(BODY_ARGS) == 15`; AC-21 asserts exactly **six** `post_milestone` entries; AC-23 asserts `terminal.js` byte-clean. | spec vs code | **Code wins — settled by measurement, not argument.** Measured on HEAD `c243773`: `API_ROUTES`=14, `POST_ROUTES`=16, **`BODY_ARGS`=16**, **`post_milestone.edits`=7**, `terminal.js` baseline `ace78240` vs current `781bed86`. Each moved because a *later correct change* (the eighth verb, D60 reachability, D6's terminal fit) shifted a count the plan restates. The plan's own A11 predicted exactly this for `terminal.js`: *"the count moves six → seven and the plan is wrong by one."* | **Yes, decisively.** Running AC-28's whole-tree gate unamended produces three reds that are **not defects**, and a run that reports them as defects is worse than no run. Round 5 measures the tree as it is and declares the three clauses stale. **The plan is NOT amended mid-QA** — see the note below. | **blocking** |
| **C-2** | **No acceptance criterion, P-property or flow map covers any event/SSE obligation.** Spec §12 fixes the envelope and forbids polling; the design says *"The Projects page adds no counters"*. No `project.*` kind is listed anywhere in §12. | spec vs code | **Unresolved, and that is the finding.** The code publishes six `project.*` kinds; they exist only post-hoc, from D7's remediation. There is no criterion from which *"a mutation tells a second client"* could ever have failed. | **Yes.** D7 is what this hole looked like when a browser finally ran: six mutations, six 200s, **zero frames**. Round 5 must assert the event obligation directly, because nothing in the acceptance set will. A **second live client** is mandatory in the scenario matrix. | **blocking** |
| **C-3** | AC-23 and AC-21's `escape.js` clause **pass for the wrong reason.** Both use `git diff --name-only <path>`, which reads the **working tree**. | code (measured) | **Neither — the check's meaning drifted.** The commands are clean because the changes are *committed*. They now assert "no uncommitted edits", not "byte-identical to the milestone baseline". | **Yes.** Any byte-cleanliness assertion round 5 makes must compare against `consumer_manifest.json`'s `baseline` digests, never `git diff`. | **blocking** |
| **C-4** | **AC-28's command runs `pytest -m live`.** | spec vs standing user constraint | **The user constraint wins, absolutely.** `-m live` starts real `claude` processes against the user's real `~/.claude.json`. It is forbidden in this workflow. | **Yes.** AC-28 cannot be executed as written. Round 5 substitutes a served-`controld` render sweep over `render_check.VIEWPORTS` that carries no `live` marker, and declares in the report that AC-28's final clause was **not run**, with the reason — never silently dropped. | **blocking** |
| **C-5** | How many project verbs ship. `design:168-179`, `plan:1194`, `plan:1264` fix the surface at **seven**, and T3.1 lists "an eighth verb" as out-of-scope drift. | spec vs code | **Code wins.** Measured: 6 project/repo POST verbs (`create_project`, `rename_project`, `set_project_description`, `delete_project`, `add_repo`, `remove_repo`) + 3 GET (`get_project`, `list_repos`, `list_projects`). `set_project_description` was added deliberately (commit `41c4174`, "The eighth verb is drivable"). | **Yes, mildly.** The scenario matrix covers the shipped surface, not the planned seven. `set_project_description` needs its own rows, including the "absent clears" semantics. | deferred → shaped S-PROJ-DESC |
| **C-6** | `DeletePlan.running` and killability. `t9-1.md` gap 2 says the plan *"does not say which sessions are killable, so the page cannot warn in advance"*; `qa-remfix.md:42` says *"the server sends `killable: []` / `unkillable: [ids]` — it already knows"*. | spec vs spec (inside one lane) | **`r2`: resolved from source, not left open.** `store/reads.py:283-284` splits `alive` on `runner_handle is not None`; `tools_projects_delete.py:128-136` projects all three keys unconditionally. **`qa-remfix.md` is right.** `r1` recorded this as *"unresolved — settle empirically"* because no lane read `store/reads.py` | **Yes, but as a measurement.** Scenario **S0** drives a real delete against a real running session and records the refusal record's actual fields — the projection five scenarios consume is worth reading once. It is **not** a gate over four live branches: with this seed, B-OWNED is the only reachable binding, and the branch that `r1` said would halt wave 1 (B-ABSENT) cannot occur | **resolved** (was `blocking`) |
| **C-7** | `last_activity_at`. `design:193-196` says the design *"fills it, from the project's most recent session event"*; `plan:177` (RD-3) and `:2256` (ADR-P4) say it is **derived at read time** and the column left unwritten. | spec vs spec | **Plan wins** — it is the later decision and the plan flags this itself as Difference #1. Corroborated by the `code` lane's X3: the three write verbs answer `last_activity_at=None` unconditionally. | **Yes.** Assert the derived value at read time; never assert the column. | deferred → shaped S-PROJ-READ |
| **C-8** | `viewport-drift` — `test_projects_page.py` and `test_settings_live.py` hard-code 1280x900 and reference `render_check.VIEWPORTS` **zero times**. | artifacts vs code | **Both agree it is open.** It was blocked on *"tests/web is lane A territory until the merge"*. **The merge has now happened, so the blocker is gone.** | **Yes.** This is the exact drift that hid D1, still live in the tree. Closing it rewrites node ids and trips the 1480-id freeze, so it needs retirement entries — it is **harness-build work**, handed to `qa-build`, not done here. | **blocking** (for the harness, not the plan) |

### Why the plan is NOT amended mid-QA

Revision 6 amended this plan **before** the QA route started, and that was right. C-1 arrives **during**
it. Amending the acceptance criteria now would mean the run rewrites its own exam and then passes it,
which is precisely the failure this route exists to prevent — and it is the same shape as the check
that reports success without checking. The three stale clauses are therefore recorded as findings and
routed out (§8) for a revision 7 the user or a BUILD owns. Round 5 measures the tree as it is.

---

## 4. Observation points, by boundary

| Boundary | UI | API | DB | Queue | Logs |
| --- | --- | --- | --- | --- | --- |
| `FleetHandler` | — | 200/400/403/404/500; `X-Content-Type-Options: nosniff` on every response | — | — | `{"ok":false,"data":null,"error":GENERIC_ERROR,"correlation_id":"<uuid4 hex>"}` — **V**, but the id must be matched as a *pattern*, never a value |
| `routes.py` | — | dropped-field behaviour; path-param-wins. **`r3`: two guards, and only their conjunction is observable at the wire.** `BODY_ARGS` drops anything undeclared (`:247-249`) **and** `args.update(captured)` applies the path parameter last (`:250`). For `/api/projects/{project_id}/rename` the path parameter is **`project_id`** and `BODY_ARGS` is `("name",)`, so a body key must be spelled `project_id` to test the guards at all — any other spelling is dropped as an ordinary undeclared field and proves nothing about redirection. The single-guard separation lives at `tests/web/test_routes_m3.py::test_no_declared_field_shadows_a_path_parameter`, not over HTTP | — | — | — |
| registry + chokepoint | — | envelope shape | — | — | one JSONL audit record per gated invoke: `at`, `tool`, `decision`, `approved_by`, redacted args — **Vp** (fields named, format not quoted) |
| project verbs | `#p-refusal` text | record's positive key + `refused` | `workspace`, `repo`, `workspace_repo` edge, `session` cascade, `anomaly.stop_failed` | — | — |
| `announce()` | — | — | — | one `StreamEvent` per **succeeded** mutation; refusals publish nothing | `project.created\|renamed\|described\|deleted\|repo_added\|repo_removed` — **V** |
| `sse.py` | `#stream-status` = `connecting`→`live`/`reconnecting`/`unreadable` | — | — | `id:` = monotonic `seq`; `stream.gap` when a client is behind the ring | `: open` and `: keep-alive` comments — **V** |
| WebSocket | `data-terminal-cols` / `-rows` on `#session-terminal` | 101 accept; first binary frame == snapshot **byte-for-byte**; close `CLOSE_NORMAL` | — | — | — |
| the four pages | `[data-level]`, `aria-current`, `aria-pressed`, `hidden`, `data-error`, `data-reserved`, `data-danger`, `data-empty`, `data-kind`, `data-choice`, `title` on every truncatable value | — | — | — | **`console.error` / `pageerror` — the six browser test files already fail on any** |
| pixel geometry | `render_check.py` at 390 / 820 / 1280; `SLACK_PX=1`; `FILL_FLOOR=0.75` (opt-in); `[id^="page-"]` exclusivity at arrival and after every nav click | — | — | — | — |

---

## 5. Testability blockers

| # | Blocker | Where | Consequence |
| --- | --- | --- | --- |
| B1 | **No health or readiness endpoint.** | `API_ROUTES` | The only liveness proxy is `GET /api/fleet`, which needs a working store — so readiness gating uses a route that can fail for unrelated reasons. Env plan must state this. |
| B2 | **`render_check.py` is structurally blind to intra-page layout collapse.** `#page-flock`'s rectangle is byte-identical healthy and broken (56→900 in both); Chromium reports the **implicit** grid track so both read as three rows. | `t10-1.md` | *"No per-root rectangle can distinguish those, and there is no generic property of a page root that does."* Any grid-collapse assertion must measure the **panes**, not the root. |
| B3 | **Vacuous assertions over self-sizing boxes.** A 307,418px container passed every "the content fits inside its box" assertion, because the box grew to fit the content. | lane B | Every containment assertion must be against the **viewport**, never the parent. |
| B4 | **Module-graph reachability certifies a fetch, not a call.** `flock.js` was *reached* while the page never drew. | `integration.md:64-75` | *"Loaded is not driven, and a walk structurally cannot see the difference."* |
| B5 | **A lexical `try`-scan cannot see whether the `catch` does anything** — a silent `catch {}` satisfies it. | `qa-remfix.md:88-91` | |
| B6 | **Green suites over unpopulated fixtures.** Every `tests/web` fixture seeded one project and at most two sessions, all *attached*, so `DeletePlan.killable` was empty in every test that read it; no two projects shared a name; no path ellipsised. **Nine of eleven round-1 defects were invisible at n=1.** | `qa-remfix.md:17-34` | Round 5 seeds **n>1 everywhere**, with at least one owned session, one duplicate name, and one very long path. |
| B7 | **`app_state["kill.<id>"]`'s null-row distinction is not observable through any `Store` verb** — only a direct sqlite open could see it, which the storage-boundary test forbids. | `qa-remfix-3.md:151-157` | |
| B8 | **`web/server.py` is byte-pinned**, so `_CONTENT_TYPES` is `.html`/`.js`/`.css` only. | `design:64-66` | **No font, image, SVG or JSON data fixture may enter the static tree.** Hard constraint on any fixture round 5 stages. |
| B9 | **`controld` refuses to start with `XDG_RUNTIME_DIR` inside the scratchpad** (`SocketPathTooLong`). **`r4`, measured — the premise this row carried was wrong and the consequence was right.** Budget **107** bytes (107 BOUND, 108 REFUSED on real `AF_UNIX` binds); fixed suffix `/shepherd/controld.sock` **23**; therefore the ceiling on `XDG_RUNTIME_DIR` is **84**. The scratchpad **root** is **76** → 99, *accepted* with margin +8; **88 is the `xdg_runtime` subdir form** → 111, **refused by 4**; a per-run root under the scratchpad (≤88) is refused for the same reason; `/tmp/shq5-<pid>` is **17** → 40, margin **+67**. `r1`–`r3` quoted 88 as *"the scratchpad path alone"*, which described a different path than the prose around it. | `integration.md:205-211`; **`r4`:** `setup.md` §2, computed with the product's own `plan_socket` (`host/base.py:147-167`) and `LINUX_SOCKET_PATH_BUDGET` (`host/linux.py:42`) | Only the runtime dir may point at a short throwaway; data and config stay in the scratchpad. **Unchanged by the correction** — the intended form really is refused and the chosen form really does fit. |
| B10 | Registry, stream ring and `compose._PLANE` are **module-global** (ADR-7). | `compose.py:171` | **Two servers cannot coexist in one process.** Parallel processes fine, parallel threads not. |
| B11 | `add_repo` shells out to git via `probe_repo` with **no stub seam** at the toolsurface layer. | `tools_projects.py:231` | Every `add_repo` scenario needs a **real repository on disk**. |
| B12 | **The page-level clock is not injectable.** `app.js:115` calls `Date.now()` directly in `drawFlock`; `flock.js::ago` takes the clock as a parameter, so the unit seam exists and the browser seam does not. | `app.js:115` | Relative-time assertions in a browser must tolerate real time or seed absolute timestamps far from boundaries. |
| B13 | **`js_syntax_check.py` needs playwright, as `render_check.py` already did, and neither is declared in `pyproject.toml`.** The whole file sits behind `importorskip`, so a machine without playwright **collects and passes**. | deferred_findings | A silently-skipped gate. Preflight must assert playwright is present, not assume it. |
| B14 | **`tests/web/test_ws.py`'s 14 reader tests assert a contract with no implementer** — the WebSocket read half has no caller in `src/`, by decision. | `test_ws_read_path.py` | **Vacuous by construction.** A green run there proves nothing about the product. |
| B15 | **`pre_m4_routes.json` freezes only the pre-T24 surface**; the nine Projects/M4 routes are additive-checked only, never frozen. | code lane | A change to the delete body contract would pass that gate. |
| B16 | **Stated flake policy is no retries**, with fixed 700ms-after-navigation and 350ms-after-nav-click waits. | `plan:2124-2126` | *"A flaky render check is a render check that has stopped being evidence."* |
| B17 | `correlation_id` is `uuid4().hex` per request with **no injection point**. | `server.py:123` | Match a pattern, never a value. |

---

## 6. User Action Inventory — UNREDUCED

See `research/code.md` for the full table with element-to-handler mapping. Summary of the space:

| Control | Kind | Options | Enumerated from | Complete? |
| --- | --- | --- | --- | --- |
| six nav entries | nav | shepherd, flock, queues, projects, kanban, settings | code | yes |
| eight legend keys + info button | filter | needs_you, error, unfinished, running, paused, blocked, finished, unclassified | code | yes |
| project rows on the Flock | select | data-driven | not_enumerated | **no** |
| session cards | select | data-driven | not_enumerated | **no** |
| `next_actions[]` | toggle | 7 kinds; only `inspect`, `external`-with-target and `none` are live — the other four render **inert with a `not yet` badge** | code | no |
| decision-card choices | toggle | engine's own numbered choices, or approve/reject when unreadable — **inert by construction** | code | no |
| Projects list rows | select | data-driven | not_enumerated | **no** |
| `#proj-new` / `#proj-edit` / `#proj-delete` | toggle | Edit and Delete are **absent, not disabled**, on `unassigned` | code | yes |
| `#p-name` / `#p-desc` / `#p-new-path` | text | empty · whitespace-only · duplicate name · non-existent path · non-directory · non-git dir · bare repo · subdirectory of a repo · 935px-long path | code | no. **`r3`: three of these nine are not wire values, and reading them as such produced a fabricated defect.** *empty* and *whitespace-only* are refused **in the page** (`projects.js:658-661`, constant at `:52-54`) and issue **no request**. *duplicate name* is a page-side **warning, not a refusal**: `create_project` returns `created: True` unconditionally (`tools_projects.py:158-169`) over a bare INSERT with no name check (`store/projects.py:52-70`), because identity is `workspace.id` and never the name (E1/D57) — the flag is page memory (`projects.js:620`, reset at `:547`). The remaining six are wire values and refuse through `probe_repo`. The **space is unchanged**; what changed is which seam each value can be driven at |
| delete-dialog choices | toggle | Delete (no `on_running`) · Stop them then delete (`kill_sessions`, **disabled up front when `killable` is empty**) · Move to Unassigned (`orphan`) · Wait · Cancel | code | no |
| ten Settings sections | select | account, notifications, api-keys, autonomy, shepherd, discovery, limits, users, data, system | code | yes |
| autonomy options | toggle | 2 = ask, 3 = auto | code | no |
| composer keyboard | text | Enter = send · Shift+Enter = newline · empty = no-op | code | yes |
| inline-rename keyboard | text | Enter = commit · Escape = revert | code | yes |
| `#p-new-path` keyboard | text | Enter = add path, **never submit the form** (`projects.js:480-482`) | code | yes. **`r3`: the control exists in the dialog's EDIT mode only.** `projects.js:549` sets `#p-paths-section.hidden = !editing`, and `addDraftPath` returns at `:586` when `draft.project === null` — so in **create** mode the field is hidden and the handler issues no request at all. Any scenario driving this row must open the dialog via `#proj-edit` on a real project, never via `#proj-new` |
| drawer / rail toggles | toggle | drawer open/closed, rail open/collapsed | code | yes |
| dates | date | null ("no activity yet" / "never seen") · <60s ("just now") · minute/hour/day/week/month/year · `deadline_at` | code | no |
| viewport widths | filter | 390x844, 820x1180, 1280x900 | code | no — **nothing above 1280 or below 390 has ever been driven** |

**No `<select>` element exists anywhere in the shipped UI** — every option set is a button group.

---

## 7. Action chains

| Chain | Steps | Why it is worth testing as a chain |
| --- | --- | --- |
| Flock drill-down and back | Flock → project → card → session pane + WS → back → back | The only path that opens a WebSocket; `data-level` must unwind cleanly |
| Edit a project's paths | Projects → row → Edit → add path → remove path → Save | Draft state lives in the module across three round trips |
| **Delete against running sessions** | Delete → count → Delete (no `on_running`) → read refusal → Stop them → read `kill_failures` → Move to Unassigned | The richest refusal surface in the product, and C-6's binding probe |
| Duplicate-name re-application | New → existing name → Create (warn) → change name (**re-arms**) → existing name again → Create (warn) → Create (creates) | The arming flag is per-name; a stale arm would create silently |
| Double-submit race | open dialog → two `click()` in one tick | Guarded by **in-flight flags, deliberately not `disabled`**, because the nodes are rebuilt on every answer. Four other POST handlers are deliberately **unguarded** on an idempotency bet |
| Cross-page nav via a session link | Projects → project → session mini-link → shell shows Flock **and opens that session** | Two `data-` attributes cooperating across a page boundary |
| **Envelope burst, two live clients** | second SSE client attached → drive N mutations → observe frames and `refreshAll` coalescing | C-2's hole. **Never driven at two live browser tabs** — the two-tab driver is not committed |
| Daemon death mid-flow | open each page → stop `controld` → one action per page | **`r2`, measured — and the `r1` wording of this row was false of the tree.** `chat.js:131-132`, `app.js:65-66` and `projects.js:49-50` define a **byte-identical** string; `settings.js:209-211` differs; **`flock.js` defines none at all** and the Flock page's failure path runs through the shell's shared `app.js::showError` banner (`#stream-message-text`). So the chain is not "each module writes **its own** sentence": it is **three named elements carrying two distinct strings, plus one shared banner**. Asserted per element in test plan S29, with the four strings quoted in its §5 |
| Nav away and back | mount all → navigate → return | Every page is mounted **once** before any is shown; module state survives navigation |

---

## 8. What no source can answer, and findings to route out

### Open questions

| Question | Who could answer | Blocks what |
| --- | --- | --- |
| ~~Does `DeletePlan` distinguish owned from attached in `killable`? (C-6)~~ | ~~the running system~~ | **`r2`: closed, by reading the tree.** `store/reads.py:283-284` computes `killable = tuple(s.id for s in alive if s.runner_handle is not None)` and `unkillable` as the complement; `toolsurface/tools_projects_delete.py:128-136` emits `doomed`/`killable`/`unkillable` **unconditionally**. `qa-remfix.md:42` is right and `t9-1.md` gap 2 is wrong. **S0 remains as a measurement** of a projection five scenarios consume — not as a four-branch gate. The question needed one file opened, and the `code` lane never opened it |
| Is the recon document still authoritative over the plan? (`plan:186` says it outranks everything) | user | Nothing blocking; no lane read it — recorded as G-12 |
| Should AC-16/21/23 become revision 7? (C-1) | user, or a BUILD | Nothing in round 5 — the run measures the tree and declares the clauses stale |

### Findings that are not test-design inputs

| Finding | Type | Owner | Route to |
| --- | --- | --- | --- |
| **AC-16, AC-21, AC-23 are false of the tree** — `BODY_ARGS`=16 not 15, `post_milestone`=7 not 6, `terminal.js` changed | stale-artifact | plan | **user decision → plan revision 7** |
| **AC-21 and AC-23 check the working tree, not the baseline** — they pass because the change is committed | stale-artifact | plan | plan revision 7 |
| **AC-28's command runs `pytest -m live`**, which is forbidden in this workflow | product-question | plan | plan revision 7; round 5 substitutes and declares |
| X1 — `project_repo_row` emits a D60 holders list, `git_common_dir`, `vcs_remote`, `active`, `added_at`; **`projects.js` renders only `root_path`**, and the projection's docstring describes a renderer that does not exist | defect | web | **DEBUG offer** |
| X2 — `remove_repo` returns `{"removed": bool}` with **no `refused` key**, breaking the family's stated one-refusal-shape rule; the page discards the answer, so a `False` is invisible | defect | toolsurface | **DEBUG offer** |
| X3 — `create_project` / `rename_project` / `set_project_description` answer `repo_count=0, last_activity_at=None` **unconditionally** | defect | toolsurface | **DEBUG offer** |
| X4 — `session.js::localOnly` reads `title_source` / `title_synced_at`, which `project_session` never emits; the marker is `false` for every served row | defect (known, T19-b) | web | ticket |
| `POST /api/sessions/{id}/permission` is routed and registered and **no page calls it** | product-question | web | user decision |
| GAP 1 — `DeletePlan.doomed` never reaches a consumer; the page derives a **copy** of a store derivation | defect | toolsurface | DEBUG offer |
| GAP 2 — the page can offer a `kill_sessions` button that **cannot succeed**, with a refusal that does not say why | defect | toolsurface | DEBUG offer |
| GAP 5 — `delete_project` destroys on its first call when nothing is running; **a dry-run would close it** | product-question | toolsurface | user decision |
| A kill that **hangs** still blocks the verb — no timeout was added | defect | orchestration | DEBUG offer |
| **`js_syntax_check.py` and `render_check.py` both need playwright; neither is declared in `pyproject.toml`** — a machine without it collects and passes | defect | tooling | ticket |
| `main` and `integration` have **no common ancestor**; a PR needs `--allow-unrelated-histories` | product-question | repo | **user decision** |
| G1/G2 — the cc10x isolation guard no-ops unless `workflow_type=="QA"`, and its Bash allowlist is a **substring** match | defect | cc10x plugin (upstream) | ticket, not ours |
| Spec §12's headline still says *"one rail that is always present"*; D66 removed it. Register ranges say D57–D64 / U1–U15; the tree ships D57–D67 / U1–U18 | doc-debt | spec | doc fix |
| `ui-decisions.md:3` says *"Status: design only. No file under `src/shepherd/web/` has been changed"* — the same file records the port at `:100` | doc-debt | spec | doc fix |
| `ui-decisions.md:146` *"## Open — Nothing is gating the implementation"* sits above U4, which is **not** struck through | doc-debt | spec | doc fix |
| Plan §internal arithmetic: C15 (twelve vs eighteen screenshots), C17 (three vs two assertions), C18 (seven vs six entries), C19 (Durable Decisions points at a retired Phase 2) | doc-debt | plan | doc fix |
| Appendix A of the spec is stale (C22) — macOS paths under a Linux target, and an example row built on `workspace.root_path`, which D57 removes | doc-debt | spec | doc fix |

---

## 9. Handoff to the plan

- The full input space is **§6, unreduced**. The test plan reduces it by a named technique and states what it leaves uncovered.
- **`S0` is mandatory and it is C-6's measurement** — **`r2`: not a four-branch gate.** C-6 is answerable from `store/reads.py:283-284` and `tools_projects_delete.py:128-136`, and the answer is that the record **does** distinguish owned from attached and always carries the three keys. S0 drives a real delete against a real running session and records `killable` / `unkillable` / `doomed` verbatim, because a projection five scenarios consume should be read once rather than inferred four times; the delete-dialog family still runs after it. **The gate moved** to the thing four rounds never executed — *can a kill land on a real pane* — which is proved fixture-side at bring-up (test plan §3c) and product-side by S11.
- **`r2`: three of this file's own restatements were corrected** — this bullet, §8's C-6 row, and §7's daemon-death chain. Every other claim here was re-verified and stands, including §6's unreduced inventory, which is what exposed the two `full-combinatorial` rows in the test plan that claimed `Uncovered: none` over sets with undriven members (`#proj-edit` on an ordinary project, and the **Wait** choice).
- **C-1, C-2, C-3, C-4 and C-8 are `blocking` and are settled as follows**: C-1/C-3/C-4 by declaring the three clauses stale and measuring the tree (never by amending the plan mid-run); C-2 by putting a **second live SSE client** in the matrix as a first-class requirement; C-8 by handing the `viewport-drift` parametrisation to `qa-build` with its retirement entries.
- **Every §5 blocker must appear** in `env-plan.md` as a blocker with an owner, or in `test-plan.md` as a known gap. B8, B9, B10, B11, B13 and B16 constrain the environment directly.
- **Ground never driven, and therefore where round 5's yield will come from**: a real tmux pane (now authorised, `-L shepherd-qa`), the terminal WebSocket against an owned session, two live browser tabs, touch events, `prefers-reduced-motion` / forced-colors / zoom / RTL, anything above 1280 or below 390, the production audit sink on disk, and ordering/coalescing under concurrency.
- **Do not re-prove** what round 3 proved and round 4 re-verified (D1, D2, D3 closed at `b1c1eb9`), and **do not trust** round 1's eleven closures — they are recorded with no id, no description and no named check, and cannot be re-verified at all (evidence gap E1).
