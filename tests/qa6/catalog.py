"""The 161 test-plan scenarios: id, wave, tier, class, lane, oracle source, prediction.

**Generated once from `test-plan.md` r3** (the `### <ID> — <title>` headings, their
`**Tier:** … · **Predicted:** …` line, and the §3 build-order table) and then
checked in as data, so the report can account for every id without parsing a
document at run time. `test_harness_guards.py` re-derives the id set, the wave
sizes (6/27/23/18/20/34/19/11/3) and the tier split (8/96/57) from this table and
fails if any drifted.

`predicted` is the planner's expectation, recorded so the report can say whether
a finding was anticipated. The executor never adjusts an oracle to match it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Scenario:
    id: str
    wave: int
    tier: str
    klass: str
    lane: str
    oracle_source: str
    predicted: str
    title: str


PLANNED_TOTAL: Final[int] = 161

SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario('S0', 1, 'e2e_backend', 'edge-case', 'LIVE + HOST', 'feature-map C-10', '`needs_real_home` (tests/e2e/conftest.py:195 measured "Not logged in" with a throwaway HOME)', 'environment-truth probe (include whenever the feature map records a contradiction the environment can settle)'),
    Scenario('W1', 1, 'e2e_backend', 'happy-path', 'SUB', 'backend §1 (controld start), env readiness T1', 'PASS', 'SUB controld comes up on an ephemeral port and is ready by four signals'),
    Scenario('W2', 1, 'e2e_backend', 'edge-case', 'SUB + HOST', 'feature-map C-5, C-6; U2', 'PASS', "the instance is isolated: nothing it touches is the user's"),
    Scenario('W3', 1, 'ui', 'happy-path', 'SUB', 'spec O1, O2, O43; HANDOFF checklist', 'PASS', 'a real browser renders the shipped page live'),
    Scenario('W4', 1, 'e2e_backend', 'happy-path', 'SUB', 'backend §1; shutdown.py:66-68', 'PASS', 'SIGTERM stops controld cleanly and says so'),
    Scenario('W5', 1, 'integration', 'edge-case', 'UNIT + real tmux', 'product-contract (runner/pane.py `PANE_RULES`; docs/probes/2026-09-20-macos-pane/SECTION.md: the capture "classifies as PROMPT_READY")', 'PASS on (a) and (b); (c) recorded (its dialog capture is from Linux)', "the fake engine's pane classifies as the product expects (shim fidelity)"),
    Scenario('C1', 2, 'e2e_backend', 'happy-path', 'CLI + SUB', 'spec (README run steps; O49 admits blindness)', 'FAIL (C-1 / D3)', "`shepherd status` shows the running daemon's fleet"),
    Scenario('C2', 2, 'e2e_backend', 'happy-path', 'CLI + SUB', 'spec O47 (README:76)', 'FAIL (discovery/fleet lines "unknown", C-1)', '`shepherd doctor` reports engine, schema, database and discovery'),
    Scenario('C3', 2, 'e2e_backend', 'happy-path', 'CLI', 'spec S5, OP hooks; backend §1 install-hooks', 'FAIL (C-1: the tool is not registered in the CLI process)', '`shepherd install-hooks` dry-runs, then installs into a sandbox file'),
    Scenario('C5', 2, 'integration', 'error-handling', 'CLI', 'backend §1 (parse errors → `shepherd: <problem>` + usage, exit 64; "Refused --since → 64"; no `--settings` → exit 64 NEEDS_SETTINGS); spec O48', 'PASS on 8 argv; FAIL on `[replay, --since, 2026-13-45]` (main.py:112-125 checks presence only, so the date reaches an unregistered tool and exits 1 with daemon advice, commands.py:82-87 — a C-1 consequence)', 'CLI usage errors exit 64 with a readable problem'),
    Scenario('C7', 2, 'e2e_backend', 'error-handling', 'SUB', 'product-contract (controld.start docstring: "a refusal that wrote `shepherd.db` is no refusal") + spec "refuses to start"', 'FAIL (store opened and migrated before the bind)', 'controld on an occupied port refuses and writes nothing (C-24)'),
    Scenario('C8', 2, 'e2e_backend', 'error-handling', 'SUB', 'spec S3; product-contract (base.py:147-167 budget; controld.start "the socket plan is validated first")', 'PASS', 'the 103-byte socket budget: 103 starts, 104 refuses without writing'),
    Scenario('C9', 2, 'e2e_backend', 'edge-case', 'SUB', 'spec (OP: controld is the single writer)', 'FAIL (bind_listener unlinks with no live-owner check)', "a second controld on the same TMPDIR does not steal the first one's socket"),
    Scenario('C10', 2, 'e2e_backend', 'error-handling', 'SUB', "spec O50 (refuses start); the product's refusal convention (`EXIT_REFUSED = 2` and the `controld refuses to start:` line, controld.py:50, 122-127)", 'FAIL on the exit/line clauses (`MigrationRefused` is uncaught: a traceback, exit 1 — review pass 1, finding 9); PASS on the DB-unchanged clause', 'a database newer than the binary refuses start'),
    Scenario('H1', 2, 'integration', 'happy-path', 'UNIT', 'spec S5 (README:9-10, OP:2366-2374); backend §2 entry shape', 'PASS', 'install into a missing sandbox settings file'),
    Scenario('H2', 2, 'integration', 'edge-case', 'UNIT', 'spec S5 ("idempotent"; "removes only our entries")', 'PASS', "reinstall is byte-idempotent and keeps the user's own entries"),
    Scenario('H3', 2, 'integration', 'happy-path', 'UNIT', 'spec S5', 'PASS', 'uninstall removes only ours'),
    Scenario('H4', 2, 'integration', 'edge-case', 'UNIT', 'spec S5 ("backed up before writing"), README "reversible"', 'FAIL (one `.shepherd-backup`, overwritten each run)', 'the original settings survive two installs (C-25)'),
    Scenario('H5', 2, 'integration', 'error-handling', 'UNIT', 'backend §2 (install refusal) + spec S5 ("validated")', 'PASS', 'invalid settings files are refused and never written'),
    Scenario('A1', 2, 'e2e_backend', 'happy-path', 'SUB', 'spec (OP §13 envelope); web-ui §3', 'PASS', 'every session-free GET route answers the envelope'),
    Scenario('A2', 2, 'e2e_backend', 'error-handling', 'SUB', 'spec S8; §0 row 2 shape (a)', 'PASS', 'a refusal that takes the 400 shape leaks no reason'),
    Scenario('A3', 2, 'e2e_backend', 'error-handling', 'SUB', 'web-ui §3 (static allow-list); spec S9', 'PASS', 'unknown paths and non-shipped static files are 404'),
    Scenario('A4', 2, 'e2e_backend', 'error-handling', 'SUB', 'web-ui §3 (bad body → 400; limit 1 MiB)', 'PASS', 'body limits and bad bodies'),
    Scenario('A5', 2, 'e2e_backend', 'edge-case', 'SUB', 'spec S1, S2', 'PASS', 'origin and host checks, pairwise'),
    Scenario('A6', 2, 'e2e_backend', 'edge-case', 'SUB', 'web-ui §3', 'PASS', 'undeclared fields are dropped; the path parameter wins'),
    Scenario('A7', 2, 'e2e_backend', 'error-handling', 'SUB', 'spec S8', 'PASS on the body; the audit `failure` records the class name only', 'a failure never leaks internals'),
    Scenario('A8', 2, 'e2e_backend', 'edge-case', 'SUB + HOST', 'spec S1', 'PASS', 'loopback only'),
    Scenario('E1', 2, 'e2e_backend', 'happy-path', 'SUB', 'spec O42; web-ui §3; product-contract `web/sse.py:30-33` ("How long the stream waits between events before writing a keep-alive comment", `IDLE_TIMEOUT_S = 15.0`)', "PASS on framing; **FAIL on the keep-alive clause**: after an event the subscriber waits 15 s, returns `delivered=True` and re-subscribes, so the first keep-alive comes about 30 s after the POST (sse.py:116-123; stream.py:120-130 — review pass 1, finding 9). The report states that this violates sse.py's own docstring", 'SSE framing, headers and keep-alive'),
    Scenario('E2', 2, 'e2e_backend', 'happy-path', 'SUB', 'spec O42 (monotonic seq)', 'PASS', 'two clients see the same ordered stream under concurrent writers'),
    Scenario('E3', 2, 'e2e_backend', 'happy-path', 'SUB', 'spec O42', 'PASS', 'Last-Event-ID resumes exactly within the ring'),
    Scenario('E4', 2, 'e2e_backend', 'edge-case', 'SUB', 'web-ui §3 (`stream.gap` when > 4096 behind)', 'PASS (the first real exercise of the branch qa5 O3 never reached)', 'a client behind the ring is told (ring overflow)'),
    Scenario('E5', 2, 'e2e_backend', 'edge-case', 'SUB', 'spec O42 ("Last-Event-ID replays the gap")', "FAIL (the new daemon's seq restarts below the client's id)", 'Last-Event-ID across a daemon restart (C-9)'),
    Scenario('E6', 2, 'e2e_backend', 'happy-path', 'SUB', 'web-ui §3; D58', 'PASS', 'project frames carry the project id'),
    Scenario('C4', 3, 'e2e_backend', 'happy-path', 'CLI', 'spec (OP §8 replay; README uninstall)', 'FAIL (C-1)', '`shepherd uninstall-hooks`, `replay` and `recompute` work from the CLI'),
    Scenario('C6', 3, 'e2e_backend', 'happy-path', 'SUB (wave 3, the hooks module instance)', "spec O48, O50; backend §1 sessiond; sessiond.py:86-87 (the stop line's four fields)", 'PASS', 'sessiond: required flag, relay, schema mismatch, stop line'),
    Scenario('H6', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec S13 (hooks time out; a dead daemon never harms agents); sourced `alarm 0.25`', 'PASS', 'the dispatch one-liner delivers, and cannot hang an agent'),
    Scenario('D1', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D47, OP discovery', 'PASS', 'a busy sidecar registers a running attached session'),
    Scenario('D2', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec (OP §Notification: idle_prompt 60 s after Stop; D47)', 'PASS', 'the 60-second idle threshold, bracketed and crossed'),
    Scenario('D3', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec O32 (the actual ask, never "needs attention"); D47', 'PASS', 'waiting sessions carry the ask verbatim; leaving needs_you clears it'),
    Scenario('D4', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D47 liveness', 'PASS', 'the process exits: stopped with an end time'),
    Scenario('D5', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec D47 (liveness by pid + start token)', 'PASS', 'a live pid with the wrong start token is not that session'),
    Scenario('D6', 3, 'e2e_backend', 'error-handling', 'SUB', 'backend §2 (malformed_payload anomaly)', 'PASS', 'malformed and unreadable sidecars are counted, not fatal'),
    Scenario('D7', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec D47 (`cli` registers; `sdk-cli` skipped)', 'PASS', 'sdk-cli and other entrypoints are skipped and counted'),
    Scenario('D8', 3, 'e2e_backend', 'edge-case', 'SUB', 'backend §2 (unknown_registry_status)', 'PASS', 'an unknown status keeps the prior state and is counted'),
    Scenario('D9', 3, 'e2e_backend', 'edge-case', 'SUB', 'product-contract (registry.py:59-62, 186-188; discovery_loop.py:65-66: "never on a timer")', 'FAIL (a fork every 2 s pass)', 'discovery never forks `claude agents --json` on a timer (C-15)'),
    Scenario('D10', 3, 'e2e_backend', 'edge-case', 'SUB', 'backend §2 (sweep on stored sessions survives restart) + spec O-restart continuity', 'PASS', 'liveness survives a controld restart'),
    Scenario('D11', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec O29 (D29)', 'PASS', 'the title ratchet: a user title is never overwritten by the engine'),
    Scenario('D12', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec OP:976-993 table; O57 ("unmapped values go to unknown and are counted"); the spec text after the table ("`verification_required` and `cloud_credential_error`, which no row above maps"; "`SessionEnd.reason` also has `other` … which no row above maps")', "PASS on 16 cases; FAIL on 3 — `verification_required` and `cloud_credential_error` (the code maps both to `auth_failed`) and SessionEnd `other` (the code maps it to `DEFERS`, stop_map.py:124, DP8). All three are reported as **spec-vs-design contradictions** for the owner; the oracle stays the spec's (review pass 1, finding 11)", "mechanical stop evidence maps to the spec's reason and bucket"),
    Scenario('D13', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D48 (git-common-dir), D59', 'PASS', "a session's cwd binds it to the project owning that repo"),
    Scenario('P1', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D57, O35', 'PASS', 'create, list and get; duplicate names are two projects'),
    Scenario('P2', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D59, O37; §0 row 2 shape (b) (tools_projects.py:154-157, 175-190); derived for the whitespace rename (the API refuses what the UI refuses, projects.js:54)', 'PASS, except the whitespace rename, predicted FAIL (no server-side check)', 'rename, describe, clear; Unassigned refuses every verb with a negative record'),
    Scenario('P3', 3, 'e2e_backend', 'error-handling', 'SUB', 'spec S12 (canonicalised paths), D48', 'PASS on spec-backed classes; the rest recorded', 'add_repo path classes'),
    Scenario('P4', 3, 'e2e_backend', 'edge-case', 'SUB', 'web-ui §3 (`{removed}`)', 'PASS', 'remove_repo'),
    Scenario('P5', 3, 'e2e_backend', 'edge-case', 'SUB', 'spec D60, O38', 'PASS', 'a repo shared by two projects sends new sessions to Unassigned'),
    Scenario('P6', 3, 'e2e_backend', 'happy-path', 'SUB', 'spec D61', 'PASS', 'delete with nothing running forgets the project and its sessions'),
    Scenario('P9', 3, 'e2e_backend', 'error-handling', 'SUB', 'orchestration §8; §0 row 2 shape (b) (tools_projects_delete.py:105-115)', 'PASS', 'invalid delete requests change nothing'),
    Scenario('T1', 4, 'e2e_backend', 'happy-path', 'SUB', 'web-ui §3 (WS)', 'PASS', 'the terminal stream: snapshot, then live chunks'),
    Scenario('T2', 4, 'e2e_backend', 'error-handling', 'SUB', 'spec S2; web-ui §3', 'PASS', 'terminal refusals happen before the upgrade'),
    Scenario('T3', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec USER_ACTION_INVENTORY "type to pty" (session pane input)', 'FAIL (the server never reads the socket)', 'keystrokes typed into the terminal reach the pane (C-19)'),
    Scenario('T4', 4, 'e2e_backend', 'happy-path', 'SUB', 'web-ui §3 (close 1000)', 'PASS (closes qa5 O13)', 'a dying pane closes the stream normally'),
    Scenario('O1', 4, 'e2e_backend', 'happy-path', 'SUB', 'spec (OP §9, D49, S12); spawn.py:79-83 (PROMPT_READY → `starting`)', 'PASS', 'spawn an owned session in a registered repo'),
    Scenario('O2', 4, 'e2e_backend', 'error-handling', 'SUB', 'spec S12', 'PASS', 'admission refuses paths outside the allowlist'),
    Scenario('O3', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec O54 (depth 3, 5 children, 20 total; a readable tool error)', 'PASS', 'the three recursion caps at their boundaries'),
    Scenario('O4', 4, 'e2e_backend', 'edge-case', 'SUB', 'derived (O5 "no empty card"; one refused action leaves no state)', 'FAIL (the row is written before `runner.start`)', 'a spawn the runner refuses leaves no session behind'),
    Scenario('O5', 4, 'e2e_backend', 'happy-path', 'SUB', 'spec OP table (`killed` → unfinished); OP §9', 'PASS', 'kill an owned session'),
    Scenario('O6', 4, 'e2e_backend', 'error-handling', 'SUB', 'backend/orchestration (`no_pane`)', 'PASS', 'kill refusals'),
    Scenario('O7', 4, 'e2e_backend', 'happy-path', 'SUB', 'orchestration §2 (interrupt sends Escape)', 'PASS', 'interrupt delivers Escape to the pane'),
    Scenario('O8', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec O52; orchestration §6', 'PASS', 'the mailbox is idempotent and validates the origin label'),
    Scenario('O9', 4, 'e2e_backend', 'error-handling', 'SUB', 'spec O51 (writes only to owned sessions)', 'PASS', 'the mailbox refuses sessions it cannot own'),
    Scenario('O10', 4, 'e2e_backend', 'happy-path', 'SUB', 'spec O53', 'PASS', 'ask forks the engine and hides the fork'),
    Scenario('O11', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec (OP reconcile; §9)', 'PASS', 'owned panes survive a controld restart and stay killable'),
    Scenario('O12', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec README capability 3 ("sessions message and spawn each other")', 'FAIL (no SESSION caller is ever constructed)', 'no path exists by which a session can call a Shepherd tool (C-13)'),
    Scenario('P7', 4, 'e2e_backend', 'edge-case', 'SUB', 'spec D61, O36; AC10', 'PASS', 'running sessions refuse the delete; kill_sessions resolves owned, not attached'),
    Scenario('P8', 4, 'e2e_backend', 'happy-path', 'SUB', 'spec D59, D61', 'PASS', 'orphan moves running sessions to Unassigned'),
    Scenario('M1', 5, 'e2e_backend', 'happy-path', 'INP', 'orchestration §3 (streaming projection); spec O11', 'PASS', 'a master turn streams its events'),
    Scenario('M2', 5, 'e2e_backend', 'error-handling', 'INP', 'orchestration §3', 'PASS', 'a second send while a turn is live is refused, not queued'),
    Scenario('M3', 5, 'e2e_backend', 'happy-path', 'INP', 'spec O55, D54; OP:1696-1701', 'PASS', 'level 2: a destructive master call waits for approval, then runs'),
    Scenario('M4', 5, 'e2e_backend', 'happy-path', 'INP', 'spec O12, D54; orchestration §1', 'PASS', 'reject denies the call and says so to the master'),
    Scenario('M5', 5, 'e2e_backend', 'edge-case', 'INP', 'orchestration §1 (compare-and-set)', 'PASS', 'a second decision is a no-op; bad decisions are refused'),
    Scenario('M6', 5, 'e2e_backend', 'edge-case', 'INP', 'spec D54; orchestration §3 interrupt', 'PASS', 'interrupting the master withdraws its pending card (AC17)'),
    Scenario('M7', 5, 'e2e_backend', 'happy-path', 'INP', 'spec O55 (allow and log at 3); spec audit records the level (feature-map C-4)', 'FAIL on the audit clause only (autonomy_level is 0)', 'level 3: no card, the call runs, and the audit says level 3 (C-4)'),
    Scenario('M8', 5, 'e2e_backend', 'edge-case', 'INP', 'product-contract (compose.py:498, level re-read per authorize) + spec D8', 'PASS', 'a level change between two calls of one turn applies to the second'),
    Scenario('M9', 5, 'e2e_backend', 'edge-case', 'INP', 'spec OP:1696-1701, D58', 'PASS', 'the gate matrix, every reachable cell'),
    Scenario('M10', 5, 'e2e_backend', 'error-handling', 'INP', 'spec D32 (a capability absent from the audience has no surface)', 'PASS', 'the master cannot call a tool outside its audience'),
    Scenario('M11', 5, 'e2e_backend', 'happy-path', 'INP', 'spec D31, O13', 'PASS', 'the wake summary opens the next turn at level 2 (AC4)'),
    Scenario('M12', 5, 'e2e_backend', 'edge-case', 'INP', 'spec D31 / O13; wake.py:10-12 ("level 3 drains when the stop happens")', 'FAIL (the only drain caller is the start of a user turn)', 'level 3: a stopped master-spawned session wakes the master immediately (C-2)'),
    Scenario('M13', 5, 'e2e_backend', 'edge-case', 'INP', 'spec D31 (only unfinished/error outcomes on master-owned sessions; needs_you never)', 'PASS', 'the wake set excludes what the spec excludes'),
    Scenario('M14', 5, 'e2e_backend', 'edge-case', 'INP', 'spec D31 (attempt < 2 along `retry_of`)', 'FAIL (no production path sets `retry_of`)', 'the retry cap refuses a third master retry, end to end (C-3)'),
    Scenario('M15', 5, 'integration', 'edge-case', 'UNIT', 'spec D31', 'PASS', 'the retry-cap logic works at its own seam'),
    Scenario('M16', 5, 'e2e_backend', 'edge-case', 'INP', 'spec OP:831 (records every allowed or denied action), D8, feature-map C-4', 'FAIL on `autonomy_level`; PASS on the rest', 'audit records are complete, include denials, and state the level (C-4, C-20)'),
    Scenario('M17', 5, 'e2e_backend', 'edge-case', 'INP-long', 'spec O55 (600 s)', 'PASS', 'an unanswered approval times out at 600 s (C-21)'),
    Scenario('M18', 5, 'e2e_backend', 'error-handling', 'INP', 'spec S8; D31 (the wake summary opens the first turn)', "FAIL on (b)'s reason text and on (c)", 'a failed turn is reported without internals, and the slot is freed'),
    Scenario('M19', 5, 'e2e_backend', 'edge-case', 'INP (last in its process)', 'spec M4 clause 20 (shutdown.py `withdrawn` docstring)', 'PASS', 'shutdown withdraws a pending card and says so'),
    Scenario('P10', 5, 'e2e_backend', 'happy-path', 'INP', 'spec D58, O39', 'PASS', "the master's project verbs at level 2"),
    Scenario('U1', 6, 'ui', 'happy-path', '', 'spec O1, O2, O3, O33', 'PASS', 'every root by mouse: exactly one visible, labelled, stubs honest'),
    Scenario('U2', 6, 'ui', 'edge-case', '', 'spec O2; derived (WCAG 2.1.1 keyboard) for the expand clause', 'PASS on nav; FAIL on the expand clause (`#mark` is a non-focusable span)', 'every root by keyboard; the collapsed rail can be expanded by keyboard'),
    Scenario('U3', 6, 'ui', 'happy-path', '', 'web-ui §2 (items 8, 9)', 'PASS (closes qa5 O7)', 'collapse and expand the rail by mouse; nav still works collapsed'),
    Scenario('U4', 6, 'ui', 'edge-case', '', 'web-ui §2 item 7; derived (WCAG 2.4.3 focus order) for the hidden-nav clause', 'PASS on open/navigate; FAIL on the hidden-nav clause', 'the phone drawer by touch'),
    Scenario('U5', 6, 'ui', 'error-handling', '', 'web-ui §1 (shell)', 'PASS', 'an error message shows and can be dismissed'),
    Scenario('U6', 6, 'ui', 'happy-path', '', 'spec O23 (U10, U1)', 'PASS', 'the legend: every key by hover, focus and click; every opener × closer; the phone sheet'),
    Scenario('U7', 6, 'ui', 'happy-path', '', 'spec O7, O8, O9, O10a, O24', 'PASS', 'bucket colours, glyphs and the new vocabulary'),
    Scenario('U8', 6, 'ui', 'edge-case', '', 'spec O21, O22; §0 rule 3 for the unreachable class', 'PASS', 'a card carries exactly four things; relative time classes'),
    Scenario('U9', 6, 'ui', 'happy-path', '', 'spec O20, O27, O28', 'PASS', 'drill to an attached session: header, banner, three panes'),
    Scenario('U10', 6, 'ui', 'happy-path', '', 'spec O25; spec inventory "type to pty" for the typing clause', 'PASS except the typing clause, FAIL (C-19)', "an owned session's live terminal; typing reaches the pane (C-19); the degraded path"),
    Scenario('U11', 6, 'ui', 'edge-case', '', 'spec O26 (labelled-and-inert kinds; a targetless `external`), O27; `signals/stop_rules.py:89-153` for the labels', 'PASS', 'next_actions in the header: all shown, labelled, inert where unbuilt'),
    Scenario('U12', 6, 'ui', 'happy-path', '', 'spec O26 ("honest [why?]")', 'PASS', 'the why-note'),
    Scenario('U13', 6, 'ui', 'edge-case', '', 'spec O29; derived ("Escape cancels to the current title"; "one intent, one request")', 'PASS on rename; FAIL on the stale-Escape and double-Enter clauses', 'rename by click-to-edit, and its edge cases (AC6)'),
    Scenario('U14', 6, 'ui', 'edge-case', '', 'spec O30 (U11; DCS:75-91)', 'PASS on rendering; FAIL on the choose clause', "the needs-you decision card shows the engine's choices, and choosing one answers it (C-18)"),
    Scenario('U15', 6, 'ui', 'happy-path', '', 'spec O34, O35, O37', 'PASS', 'the Projects list and detail'),
    Scenario('U16', 6, 'ui', 'edge-case', '', 'spec D57, S10; web-ui §2 items 41-45', 'PASS', 'create a project: name classes, Cancel, Escape, duplicate (AC7)'),
    Scenario('U17', 6, 'ui', 'edge-case', '', 'web-ui §2 item 47; derived ("a retried save does not re-send a step that succeeded")', 'PASS on the edit; FAIL on the partial-save clause', 'edit a project; a partial save does not repeat the rename (AC8)'),
    Scenario('U18', 6, 'ui', 'edge-case', '', 'web-ui §2 items 48-50; derived (a refused removal is shown; one click, one add)', 'PASS on add/remove; FAIL on the refused-remove clause', 'repo paths in the edit dialog (AC9)'),
    Scenario('U19', 6, 'ui', 'edge-case', '', 'spec D61, O36; web-ui §2 items 51-56', 'PASS', 'delete dialog: every choice (AC10, AC11)'),
    Scenario('U20', 6, 'ui', 'edge-case', '', 'derived (a stale view does not offer live actions on a deleted entity; no crash)', 'PASS on the list update; the stale-detail clause recorded', 'delete in one tab, act in another (AC12)'),
    Scenario('U21', 6, 'ui', 'edge-case', '', 'spec O34 (U14)', 'PASS; the new-tab result recorded as a finding (no deep links)', "a project's session link opens it in the Flock (AC13)"),
    Scenario('U22', 6, 'ui', 'happy-path', '', 'spec O5, O14, O18', 'PASS', 'Settings: all ten sections'),
    Scenario('U23', 6, 'ui', 'happy-path', '', 'spec O15, O16, O17 (D65, U12)', 'PASS', 'the autonomy toggle lives only in Settings'),
    Scenario('U24', 6, 'ui', 'error-handling', '', 'spec S8 (a literal plus a correlation id reaches the browser); derived for Settings specifically', 'FAIL (the refusal is silent)', 'a refused or unreachable autonomy change is visible'),
    Scenario('U33', 6, 'ui', 'edge-case', '', 'spec O44 (no `<noscript>`, admitted), O46', 'PASS on "claims nothing false"; the empty frame recorded as the admitted finding', 'with JavaScript off, the page claims nothing false'),
    Scenario('U34', 6, 'ui', 'edge-case', '', 'spec O43; O23 ("on a narrow screen the sheet rises from the bottom"); app.css:2472-2484 (the only thing the 600 px rule changes is `dialog.sheet`); derived (44 × 44 px touch targets, patterns #12) for the target clause', 'PASS on overflow/console/sheet; the target clause recorded per control', 'every root at four widths: no sideways scroll, no console errors, touch targets; the legend sheet at 600/601'),
    Scenario('U35', 6, 'ui', 'edge-case', '', 'spec O20, O34 (U9, U14); app.css:1962 (`.panes2`) and 2050-2078 (the shell block: rail → off-canvas drawer, `#drawer-open` shown, `.thread`/`.bubble` restyled)', 'PASS', 'the 760/761 breakpoint: the shell drawer on every root, one or two panes on Projects and Settings'),
    Scenario('U36', 6, 'ui', 'edge-case', '', 'spec O20', 'PASS', 'the 900/901 breakpoint on the Flock'),
    Scenario('U37', 6, 'ui', 'happy-path', '', 'spec O20', 'PASS', 'phone drill-down on every page by touch (AC15)'),
    Scenario('U41', 6, 'ui', 'edge-case', '', 'derived (WCAG 2.4.3)', 'FAIL (`replaceChildren` drops focus)', 'keyboard focus survives a list rebuild'),
    Scenario('U42', 6, 'ui', 'edge-case', '', 'spec S10', 'PASS', 'user text is shown as text everywhere'),
    Scenario('U43', 6, 'ui', 'edge-case', '', 'spec O5', 'FAIL in Settings (object-valued audit args or discovery fields, web-ui risk 5)', 'nothing renders as `[object Object]`, `undefined` or `NaN`'),
    Scenario('U44', 6, 'ui', 'edge-case', '', 'spec O6', 'PASS', 'dark only, whatever the OS asks for'),
    Scenario('U45', 6, 'ui', 'edge-case', '', 'spec O27 (the header shows the bucket chip and why)', 'FAIL (the header changes only on a re-click)', "the session header follows the session's state"),
    Scenario('U25', 7, 'ui', 'edge-case', 'INP', 'web-ui §2 items 12-14; derived for whitespace, IME and double-send', 'PASS on (1)-(3), (6); FAIL on (4), (5), (7)', 'the composer: text classes, keys, double send'),
    Scenario('U26', 7, 'ui', 'happy-path', 'INP', 'spec O5, O11', 'PASS on the order; FAIL on the step-detail clause if the detail is an object', 'a turn renders line by line with expandable tool steps'),
    Scenario('U27', 7, 'ui', 'happy-path', 'INP', 'spec O12', 'PASS on approve; the "leaves every position" clause may FAIL (the code removes the buttons, not the card)', 'approve through the card (AC1)'),
    Scenario('U28', 7, 'ui', 'happy-path', 'INP', 'spec O12', 'as U27', 'reject through the card (AC2)'),
    Scenario('U29', 7, 'ui', 'edge-case', 'INP', 'orchestration §1 (compare-and-set); derived (the UI reports the decision the user made)', 'PASS on single decision; the status text recorded', 'a double click on Approve decides once (AC3)'),
    Scenario('U30', 7, 'ui', 'edge-case', 'INP', 'derived (one approval, one card in its position — O12)', 'FAIL (no de-duplication)', 'a card is shown once when the load read and the stream both carry it'),
    Scenario('U31', 7, 'ui', 'happy-path', 'INP', 'spec D8, D65, O55', 'PASS', 'flipping autonomy changes whether a card appears (AC16)'),
    Scenario('U32', 7, 'ui', 'happy-path', 'INP', 'spec O13', 'PASS', 'the wake summary through the UI (AC4)'),
    Scenario('U38', 7, 'ui', 'error-handling', '', 'spec O46 with the feature map\'s declared oracle (not `live` after > 2 × keep-alive = 30 s); derived for "dead ≠ empty"', 'FAIL on both (BC-2; web-ui risk 2)', 'a stopped daemon is never shown as live or as an empty fleet'),
    Scenario('U39', 7, 'ui', 'edge-case', '', 'spec O42', 'FAIL (the old Last-Event-ID filters the new events)', 'a page open across a daemon restart keeps up (AC14, C-9)'),
    Scenario('U40', 7, 'ui', 'error-handling', '', 'web-ui §1 (`#stream-status` has an `unreadable` state); derived ("reconnecting" forever is not an honest status for a permanent 403)', 'FAIL', 'a permanently refused stream says so'),
    Scenario('U46', 7, 'ui', 'edge-case', 'INP', 'spec D54, O12', 'PASS on the late click; the "card leaves" clause as U27', 'a withdrawn card leaves the page and a late click says so (AC17)'),
    Scenario('R1', 7, 'ui', 'edge-case', '', 'derived (the counts shown agree with the cards shown)', 'FAIL', 'loadFleet never applies half of a refresh'),
    Scenario('R2', 7, 'ui', 'edge-case', '', 'spec O16 ("shows the current level and changes it"); derived (the last click is the intent)', 'FAIL', 'the last autonomy click wins'),
    Scenario('R3', 7, 'ui', 'edge-case', '', 'spec O41 (the race class); derived for rename', 'FAIL', 'a rename reply never paints into another session'),
    Scenario('R4', 7, 'ui', 'edge-case', '', 'spec O41; derived', 'FAIL', "an old project's paths never appear in another's edit dialog"),
    Scenario('R5', 7, 'ui', 'edge-case', '', 'derived (a click on a visible, enabled button takes effect)', 'FAIL', 'a list refresh never swallows a click on Edit (DUP-2)'),
    Scenario('R6', 7, 'ui', 'edge-case', '', 'spec O41', 'PASS', 'regression: a slow session read never paints over the newer one (BC-1 / DUP-1)'),
    Scenario('R7', 7, 'ui', 'edge-case', '', 'spec O41', 'PASS', 'regression: a slow project read never paints over the newer one'),
    Scenario('L1', 8, 'ui', 'happy-path', 'LIVE-A', 'spec O11, D10', 'PASS', 'a real master turn with the default model, through the UI'),
    Scenario('L2', 8, 'ui', 'happy-path', 'LIVE-A', 'spec O12, O55', 'PASS (the "card leaves" clause as U27)', "approve a real master's destructive call through the UI"),
    Scenario('L3', 8, 'e2e_backend', 'edge-case', 'LIVE-A', 'spec D10', 'PASS', 'the master resumes its conversation across turns'),
    Scenario('L4', 8, 'e2e_backend', 'happy-path', 'LIVE-A', 'spec S13, OP hook lane', 'PASS', 'a real `claude` fires the installed hooks into sessiond'),
    Scenario('L5', 8, 'e2e_backend', 'happy-path', 'LIVE-A', 'spec OP §9; DCS (refuse to auto-answer the trust dialog); D47', 'PASS', 'a real owned session: trust dialog, ready, idle, and the real sidecar'),
    Scenario('L6', 8, 'ui', 'edge-case', 'LIVE-A', 'spec O30', 'PASS on rendering; FAIL on the choose clause; PASS on the HTTP positive control', 'a real permission dialog as a decision card, and choosing in the UI (C-18)'),
    Scenario('L7', 8, 'e2e_backend', 'happy-path', 'LIVE-A', 'spec O51 (D44, D45), O52', 'PASS (the macOS mid-turn `UNREADABLE → REFUSE_NO_PTY` rule recorded if it fires)', 'mailbox delivery to a real session: send now, clear then send, queue'),
    Scenario('L8', 8, 'e2e_backend', 'happy-path', 'LIVE-A', 'spec O53', 'PASS', 'ask forks the real engine'),
    Scenario('L9', 8, 'e2e_backend', 'edge-case', 'LIVE-A', 'spec O29, D29', 'PASS', 'renaming a real owned session is local-only and sticks'),
    Scenario('L10', 8, 'e2e_backend', 'edge-case', 'LIVE-A', 'spec O56 (D42)', 'PASS', "the real master has no tools but Shepherd's"),
    Scenario('L11', 8, 'e2e_backend', 'error-handling', 'LIVE-B', 'spec S8', 'FAIL (`master.error` carries `repr(error)`)', 'a real master failure reaches the page without internals'),
    Scenario('Z1', 9, 'e2e_backend', 'edge-case', 'HOST', "U2; S0's mode rules", 'PASS', "the user's Claude settings and projects are as they were"),
    Scenario('Z2', 9, 'e2e_backend', 'edge-case', 'HOST', 'CLAUDE.md tmux rules; spec S7; D49', 'PASS', 'tmux: nothing but our own sockets was touched, and ours are gone'),
    Scenario('Z3', 9, 'e2e_backend', 'edge-case', 'HOST', 'R1', 'PASS', 'port 8787 untouched; nothing left running'),
)

BY_ID: Final[dict[str, Scenario]] = {scenario.id: scenario for scenario in SCENARIOS}


def wave_ids(wave: int) -> tuple[str, ...]:
    return tuple(scenario.id for scenario in SCENARIOS if scenario.wave == wave)
