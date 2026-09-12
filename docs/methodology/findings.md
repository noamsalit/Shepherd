# Findings — QA-parallel-to-BUILD under cc10x

Written **during** the run. Protocol: `parallel-qa-experiment.md`.

Rule for this file: record what happened, including the parts that make the
methodology look bad. An experiment that only produces confirmations was not an
experiment.

---

## Run log

| When | Lane | Phase | What happened | Worked / Didn't |
|---|---|---|---|---|
| 2026-09-12 | — | setup | cc10x installed mid-session; components bind at session start, so it was **not loaded** and could not be used in the session that installed it. | **Didn't** — costs a full restart. Not documented in the plugin's README; `claude plugin details` shows the inventory that *will* load, which reads as if it is live. |
| | | | | |

---

## The five measurements

### 1. Did the QA harness catch BUILD drifting off a Protocol?
*(primary signal — quote the mismatch)*

> not yet run

### 2. Did the `.cc10x/` memory files lose an update?
*(hashes of `activeContext.md`, `progress.md`, `patterns.md` at each phase boundary)*

> not yet run

### 3. Where did Lane Q block on Lane B?
*(predicted: `qa-executor` only)*

> not yet run

### 4. Did the router misroute?
*(especially BUILD prompts pulled into QA by a stray keyword)*

> not yet run

### 5. Cost
*(~3,415 tok always-on per lane; ~23k per router invocation; two lanes pay both)*

> not yet run

---

## Verdict

*(fill in at the end: keep the methodology, keep it with changes, or drop it —
and say which of the five measurements decided it)*
