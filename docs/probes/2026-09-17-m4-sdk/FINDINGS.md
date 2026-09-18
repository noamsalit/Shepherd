# M4 Task 1 probes P1–P4 — findings (2026-09-17)

Four Agent SDK questions M4's design rests on, answered before any code that reads them exists.
Written in `docs/specs/data-schemas.md`'s entry shape. Every fenced example below is a **byte
substring of the capture file named beside it** — the fences were extracted from the files, not
typed from memory — and `tests/test_m4_probes.py::test_findings_cite_real_capture_paths` asserts
that every `docs/probes/...` path on this page exists on disk.

**Read this first: the versions moved, and that is why P1 exists.** `data-schemas.md`'s
§Agent SDK section is pinned to **claude-agent-sdk 0.2.152 / bundled Claude Code 2.1.259 / PATH CLI
2.1.270**. Measured on this host today:

```text
claude_agent_sdk.__version__: 0.2.153
bundled __cli_version__: 2.1.273
PATH claude --version: 2.1.274 (Claude Code)
```

(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/versions.txt`.) Three drifts, none of
them covered by `docs/probes/drift_check.py`, which checks 33 hook-event names and four enums and
says so in its own docstring. Every Agent SDK shape in `data-schemas.md` was therefore *unverified*
until this run. **P1 re-pins them, and the field tables on this page are what `data-schemas.md`
§Agent SDK is re-pinned to.**

**Harness.** `docs/probes/2026-09-17-m4-sdk/probe_m4.py`, a copy of
`docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py`. The original is frozen evidence and
was **not** edited. The plan's two named defects are fixed in the copy:

1. the original pins the model id `claude-haiku-4-5-20251001`. The copy resolves the model at run
   time and P1 records what both ids do. **Both still resolve** — see P1's *Variants*.
2. the original writes flag settings containing `{"enabledPlugins": {"cc10x@cc10x": false}}`, which
   is exactly what P4 must not do. In the copy the plugin-disabling layer is opt-in per probe:
   P1–P3 keep it, **P4 writes `{}`**, and that is what makes P4 the first isolated measurement of
   cc10x under `setting_sources`.

**The safety sequence, and that it held.** P1 ran first and asserted the isolation lock from its
own capture before P2–P4 mounted anything: `tools=[]` + `strict_mcp_config=True` left the master
with exactly the probe's five inert tools and one MCP server. Every probe mounts literal-returning
fakes only; `probe_m4.py` never imports `shepherd.toolsurface` and never mounts a real handler, so
no probe master could act on the fleet. Every run passed an explicit `--settings` file inside a
`mkdtemp` directory, ran with that directory as its cwd, scrubbed every `CLAUDE*` / `ANTHROPIC*` /
`AI_AGENT` variable before spawning a CLI, and was wrapped in `anyio.fail_after`.

`~/.claude/settings.json` had the same sha256 before and after **every** probe, and no `claude`
process started by a probe survived it:

```text
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  ~/.claude/settings.json (before)
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  ~/.claude/settings.json (after)
unchanged: True
```

```text
new claude pids surviving this probe: none
```

(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/settings-sha256.txt`,
`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/pids.txt`, and the same two files in
`docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/`,
`docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/` and
`docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/`.)

Each probe left one engine-owned directory under `~/.claude/projects/` for its throwaway cwd. They
are **recorded, not deleted** (`residue.txt` in each folder) — a probe removes only what it created
itself.

**Not run, deliberately.** **P5** (provoking `ResultMessage` subtypes `error_max_budget_usd` /
`error_max_turns`, G-M4-5): the first costs money and the second a contrived prompt, and the plan's
degrade is a counted `unknown`. **P6** (addressing the master over `messaging_socket_path`,
G-M4-9): that socket is the engine's, at the engine's mode; we neither open nor advertise it, and
probing it would be probing Claude Code's internals rather than our own contract. Neither was
attempted and neither is reported here.

---

## P1 — the Agent SDK shapes re-pinned at claude-agent-sdk 0.2.153 / CLI 2.1.273 and 2.1.274

- **Produced by:** claude-agent-sdk 0.2.153 driving its bundled Claude Code 2.1.273, and the same
  configuration driven against the PATH CLI 2.1.274 (`cli_path=`), model `claude-haiku-4-5`
- **Consumed by:** G-M4-1; §6 `MasterRuntime` / `MasterCapabilities`, §11 Master configuration,
  §11.0 the exporter, §12 Chat page; D10, D19, D30, D32, D42, D53; M4 T19–T23
- **Probe:** `docs/probes/2026-09-17-m4-sdk/probe_m4.py`. Re-run:
  `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p1`
- **Status:** verified live 2026-09-17

**Real example** — the isolation lock, from the `locked` run's own `system/init`
(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/raw-stream.jsonl`):

```text
"tools": ["mcp__shepherd__fail_tool", "mcp__shepherd__fleet_summary", "mcp__shepherd__raise_tool", "mcp__shepherd__shadow_tool", "mcp__shepherd__spawn_session"], "mcp_servers": [{"name": "shepherd", "status": "connected"}], "model": "claude-haiku-4-5"
```

**The field diff against the 2026-09-14 tables**
(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/field-diff.txt`, computed by the
harness by reading its own capture back):

```text
=== locked ===
system/init: IDENTICAL
tools/list result.tools[]: IDENTICAL
tools/call result: IDENTICAL
can_use_tool request: IDENTICAL
ResultMessage: DRIFT
    added since 2026-09-14: ['first_content_frame_ms', 'result_index']
```

| Shape | 2026-09-14 (0.2.152 / 2.1.259) | 2026-09-17 (0.2.153 / 2.1.273) | 2026-09-17 (0.2.153 / 2.1.274) |
|---|---|---|---|
| `system/init` top-level keys | 24 keys | **identical** | **identical** |
| `system/init.mcp_servers[]` | `{name, status}` | `{name, status}` | **`{name, status, source}`** — `source: "sdk"` is new |
| `tools/list` `result.tools[]` | `{name, description, inputSchema}` | **identical** | **identical** |
| `tools/call` `result` | `{content, isError}` | **identical** | **identical** |
| `can_use_tool` request | `{subtype, tool_name, display_name, input, permission_suggestions, tool_use_id}` | **identical** | **`+ mcp_server: {name, source}`** |
| `ResultMessage` | the 2026-09-14 list | **`+ first_content_frame_ms`, `+ result_index`** | same two additions |
| `ToolPermissionContext` (the Python dataclass the callback receives) | `signal, suggestions, tool_use_id, agent_id, blocked_path, decision_reason, title, display_name, description` | **identical** | **identical — `mcp_server` is NOT surfaced** |

The two `can_use_tool` requests side by side. Bundled 2.1.273
(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/raw-stream.jsonl`):

```text
{"subtype": "can_use_tool", "tool_name": "mcp__shepherd__shadow_tool", "display_name": "Shadow Tool", "input": {"id": "ses_a1"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__shadow_tool"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01KMjn6mq2YVt8WAdYT6SCs3"}
```

PATH 2.1.274 (`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/locked-syscli/raw-stream.jsonl`):

```text
{"subtype": "can_use_tool", "tool_name": "mcp__shepherd__shadow_tool", "mcp_server": {"name": "shepherd", "source": "sdk"}, "display_name": "Shadow Tool", "input": {"id": "ses_a1"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__shadow_tool"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01L5QgdvP1ZkHypDiTvMRtnJ"}
```

and the matching `system/init` line on 2.1.274, where the same new identity appears:

```text
"mcp_servers": [{"name": "shepherd", "status": "connected", "source": "sdk"}]
```

The two new `ResultMessage` fields, from the `locked` capture:

```text
"result_index": 0
```

```text
"first_content_frame_ms": 624
```

**What did NOT move, and it is the load-bearing half.** `tools/call` still delivers exactly
`params.arguments` to the handler and nothing else — no caller identity, no `tool_use_id`; the SDK
still validates with `jsonschema` **before** the handler runs; a handler exception still becomes
`isError: true` with `str(exc)` and never a JSON-RPC error. All three are visible in the
`mcp_response` lines of
`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/raw-stream.jsonl`, against
`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/handler-calls.jsonl`:

```text
{"jsonrpc": "2.0", "id": 5, "result": {"content": [{"text": "max_children_per_session=5 reached", "type": "text"}], "isError": true}}
```

```text
{"jsonrpc": "2.0", "id": 6, "result": {"content": [{"text": "handler exploded on purpose", "type": "text"}], "isError": true}}
```

```text
{"jsonrpc": "2.0", "id": 7, "result": {"content": [{"text": "Input validation error: 'task' is a required property", "type": "text"}], "isError": true}}
```

A denial still reaches the model as the callback's own message, now carrying an explicit
`non_execution_kind`
(`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/deny/raw-stream.jsonl`):

```text
"tool_use_result": "Error: you declined this", "tool_result_meta": [{"id": "toolu_01AWrnAKKAi8G3DF3pJWCjnw", "non_execution_kind": "permission-rule"}]
```

**Variants and edge cases:**
- **The isolation lock holds on both binaries.** `system/init.tools` is exactly the probe's five
  tools and `mcp_servers` is exactly `shepherd`, on 2.1.273 and on 2.1.274
  (`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/isolation-lock.json`, re-asserted
  from the committed file by
  `tests/test_m4_probes.py::test_p1_capture_shows_the_isolation_lock`).
- **The model id the frozen harness pinned still resolves**, and so does the alias
  (`docs/probes/2026-09-17-m4-sdk/p1-versions-20260917T214346Z/model-resolution.txt`):

  ```text
  model=claude-haiku-4-5-20251001 rc=0 stdout='OK' stderr=''
  model=claude-haiku-4-5 rc=0 stdout='OK' stderr=''
  ```

- `skills` is now **18** and `slash_commands` **53** under `setting_sources=[]` (they were 17 and 50
  on 2026-09-14). They are still all Claude Code's own — see P4.
- `capabilities` is unchanged: `["interrupt_receipt_v1", "interrupt_cancel_queued_v1", "msg_lifecycle_v1"]`.
- `_build_input_schema`'s D53 branch is unchanged at 0.2.153: a dict is passed through only when it
  has a string `type` **and** `properties`
  (`.venv/lib/python3.12/site-packages/claude_agent_sdk/__init__.py:410`), and the `tools/list`
  exchange in the capture confirms it on the wire.

**Spec alignment:**
- `data-schemas.md` §`system/init`, §`tools/list`, §`tools/call` and §`can_use_tool` are **not
  contradicted**; they are extended by three new fields and re-pinned to today's versions. The rows
  are appended to §Agent SDK rather than rewritten.
- **A new fact D42/DP7 should know, and it cuts both ways.** At CLI 2.1.274 the `can_use_tool`
  control request carries `mcp_server: {name, source}` — the server identity the 2026-09-14 entry
  said the callback has to reconstruct from the prefixed tool name. **SDK 0.2.153 drops it**:
  `ToolPermissionContext` has no `mcp_server` field, so `authorize()` still cannot see it. Mapping
  `mcp__shepherd__<tool>` back to a `ToolDef` stays the callback's own job at M4, and the field is a
  note for the SDK version that surfaces it.
- `data-schemas.md` §Agent SDK's *Scope* paragraph is now wrong about the versions it names. It is
  re-pinned by the table appended under that section, with the old numbers left readable as the
  previous pin.

---

## P2 — `interrupt()` while an in-process MCP tool handler is running in a worker thread

- **Produced by:** claude-agent-sdk 0.2.153 + bundled Claude Code 2.1.273, one in-process MCP tool
  whose handler blocks a worker thread for 20 s via `anyio.to_thread.run_sync`, interrupted at 5 s
- **Consumed by:** G-M4-2, DP5, ADR-M4-3, D54; M4 T4 (`toolsurface/approvals.py`), T20, T27
- **Probe:** `docs/probes/2026-09-17-m4-sdk/probe_m4.py`. Re-run:
  `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p2`
- **Status:** verified live 2026-09-17. **This is a confirmation, and it confirms the stronger
  reading.** The plan moved withdrawal into our own store because `anyio.to_thread.run_sync`'s
  `abandon_on_cancel` defaults to `False`, so cancellation would be *deferred* until the worker
  returned. Measured, it is not deferred — **it never arrives at all.**

**Real example.** The handler enters, the interrupt lands at 5.00 s, and the worker thread goes on
ticking for the full twenty seconds and then returns normally
(`docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/handler-calls.jsonl`; first, sixth,
second-to-last and last lines):

```text
{"_ts": "2026-09-17T21:52:11.003Z", "tool": "slow_tool", "phase": "entered", "received": {"id": "ses_slow"}}
{"_ts": "2026-09-17T21:52:16.007Z", "tool": "slow_tool", "phase": "thread_tick", "second": 5}
{"_ts": "2026-09-17T21:52:31.017Z", "tool": "slow_tool", "phase": "thread_tick", "second": 20}
{"_ts": "2026-09-17T21:52:31.018Z", "tool": "slow_tool", "phase": "await_returned", "outcome": "worker thread ran to completion"}
```

while the turn itself was over in five seconds
(`docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json`):

```text
"interrupt": {
    "since_query_s": 5.0,
    "returned": "None",
    "call_s": 0.01
  },
  "turn_wall_s": 5.11
```

```text
"worker_thread_ticks_observed": 20,
  "worker_thread_ran_to_completion": true
```

```text
"control_cancel_request_lines": []
```

```text
"subtype": "error_during_execution",
      "terminal_reason": "aborted_tools",
      "is_error": true
```

| Question the plan asked | Captured answer | Evidence (under `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/`) |
|---|---|---|
| Does the handler's thread see cancellation? | **No.** All 20 ticks are logged; the thread ran to completion 16 s after the interrupt | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/handler-calls.jsonl` |
| Does the handler *coroutine* see cancellation? | **No.** `await anyio.to_thread.run_sync(...)` returned normally; nothing was raised into it | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json` (`await_raised: []`, `await_returned` present) |
| Does a `control_cancel_request` arrive? | **No.** Zero lines of that type in the whole stream | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json`, `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/raw-stream.jsonl` |
| What does `interrupt()` return, and how fast? | `None`, in 10 ms, 5.00 s after the query | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json` |
| What does the turn's `ResultMessage` say? | `subtype: error_during_execution`, `terminal_reason: aborted_tools`, `is_error: true`, `permission_denials: []`, `errors: ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=tool_use"]` | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json` |
| Does the client stay usable? | **Yes.** The next `query()` on the same client answered `AFTER` with the same `session_id` | `docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/answer.json` |

**Variants and edge cases:**
- **The handler outlives the client.** Closing the `ClaudeSDKClient` with the thread still running
  makes the SDK give up on its own MCP server after a five-second grace and say so on stderr:

  ```text
  SDK MCP server 'shepherd' did not stop within 5.0s of being closed (a tool is probably blocked outside the event loop); no longer waiting for it
  ```

  That line is written to the probe process's own stderr rather than the CLI's, so the harness tees
  it into the capture
  (`docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/probe-stderr.txt`, which contains
  exactly that one line). It is reproducible on every run of
  `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p2`.
- **Run-to-run variance, stated rather than smoothed.** An earlier execution of this same script
  (superseded, and its capture is not committed, so this is recorded as a caution and **not** as a
  shape) saw `CancelledError` delivered into the handler coroutine about 13 s in — at client
  teardown, after that same 5 s grace — while the worker thread nonetheless kept ticking to 20.
  Both executions agree on everything that matters: no cancellation at `interrupt()` time, no
  `control_cancel_request`, and a worker thread that always runs to completion. What varies is only
  whether the *coroutine* is eventually cancelled during teardown. **A design that relies on the
  handler being told anything is relying on the variable half.**

**Spec alignment:**
- **ADR-M4-3 and D54 hold, and they are load-bearing rather than belt-and-braces.** Because no
  cancellation reaches a running handler, the approval a turn is blocked on can only be withdrawn
  by **our own store**, keyed by id, on the master's own `interrupt()`. There is no SDK-side signal
  to hang it off. `MASTER_TOOL_RESULT_ORPHANED` is not a rare fallback: it is the normal outcome of
  interrupting a turn with a call in flight, because the call finishes into a turn that has ended.
- **`data-schemas.md` §`interrupt()` is extended, not contradicted.** Its existing rows describe an
  interrupt during streaming and during a pending `can_use_tool`; the pending-`can_use_tool` case
  *does* produce `control_cancel_request` + `CancelledError`, and this probe shows that a **running
  tool handler behaves differently from a pending approval**. §Not verified's row *"`interrupt()`
  while an in-process MCP tool handler is running"* is closed.
- **`implementation-constraints.md` C24 is about the approval and stays true.** A second constraint
  belongs beside it: *an in-process tool handler is never told the turn ended; it runs to completion
  and its result has nowhere to go.*

---

## P3 — what reaches `can_use_tool` for a tool outside `allowed_tools`

- **Produced by:** claude-agent-sdk 0.2.153 + bundled Claude Code 2.1.273, `tools=[]` +
  `strict_mcp_config=True`, two tools mounted and one allow-listed
- **Consumed by:** G-M4-3, DP7, D42's "second belt"; M4 T3, T6, T21, T23
- **Probe:** `docs/probes/2026-09-17-m4-sdk/probe_m4.py`. Re-run:
  `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p3`
- **Status:** verified live 2026-09-17

**Real example** (`docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/answer.json`):

```text
"can_use_tool_calls": [
    "mcp__shepherd__shadow_tool"
  ],
  "shadow_tool_reached_can_use_tool": true,
  "allowlisted_tool_reached_can_use_tool": false
```

and the context the callback received, in full
(`docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/can-use-tool.jsonl`):

```text
"context": {"signal": null, "suggestions": [{"type": "addRules", "rules": [{"tool_name": "mcp__shepherd__shadow_tool", "rule_content": null}], "behavior": "allow", "mode": null, "directories": null, "destination": "localSettings"}], "tool_use_id": "toolu_01NZscrf9wfervpK7MW5gbEK", "agent_id": null, "blocked_path": null, "decision_reason": null, "title": null, "display_name": "Shadow Tool", "description": null}
```

The `CanUseToolShadowedWarning` is still emitted, and it names **exactly the allow-listed set** —
that is, the tools the callback will *not* see, not the tools it will
(`docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/warnings.txt`):

```text
CanUseToolShadowedWarning: can_use_tool will not be invoked for: mcp__shepherd__fleet_summary. An allowed_tools entry that allows a whole tool auto-approves it before the callback is consulted. To gate every tool call, use a PreToolUse hook; or narrow the entry so calls fall through to can_use_tool. Allow rules from settings files can also shadow the callback but are not visible here.
```

| Question the plan asked | Captured answer | Evidence (under `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/`) |
|---|---|---|
| Does a tool outside `allowed_tools` reach `can_use_tool`? | **Yes**, and it is the only call the callback saw | `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/answer.json`, `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/can-use-tool.jsonl` |
| Does an allow-listed tool reach it? | **No** — it is auto-approved before the callback | same |
| What does the request carry? | `tool_name` (prefixed), `tool_input`, and a `ToolPermissionContext` with `tool_use_id`, `display_name`, `suggestions` and six `null` fields. **No `mcp_server`** at this CLI version — see P1 | `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/can-use-tool.jsonl` |
| Is `CanUseToolShadowedWarning` still emitted? | **Yes**, once per process, at client connect | `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/warnings.txt` |
| Does it name exactly the allow-listed set? | **Yes** — `mcp__shepherd__fleet_summary`, the one allow-listed entry, and nothing else | same |
| Did the shadowed tool still run? | **Yes**, once the callback allowed it | `docs/probes/2026-09-17-m4-sdk/p3-shadow-20260917T214506Z/handler-calls.jsonl` |

**Variants and edge cases:**
- The warning's own text points at the alternative M4 did not take: *"To gate every tool call, use a
  PreToolUse hook"*. It also warns that settings-file allow rules can shadow the callback invisibly
  — under `setting_sources=[]` there are none, which is one more reason the isolation lock is not
  optional.
- The same shadow behaviour appears in P2 for a different reason: P2 allow-lists its only tool, so
  P2's warning names `mcp__shepherd__slow_tool` and the callback is never consulted there
  (`docs/probes/2026-09-17-m4-sdk/p2-interrupt-20260917T215207Z/meta.json`, `warnings`).

**Spec alignment:**
- **DP7's worry does not materialise, and D42's assumption holds.** The belt fires precisely for the
  unexpected: a mounted tool absent from `allowed_tools` reaches `authorize()`. DP7's degraded
  reading — *"the belt is mounted and records nothing"* — is **not** what the engine does, and
  `MASTER_TOOL_UNEXPECTED` is reachable by a real master, not only by the deterministic lane.
- `data-schemas.md` §`can_use_tool`'s line *"The callback is not consulted for `allowed_tools`
  entries"* is **confirmed** at 0.2.153 / 2.1.273, and its converse is now captured too.

---

## P4 — `system/init.plugins` with cc10x enabled, under `setting_sources=[]` and `None`

- **Produced by:** claude-agent-sdk 0.2.153 + bundled Claude Code 2.1.273, two runs with **no
  flag-settings override of `enabledPlugins`** (`--settings` pointing at a file containing `{}`),
  throwaway cwd, `tools=[]` + `strict_mcp_config=True`
- **Consumed by:** G-M4-4, DP10, §18's risk row *"`setting_sources=[]` truly isolating the master
  from the global `CLAUDE.md`/cc10x — verify in M4 and **assert it in a test** — do not trust it"*;
  D10, D19; M4 T19, T21, T22
- **Probe:** `docs/probes/2026-09-17-m4-sdk/probe_m4.py`. Re-run:
  `.venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p4`
- **Status:** verified live 2026-09-17. **This is the first isolated measurement of it.** Every
  2026-09-14 run disabled cc10x through flag settings, so the effect of `setting_sources` alone
  could not be seen. This host has cc10x enabled at user scope, which is what made it probeable.

**Real example.** Same binary, same options, same `{}` flag settings, same throwaway cwd — the only
difference is `setting_sources`. With `[]`
(`docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/setting-sources-empty/raw-stream.jsonl`):

```text
"plugins": []
```

With `None`
(`docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/setting-sources-none/raw-stream.jsonl`):

```text
"plugins": [{"name": "cc10x", "path": "/root/src/cc10x-qa/plugins/cc10x", "source": "cc10x@cc10x", "version": "12.8.2"}]
```

and side by side in the probe's own answer
(`docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/answer.json`):

```text
"setting_sources": [],
    "flag_settings_body": "{}",
    "plugins": [],
    "skills_count": 18
```

```text
"setting_sources": null,
    "flag_settings_body": "{}",
    "plugins": [
      {
        "name": "cc10x",
        "path": "/root/src/cc10x-qa/plugins/cc10x",
        "source": "cc10x@cc10x",
        "version": "12.8.2"
      }
    ],
    "skills_count": 32
```

| `setting_sources` | `system/init.plugins` | `skills` | `slash_commands` | `tools` | `mcp_servers` |
|---|---|---|---|---|---|
| `[]` | **`[]`** — cc10x excluded | **18**, all Claude Code's own | 53 | the one probe tool | the probe's server only |
| `None` (flag absent) | **cc10x 12.8.2, loaded from `/root/src/cc10x-qa/plugins/cc10x`** | **32** — the 18 plus `cc10x:agent-common`, `cc10x:cc10x-guide`, `cc10x:cc10x-router`, `cc10x:diff-driven-docs`, `cc10x:update` and seven `anthropic-skills:*` | 67 | the one probe tool | the probe's server only |

**Variants and edge cases:**
- **`strict_mcp_config=True` and `tools=[]` are what hold the tool surface**, and they hold it under
  *both* `setting_sources` values: `system/init.tools` is the single probe tool in both runs and the
  account connectors appear in neither. **`setting_sources` governs plugins, skills and slash
  commands; it does not govern tools.** Keeping the two levers separate in the master's option block
  is not redundancy.
- **Skills are not excluded by `setting_sources=[]`.** Eighteen Claude Code skills and 53 slash
  commands are listed either way. `tools=[]` is what makes them unreachable, by removing the `Skill`
  tool — the same conclusion the 2026-09-14 entry reached, re-measured at 18 / 53.
- The injected transcript attachments were **identical** in the two runs — `environment`, `model`,
  `total_tokens_reminder`, `session_context`, `date`, `prompt_snapshot` ×2 — with **no cc10x hook
  attachment in either** (`answer.json` `attachment_subtypes`, and the copied transcripts under
  `docs/probes/2026-09-17-m4-sdk/p4-plugins-20260917T214517Z/setting-sources-none/`). cc10x was
  *registered* under `None` but fired nothing for a one-word prompt with one tool mounted. **What is
  proved is registration, not quiescence:** a plugin that is loaded is a plugin that can fire.
- A caution from an earlier, superseded execution of this probe, kept because it is the reusable
  part: that run left the process cwd at the repo rather than a throwaway directory, and its
  `setting_sources=None` transcript then carried `hook_success` and `hook_additional_context`
  attachments and an `instructions` attachment naming the repo's own `CLAUDE.md`. The harness was
  fixed (`os.chdir(WORK)` plus an explicit `cwd=`) and all four probes re-run, so the committed
  captures differ only in **user** scope. The lesson: *`cwd=None` on `ClaudeAgentOptions` means the
  calling process's cwd, and a probe that does not chdir is probing the repo.*

**Spec alignment:**
- **§18's risk row is closed in the affirmative, and it is now assertable.** `setting_sources=[]`
  **does** exclude the cc10x user plugin on a host where cc10x is enabled. §18 said *"do not trust
  it"*; the reason to have doubted it is gone, and T22's isolation test should assert
  `system/init.plugins == []` from a live `system/init` rather than from the option values.
- **`data-schemas.md` §`setting_sources` isolation is corrected where it hedged.** Its Status line
  says *"cc10x exclusion is not verifiable here, because the safety rules require disabling it via
  flag settings in every run"*. That is no longer true: the disabling layer was the harness's
  choice, not a safety requirement, and removing it costs nothing because `tools=[]` +
  `strict_mcp_config=True` is what bounds the master. §Not verified's row *"`setting_sources=[]`
  excluding the cc10x user plugin"* is closed.
- **Spec line 1528's comment `# no CLAUDE.md, no cc10x, no skills` is now two-thirds right rather
  than one-third.** "no cc10x" is **confirmed**. "no CLAUDE.md" held for project scope on
  2026-09-14. **"no skills" is still wrong** — 18 are listed. The comment should read *no project
  `CLAUDE.md`, no user plugins; Claude Code's own skills are still listed and `tools=[]` is what
  makes them unreachable.*
- Still **not** probed and not claimed: user-scope `~/.claude/CLAUDE.md` exclusion. None exists on
  this host and creating one would write user config.

---

## What these four invalidate, and what they do not

| Plan item | Verdict |
|---|---|
| **DP7 / D42's second belt** (T3, T6, T21, T23) | **Upheld by P3.** The belt fires for a tool outside `allowed_tools`. DP7's degraded fallback is not needed. |
| **ADR-M4-3 / D54's withdrawal** (T4, T20, T27) | **Upheld and strengthened by P2** — and its rationale changes. Withdrawal must be ours because cancellation does not reach a running handler *at all*, not merely late. |
| **T22's isolation test** | **Upheld, and it can be stronger, by P4.** It can assert `system/init.plugins == []` beside `tools` and `mcp_servers`. |
| **T20's exporter (D53)** | **Unaffected.** `_build_input_schema`'s branch is unchanged at 0.2.153. |
| **`data-schemas.md` §Agent SDK's version pin** | **Invalidated and re-pinned by P1** to 0.2.153 / 2.1.273 / 2.1.274. |
| **`data-schemas.md` §`setting_sources` isolation Status line** | **Invalidated by P4**: the cc10x exclusion *was* verifiable here. |
| **Spec line 1528's `# no cc10x`** | **Confirmed by P4** for the first time. |
| **Spec line 1528's `# no skills`** | **Still wrong** (18 skills). Unchanged from 2026-09-14. |
| No other task's design | Nothing in P1–P4 contradicts T2–T27 as written. |
