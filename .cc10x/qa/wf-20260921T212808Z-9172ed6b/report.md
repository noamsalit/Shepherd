# QA Report: Projects backend + dark-only web UI redesign (Shepherd / Flock / Projects / Settings) — round 5

**Verdict:** BLOCKED
**Run:** 2026-09-23T01:41:23Z → 2026-09-23T01:47:58Z · **Environment:** local · **Duration:** 105 s + 95 s + 95 s (three full-suite runs)
**Workflow:** `wf:wf-20260921T212808Z-9172ed6b` · **Test plan:** `.cc10x/qa/wf-20260921T212808Z-9172ed6b/test-plan.md` (`r4`)

> **This file records what the run OBSERVED. A claim it cannot point at evidence for does not go in.**
>
> The test plan is a prediction of what will be exercised; this is the account of what was. Where
> they disagree, this file is right and the plan is the thing that was wrong — say so in
> `## Coverage gaps` rather than quietly narrowing the plan to match the run.
>
> **Sections are not optional when empty.** A section omitted because it had nothing in it reads as
> a section that was considered and came back clean, and those are not the same claim. Every heading
> below stays, with `None` under it if that is the truth.

**Runs executed, and why more than one.** Three back-to-back full-suite runs, not one. The harness
carries a declared ~1-in-4 product race behind it and the previous round's *second* back-to-back run
is what went red, so a single green run is not evidence against a race.

| Run | Started | pytest exit | Harness counts | Published `qa5-latest.json` |
| --- | ------- | ----------- | -------------- | --------------------------- |
| 1 | 2026-09-23T01:41:23Z | **1** | `PASS 35 · FAIL 1 · BLOCKED 0 · PARTIAL 1` | yes (record set complete) |
| 2 | 2026-09-23T01:43:44Z | 0 | `PASS 36 · FAIL 0 · BLOCKED 0 · PARTIAL 1` | yes — **overwrote run 1's red** |
| 3 | 2026-09-23T01:46:23Z | 0 | `PASS 36 · FAIL 0 · BLOCKED 0 · PARTIAL 1` | yes |

Run 3 was not a retry chasing green — run 2 was already green. It was run to put a number on the
nondeterminism, and it could only have made the verdict worse. Measured hit rate for the red: **1/3**.

---

## 1. Failure classes

| Class | Count |
| ----- | ----- |
| missing-input | 1 |
| wrong-guess | 3 |
| defect | 1 |
| unconfirmed | 0 |

**What the counts mean here.** Two of the five are things a check actually returned on: the single
`defect` is the shipped `projects.js:254` race that turned run 1 red (S33), and the single
`missing-input` is S29's `#stream-status` assertion, which could not be adjudicated because no
source states how fast the page must notice a dropped stream *and* the run never measured whether
the in-process `controld.stop` closed the accepted socket at all — so the check has no oracle, which
is why S29 is BLOCKED rather than FAIL or PASS. The three `wrong-guess` entries are the three stale
acceptance criteria (AC-16, AC-21, AC-23): **no check failed for them**, because S31 is the scenario
whose job is to measure them and it asserts the measured values and passes. They are counted here
because plan §0 rule 5 classes "an expectation this plan inferred losing to the tree" as a finding
about the plan, and `wrong-guess` is that class under this contract's name for it. **`unconfirmed`
is 0 on purpose and the reason is measured, not assumed** — see §4's `Measured on` note: `integration`
and `main` have no common ancestor, so there is no distance to be behind by, and the severity cap
does not fire. Round 3 read `rev-list HEAD..main = 2` as a currency deficit and capped every
severity on the strength of it; that number is a set difference across disjoint histories.

**Taking `defect: 1` as the headline would be reading the opposite of what this run found.** The one
defect is real, shipped, and reproduced; the run is BLOCKED on a separate unadjudicable check; and
**AC-28's final clause was not executed at all** (below). A green count here is not a green run.

## 2. Summary

| Tier | Total | Passed | Failed | Blocked | Flaky |
| ---- | ----- | ------ | ------ | ------- | ----- |
| integration | 5 | 5 | 0 | 0 | 0 |
| e2e_backend | 13 | 13 | 0 | 0 | 0 |
| ui | 17 | 16 | 0 | 1 | 1 |
| **Total (plan scenarios S0–S34)** | **35** | **34** | **0** | **1** | **1** |

Two further rows are recorded by every complete run and are **not** plan scenarios: `BRINGUP` and
`WAVE2-LIVENESS`. Both PASSED in all three runs; they are reported under §6 as environment evidence
and appear in §3 for completeness. The harness's own planned set is therefore 37, and all three runs
recorded exactly 37 with `missing=[] extra=[] duplicated=[]`.

**The verdict is BLOCKED, and it does not round up.** S29 is not a PASS and is not a PARTIAL that
can be read as one; S33 is a PASS only in the flaky sense, and the thing that made it red is a
shipped product defect rather than test nondeterminism.

### Declarations carried verbatim

**AC-28's final clause was NOT executed.** Its command invokes `pytest -m live`, which starts real
`claude` processes against the user's real `~/.claude.json` and is forbidden by a standing user
constraint (C-4). S30 substitutes a served-`controld` render sweep over `render_check.VIEWPORTS`
carrying no `live` marker. **A PASS on S30 does not discharge AC-28.** S30 passed in all three runs
(`18 pages checked · 18 screenshots · 0 failures`, exit 0) and AC-28 remains undischarged.

**Three acceptance criteria are stale against the tree, measured this run (S31, all three runs
identical):** `routes.BODY_ARGS` is **16**, not the 15 AC-16 asserts · `consumer_manifest`
`post_milestone.edits` is **7**, not the 6 AC-21 asserts · `web/static/terminal.js` has left its
manifest baseline, `ace78240` → measured `781bed86a4092e0f8df0f1811ed754d7c2fdcf2b39020c35d05501d880942017`,
so AC-23's byte-clean assumption does not hold. Each moved because a *later correct change* shifted
a count the plan restates. **The plan was deliberately not amended mid-run** — amending it would mean
the run rewrote its own exam and then passed it. They are reported here as findings for a revision 7.

**The declared product race.** `web/static/projects.js:252-256` — `projectRow`'s click handler calls
`loadDetail(project.project_id)` **without awaiting it** and then `renderList()`, while
`submitProject`'s create branch already has a `loadDetail` of its own in flight. The harness's
`networkidle` settle and `press_until_open` are a **workaround, not a fix**. **The presses this
round: `press_until_open` reported exactly 1 press for S19, S32 and S33 in every one of the three
runs — the retry path was never exercised.** Run 1's red landed *downstream* of the dialog opening:
the dialog opened on the first press and then held the wrong project. A workaround that is not even
being exercised is not the thing holding this scenario up, and the defect is shipped. Full candidate
in §4 and §8.

**S29 is PARTIAL in the harness's vocabulary, and this report records it as BLOCKED, not PASS.**
`#stream-status` still read `live` 30 s after `controld.stop`. My judgement on whether it is a bug
candidate: **yes, at low severity, and the reason it is not higher is stated rather than assumed.**
A page claiming `live` over a dead stream is the one state that indicator exists to deny — but the
mechanism to deny it *exists in the shipped code* (`sse.js:33`, `source.addEventListener("error", () =>
onStatus("reconnecting"))`, consumed at `app.js:364` → `flock.js:546`), so this is not an unreachable
state. What this run cannot say is whether the browser had anything to notice: the shutdown was an
in-process `controld.stop`, and whether it closed the already-accepted SSE socket was never measured.
Candidate in §4; `missing-input`, because the check lacks an oracle, not because the product is clear.

## 3. Scenario results

**How to read these blocks.** Every expected/actual string below is **verbatim from the run's own
record file** (`.cc10x/qa/{wf}/runs/qa5-run-*.json`), not paraphrased. The harness records **one
composite assertion block per scenario** rather than one string per observation point; where a
scenario asserts at several points, the first row carries that block and the rest are marked
`(same assertion block as above)`. That is a real limit on the granularity of the evidence and it is
named rather than papered over — it is why S33's and S29's blocks below are reconstructed by hand
from the failure output rather than lifted from the record. Rows marked `n/a` are points the **test
plan names no assertion at**, not points that were skipped.

Thirty-seven blocks: the plan's 35 scenarios (S0–S34) plus the two harness-level rows every complete
run records. Values below are from **run 2** except where a run is named.

### BRINGUP — PASS

**Class:** harness-level (not a plan scenario) · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `BRINGUP`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | eleven bring-up steps arrive: run root, runtime dir, env, store, four panes, controld bound, /api/fleet 200, seed, chromium, rig live, controls green | port=33825, panes=['shepherd_r5a', 'shepherd_r5b', 'shepherd_r5c', 'shepherd_r5d'], socket=shepherd-qa, projects=8 | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S0 — PASS

**Class:** edge-case · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S0`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | 200; deleted=false; a non-empty refusal; five projection keys; KILLABLE==[S-own-1], UNKILLABLE==[S-att-1]; P4 intact; no stop_failed; one allow/claimed_human audit record; zero frames in the window | binding=B-OWNED killable=['01M35YXR1WQ03PAW0KKEJV5H0Q'] unkillable=['01M35YXR2A2TQTN67GNCNKZHJD'] doomed=5 running=['01M35YXR2A2TQTN67GNCNKZHJD', '01M35YXR1WQ03PAW0KKEJV5H0Q'] refused='2 session(s) are still running in this project; choose whether to stop them or move them to Unassigned' | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**killable:** ['01M35YXR1WQ03PAW0KKEJV5H0Q']
**unkillable:** ['01M35YXR2A2TQTN67GNCNKZHJD']
**doomed:** ['01M35YXR2NZHEQ2VV9GGV2RQ9T', '01M35YXR2QG0QBY9PEH5A73SMG', '01M35YXR2TNVXB497ET21AQAXJ', '01M35YXR2A2TQTN67GNCNKZHJD', '01M35YXR1WQ03PAW0KKEJV5H0Q']
**running:** ['01M35YXR2A2TQTN67GNCNKZHJD', '01M35YXR1WQ03PAW0KKEJV5H0Q']

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S1 — PASS

**Class:** happy-path · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S1`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | exactly one [id^=page-] visible at arrival and after every nav click; aria-current follows; the two stubs render; zero console.error/pageerror | roots seen in order: ['page-shepherd', 'page-flock', 'page-projects', 'page-queues', 'page-kanban', 'page-settings'] | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S2 — PASS

**Class:** happy-path · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S2`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | eight workspaces; two ids share 'Shepherd'; read-path repo_count 2 and 1; last_activity_at derived; #proj-list eight rows; unassigned has no #proj-edit and no #proj-delete child; the empty class renders a sentence | names=['Attached-only', 'Doomed', 'Flock', 'Orphan-subject', 'Shepherd', 'Shepherd', 'Stale-handle', 'Unassigned']; detail_keys=['found', 'project']; empty_pane='Shepherd\nEdit\nDelete\n\nDESCRIPTION\n\nNo description.\n\nREPOSITORY PATHS\n\nNo paths yet — no session can be started here.\n\nWO' | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S3 — PASS

**Class:** happy-path · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S3`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | both streams 200 text/event-stream + no-store + nosniff; `: open` seen; both clients get project.created with `id: <seq>` and no `event:` name; a wrong-Origin stream is 403 with no stream body | seqs={'A': 15, 'B': 15}; refusal=403 | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### WAVE2-LIVENESS — PASS

**Class:** harness-level (not a plan scenario) · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `WAVE2-LIVENESS`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | the rig is still live at the start of wave 2: the control's two frames, project.created then project.deleted, at both clients | interior carried [2, 2] frames from wave 1 | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S4 — PASS

**Class:** happy-path · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S4`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | six 200s, each with its own positive key true; six frames at the second client in the fixed order, each with project_id promoted to the envelope top level and strictly increasing id:; six audit records | kinds=['project.created', 'project.renamed', 'project.described', 'project.repo_added', 'project.repo_removed', 'project.deleted']; seqs=[19, 20, 21, 22, 23, 24]; audit=['create_project', 'rename_project', 'set_project_description', 'add_repo', 'remove_repo', 'delete_project'] | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S5 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S5`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | 200 with renamed=false, project=null, a non-empty refusal naming the reserved project; the name is unchanged; no row added or removed; one audit record for the refused invoke; zero frames in the counted window | refused='the Unassigned project cannot be renamed: it is the reserved landing place for work that matched no declared project, and every discovered session binds to it (D59)'; audit=['rename_project'] | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S6 — PASS

**Class:** edge-case · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S6`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | described=true twice; the text lands then an absent field clears it; repo_count=0/last_activity_at=null on both write records while P1 has two repos (X3); the edges are untouched; two project.described frames; two audit records; #p-desc-note reflects the cleared state | #p-desc after clear=''; #p-desc-note='Saved by set_project_description when you press Save.'; frames=['project.described', 'project.described'] | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**measurement:** S6's UI row names `#p-desc-note` as reflecting the cleared state. `projects.js:544` writes a fixed sentence there in edit mode and '' outside one — it reflects the dialog mode, never the description. `#p-desc` is the element that carries the claim, and it is empty.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S7 — PASS

**Class:** edge-case · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S7`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | project_id promoted to the envelope top level and absent from the payload; the payload is JSON-whitelisted; the frame is `id: <seq>` with no `event:` line | fields=['data', 'id']; envelope_project_id=01M35YXTCAF730JRKXWJ0XMZ9Q; payload_keys=[] | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S8 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S8`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | a reattach with a stale Last-Event-ID resumes strictly after it, with no duplicate and no frame lost; a stream.gap notice, if issued, arrives before any replayed frame | stale_seq=31; replayed=[32, 33, 34, 35]; gap_notices=0 | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**known_window:** sse.py:124-128 — a single missed frame here is BLOCKED, not FAIL

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S9 — PASS

**Class:** happy-path · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S9`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | the dialog names P4 by name and id; #dlg-delete-doomed renders the server's own ids, one per id; #dlg-delete-live lists both running sessions; Wait and #dlg-delete-cancel each close, write nothing and fire no POST; no second /api/sessions read; zero frames in the window | choices at open=['delete']; after the refusal=['cancel', 'kill_sessions', 'orphan']; posts=['POST http://127.0.0.1:33825/api/projects/01M35YXR0G6XSBKD6Q33RR5P09/delete'] | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**measurement:** S9's UI row asks for five co-resident choices in #dlg-delete-choices. The group is two-phase: one at open, three from the server's refusal (projects.js:940-1005), and #dlg-delete-cancel is outside the group. Five distinct controls exist; they are never simultaneous.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S10 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S10`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | on P4 (killable non-empty) the kill_sessions choice is enabled; on P5 (attached-only) it is disabled, and the disabled state is visible before any click; both match answer.killable.length === 0 exactly; zero frames | {'P4': {'disabled': False, 'killable': ['01M35YXR1WQ03PAW0KKEJV5H0Q']}, 'P5': {'disabled': True, 'killable': []}} | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S12 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S12`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | deleted=false; killed=[]; kill_failures==[] (a no_pane is a False, not a raise — see measurement); a non-empty refusal; P5 kept; no ended_at moved; stop_failed UNCHANGED; the kill choice is disabled and the dialog's live region names every still-running session id with no .dlg-reason node; the body carries the default-refuse sentence; exactly two delete_project audit records; zero project.* frames in the window | failures=[]; running=['01M35YXR2JT3TDFCYMXM1JQ9TT', '01M35YXR2GK46QF1458V4G68FP']; stop_failed 0->0; reasons=[]; body='2 session(s) are still running in this project; choose whether to stop them or move them to Unassigned This deletes the project and 2 session records.' | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**measurement:** SUPERSEDED PLAN WORDING (test-plan S12, API and UI rows): 'deleted=false, killed=[], one kill_failure per attached session with a reason naming no_pane, a non-empty refusal; ... stop_failed up by exactly the failure count; the dialog renders what was not stopped and why, naming the session id'. That is what the plan asked for; the `expected` field above is what this scenario asserts, because the `expected` field is the one a reader scans and it must not state the opposite of the code. Why they differ: kill_failures records a RAISE only (tools_projects_delete.py:174-178); kill_for_delete turns no_pane into False (compose.py:451-462). The sessions appear under `running` and in '#dlg-delete-live' as 'Still running:', with the why carried by the refusal sentence in #dlg-delete-body. stop_failed does not move. A finding about the plan's reading, not a product FAIL.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S11 — PASS

**Class:** happy-path · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S11`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | killed == [S-own-1]; S-att-1 is in `running` and named by `refused`; the pane shepherd_r5a is gone from the shepherd-qa socket; S-own-1 has ended_at and S-att-1 does not; the project's fate matches `deleted`; one claimed_human audit record; a project.deleted frame iff deleted | deleted=False; killed=['01M35YXR1WQ03PAW0KKEJV5H0Q']; failures=[]; frames=['session.killed']; sessions_left_on_socket=['shepherd_r5b', 'shepherd_r5c', 'shepherd_r5d'] | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**inferred_row:** `deleted` was an I row (§0 rule 5): the plan read `commit_project_delete` as re-deriving and refusing while a live session remains. Measured: False, and now PINNED rather than read off the answer — an expectation derived from the value under test agrees with whatever the product says.
**measurement:** S11's API row expects kill_failures to contain S-att-1 'with a reason naming no_pane'. Measured empty: kill_landed turns no_pane into False and only a raise is recorded as a failure.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S13 — PASS

**Class:** edge-case · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S13`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | deleted=true; orphaned names both running sessions; destroyed names the three finished ones; severed carries exactly one {session_id, column} link — S-att-4's retry_of into P6 — and the column is NULL afterwards; both survivors belong to unassigned; the three finished rows are gone; the workspace row is gone; the pane shepherd_r5d still exists; exactly one project.deleted frame; after a reload the Flock lists no P6 and shows both orphans as cards under Unassigned, with no destroyed session among them | orphaned=['01M35YXR27H8W5JG6SA4Q2EZF2', '01M35YXR2K0R37FCSVBF2KXHDP']; destroyed=['01M35YXR2XYZ8Q78A4QEHMJDQC', '01M35YXR30319AV3P69GVMMKNE', '01M35YXR34QGG9SDJW11HXH0TZ']; severed=[{'session_id': '01M35YXR2EGS50699FK41HB37S', 'column': 'retry_of'}]; flock_head='UNASSIGNED'; orphan_cards_under_unassigned=['01M35YXR27H8W5JG6SA4Q2EZF2', '01M35YXR2K0R37FCSVBF2KXHDP']; cards=['01M35YXR27H8W5JG6SA4Q2EZF2', '01M35YXR2K0R37FCSVBF2KXHDP'] | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S14 — PASS

**Class:** happy-path · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S14`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | HTTP 101; the first binary frame carries the pane's own bytes including the marker the fixture wrote, byte-transparent; the pane survives the read; a wrong-Origin upgrade is 403 with no frame handed over; one terminal_stream audit record | snapshot=157 bytes; frames=[2]; refused=403; close_code=None | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**measurement:** PLAN CLAUSE NOT RUN (test-plan S14: '...and the socket closes with CLOSE_NORMAL'). `wsclient.Upgrade.close_code()` implements the read and is called by nothing, because on a LIVE pane there is no close to read: `server.py::_terminal` writes the snapshot, then every chunk `runner.attach()` yields, and only then a close frame — against a real tmux pane that is a stream with no end. `read_frames` therefore stops at a caller-named frame COUNT and closes from this side, so the close code reported here is whatever the client observed (None when the harness closed first), never the server's CLOSE_NORMAL. A helper that read 'to the close frame' would hang forever on exactly the ground round 5 exists to drive. The clause is a real gap in this scenario's coverage and is stated rather than omitted from the PASS.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S15 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S15`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | data-terminal-cols/rows are >0 at both viewports and differ between them; the terminal box stays inside the viewport; the pane's own geometry is still -x 160 -y 45 at both, and the page's reported geometry differs from it at at least one — terminal_resize has no route | page={'w1280': {'cols': 59, 'rows': 30}, 'w390': {'cols': 45, 'rows': 23}}; pane=(160, 45); diverged_at=['w1280', 'w390'] | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S16 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S16`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | 404 after a valid handshake, with no 101 and no frame; the session pane renders a sentence explaining there is no pane; one audit record; zero console.error/pageerror | status=404; pane_text="UNCLASSIFIED\n—\n✎\nstarting\nattached\n—\n\n—\n\nnothing to do\nwhy?\n\nread-only — this session wasn't started here. Open it in the platform to get a terminal." | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S17 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S17`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | the stale handle is in killable; killed == []; exactly one kill_failure naming the session with a reason beginning RunnerRefusal:; stop_failed up by exactly 1; the project's fate matches `deleted`; the pane is absent before and after; one audit record and no GENERIC_ERROR | deleted=False; failure={'session_id': '01M35YXR241W00TK8R6DPKSJ8P', 'reason': 'RunnerRefusal: tmux exited 1 for [\'kill-session\', \'-t\', \'=shepherd_r5c:\']: "can\'t find session: shepherd_r5c"'}; stop_failed 0->1; cleanup branch: deleted == false; P7 survives | PASS |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**cleanup_branch:** deleted == false; P7 survives

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S18 — PASS

**Class:** happy-path · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S18`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | tab B shows the new project and the rename with no reload and no user action; #stream-status reads live throughout; tab B issues no mutation; GET /api/projects in the burst is at most two per envelope, counted at page.on('request'); two frames; zero console errors in both tabs | rows 7->8; burst list reads=2; frames=['project.created', 'project.renamed'] | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S19 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S19`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | every real touch tap reaches its handler; #shell[data-rail] flips both ways and the nav stays reachable; the dialog's primary control is HIT_TESTABLE; in EDIT mode #p-paths-section is visible and Enter on #p-new-path issues exactly one …/repos/add answering added==false without submitting the form; P1's repo set is unchanged; zero frames in the window | rail open->collapsed->open (#collapse collapses, #mark restores — two controls, not one toggle); refusal="'/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/qa5-2042719/work/no-such-path-for-s19' is not a path that exis"; repos_add_requests=1; drawer_controls_excluded_by_name=['nav-shepherd', 'nav-flock', 'nav-projects', 'nav-queues', 'nav-kanban', 'nav-settings'] | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S20 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S20`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | every CONTROL_SET selector resolves to >=1 element on the page its control lives on, in both passes, and the two resolution maps are identical; for every id, HIT_TESTABLE holds under reduced motion wherever it held in the baseline pass; the ids that were False on BOTH sides are named rather than dropped; the legend sheet opens and closes in both passes; dialogs open and close; zero console errors | baseline={'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}; reduce={'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}; sheet={'baseline': True, 'reduce': True}; resolution={'legend-info': 1, 'proj-new': 1, 'nav-shepherd': 1, 'nav-flock': 1, 'nav-projects': 1, 'nav-queues': 1, 'nav-kanban': 1, 'nav-settings': 1, 'drawer-open': 1, 'collapse': 1}; hit_testable_in_baseline=['collapse', 'legend-info', 'nav-flock', 'nav-kanban', 'nav-projects', 'nav-queues', 'nav-settings', 'nav-shepherd']; vacuous_on_both_sides=['drawer-open', 'proj-new'] | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S21 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S21`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | exactly one [id^=page-] visible per navigation in both modes; no horizontal overflow beyond SLACK_PX measured against the VIEWPORT; every CONTROL_SET id stays HIT_TESTABLE wherever the baseline pass had it; under RTL both Projects panes satisfy PANE_HEALTHY; every CONTROL_SET selector resolves to >=1 element on the page its control lives on at each width; the ids False on BOTH sides of each differential are named | widths=['w390', 'w820', 'w1280'] (from ROUND5_WIDTHS by reference); modes=['forced-colors@w1280', 'forced-colors@w390', 'forced-colors@w820', 'rtl@w1280', 'rtl@w390', 'rtl@w820']; baseline={'w390': {'nav-shepherd': False, 'nav-flock': False, 'nav-projects': False, 'nav-queues': False, 'nav-kanban': False, 'nav-settings': False, 'drawer-open': True, 'collapse': False, 'legend-info': True, 'proj-new': False}, 'w820': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}, 'w1280': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}}; snapshots={'forced-colors@w390': {'nav-shepherd': False, 'nav-flock': False, 'nav-projects': False, 'nav-queues': False, 'nav-kanban': False, 'nav-settings': False, 'drawer-open': True, 'collapse': False, 'legend-info': True, 'proj-new': False}, 'forced-colors@w820': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}, 'forced-colors@w1280': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}, 'rtl@w390': {'nav-shepherd': False, 'nav-flock': False, 'nav-projects': False, 'nav-queues': False, 'nav-kanban': False, 'nav-settings': False, 'drawer-open': True, 'collapse': False, 'legend-info': True, 'proj-new': False}, 'rtl@w820': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}, 'rtl@w1280': {'nav-shepherd': True, 'nav-flock': True, 'nav-projects': True, 'nav-queues': True, 'nav-kanban': True, 'nav-settings': True, 'drawer-open': False, 'collapse': True, 'legend-info': True, 'proj-new': False}}; resolution={'w390': {'legend-info': 1, 'proj-new': 1, 'nav-shepherd': 1, 'nav-flock': 1, 'nav-projects': 1, 'nav-queues': 1, 'nav-kanban': 1, 'nav-settings': 1, 'drawer-open': 1, 'collapse': 1}, 'w820': {'legend-info': 1, 'proj-new': 1, 'nav-shepherd': 1, 'nav-flock': 1, 'nav-projects': 1, 'nav-queues': 1, 'nav-kanban': 1, 'nav-settings': 1, 'drawer-open': 1, 'collapse': 1}, 'w1280': {'legend-info': 1, 'proj-new': 1, 'nav-shepherd': 1, 'nav-flock': 1, 'nav-projects': 1, 'nav-queues': 1, 'nav-kanban': 1, 'nav-settings': 1, 'drawer-open': 1, 'collapse': 1}}; vacuous_on_both_sides={'forced-colors@w390': ['collapse', 'nav-flock', 'nav-kanban', 'nav-projects', 'nav-queues', 'nav-settings', 'nav-shepherd', 'proj-new'], 'forced-colors@w820': ['drawer-open', 'proj-new'], 'forced-colors@w1280': ['drawer-open', 'proj-new'], 'rtl@w390': ['collapse', 'nav-flock', 'nav-kanban', 'nav-projects', 'nav-queues', 'nav-settings', 'nav-shepherd', 'proj-new'], 'rtl@w820': ['drawer-open', 'proj-new'], 'rtl@w1280': ['drawer-open', 'proj-new']} | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S22 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S22`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | at 200% and 50%: containment against the viewport at all four live pages; the Projects panes satisfy PANE_HEALTHY (>=1 HIT_TESTABLE control wholly inside the pane AND the root at FILL_FLOOR, read from render_check.py, never re-spelled); the nav stays reachable | base width=w1280 (by reference); css viewports={'200%': 640, '50%': 2560} | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**measurement:** The plan's `body { zoom }` emulation does not move media queries, so it asks the desktop layout to fit half the pixels and overflows by 276px on the Flock — a state no browser produces. Zoom is emulated as device_scale_factor plus a scaled CSS viewport instead.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S23 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S23`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | at 320, 1920 and 2560: exactly one root visible per nav, the nav reachable (via the drawer where it is off-canvas), all ten Settings sections selectable with a control in each panel, no horizontal overflow against the viewport; with the rail collapsed at the widest width the nav is still reachable and every root still meets FILL_FLOOR; screenshots under the run root's shots/, never the static tree (B8) | widths=['w320', 'w1920', 'w2560'] (by reference); settings_sections={'w320': {'sections': 10, 'with_controls': 1, 'nav': 'via drawer'}, 'w1920': {'sections': 10, 'with_controls': 1, 'nav': 'direct'}, 'w2560': {'sections': 10, 'with_controls': 1, 'nav': 'direct'}} | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S24 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S24`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | at 760, 761, 820 and 900: #proj-list and #proj-detail, and the Settings nav column and detail panel, each wholly contain the box of >=1 HIT_TESTABLE control, and the owning root reaches FILL_FLOOR; P3's long repo path is clipped and carries the full value as its title; the rail-open half holds at the desktop width | widths=['w760', 'w761', 'w820', 'w900'] (by reference); path_title_len=165; clipped=1254>704 | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S25 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S25`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | each of #dlg-project, #dlg-delete and #dlg-legend reports open:true with a computed display that is not none, and its primary control satisfies HIT_TESTABLE (which subsumes non-zero box, not painted over and not pointer-events:none); Escape closes each one | {'dlg-project': {'open': True, 'display': 'block'}, 'dlg-delete': {'open': True, 'display': 'block'}, 'dlg-legend': {'open': True, 'display': 'block'}} | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S32 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S32`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | the dialog opens in edit mode pre-filled with P1's values; the add and the remove each issue exactly one POST at the moment they are pressed; the draft list goes 2 -> 3 -> 2 before any Save; Save issues exactly one …/description and ZERO …/rename; P1's name is byte-identical and its description is the new text; exactly two repo edges, the removed one gone; frames repo_added, repo_removed, described and no renamed | calls=['POST http://127.0.0.1:33825/api/projects/01M35YXR04G24FPFMJP1B853MT/repos/add', 'POST http://127.0.0.1:33825/api/projects/01M35YXR04G24FPFMJP1B853MT/repos/remove', 'POST http://127.0.0.1:33825/api/projects/01M35YXR04G24FPFMJP1B853MT/description']; repos_after=['01M35YXR1FXAFND9AAGDRDCXQ0', '01M35YXSW697WVNHRA7ERS1SE6'] | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S26 — PASS

**Class:** happy-path · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S26`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | exactly three new JSONL records for the three calls under test, in order, each with at/tool/decision/approved_by and a mapping of redacted args; GET /api/autonomy reads back 2; the project is gone; audit_line_lost is 0; one project.deleted frame and zero for the two autonomy POSTs; the control's own two gated invokes are asserted separately | tools=['set_autonomy_level', 'set_autonomy_level', 'delete_project']; delete record decision='allow' approved_by='claimed_human'; control=['create_project', 'delete_project'] | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**records:** [{'at': '2026-09-23T01:44:31.438Z', 'correlation_id': 'aad5d35a718a42029afde896e2210afd', 'actor_kind': 'human', 'actor_id': 'web', 'tool': 'set_autonomy_level', 'blast_class': 'local_destructive', 'autonomy_level': 0, 'decision': 'allow', 'approved_by': 'claimed_human', 'approval_id': None, 'result': 'ok', 'failure': None, 'duration_ms': 4}, {'at': '2026-09-23T01:44:31.442Z', 'correlation_id': 'ce218ee0a571461babfbae8b76b416f3', 'actor_kind': 'human', 'actor_id': 'web', 'tool': 'set_autonomy_level', 'blast_class': 'local_destructive', 'autonomy_level': 0, 'decision': 'allow', 'approved_by': 'claimed_human', 'approval_id': None, 'result': 'ok', 'failure': None, 'duration_ms': 2}, {'at': '2026-09-23T01:44:31.446Z', 'correlation_id': 'f0a77cfbbced4ccca69ad3ae7198642b', 'actor_kind': 'human', 'actor_id': 'web', 'tool': 'delete_project', 'blast_class': 'local_destructive', 'autonomy_level': 
**measured_claim:** approved_by for the destructive call is 'claimed_human' — policy.TABLE allows LOCAL_DESTRUCTIVE for Audience.HUMAN at both autonomy levels.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S27 — PASS

**Class:** edge-case · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S27`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | each client receives exactly ten frames with strictly increasing id: and no duplicate; the two clients' frame sets are equal; ten mutations landed with no lost update; ten audit records; an observer tab runs refreshAll at most twice per burst, counted at page.on('request') | A=[82, 83, 84, 85, 86, 87, 88, 89, 90, 91]; B=[82, 83, 84, 85, 86, 87, 88, 89, 90, 91]; observer_reads=1 | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S28 — PASS

**Class:** edge-case · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S28`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | two Create clicks in one tick produce ONE POST, ONE workspace row and ONE frame; the composer's three keyboard cases behave (Enter sends, Shift+Enter newlines, empty is a no-op) | create_posts=1; rows=1; master_sends=1 | PASS |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | (same assertion block as above) | (same record as above) | PASS |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**declared_uncovered:** Four other POST handlers are deliberately unguarded on an idempotency bet. Driving them would assert the bet, not the guard.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S33 — PASS *(flaky — FAIL on run 1, PASS on runs 2 and 3; hit rate 1/3)*

**Class:** error-handling · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (node id `tests/qa5/test_wave6_sinks.py::test_s33_the_pages_validation_surface`)
**Exit code:** 1 (run 1) / 0 (runs 2, 3)

**This block reports the RED, because the red is the finding.** Per the flake policy the scenario is
recorded `PASS` with `flaky: true` — it passed on re-run — and the pass is not read as confidence,
because the thing that made it fail is a shipped product race, not test nondeterminism.

| Observation point | Expected | Actual (run 1 — FAIL) | Result |
| ----------------- | -------- | --------------------- | ------ |
| UI | (a) empty name issues EXACTLY ZERO requests and is refused by `required` itself; (b) a single space issues ZERO requests and renders `NEEDS_NAME` in `#p-refusal`; (c) warns, warns on a second duplicate, re-arms, warns again, creates on the fourth press | (a) `#p-refusal=''` with `validity.valueMissing=True`; (b) `'A project needs a name — this one is only whitespace.'`; (c) the three warnings landed and the fourth press created exactly one workspace — **all of this passed in run 1 too** | PASS |
| UI | edit mode: `#p-paths-section` visible and `#p-paths .path` reaches **2** (P1's two seeded repo paths) before (d)/(e) are driven | `#p-paths-section.hidden === False` held; `document.querySelectorAll('#p-paths .path').length === 2` **never became true within the 10 s bound** — `playwright._impl._errors.TimeoutError: Page.wait_for_function: Timeout 10000ms exceeded` at `tests/qa5/test_wave6_sinks.py:454` | **FAIL** |
| API | (d),(e) each issue exactly one `…/repos/add` answering `added==false` with a refusal naming the path | **not reached in run 1** — the scenario aborted before (d)/(e). In runs 2 and 3: `posts=['POST /api/projects', 'POST /api/projects/<P1>/repos/add', 'POST /api/projects/<P1>/repos/add']`, both refusals naming the offending path | not reached (run 1) / PASS (runs 2, 3) |
| DB | exactly one new workspace row net of the control; no new edge | runs 2, 3: one new workspace row, no new edge | PASS (runs 2, 3) |
| Queue | zero frames in the counted window, bracketed by the §3a control's two frames | runs 2, 3: window interior zero; control frames `project.created`, `project.deleted` in order at both clients | PASS (runs 2, 3) |
| Logs | n/a — the plan names no audit assertion for S33 | — | n/a |

**Measured instrumentation at the failure point:** `s33_edit_dialog_presses = 1` in **all three runs**
— `press_until_open` opened the edit dialog on its first press every time. The red is therefore
downstream of the press-retry workaround, which was never exercised this round.

**What the evidence does and does not establish.** It establishes that the edit dialog opened on a
project whose draft path list never reached two, immediately after the harness had already (i) waited
for `networkidle` and (ii) waited for P1's own first repo path to be present in `#proj-detail`. That
is the declared race's signature verbatim — *"leaving `#proj-edit` bound to a different project and
the draft path list stuck at zero"*. It does **not** establish the exact interleaving: the harness's
assertion at `:454` dumps no dialog-bound project id, so the losing/winning `loadDetail` was not
directly observed. Stated rather than smoothed over.

**Stub reach:** none — real `controld`, real store, real chromium.

### S34 — PASS

**Class:** error-handling · **Tier:** e2e_backend
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S34`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | (a) 403, (b) 400, (c) 404, each with exactly {"ok":false,"data":null,"error":"GENERIC_ERROR","correlation_id":"<32 hex>"} and the id matched as a pattern; (d) 200, the rename lands on P1 and the body's project_id redirects nothing while the undeclared colour is dropped; (e) added==false with a refusal naming the directory; exactly one project.renamed frame and none from the four refusals; audit records for (d) and (e) only | correlation ids=['53c4e2536efb4e44b493bbee7d701317', '23a278cbb27d4d1eba83a47be64ab9f0', 'f7ea810b8e54428481b81e19637759df']; decoy name 'S34-DECOY' -> 'S34-DECOY'; audit=['rename_project', 'add_repo'] | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | (same assertion block as above) | (same record as above) | PASS |
| Logs | (same assertion block as above) | (same record as above) | PASS |

**deferred_gap:** This seam cannot separate routes.py's two no-redirect guards: removing either alone leaves the assertion green. The unit seam that can is tests/web/test_routes_m3.py::test_no_declared_field_shadows_a_path_parameter.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S30 — PASS

**Class:** happy-path · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S30`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | render_check.py against the SERVED url with --fail-on-empty and --must-fill exits 0 over every entry of render_check.VIEWPORTS, read from the module and never re-spelled | argv=['/root/Shepherd/tools/render_check.py', '--url', 'http://127.0.0.1:33825/', '--fail-on-empty', '--must-fill', '/tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/qa5-2042719/shots/s30']; viewports=['phone', 'tablet', 'desktop']; exit=0; summary=['18 pages checked · 18 screenshots · 0 failures', 'screenshots in /tmp/claude-0/-root-Shepherd/fe792a67-63e7-4d03-b537-ea06fb5701f9/scratchpad/qa5-2042719/shots/s30']; screenshots=18 over 6 page roots | PASS |
| API | (same assertion block as above) | (same record as above) | PASS |
| DB | n/a — the plan names no assertion at this point | — | n/a |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**declaration:** AC-28's final clause was **not run**. Its command invokes `pytest -m live`, which starts real `claude` processes against the user's real `~/.claude.json` and is forbidden by a standing user constraint. S30 is a substitute sweep carrying no `live` marker, and a PASS here does not discharge AC-28.
**unfalsifiable_here:** --fail-on-empty is a whole-body emptiness check and index.html ships the nav, the wordmark and the section labels as static markup, so the body can never be empty while the shell is served. It costs nothing and catches a server answering 200 with nothing; it is not evidence about layout. --must-fill is the flag that engages FILL_FLOOR.

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S31 — PASS

**Class:** edge-case · **Tier:** integration
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (serial, one process; this scenario is node id `S31`)
**Exit code:** 0

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | n/a — the plan names no assertion at this point | — | n/a |
| API | n/a — the plan names no assertion at this point | — | n/a |
| DB | BODY_ARGS == 16 (AC-16 says 15 — stale); post_milestone.edits == 7 (AC-21 says 6 — stale); terminal.js digest != its manifest baseline (AC-23 assumes byte-clean — stale); API_ROUTES == 14; POST_ROUTES == 16; sha256(web/server.py) equals the manifest baseline | {'BODY_ARGS': 16, 'API_ROUTES': 14, 'POST_ROUTES': 16, 'post_milestone.edits': 7}; server_sha256=215b223bda4aacde…; terminal_sha256=781bed86a4092e0f…; stale=['AC-16 says BODY_ARGS == 15', 'AC-21 says post_milestone.edits == 6', 'AC-23 assumes terminal.js is byte-clean'] | PASS |
| Queue | n/a — the plan names no assertion at this point | — | n/a |
| Logs | n/a — the plan names no assertion at this point | — | n/a |

**Stub reach:** none — every dependency in this scenario is real (`controld`, SQLite `Store` at schema 004, real tmux panes on `shepherd-qa`, real `git`, real chromium).

### S29 — BLOCKED

**Class:** error-handling · **Tier:** ui
**Command:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (node id `tests/qa5/test_wave6_sinks.py::test_s29_*`; runs last, after `controld.stop`)
**Exit code:** 0 — **and that is part of the finding.** The harness records this scenario `PARTIAL`,
which is a fourth verdict outside this report's PASS/FAIL/BLOCKED vocabulary. It does not round up.

| Observation point | Expected | Actual | Result |
| ----------------- | -------- | ------ | ------ |
| UI | with `controld` stopped, `#shepherd-status` and `#p-refusal` carry `app.js`'s own constant, read out of the module and never re-spelled | `'The request did not reach the server — Shepherd may not be running.'` on both | PASS |
| UI | `#settings-note` carries `settings.js`'s different constant | `'The request did not reach the server — Shepherd may not be running, so these num…'` | PASS |
| UI | the Flock's failure surfaces in the shell's shared banner, unhidden | `'The request did not reach the server — Shepherd may not be running.'`, banner unhidden | PASS |
| UI | `#stream-status` **not** reading `live` | `stream_status='live'` (`noticed=False`) 30 s after `controld.stop` | **NOT_CHECKED — no oracle** |
| UI | zero `console.error` / `pageerror` — a network failure must be handled, not thrown | zero page errors; 4 browser *network notices*, which are not page errors | PASS |
| API | `shutdown_hung` empty | `shutdown_hung=()` | PASS |
| DB | n/a — the plan names no store assertion for S29 | — | n/a |
| Queue | n/a — S29 asserts the stream is *closed*, which is the `#stream-status` row above | — | n/a |
| Logs | n/a — the plan names no audit assertion for S29 | — | n/a |

**Why NOT_CHECKED rather than FAIL, and why the scenario is BLOCKED rather than PASS.** Plan §0 rule
1 is explicit: *"No latency SLO is stated anywhere in the authority documents. Every time bound here
is a harness liveness bound. Blowing one is `BLOCKED`/`TIMEOUT`, never a product `FAIL`."* The 30 s
is the harness's bound, sourced from nothing. The assertion therefore has no oracle and no verdict
was rendered on it. Under this report's contract an observation point with no verdict prevents the
scenario from being `PASS`, so the scenario is `BLOCKED` — and `SCENARIOS_BLOCKED > 0` is what makes
the whole run's verdict `BLOCKED`.

**Stub reach:** none.

## 4. Failures

Two entries. One is a reproduced shipped defect; one is a check with no oracle. Neither is a harness
bug — those are §5.

### F1 — `projects.js:254` starts a detail read it never awaits, and a second read can overtake it

**Failure class:** defect
**Severity:** high
**Measured on:**

| repo | branch | sha | commits_behind | dirty |
| ---- | ------ | --- | -------------- | ----- |
| Shepherd (`/root/Shepherd`) | `integration` | `c243773` | **0** | yes — bookkeeping only |

Measured at report time with `git rev-parse --abbrev-ref HEAD`, `git rev-parse --short HEAD`,
`git rev-list --count HEAD..main`, `git status --porcelain`. **`commits_behind` is 0, and the raw
number is 2.** `git merge-base HEAD main` exits 1: the two branches have **no common ancestor**
(roots `8685558` for `integration`, `22d9ef2` for `main`). `git rev-list --count HEAD..main = 2` is a
set difference across disjoint histories — the two commits are `22d9ef2` ("Baseline: spec…") and
`bd10b01` ("Build M1–M4…"), a two-commit unrelated root line, while `main..HEAD` is 108. There is no
distance for `integration` to be behind by, so `commits_behind` is 0 and **the severity cap does not
fire.** Round 3 read this number as a currency deficit and capped every severity on it; this is that
misreading named so it is not repeated. The dirty tree is this workflow's own bookkeeping:
`git status --porcelain src/ tools/ docs/probes/` is empty, verified before and after every run.

**Sibling set:** `set_name: "every call site of the Projects page's two async view-loaders (loadList, loadDetail) in src/shepherd/web/static/projects.js"` — enumerated from `grep -n "loadDetail\|loadList" projects.js` **before** any member was judged.

**Siblings swept:**

| # | Member | Affected | Basis |
| - | ------ | -------- | ----- |
| 1 | `:194` `await loadList()` in `reload()` | false | awaited; the caller cannot continue before the list has landed |
| 2 | `:196` `await loadDetail(view.openId)` in `reload()` | false | awaited |
| 3 | **`:254` `loadDetail(project.project_id)` in `projectRow`'s click handler** | **true** | **not awaited**; `renderList()` runs synchronously on the next line and the handler returns while the read is in flight. This is the defect |
| 4 | `:678` `await loadList()` in `submitProject`'s create branch | false (counterparty) | awaited — but the dialog is closed at `:677`, one line *before* it, so the create looks finished to a user while two reads are still outstanding. This is the other half of the race, not a second instance of the defect |
| 5 | `:680` `await loadDetail(answer.project.project_id)` in `submitProject`'s create branch | false (counterparty) | awaited; the read that overtakes |
| 6 | `:966` `await loadList()` in `onDeleteAnswer` | false | awaited |
| 7 | `:1038` `await loadList()` in `renderDeleteOutcome` | false | awaited |
| 8 | `:1085` `loadList()` in `mountProjects` | false | **not awaited, same shape, different risk**: mount-time, exactly one loader in flight, and nothing reads its result synchronously. Named rather than dropped, because the shape alone is not the bug |

Eight members enumerated, eight findings. Exactly one site is affected; one other shares the shape
without the risk, and two more are the race's counterparties rather than instances of it.

**Siblings swept — branch axis:** n/a — single repo, not a cross-repo contract mismatch.
**Env setup:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` — the harness brings its whole environment up and down itself (run root, `XDG_RUNTIME_DIR`, store at schema 004, four tmux panes on `shepherd-qa`, `controld`, seed, chromium, two SSE clients).
**Repro:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/test_wave6_sinks.py::test_s33_the_pages_validation_surface -q` **will not reproduce in isolation** — the scenario depends on the serial seeded world the whole package builds. The reproducing command is the full suite; it reproduced on 1 of 3 attempts.
**Evidence:**

```
FAILED tests/qa5/test_wave6_sinks.py::test_s33_the_pages_validation_surface
  - playwright._impl._errors.TimeoutError: Page.wait_for_function: Timeout 10000ms exceeded.

tests/qa5/test_wave6_sinks.py:454:
    assert page.eval_on_selector("#p-paths-section", "el => el.hidden") is False
>   page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 2")
```

and, from the harness's own declaration constant (`tests/qa5/report.py:LOAD_DETAIL_RACE_DECLARATION`,
carried verbatim into every run file):

```
PRODUCT DEFECT, reproduced and worked around, not fixed: `web/static/projects.js:252-256` —
`projectRow`'s click handler calls `loadDetail(project.project_id)` WITHOUT awaiting it and then
`renderList()`, while `submitProject`'s create branch already has a `loadDetail` of its own in
flight. Two unawaited reads race and the later one to RESOLVE wins, so the detail pane can show a
project for a frame and then be overwritten — leaving `#proj-edit` bound to a different project and
the draft path list stuck at zero. Measured at approximately one full-suite run in four. A real user
hits it by clicking a project row while a create is still settling. ... but a settle in the test does
not fix the product, and the defect is shipped.
```

The shipped source, read this run:

```js
// src/shepherd/web/static/projects.js:252-256
row.addEventListener("click", () => {
  root().dataset.level = "detail";
  loadDetail(project.project_id);   // <- not awaited
  renderList();
});
```

### F2 — `#stream-status` read `live` 30 s after the daemon stopped, and the check has no oracle

**Failure class:** missing-input
**Severity:** low
**Measured on:**

| repo | branch | sha | commits_behind | dirty |
| ---- | ------ | --- | -------------- | ----- |
| Shepherd (`/root/Shepherd`) | `integration` | `c243773` | **0** | yes — bookkeeping only (`src/`, `tools/`, `docs/probes/` empty) |

Same measurement and the same disjoint-history reasoning as F1. Not capped.

**Sibling set:** `set_name: "every path that writes the shell's connection indicator — the three onStatus calls in sse.js plus the single consumer chain"` — enumerated from `grep -rn "stream-status\|onStatus\|connect(" src/shepherd/web/static/*.js` before judging.

**Siblings swept:**

| # | Member | Affected | Basis |
| - | ------ | -------- | ----- |
| 1 | `sse.js:20` `source.addEventListener("open", () => onStatus("live"))` | true | this is the write that was still standing at +30 s |
| 2 | `sse.js:27` parse failure → `onStatus("unreadable")` | not_applicable | a different trigger (malformed frame), not reached by a stopped daemon |
| 3 | `sse.js:33` `source.addEventListener("error", () => onStatus("reconnecting"))` | **true — and it is the exculpating member** | the denial mechanism **exists in the shipped code**. This is not an unreachable state; it is a state that did not arrive within the harness's unsourced 30 s |
| 4 | `app.js:364` `connect(onEnvelope, renderStatus)` | false | the sole subscription; correctly wires status through to the renderer |
| 5 | `flock.js:546` `renderStatus(status)` → `#stream-status.textContent` | false | writes whatever it is handed; no logic of its own |

Five members enumerated, five findings.

**Siblings swept — branch axis:** n/a — single repo, not a cross-repo contract mismatch.
**Env setup:** `cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q` (S29 runs last, after every other scenario, and stops `controld` itself).
**Repro:** full suite; S29 reported the same `stream_status='live'` in **all three** runs — deterministic.
**Evidence:**

```
S29 PARTIAL
observed={'shepherd': 'The request did not reach the server — Shepherd may not be running.',
          'projects': 'The request did not reach the server — Shepherd may not be running.',
          'settings': 'The request did not reach the server — Shepherd may not be running, so these num',
          'flock':    'The request did not reach the server — Shepherd may not be running.'};
stream_status='live' (noticed=False); shutdown_hung=(); browser network notices (not page errors)=4
```

**What a debugger should settle first, and it is cheap:** does the in-process `controld.stop` close
the already-accepted SSE socket? If it does, the page had something to notice and did not — and the
severity is wrong. If it does not, there was no error for `sse.js:33` to fire on and the product is
not implicated at all. That single question is the missing input, and it is why this is classed
`missing-input` rather than `defect`.

## 5. Harness issues

| Issue | What it undermines | Rebuild needed |
| ----- | ------------------ | -------------- |
| `RunReport.publish_latest` is last-writer-wins. Run 1 correctly published a `FAIL` to `qa5-latest.json`; run 2 overwrote it with a green one **40 s later**. The per-run timestamped files survive, so no evidence was destroyed — but "the record of record" now shows a clean run where the last three runs contained a red | The published artifact's usefulness as *the* answer. Anyone reading `qa5-latest.json` alone after today sees `FAIL: 0` | no — worth a guard (refuse to overwrite a published red with a green one, or publish to a per-run name and symlink), but it did not weaken this run's evidence |
| The harness's verdict vocabulary has a fourth value, `PARTIAL` (`report.py:record`), which the router contract does not carry. S29 is its only user. It does not round up, which is the right instinct, but it forces the executor to re-adjudicate the scenario rather than read a verdict | Nothing, this round — but a `PARTIAL` is one careless reading away from being summed with `PASS` | no |
| A scenario that dies before its own `record()` call gets a harness-written fallback row whose `expected`/`actual` describe *the test's failure to record*, not the scenario's own expected/actual (run 1's S33: `"was expected to run to its own record() call"` + a pytest traceback). The fallback is a real improvement over the pre-remediation behaviour — it is why run 1 could express a failure at all — but the red's evidence is a traceback rather than structured expected/actual, and the failing assertion at `:454` dumps no page state | The structure of a red's evidence, not its existence. §3's S33 block had to reconstruct the observation table by hand | no — a state dump on the `#p-paths` wait would have made F1's interleaving directly observable instead of inferred |

**What held.** The publication gate did its job: all three runs recorded exactly the planned 37 with
`missing=[] extra=[] duplicated=[]`, and run 1 published *with* its `FAIL` rather than swallowing it —
which is exactly the failure mode (140 run files, `FAIL` total 0, 47 all-green with `scenarios: 0`)
that the emit/publish split was built to close. The §3a SSE rig re-proved itself at two frames per
client in every run (`rig_probe {'A': 2, 'B': 2}`), and the fixture-side controls were green before
wave 1 in every run.

## 6. Environment

| Fact | Value |
| ---- | ----- |
| Services provisioned | `controld` (HTTP + SSE + WebSocket + registry + chokepoint + audit sink + discovery loop) on an ephemeral loopback port (run 2: `127.0.0.1:33825`) · SQLite `Store` at `user_version = 4` · `LocalRunner` against tmux socket **`shepherd-qa`** with four real panes (`shepherd_r5a`–`shepherd_r5d`) plus the control pane `shepherd_r5z` · real `git` via `probe_repo` · headless chromium `/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome` · two live SSE clients A and B |
| Services stubbed | **None.** No stub reached any verdict in any scenario. `spawn_session`, the Agent SDK master turn loop and `pytest -m live` were not exercised at all (C-4) — that is an absence of coverage, not a stub; see §7 |
| Readiness wait | Gated, never slept: bring-up is eleven steps ending on the `bound` event plus a functional `GET /api/fleet` probe, then the §3a rig control (create `RIG-PROBE`, assert `project.created` at **both** clients, delete), then the fixture-side controls. `BRINGUP` PASSED in all three runs. `rig_probe = {'A': 2, 'B': 2}` in all three. Full suite wall time: 105 s / 95 s / 95 s |
| Teardown status | **clean** |
| Teardown evidence | Verified independently by me after runs 2 and 3, not taken from the harness's own log. `tmux -L shepherd-qa ls` → `no server running on /tmp/tmux-0/shepherd-qa`. `ls -d /tmp/shq5-*` → `No such file or directory` (both runtime dirs gone). `ls -d …/scratchpad/qa5-2*` → `No such file or directory` (both run roots gone). `git worktree list \| wc -l` → **14**, identical to the pre-run baseline, and `$SCRATCH/macwt dade568 (detached HEAD)` still registered. `git status --porcelain src/ tools/ docs/probes/ tests/ pyproject.toml` → only `?? tests/qa5/`. `ps -eo args \| grep -Ei "controld\|chrome-linux64\|pytest"` → nothing. The harness's own teardown log agrees: `kill panes: shepherd_r5a=gone, shepherd_r5b=killed, shepherd_r5c=gone, shepherd_r5d=killed, shepherd_r5z=gone` · `socket empty: no session remains on shepherd-qa` |
| **The user's own tmux socket** | `tmux -L shepherd ls` → `m3` and `master`, **byte-identical before and after all three runs**. The socket was never written to. No `kill-server` was issued at any blast radius, by me or by the harness |
| Leaked resources | **None.** One pre-existing directory, `…/scratchpad/qa5-mutations`, remains — it is the *build* phase's mutation-driver root, predates this run, and is not this run's to remove. My run roots were `qa5-2041221`, `qa5-2042719`, `qa5-2044242`; all three are gone |
| Product code touched | **false** — `git status --porcelain src/ tools/ pyproject.toml` empty before and after |
| Test code touched | **false** — `tests/qa5` is untracked, so git cannot speak for it; verified instead by content hash. `find tests/qa5 -name '*.py' -not -path '*__pycache__*' \| sort \| xargs md5sum \| md5sum` → `c8aca30e4096e1f4f8ac0a125a8c655a` **before run 1 and after run 3**, and `find tests/qa5 -name '*.py' -newermt "2026-09-23 01:38"` returned nothing |
| Harness-level rows (not plan scenarios) | `BRINGUP` PASS ×3 — `port=33825, panes=[r5a,r5b,r5c,r5d], socket=shepherd-qa, projects=8`. `WAVE2-LIVENESS` PASS ×3 — the rig's two frames, `project.created` then `project.deleted`, at both clients before wave 2 consumed it |
| Measured environment | `run_root=/tmp/…/scratchpad/qa5-<pid>` · `XDG_RUNTIME_DIR=/tmp/shq5-<pid>` (socket budget spent: **40** of 107 bytes) · `PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright` pinned, as preflight's P1 correction requires · `tmux 3.4` · `schema_version 4` · `pane_sweep: shepherd-qa was already empty` at the start of every run |

## 7. Coverage gaps

| Gap | Why it was not covered | What would close it |
| --- | ---------------------- | ------------------- |
| **AC-28's final clause — the whole of it** | Its command invokes `pytest -m live`, forbidden by standing constraint C-4 (real `claude` processes against the user's real `~/.claude.json`). S30's served-`controld` sweep is a substitute and **its PASS does not discharge AC-28** | A user decision to authorise a live lane, in an environment with a throwaway `~/.claude.json` |
| `#stream-status` over a genuinely dropped stream | S29's only shutdown is an in-process `controld.stop`, and whether that closes the accepted SSE socket was never measured. No source states a detection deadline | Kill `controld` as a real process (or close the socket explicitly) and assert `#stream-status` reaches `reconnecting`; and state a deadline in an authority document so the assertion has an oracle |
| The exact interleaving behind F1 | The failing wait at `test_wave6_sinks.py:454` dumps no page state, so the dialog's bound project id at failure time was never read | A state dump on that wait (`#proj-detail` contents + the dialog's bound id), or instrumenting `loadDetail` resolution order |
| `spawn_session`, the Agent SDK master turn loop, `sessiond` and the relay | Out of scope by plan §1 — all require a real `claude` process | The same live-lane authorisation as AC-28 |
| The WebSocket **read** half (`tests/web/test_ws.py`'s 14 reader tests) | Vacuous by construction — the contract has no implementer in `src/` (B14). Round 5 drives the **write** half only and makes no claim about those 14 | An implementer, or retirement of the 14 |
| `POST /api/sessions/{id}/permission` | Routed, registered, called by no page (plan §1) | A caller |
| Round 1's eleven closures | Recorded with no id, no description and no named check. **They cannot be re-verified at all** — not by this run and not by any future one | Nothing; the evidence does not exist. Treat those eleven as unverified |
| Two of the nine `#p-name`/`#p-new-path` values — **bare repo** and **subdirectory-of-a-repo** | Each needs a distinct real repository shape on disk (B11) and exercises `probe_repo`, not the page. Carried as a `deferred` gap by the plan itself | Two more seeded repo fixtures |
| `runner_socket` in its **OFF** state (`shepherd-runner`, the default) | Not driven. The plan's own note: that is the state the previous four rounds ran in, which is what made `killable` empty everywhere | A run with the default socket, if the OFF path is ever considered at risk |
| S34's path-precedence guard cannot be isolated at this seam | `routes.py` has two no-redirect guards and removing either alone leaves S34(d) green. Recorded by the harness as a `deferred_gap` | The unit seam that can separate them: `tests/web/test_routes_m3.py::test_no_declared_field_shadows_a_path_parameter` |
| **Seven plan-wording divergences resolved at build time, not at run time** | The harness recorded each as a `measurement` in its own scenario detail rather than weakening the assertion: S6 (`#p-desc-note` reflects the dialog mode, never the description — `#p-desc` carries the claim) · S9 (the five delete choices are two-phase and never simultaneous) · S11 (`deleted` was an inferred row; measured `False` and now pinned) · S12 (superseded plan wording on `kill_failures`/`stop_failed`) · S14 (the `CLOSE_NORMAL` clause is not run — on a live pane there is no close to read) · S22 (`body { zoom }` does not move media queries; emulated as `device_scale_factor` + scaled CSS viewport) · S33 (an empty name is refused by the browser's own `required`; `NEEDS_NAME` is the *space* case) | Each is a finding for a plan revision 7, alongside AC-16/21/23. None weakens this run's verdicts — all are visible in §3's per-scenario detail |
| Scenarios marked `unproven by stub` | **None.** No stub reached any verdict in any scenario | — |

## 8. Bug candidates

```yaml
BUG_CANDIDATES:
  - title: "projects.js:254 starts loadDetail() without awaiting it, so a concurrent detail read can overtake it and rebind #proj-edit to the wrong project"
    severity: "high"
    measured_on:
      - repo: "Shepherd"
        branch: "integration"
        sha: "c243773"
        commits_behind: 0      # raw `rev-list HEAD..main` = 2, but merge-base exits 1: disjoint roots 8685558/22d9ef2. No distance exists; cap does not fire.
    failure_class: "defect"
    scenario: "S33"
    tier: "ui"
    expected: "after the edit dialog opens on P1, #p-paths .path reaches 2 (P1's two seeded repo paths)"
    actual: "#p-paths .path never reached 2 within the 10s bound; TimeoutError at tests/qa5/test_wave6_sinks.py:454, with #p-paths-section.hidden already False"
    repro: "Run the full qa5 suite. In S33, press Create on a fourth (unique) name so submitProject's create branch starts `await loadList(); await loadDetail(newId)` AFTER closing the dialog, then click P1's row, which starts an UNAWAITED loadDetail(P1). The later read to resolve wins the detail pane; #proj-edit's click closure is captured at render time (projects.js:343), so the edit dialog opens on whichever project rendered last."
    repro_command: "cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q"
    repro_ladder_rung: 3
    repro_deterministic: false
    hit_rate: "1/3 this round (runs 1,2,3); ~1/4 measured by the harness builder"
    env_setup_command: "cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q   # the harness brings its own environment up and down"
    env_mode: "local"
    services_required: ["controld", "sqlite Store @ schema 004", "tmux socket shepherd-qa", "chromium (playwright)"]
    services_stubbed: []
    boundary_observations:
      - order: 1
        boundary: "controld HTTP — GET /api/projects/{id}"
        kind: "api"
        expected: "each loadDetail issues one read and both return 200"
        actual: "both returned; networkidle reached"
        result: PASS
      - order: 2
        boundary: "projects.js view state — view.openId / renderDetail()"
        kind: "ui"
        expected: "the detail pane settles on the project whose row was clicked"
        actual: "#proj-detail contained P1's first repo path at the moment it was checked"
        result: PASS
      - order: 3
        boundary: "projects.js:343 — #proj-edit's click closure, captured at detail-render time"
        kind: "ui"
        expected: "#proj-edit bound to P1"
        actual: "the edit dialog opened on the first press (s33_edit_dialog_presses=1) but on a project with != 2 repo paths"
        result: FAIL
      - order: 4
        boundary: "loadDraftPaths() -> GET /api/projects/{id}/repos"
        kind: "api"
        expected: "two draft paths rendered into #p-paths"
        actual: "#p-paths .path stayed below 2 for the full 10s bound"
        result: FAIL
    first_failing_boundary: "projects.js:343 — #proj-edit's click closure, captured at detail-render time"
    baseline: "unknown"
    baseline_evidence: "Four prior QA rounds found 22 defects but none ran this route and round 1's eleven closures carry no id, description or check. No round before 5 drove #proj-edit on an ordinary project at all (plan §2, B2), so there is no earlier observation of this path to compare against."
    variants_exercised:
      role: "web / Audience.HUMAN (the only role that exists)"
      tenant: null
      locale: "default; RTL exercised separately by S21"
      inputs: { "viewport": "1280x900", "dialog_mode": "edit", "project": "P1 (two repo paths)" }
    evidence: |
      FAILED tests/qa5/test_wave6_sinks.py::test_s33_the_pages_validation_surface
        - playwright._impl._errors.TimeoutError: Page.wait_for_function: Timeout 10000ms exceeded.
      tests/qa5/test_wave6_sinks.py:454:
          assert page.eval_on_selector("#p-paths-section", "el => el.hidden") is False
      >   page.wait_for_function("() => document.querySelectorAll('#p-paths .path').length === 2")

      src/shepherd/web/static/projects.js:252-256
        row.addEventListener("click", () => {
          root().dataset.level = "detail";
          loadDetail(project.project_id);   // not awaited
          renderList();
        });
    suspected_service: null
    suspicion_basis: "Single-service page-side defect; naming a service would add nothing. The first failing boundary is stated above and it is inside projects.js."
    siblings_swept:
      set_name: "every call site of the Projects page's two async view-loaders (loadList, loadDetail) in src/shepherd/web/static/projects.js"
      members:
        - "projects.js:194 await loadList() in reload()"
        - "projects.js:196 await loadDetail(view.openId) in reload()"
        - "projects.js:254 loadDetail(project.project_id) in projectRow click handler"
        - "projects.js:678 await loadList() in submitProject create branch"
        - "projects.js:680 await loadDetail(answer.project.project_id) in submitProject create branch"
        - "projects.js:966 await loadList() in onDeleteAnswer"
        - "projects.js:1038 await loadList() in renderDeleteOutcome"
        - "projects.js:1085 loadList() in mountProjects"
      findings:
        - member: "projects.js:194 await loadList() in reload()"
          affected: false
          basis: "awaited"
        - member: "projects.js:196 await loadDetail(view.openId) in reload()"
          affected: false
          basis: "awaited"
        - member: "projects.js:254 loadDetail(project.project_id) in projectRow click handler"
          affected: true
          basis: "not awaited; renderList() runs synchronously on the next line and the handler returns with the read in flight"
        - member: "projects.js:678 await loadList() in submitProject create branch"
          affected: false
          basis: "awaited — but the dialog closes at :677, one line earlier, so the create looks finished while two reads are outstanding. Counterparty, not a second instance"
        - member: "projects.js:680 await loadDetail(answer.project.project_id) in submitProject create branch"
          affected: false
          basis: "awaited; this is the read that overtakes"
        - member: "projects.js:966 await loadList() in onDeleteAnswer"
          affected: false
          basis: "awaited"
        - member: "projects.js:1038 await loadList() in renderDeleteOutcome"
          affected: false
          basis: "awaited"
        - member: "projects.js:1085 loadList() in mountProjects"
          affected: false
          basis: "not awaited, same shape, different risk: mount-time, one loader in flight, nothing reads the result synchronously"
      branch_axis: []   # single repo; not a cross-repo contract mismatch

  - title: "#stream-status still read `live` 30s after controld stopped; the denial mechanism exists but did not fire, and the check has no stated deadline"
    severity: "low"
    measured_on:
      - repo: "Shepherd"
        branch: "integration"
        sha: "c243773"
        commits_behind: 0      # same disjoint-history reasoning as above
    failure_class: "missing-input"
    scenario: "S29"
    tier: "ui"
    expected: "#stream-status not reading `live` once controld has stopped"
    actual: "stream_status='live' (noticed=False) at +30s, in all three runs"
    repro: "Run the full suite; S29 runs last and stops controld itself, then reads #stream-status after a 30s bounded wait."
    repro_command: "cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q"
    repro_ladder_rung: 3
    repro_deterministic: true
    hit_rate: "3/3"
    env_setup_command: "cd /root/Shepherd && CI=true .venv/bin/python -m pytest tests/qa5/ -q"
    env_mode: "local"
    services_required: ["controld", "chromium (playwright)"]
    services_stubbed: []
    boundary_observations:
      - order: 1
        boundary: "controld — in-process stop()"
        kind: "api"
        expected: "the daemon stops and subsequent HTTP reads fail"
        actual: "stopped; shutdown_hung=(); 4 browser network notices; all three module failure sentences rendered"
        result: PASS
      - order: 2
        boundary: "browser EventSource — did it see an error at all?"
        kind: "logs"
        expected: "an `error` event, which sse.js:33 turns into onStatus('reconnecting')"
        actual: "NOT INSTRUMENTED — whether the accepted SSE socket was closed by an in-process stop was never measured"
        result: NOT_CHECKED
      - order: 3
        boundary: "flock.js:546 — #stream-status.textContent"
        kind: "ui"
        expected: "anything other than `live`"
        actual: "`live`"
        result: NOT_CHECKED   # no oracle: no source states a detection deadline (plan §0 rule 1)
    first_failing_boundary: null
    baseline: "unknown"
    baseline_evidence: "No prior round drove a daemon-down browser scenario; S29 is new in round 5."
    variants_exercised:
      role: "web / Audience.HUMAN"
      tenant: null
      locale: "default"
      inputs: { "wait_s": 30, "shutdown": "in-process controld.stop()" }
    evidence: |
      S29 PARTIAL
      observed={'shepherd': 'The request did not reach the server — Shepherd may not be running.',
                'projects': 'The request did not reach the server — Shepherd may not be running.',
                'settings': 'The request did not reach the server — Shepherd may not be running, so these num',
                'flock':    'The request did not reach the server — Shepherd may not be running.'};
      stream_status='live' (noticed=False); shutdown_hung=(); browser network notices (not page errors)=4

      src/shepherd/web/static/sse.js:33
        source.addEventListener("error", () => onStatus("reconnecting"));
      src/shepherd/web/static/app.js:364
        connect(onEnvelope, renderStatus);
      src/shepherd/web/static/flock.js:546
        const node = document.getElementById("stream-status"); node.textContent = status;
    suspected_service: null
    suspicion_basis: "The denial mechanism is present and correctly wired (sse.js:33 -> app.js:364 -> flock.js:546), so this is NOT an unreachable state. Whether the product is implicated at all turns on one unmeasured fact: does an in-process controld.stop close the already-accepted SSE socket? Stating a service here would be a guess."
    siblings_swept:
      set_name: "every path that writes the shell's connection indicator — the three onStatus calls in sse.js plus the single consumer chain"
      members:
        - "sse.js:20 open -> onStatus('live')"
        - "sse.js:27 JSON parse failure -> onStatus('unreadable')"
        - "sse.js:33 error -> onStatus('reconnecting')"
        - "app.js:364 connect(onEnvelope, renderStatus)"
        - "flock.js:546 renderStatus -> #stream-status.textContent"
      findings:
        - member: "sse.js:20 open -> onStatus('live')"
          affected: true
          basis: "this is the write still standing at +30s"
        - member: "sse.js:27 JSON parse failure -> onStatus('unreadable')"
          affected: not_applicable
          basis: "a different trigger (malformed frame); a stopped daemon does not reach it"
        - member: "sse.js:33 error -> onStatus('reconnecting')"
          affected: true
          basis: "the exculpating member — the denial mechanism EXISTS in shipped code, so the state is reachable; it simply did not arrive inside the harness's unsourced 30s"
        - member: "app.js:364 connect(onEnvelope, renderStatus)"
          affected: false
          basis: "sole subscription, correctly wired"
        - member: "flock.js:546 renderStatus -> #stream-status.textContent"
          affected: false
          basis: "writes whatever it is handed; no logic of its own"
      branch_axis: []   # single repo; not a cross-repo contract mismatch
```
