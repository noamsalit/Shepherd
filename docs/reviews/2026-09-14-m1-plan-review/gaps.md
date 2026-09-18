# Shepherd M1 plan: workability gaps

2026-09-14

## Bottom line

**The plan is workable only with conditions.** No blocker survived. It can be built, and its M1 schema, storage boundary and hookd contract all match live readings. It is not workable as written, though, because rework is already built in, for three main reasons:

1. **The logical architecture is not in the spec.** As a result, the plan's layout and import rules follow no layering. The web/cli reads go straight to Store and are labelled "stable". The Claude Code vocabulary sits outside the EngineAdapter seam.
2. **Several fold rules rest on a partial probe that live readings contradict.** Examples are StopFailure, task-notification prompts that overwrite the brief, and needs_you after a denied permission. That probe data exists only in /tmp.
3. **Internal logic gaps would ship ghost sessions and a stale footer.** The sweep branch can never run, engine_proc is kept only in memory, and the sessiond construction order cannot be built.

## How this was reviewed

- **Angles:** arch-in-spec, plan-vs-architecture, plan-vs-spec, plan-internal, probe-hooks, probe-transcripts, probe-env-provenance.
- **Live probes:**
  - claude 2.1.270: headless `-p` hook captures, plus schema and call-site reads of the binary
  - scans of ~/.claude/projects transcripts
  - SQLite 3.45.1 DDL runs and a Python 3.12.3 venv with mypy
  - no tmux or TUI runs
- **Refutation:** every finding went through an adversarial skeptic pass. 8 findings were refuted and dropped, and many were downgraded.
- **Evidence:** `docs/reviews/2026-09-14-m1-plan-review/evidence/`. Paths below are relative to that folder. `plan:` means `docs/plans/2026-09-13-m1-foundation-visibility-plan.md` and `spec:` means `docs/specs/orchestrator-platform.md`.

**Counts:** 0 blockers, 23 major, 43 minor.

## 1. Real-life data and schema alignment

| ID | Sev | Gap | Evidence | Why it matters |
|---|---|---|---|---|
| G1 | major | The raw hook-payload data behind Ground Truth 1-4 is not in the repo, nor are the T09 fixtures, T11 `PROBE_ACCEPTED_EVENTS` or the tmux spike captures. It exists only in other sessions' /tmp scratchpads, and the plan gives no path to it. | plan:74, 1106, 1542; probe-env-provenance-skeptic/verifier-checks.txt (tmpfiles `D /tmp 30d`, git ls-files) | Named build inputs can vanish, and the Ground Truth cannot be re-checked from the repo. |
| G2 | major | Background-task completions fire UserPromptSubmit with a `<task-notification>` prompt. The fold writes that prompt into brief and title, so PD-10's claim that the brief "equals the transcript's lastPrompt" is false. | plan:165, 415; probe-env-provenance-skeptic/run4-task-notification-brief.txt; probe-hooks/run1-events.jsonl | Core M1 card text is overwritten with XML. |
| G3 | major | M1 does not register StopFailure. Claude Code fires StopFailure instead of Stop on API errors, prompt_too_long and exhausted malformed tool use, so the session stays "running". | plan:123 (DV-04), 424-425; probe-hooks-skeptic/skeptic-rechecks.txt (every StopFailure call site returns from the query loop) | Interactive sessions show running for up to 3 h. |
| G4 | major | After an unapproved PermissionRequest the session keeps working, but the fold holds needs_you until Stop. A later, unrelated call to the same tool clears it spuriously. | plan:415-420; probe-hooks-skeptic/skeptic-rechecks.txt (run1 10:13:57, 10:14:09) | The top-of-fleet signal is wrong in both directions. |
| G5 | major | Ground Truth 2 says PostToolUseFailure and StopFailure "never fired", but both fire on 2.1.270. The M2 precondition then tells the next plan to treat them as unknown. | plan:91, 189, 418; probe-hooks/run2-events.jsonl; probe-hooks/v7-stopfailure-shell.txt | A "ground truth that overrides the spec" is an artefact of what the probe provoked. |
| G6 | major | PD-09 treats background subagents as "honestly unknown", yet transcripts record their completion as task-notification entries with a `<status>`. Nested agents' results live in the parent agent's transcript. | plan:164; probe-transcripts/subagent-state-scan.txt; probe-transcripts/existing-meta-json.txt | Most real subagents on this host would show unknown. |
| G7 | major | The spec's hook facts are wrong, and the uncommitted edits did not correct them. Wrong names: `StopFailure.error_type` (real: `error`), `Stop.stop_reason` (absent), `end_reason` (real: `reason`), `start_reason` (real: `source`, with `fork`). The "common fields on every event" list is also false. | spec:399, 778-780, 800, 811-819, 1051, 2168; probe-hooks/binary-sdk-hook-input-schemas.txt; probe-hooks/field-matrix-observed.txt | M2 planners read the spec as law and would key logic on fields that do not exist. |
| G8 | major | The spec's D2 and §5 still say macOS .pkg, launchd, Keychain and TypeScript/tsc. The user-approved Linux decision is recorded only in untracked .cc10x memory and plan DV-01/DV-02. | spec:105, 256-260, 1895; .cc10x/activeContext.md:22-26; probe-env-provenance-skeptic/verifier-checks.txt (0 hits for linux or systemd) | The "law" contradicts the plan on the platform and the toolchain. |
| G9 | minor | Transcript `lastPrompt` is a whitespace-collapsed preview of about 200 characters ending in "…", yet the spec and PD-10 use it as the brief. | spec:513; plan:165, 1553, 1605; probe-transcripts/lastprompt-truncation.txt | Sessions first seen without a prompt store a clipped brief. |
| G10 | minor | Plan payload details are wrong: `source` omits `fork` (and A10 omits the observed `resume`), SubagentStart has no `agent_transcript_path`, and plan:189 says `error_type`. | plan:90, 148, 182, 189; plan-vs-spec-skeptic/rechecks.txt | The errors carry into M2 and M3 plans. |
| G11 | minor | Workflow subagents live under `subagents/workflows/wf_<id>/` with a journal.jsonl, and their meta has no toolUseId. Ground Truth 5 and T10 do not cover this shape. | plan:95-96, 1606; probe-env-provenance-skeptic/verifier-checks.txt | Subagent listing misses these agents or cannot classify them. |
| G12 | minor | "77 events in 4 runs" comes from a partial copy of an 89-event, 5-run probe. The missing run4 holds the only populated `background_tasks` (a shell task) and the only auto-revive after Stop. | plan:83, 424; probe-env-provenance/event-counts-backup.txt; probe-env-provenance/event-counts-32df7fce.txt | Fixtures copied from that partial set miss both cases. |
| G13 | minor | PermissionDenied fires only on auto-mode classifier denials, so DV-07's defensive use of it never covers human or rule denials. | plan:126, 418; probe-hooks/binary-permissiondenied-callsites.txt | The rationale rests on an event that cannot occur (see G4). |
| G14 | minor | In `-p` runs that exit on an error, the Python hook dispatched at shutdown dies (status 1, no trace), so StopFailure and SessionEnd are lost. This is inferred, not observed as a signal. | probe-hooks/v8-trace.txt; probe-hooks/v8-debug-hooklines.txt; probe-hooks/v7-stopfailure-shell.txt | Headless error exits depend on the /proc sweep only. |
| G15 | minor | Ground Truth 10 overstates settings validation. The silent ignore applies only to `-p` mode, invalid hook subtrees did not void the file, and the installer detects only invalid JSON. | plan:109, 123, 1631; probe-env-provenance/claude-help-2.1.270.txt; probe-hooks/v2/v3/v6-events.jsonl | The L02 ladder guards a mode that did not reproduce. |
| G16 | minor | "Notification never fires" rests on `-p` runs only. M1 does not register Notification, so no T19 TUI check can disprove it. | plan:123, 126, 1980; probe-hooks/binary-notification-types.txt | The idle and quota degrades stay permanently unverified. |
| G17 | minor | The slug rule is wrong for long cwds: Claude Code truncates the slug and appends a hash. | plan:94, 1602; probe-transcripts/slug-long-unicode-check.txt | A rule marked "verified" is false. |
| G18 | minor | API-error and synthetic assistant entries carry model `<synthetic>`, which parse_signals turns into a ModelSignal. | plan:1605; probe-transcripts/existing-transcripts-analysis.json | Rate-limited or logged-out sessions show model `<synthetic>`. |
| G19 | minor | Title facts are incomplete: `--name` writes custom-title, named sessions get no ai-title, hooks carry `session_title`, and a custom-title.json sidecar exists. | plan:87, 144; probe-transcripts/hook-captures.jsonl | Named and Remote Control sessions show their launch name. |
| G20 | minor | DV-30 maps SessionStart `compact` to running, but 2 of the 3 observed compactions were manual `/compact` at the prompt. | plan:148, 414; probe-transcripts/compaction-entries.txt | An idle session may show running (conditional). |
| G21 | minor | The entry and meta shapes in Ground Truth 5-6 are incomplete, with many unlisted types and optional fields. The "18 transcripts" figure is a raw `find` count, not a curated sample. | plan:96-100; probe-env-provenance/origin-of-18-transcripts.txt; probe-transcripts/existing-transcripts-analysis.json | Fixtures will not exercise missing-field cases. |
| G22 | minor | The spec says `pr_url` is "free" from `pr-link` entries, but no such entry exists on this host. | spec:530; plan:127 | M2+ plans inherit an unproven data source. |
| G23 | minor | An interactive claude 2.1.269 binary is still running here, while the plan and T19 assume 2.1.270. | plan:83, 1896; probe-env-provenance-skeptic/verifier-checks.txt | Version drift is already live among attachable sessions. |
| G24 | minor | `mypy>=1.13` has no upper bound or lock, and today it resolves to 2.3.1. | plan:1269, 1278; probe-env-provenance/venv-getpip-mypy-probe.txt | Every task's gate depends on the resolution date. |

## 2. Plan coherence and adherence to the logical architecture

| ID | Sev | Gap | Evidence | Why it matters |
|---|---|---|---|---|
| G25 | major | M1's read routes take `Store` and `EngineAdapter` directly and are labelled "stable (read API)". DV-17 and the M4 precondition schedule only the mutating routes for the registry, and the spec gives no interim rule for M1-M3. | plan:136, 207, 1215, 1804; spec:1344-1347, 2083, 2086 | The named risk, a private read path below L4, is planned as permanent. |
| G26 | major | Claude Code hook names and fields live in `ingest/events.py` and `ingest/fold.py`, outside EngineAdapter. The engine must match ingest's CONSUMED_EVENTS, and the Protocol has no normalizer, a gap it inherits from spec §6. | plan:311, 1053-1067, 1123-1133, 1681; spec:287-296; plan-vs-architecture/03-claude-code-vocabulary-outside-adapter.txt | Swapping the engine means rewriting ingest and the fold, which breaks the crucial decoupling requirement. |
| G27 | major | No import rule enforces the consumer boundary for web/, cli/ or controld HTTP, and none enforces downward-only imports. R9 covers only master/, which is vacuous in M1, and cli imports daemon and engine modules. | plan:379-394, 1871; plan-vs-architecture/05-import-rules-vs-boundaries.txt | One of the two mandated boundaries is not a failing test. |
| G28 | major | The package layout follows processes and loose files (domain/, ingest/, ipc/, platform/, controld/, sessiond/), not the five layers. There is no signals/ package, although the spec names `signals/verdict.py`. | plan:321-375; spec:138, 866; plan-vs-architecture-skeptic/skeptic-rechecks.txt | No layer test can be written, and M2-M4 must relocate modules. |
| G29 | major | `engine_proc` lives only in sessiond memory, and needs_you is never aged out. After a sessiond restart, on macOS, or if A2 fails, a dead needs_you session stays needs_you forever. | plan:138, 404, 438-440, 1074, 1474, 1928 | Ghost rows pin the top of the fleet with no recovery. |
| G30 | major | Sweep rule 1's at-prompt branch can never run, because the sweep visits only `list_live_sessions()` (starting, running, needs_you), yet B1 is recorded as fixed. | plan:438, 1002, 1722, 2052 | Sessions killed while idle stay "at prompt" as ghosts. |
| G31 | major | The fleet footer (sessiond link, gated state, counters) is filled only from snapshots. No SSE event carries it, and polling is forbidden. | plan:729, 761, 765, 1171-1173, 1827, 1834 | A dead daemon and unknown counts go unseen, which undercuts principles 4 and 5. |
| G32 | major | The SSE event stream (M1) and the CLI `replay` and `recompute` commands, which rewrite session columns, are specified but are not tools. | spec:152, 545, 973, 1325-1331, 1480-1531, 1855-1874 | L4 cannot be the only path, so erosion starts in M1. |
| G33 | major | The spec lists queue workers (L3) as consumers that must pass authorize(), but its worker code calls writeback and spawn directly. | spec:1184, 1210-1225, 1261-1272 | It is either an upward import or a chokepoint bypass (lands in M5). |
| G34 | minor | PD-02 makes sessiond the fold host and a DB writer, while spec §5 draws Signals and SQLite inside controld. The plan records this as a planner decision, not a deviation. | plan:152, 157, 299; spec:199-216 | Where M2 classification runs is decided implicitly. |
| G35 | minor | Stop clears a pending needs_you, which reverses the spec's "needs_you outranks stopped", and no deviation entry records it. | spec:786, 791-792; plan:424, 1566 | A pending background-subagent prompt is hidden. |
| G36 | minor | SessionStart(`compact`) on a needs_you session nulls the reason without changing the state, which violates the plan's own CHECK invariant. | plan:410, 414, 429; plan-internal/check_ddl.out | The P06 property test can trip. |
| G37 | minor | Extra Protocols (ProcessProbe, ServiceSupervisor) sit outside the six seams. ProcessProbe has no contract suite, and its Darwin driver ignores starttime. DV-14 does not count `accept_transcript_path`. | plan:133, 834, 843, 1127, 1335, 1343 | Seam growth and drift are indistinguishable. |
| G38 | minor | The plan calls /proc "Wrapped (platform seam)", but hookd reads `/proc/<pid>/stat` directly. | plan:138, 311, 385, 736 | Porting liveness means editing hookd, not just a driver. |
| G39 | minor | The Store entry points and migrations are SQLite-shaped at the boundary (`db_path`, .sql files, sqlite3-only R1). | plan:381, 672-675, 977-991, 1749 | A database swap touches daemon wiring and platform paths. |
| G40 | minor | R9 lets all of master/ import `claude_agent_sdk`, not just the AgentSDKMaster implementation. | plan:389; spec:133, 1392-1393 | A vendor SDK is allowed into vendor-neutral master logic. |
| G41 | minor | `last_malformed_lines` exists only on the concrete ClaudeCodeEngine, while IngestService holds the Protocol. | plan:1036, 1137, 1148 | The counter needs a downcast that leaks the seam. |
| G42 | minor | As specified, `config.py` and `platform/base.py` import each other. | plan:833, 850, 857; plan-vs-architecture/06-config-platform-import-cycle.txt | The builder must improvise. |
| G43 | minor | The spec calls `tmux -L shepherd` a "dedicated socket", but the user's live sessions run there, and the default profile uses it. | spec:984; CLAUDE.md:28-29; plan:1332; plan-vs-spec/tmux-shepherd-socket-reading.txt | The "dedicated" premise is false on this host. |
| G44 | minor | The tmux-safety text contradicts itself in three ways. T19 uses bare `-t name` instead of the spike's `=<name>:` rule. T02 forbids tmux, yet it runs `tmux -L shepherd ls`. M3 re-schedules probes the spike already passed. | plan:32, 197-202, 1338, 1351, 1904-1907; docs/probes/2026-09-13-tmux-tui-spike.md | The rules that exist to prevent the incident disagree. |
| G45 | minor | Background-subagent events with the parent's prompt_id arrive after Stop. DV-28 drops the early ones and revives the parent on later ones, but cites only a MessageDisplay race. | plan:147; probe-hooks-skeptic/skeptic-rechecks.txt (run1 10:14:12-14) | This behaviour is undescribed and untested. |
| G46 | minor | The uncommitted spec edit says D14 owns the `shepherd_<id>` naming, but the D14 row does not. The plan also calls these uncommitted edits "approved". | spec:117; plan:13; plan-vs-spec/spec-diff.patch | The decision log and the prose disagree. |
| G47 | minor | The browser terminal WS path goes to sessiond and the pty, skipping authorize() and the audit log, and is never reconciled with "no second path". | spec:999-1002, 1020-1023, 1596-1598 | An ungated write path is undocumented as an exception (M3). |
| G48 | minor | The spec shows two audit writers, denials are never logged, and it cites an `action_log` that is not a table. | spec:682, 814, 1317, 1575-1590, 1898 | The single, complete audit property is not what the spec's code shows. |
| G49 | minor | The master import rule is stated as both an allowlist and a denylist, while the config in the same section uses authorize and state directly. | spec:1374-1396 | The isolation test's scope is guesswork. |
| G50 | minor | The wake set (L3) "wakes the master (L5) immediately", with no mechanism that avoids an upward call. | spec:132, 1100, 1104 | The obvious implementation breaks the downward-only rule (M4). |

## 3. Is the logical architecture in the spec?

**No.** The user's suspicion is confirmed.

| ID | Sev | Gap | Evidence | Why it matters |
|---|---|---|---|---|
| G51 | major | The spec never defines the five layers, their modules or a source layout. The only trace is a dangling "three L5 siblings", and §0 excludes any file layout. | spec:35, 1347; arch-in-spec/skeptic-recheck.txt | Nobody can tell where code belongs, and the plan invented its own tree. |
| G52 | major | The rule that dependencies point down only is absent. The only import rules are D19 (master/) and D26 (DB drivers). | spec:122, 130, 414, 1393-1395; arch-in-spec/spec-term-grep.txt | Upward imports break no written rule. |
| G53 | major | The consumer boundary is written and tested for master/ only, with no rule or test for web/ or cli/. | spec:1344-1347, 1392-1396, 2038-2041 | The named risk has no written guard. |
| G54 | major | The spec never says which layers run in controld versus sessiond, or which process folds hook events and writes session columns. | spec:199-216, 236-238, 712-713; plan:157 | The plan settled the process split itself, and nothing checks it. |
| G55 | major | The runtime-swap vs edit-time-swap rule is absent. Principle 3 ("everything pluggable, one interface") reads against D26/D33's deliberate lack of a Store Protocol. | spec:130, 153-154, 267-268, 443-449; plan-vs-spec-skeptic/rechecks.txt | The crucial decoupling rule cannot be applied or reviewed. |
| G56 | minor | The storage-boundary test is only implied ("same test as D19"), and §14 and M4 describe that test as master-only. | spec:130, 2038-2041, 2086 | Read literally, enforcement lands in M4 (the plan's R1 covers M1). |
| G57 | minor | Contract suites and Scripted* doubles are named for 4 of the 6 seams. ModelProvider and Credentials have neither. | spec:301-311, 1981-1991 | Invariant 4 is written incompletely. |
| G58 | minor | The §5 diagram draws Orchestrator (L5) as a peer of Signals and Queues and shows no web/ or cli/. | spec:195, 199-211 | It teaches a dependency picture different from the reference. |

## Other

| ID | Sev | Gap | Evidence | Why it matters |
|---|---|---|---|---|
| G59 | major | The sessiond construction order cannot be built. WriterLoop needs IngestService, which needs an open Store, but WriterLoop starts gated before the Store may open. | plan:1147-1158, 1697, 1700, 1962 | The workaround either changes signatures or weakens the no-unmigrated-DB guarantee (P04). |
| G60 | minor | T14 imports `shepherd.controld.http`, which T15 creates later, so T14 fails its mypy gate. | plan:1256, 1754; plan-internal/t14_mypy_forward_import.out | The builder must improvise at T14. |
| G61 | minor | The test profile uses `http_port` 0, but no signature reports the bound port back to StackHandle or the CLI tests. | plan:1194-1196, 1230-1232, 1332, 1865 | This is an undeclared port channel. |
| G62 | minor | `create_token` uses O_CREAT\|O_EXCL, but it must also replace the existing file atomically on each boot. | plan:686, 1521 | Taken literally, regeneration raises FileExistsError. |
| G63 | minor | The self-review calls the mechanical re-check "clean", but that check covers Consumes lines only, and revision 2 has had no fresh review. | plan:6-9, 562, 2077; plan-internal/check_hidden_refs.out | The "buildable without improvisation" claim is overstated. |
| G64 | minor | E07, E41 and E47 have no named test in their assigned tasks, and risk row R02 cites a test that no task defines. | plan:466, 476, 510, 515, 1990 | The coverage claim is inaccurate. |
| G65 | minor | Small holes and inconsistencies (full list below). | plan:142, 316, 328, 766, 769, 776, 780, 1799; plan-internal/check_ddl.out | Build-time choices pile up, and the P09 proof weakens. |
| G66 | minor | The plan gives no effort estimate and does not reconcile its size (21 tasks, 309 tests) with the spec's M1 estimate of 4-6 days. | spec:2083; plan-internal/scale_and_refs.out | A likely overrun is never recorded. |

G65 covers these holes and inconsistencies:
- The heartbeat interval cannot be injected.
- The `vcs_remote` body field is missing.
- There are no projection or key tests for the workspace and health routes.
- An S3 cross-reference points to the wrong contract.
- EXIT_UNAVAILABLE is not in the module layout.
- The `transcript_path_rejected` counter is not in the observability list.
- The WorkspaceView count keys do not match the state labels.
- DV-23's time CHECKs are weaker than claimed.

## Verified aligned

- **M1 schema:** the 0001 DDL applies on SQLite 3.45.1 with the plan's own splitter, and foreign_key_check is clean. It creates four tables, matching spec §16, and the Session dataclass matches all 38 columns (plan-internal/check_ddl.out).
- **Storage boundary is a failing test:** R1 and R3 plus the API-surface introspection test. Store verbs return frozen dataclasses with transactions kept internal, per D33 (plan:381-383, 985-1008, 1484).
- **hookd contract:** 250 ms deadline, `try/except BaseException`, `os._exit(0)`, no stdout, and a daemons-down test (plan:731-740, 1886; spec:742-757).
- **Migrations:** controld migrates and sessiond never does, backed by R2 and `test_never_migrates_unmigrated_db`. Sockets are mode 0600 and the runtime dir 0700, with a constant-time token compare (plan:382, 688-705, 1727).
- **Hook fields on 2.1.270:** Stop has no stop_reason, PermissionRequest has no tool_use_id, effort is an object, and resume keeps session_id. Ancestry is python3 ← sh ← claude, and no payload carries a timestamp (probe-hooks/field-matrix-observed.txt).
- **Settings shape:** DV-04's group shape and the `_shepherd_managed` marker are accepted in `-p` at project scope (probe-hooks/run0-settings.local.json; probe-env-provenance/live-hooks-run2marker.jsonl).
- **Transcript layout:** the path and normal-cwd slug hold, the Agent-tool subagent layout holds, `--resume` keeps the same file, and isSidechain appears only in subagent files (probe-transcripts/slug-check.txt; run2-pre-linecount.txt).
- **Host environment:** Python 3.12.3 and sqlite 3.45.1. No system mypy, pytest or node. venv plus get-pip works. systemd --user is running with Linger=no (probe-env-provenance/env-readings.txt).
- **M1 scope matches spec §16:** attached-only, read-only UI, registry deferred to M4, D34 LLM lane deferred, SSE without polling (plan:35-46, 454-464; spec:2083-2086).
- **What the spec does state:**
  - the six Protocol seams, including MasterRuntime.configure and MasterCapabilities
  - D19, D26, D32 and D33
  - the controld/sessiond split over 0600 Unix sockets
  - Scripted* doubles as peers in testkit/
  - principle 1

  (spec:130-138, 145-148, 188-232, 266-371, 1890, 1988-2037)

## Not covered

- **TUI and interactive behaviour** (tmux was prohibited): hook parity (A1), Notification, manual `/compact`, interactive settings validation and continuation after a deny.
- **macOS drivers** (launchd, Keychain, Darwin ProcessProbe): no macOS host was available.
- **Unprovoked hook behaviour:** StopFailure's rate-limit and auth variants were not provoked live, and the shutdown kill of the Python hook is inferred, not observed.
- **Transcript cases with no sample:** hooks from workflow subagents, nested foreground subagents and `pr-link` entries.
- **Imports are unobserved:** the project has no source code, so every import and boundary finding is about plan text.
- **Deliberate vs accidental omissions:** the design conversation was not available, so the spec's omissions cannot be sorted into deliberate and accidental.
- **Not fully re-checked:** spec §10, §11 beyond the tool surface, §17 and §19; systemd behaviour; the 309-test count; the mypy strict-flag sample (its source was not saved).
