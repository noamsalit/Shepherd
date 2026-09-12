# Lane prompts — paste these after restarting

Two **separate** Claude Code sessions, both in `/root/Shepherd`. Start Lane B
first: Lane Q's later phases depend on it, and the §18 probe can abort the run.

Wording note: each prompt is written to hit exactly one route. Lane B's prompt
deliberately contains **no** QA keyword (`test`, `e2e`, `coverage`, `regression`,
`verify`, `prove it works`) — any one of them would pull it into the QA route at
priority 5 before BUILD is reached at priority 8.

---

## Lane B — BUILD

```
Read docs/specs/orchestrator-platform.md in full, then build M1 from §16.

Start with the hook-payload probe in §18 before anything else — it is the one
assumption that can force a redesign, and if it fails, stop and tell me rather
than working around it.

Then: both daemons, the hookd dispatcher, ingest folding into session columns
(D24), four of the six tables (workspace, repo, session, app_state) plus
migrations, workspace/repo discovery and binding (D22), the
workspace→session→subagent tree, the fleet page, and SSE. Read-only, attached
sessions only.

Scope limits: M1 only, do not start M2. Write src/, pyproject.toml and
migrations. Do not write anything under tests/ — a parallel session owns that
directory. Do not edit docs/specs/ — the spec is frozen for this run.

The decision log in §3 is binding. If implementation pressure pushes against one
of the 34 decisions, say so and re-decide out loud; do not quietly reverse it.
```

## Lane Q — QA

```
Read docs/specs/orchestrator-platform.md in full, then design and build the test
system for M1 (§16).

The implementation is being written right now in a parallel session, so build
the harness against the interfaces the spec pins rather than against code that
may not exist yet: the six Protocols in §6, the capability dataclasses, and the
Scripted* doubles described in §14.2.

Scope limits: M1 only. Write tests/ and conftest.py. Do not write src/ or
pyproject.toml — the parallel session owns those; if you need a dependency, say
so and I will pass it across. Do not edit docs/specs/ — the spec is frozen.

Expect qa-executor to block: there will be no runnable implementation until the
other lane lands. When you reach that point, stop and report rather than waiting,
and say exactly which phase blocked and on what.
```

---

## What to watch while they run

Snapshot the shared memory files at every phase boundary, from a third shell —
this is measurement #2 and it cannot be reconstructed afterwards:

```sh
cd /root/Shepherd && md5sum .cc10x/*.md 2>/dev/null | tee -a /tmp/cc10x-memory-hashes.log
```

A hash that moves backwards, or one lane's content vanishing from
`activeContext.md`, is the finding.
