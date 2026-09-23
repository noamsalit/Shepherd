# QA research lane — source: `code`
wf:wf-20260921T212808Z-9172ed6b · branch `integration` · returned 2026-09-22
STATUS: PASS · CONFIDENCE: 86 · SOURCE_COVERAGE: partial
(not read line-by-line: app.css 2490 lines; the 11 store verbs; full bodies of the 28 web test files)

## Shape of the system
- The whole web layer is a **path -> tool-name table with no handler bodies**: routes.py:1-18, server.py:228-247.
  Every user action is therefore assertable as exactly one `invoke()` with a known argument set.
- 14 GET routes (routes.py:36-69), 16 POST routes (:88-120), plus SSE `/api/events` (deliberately NOT in
  API_ROUTES, routes.py:26) and WS `/api/sessions/{id}/terminal` (server.py:65,273-322).
- Binds 127.0.0.1 only, no knob (server.py:41,341-352). Undeclared query/body fields dropped; path
  parameter applied LAST so it always wins (routes.py:209-252).
- **Six page roots ship, not four**: index.html:56-76. `queues` (:325-330) and `kanban` (:344-349) are
  static "not built this milestone" stubs with no module.
- delete_project is a three-step verb: plan -> kill OUTSIDE any transaction on the calling thread ->
  commit that re-derives (tools_projects_delete.py:141-232). The delete dialog is drawn entirely from
  the server's own refusal record's 11 fields (:110-138).
- Event path: handler -> announce() gated on the record's own positive key (tools_projects_events.py:80-122)
  -> compose._publish -> ring -> sse.envelope promotes project_id to top level -> frame() with `id: seq`
  and NO `event:` name -> sse.js single message listener -> app.js:292-304 -> refreshAll (coalesced,
  at most two passes, no timer, app.js:253-288).

## Four code-internal contradictions (the lane's headline — recorded, NOT reconciled)
- **X1 — unrendered D60 holders.** `project_repo_row` emits `projects` (holders), `git_common_dir`,
  `vcs_remote`, `active`, `added_at` (tools_projects_reads.py:74-100) and its docstring says the page
  shows them as "shared with" (:78-89). `projects.js:310-316` renders only `root_path`; no JS file
  contains "shared" or reads `repo.projects`. The projection describes a renderer that does not exist.
- **X2 — remove_repo breaks the family's one-refusal-shape rule.** Module docstring (tools_projects.py:24-31)
  states every verb answers a boolean AND a `refused` string. `remove_repo` returns `{"removed": bool}`
  only (:289-292), and `projects.js:609-613` discards the answer and just reloads — a False is invisible.
- **X3 — repo_count=0 on the write verbs.** create_project / rename_project / set_project_description all
  answer `repo_count=0, last_activity_at=None` unconditionally (tools_projects.py:170,188,226). Renaming a
  project with 3 repos returns a record claiming 0. Masked on the page only because it always re-reads.
- **X4 — localOnly reads fields the projection never emits.** session.js:71-73 reads `title_source` /
  `title_synced_at`; `project_session` (tools_m1.py:108-135) emits neither. Self-documented as T19-b;
  the marker is `false` for every row the API serves.

## Unwired / unreachable by decision
- `POST /api/sessions/{id}/permission` -> `answer_permission` is routed and registered; **no page calls it**
  (session.js:414-418). Decision-card choices render inert by construction (:440-453).
- The WebSocket **read half is dead by decision**: web/ws.py's parse_frame/Frame/WebSocketClosed have no
  caller in src/. tests/boundaries/test_ws_read_path.py exists to make the absence loud — which means
  **tests/web/test_ws.py's 14 reader tests assert a contract with no implementer: vacuous by construction.**
- `terminal_resize` is a registered ToolDef with **no route** (terminal.js:42-50 names it as rejected).
- `escape.js` ships, is exported, and is imported by nothing in src/ (deliberate, so the scan has a target).
- `ON_RUNNING` is hardcoded in projects.js:32 and autonomy levels in settings.js:49-50; **no route exposes a
  tool schema**, so a new enum member ships with no UI and no red test.

## Testability blockers
- **No health/readiness endpoint.** Closest proxy is GET /api/fleet, which needs a working store — so
  readiness gating uses a route that can fail for unrelated reasons.
- `app.js:115` calls `Date.now()` directly in drawFlock; `flock.js::ago` takes the clock as a parameter, so
  the unit seam exists but the **page-level clock is not injectable in a browser run**.
- `correlation_id` is `uuid4().hex` per request (server.py:123) with no injection point — match a pattern,
  never a value.
- Registry, stream ring and `compose._PLANE` are module-global (ADR-7). **Two servers cannot coexist in one
  process**; parallel threads in one process are unsafe, parallel processes are fine.
- `add_repo` shells out to git via `probe_repo` with no stub seam — every add_repo scenario needs a real
  repository on disk.
- The emulator's chosen geometry is observable ONLY because terminal.js:324-325 writes
  `data-terminal-cols/-rows`.
- `sse.py:124-128` records an unclosed window (BLOCKER T15-1): a tail subscriber can miss an event in the
  instant between subscriptions. The code states the gap and does not close it.
- Good seams that DO exist: `kill` and `publish` are **required with no default** at
  `register_project_tools` (tools_projects.py:425-448) — that spelling is the QA-run-4 defect's fix.

## What the existing test surface structurally cannot see
- Byte/AST scans cannot see a runtime deletion, a computed-property sink, or a node built by one module and
  removed by another's `replaceChildren()`.
- `tests/web/test_shell.py` **loads no module** — reads index.html and app.css as text; cannot see that a
  wired id points at the wrong element.
- The reachability walk sees **imports, not calls** (app.js:14-21 records flock.js being "reached" through
  session.js for a whole phase while the page never drew).
- `pre_m4_routes.json` freezes only the **pre-T24** surface; the nine Projects/M4 routes are
  additive-checked only, never frozen — a change to the delete body contract would pass that gate.
- No consumer test asserts the unrendered projection fields (X1) — producer test only, which is exactly why
  the drift is invisible.
- Playwright 1.63.0 + chromium ARE in .venv, so the six browser-driven files really execute; only
  test_render_live.py:349 is `@pytest.mark.live` and excluded by `addopts = -q -m 'not live'` (pyproject:54).
- `render_check.VIEWPORTS` is now three widths (390/820/1280, tools/render_check.py:40-54). Any class of
  client between them is still unenumerated.

## User Action Inventory (unreduced) — see feature-map.md §6
Controls enumerated from code: 6 nav entries · 8 legend keys + info · project rows (data-driven, not
enumerated) · session cards (data-driven) · next_actions 7 kinds (only `inspect`, `external`-with-target and
`none` are live; resume/respawn/retry/escalate/requeue/reauth render inert with a `not yet` badge) ·
decision-card choices (inert) · Projects rows · #proj-new/#proj-edit/#proj-delete (Edit+Delete ABSENT, not
disabled, on `unassigned`) · #p-name/#p-desc/#p-new-path text · 5 delete-dialog choices ("Stop them, then
delete" is disabled up front when killable is empty) · 10 Settings sections · 2 autonomy levels (2=ask,
3=auto) · Enter/Shift+Enter composer · Enter/Escape inline rename · Enter on #p-new-path must NOT submit ·
drawer/rail toggles · date-scale cases · 3 viewport widths.

## Action chains worth testing as chains
Flock drill-down and back ×2 · edit a project's paths (add then remove then save) · delete against running
sessions (no on_running -> refusal -> kill_sessions -> kill_failures -> orphan) · duplicate-name
warn-then-allow, re-arming on name change · double-submit race (guarded by in-flight FLAGS, deliberately not
`disabled`, because the nodes are rebuilt on every answer) · cross-page nav via a session mini-link ·
envelope-burst coalescing · daemon death mid-flow on each of the four pages.
