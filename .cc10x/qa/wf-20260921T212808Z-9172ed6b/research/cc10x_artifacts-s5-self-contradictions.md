# `cc10x_artifacts` lane — §5 Contradictions INSIDE the artifact state
These are single-source contradictions: no cross-lane comparison catches them, and the
single-source researcher is the only agent positioned to see them at all.

1. **`updated_at` predates its own records.** json:830 says 18:25:40Z, but `scope_amendment.at` is
   18:35:12Z and the last `status_history` entry is 19:55:24Z. The file records events after it
   claims to have last been written.
2. **`plan_revision` disagrees with itself.** json:685 `plan_revision: 5`, :686
   `last_reviewed_revision: 5`, but :610 `scope_amendment.plan_revision: 6`.
   **=> Revision 6 — the QA acceptance-surface amendment — is UNREVIEWED by that count.**
3. **Phase/task counts, four numbers, three disagreeing.** activeContext.md:7-8 says "11 phases,
   29 tasks, 24 acceptance clauses"; `results.planner` says 10 / 31 / 28; `normalized_phases` holds
   10; events.jsonl:8 says 10. json:337 already records this as a standing habit:
   *"Fourth stated count in this plan to disagree with its source."*
4. **Phases 2, 4 and 10 have no `phase_status` entry at all** — yet acceptance clauses depend on
   them and `integration: completed` plus four QA rounds ran on top. Recorded absent; the history
   says the work landed.
5. **Frozen node-id count 1482 vs 1480.** activeContext.md:30-31 says 1482 (`wc -l`); the approved
   router correction at json:32 says **1480** (`grep -c '::'`). The activeContext line was never
   corrected.
6. **Retirements fifteen vs seventeen.** activeContext.md:32 says fifteen;
   `results.planner.retirements: 17`; F1 calls one of them "a 17th retirement".
7. **Bucket count seven vs eight.** progress.md:39 says "the 7-bucket palette"; report-qa3.md:340
   seeds seven; U1 says the sheet explains "all eight"; report-qa3.md:341 says the sheet has 8 rows;
   patterns.md:386-391 says `--b-text` must be declared in all eight `.bucket-*` blocks.
   **=> A test seeding seven buckets cannot see an eighth that is broken.**
8. **progress.md says there is no workflow.** ":5 M1-M4 are built, verified and QA'd. There is no
   workflow in flight" and ":23 None open" — while this same tree carries a QA workflow at round 5.
   Stamped `Last Updated 2026-09-21`.
9. **activeContext Current Focus vs Recent Changes.** :5 says "BUILD in flight"; :47 says
   "[QA-START] round 5". The header describes a BUILD, the body describes QA.
10. **activeContext:301 "Blockers: None blocking"** sits directly above three named live gaps.
    The "open items: none, beside a live list" shape — the same shape flagged in the QA law.
11. **patterns.md:411 `Last Updated: 2026-09-21`** while five of its sections are dated 2026-09-22.
12. **`workflow_type` disagrees across state files minutes apart** — precompact says PLAN/qa-execute,
    stop-state says QA/qa-research. Consistent with the documented flip, but the cursor moved
    BACKWARDS (qa-execute -> qa-research), which is correct for round 5 and would look wrong to a
    resume that trusted the cursor's monotonicity.
13. **`quality`/`results` empty after four completed rounds.** `confidence: null`,
    `evidence_complete: false`, `scenario_coverage: 0`, `convergence_state: "pending"`;
    `results.qa_researchers: []`, `results.qa_executor: null`, `evidence.qa_executor: []`,
    `remediation_history: []`, all four `traceability.*` arrays empty.
    **=> 22 defects across four rounds left NO trace in the structured result fields.**
14. **`held_branches` still lists a Phase 3 branch un-adopted**
    (`worktree-agent-af94e2c302e58b42f`, sha `e1d2fe2`) while phase-1 and phase-3 are both completed.
15. **(Router-found) `qa-remfix-4-lane-a` / `-lane-b` recorded `in_progress`** while both had
    completed and merged. Same shape as item 4. Reconciled by the router at round 5 start.

## The six-vs-seven `post_milestone` contradiction is INTERNAL to the artifact, independent of the tree
- json:84 pins *"SIX post_milestone entries, one per path"*.
- json:331 says *"Entries are per path; **seven** are needed"*.
- json:675 names `session.js` as *"the unnamed seventh post_milestone entry"*.
- json:679 F4: *"T6.4 exit says 5 post_milestone entries, its own arithmetic says 4. Third
  total-vs-rows disagreement."*
- json:673 B6: *"test_routes_m3.py:237 asserts `len(BODY_ARGS) == 10`, a second hard-coded count
  outside T4.2's declared scope."*
- json:681 **F8: "AC-21 PRINTS the post_milestone count instead of asserting it — exits 0 for any
  value, and it is the clause that would have caught F4."**

**The artifacts predicted this exact failure mode by name and left the clause unrepaired.** The
router's independent measurement (BODY_ARGS=16, post_milestone=7, terminal.js changed) is the
same disagreement arriving from the other side.
