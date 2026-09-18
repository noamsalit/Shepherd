<!-- Rendered by build_section.py from SECTION.tmpl.md. Every fenced example is pulled from a capture
     file under docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/ and checked byte-for-byte against
     it before trimming; trims are marked "...". Do not hand-edit SECTION.md; edit the template and rebuild. -->

# Claude Agent SDK (the master, M4) and MCP (the tier-2 tool surface, M4): schemas observed 2026-09-14

**Scope.** `claude-agent-sdk` 0.2.152 (Python, installed with pip into a throwaway venv under `/tmp`)
driving the Claude Code CLI it bundles (**2.1.259**), plus one control run of the same configuration
against the `claude` on PATH (**2.1.270**). The tier-2 binding was probed with a stdlib-only stdio MCP server
mounted into a headless `claude -p` (2.1.270) with `--mcp-config`. Linux 6.8. Every run used
`claude-haiku-4-5-20251001` and a timeout. Every run records `claude --version`: `meta.json` → `claude_version`
for the SDK runs, `meta.txt` → `claude_version` for the stdio run, and `_claude_version` on every hook line.

**How the evidence was made.**

| Probe | What it does | Output |
|---|---|---|
| `introspect_sdk.py` | imports the installed package and dumps `inspect.signature` / `dataclasses.fields` / `inspect.getsource` of `ClaudeAgentOptions`, the message and content-block types, `tool`, `create_sdk_mcp_server`, `SdkMcpTool`, and the `ClaudeSDKClient` methods | `captures/introspect/` |
| `master_probe.py <scenario>` | one minimal master per scenario. It patches the SDK transport class to log every JSON object on the CLI's stdout (`_dir:"in"`) and every line the SDK writes to its stdin (`_dir:"out"`). It also logs the parsed SDK objects, what each in-process tool handler received and returned, what `can_use_tool` received and returned, and the Python hook inputs | `captures/<scenario>/raw-stream.jsonl`, `messages.jsonl`, `handler-calls.jsonl`, `can-use-tool.jsonl`, `hooks.jsonl`, `meta.json` |
| `stdio/run_stdio_probe.sh` + `stdio/mcp_logger_server.py` + `stdio/capture_hook.sh` | tier-2 binding. The server logs every JSON-RPC line it reads or writes, verbatim. Hooks for PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest and PermissionDenied are declared in `<tmpdir>/work/.claude/settings.json` and append the raw stdin, the event name, a UTC timestamp and the `/proc` parent chain | `captures/stdio-mcp/` |
| `redact_captures.py` | privacy pass. The CLI's `initialize` response carries `account.email`/`account.organization`, and the transcripts carry an injected `userEmail` line. Both are replaced by `<redacted>` in every capture file | in place |
| `summarize.py` | field-presence matrix over all 486 captured CLI stdout objects | `captures/_field-matrix.txt` |
| `build_section.py` | renders this file from `SECTION.tmpl.md` | `SECTION.md` |

Re-run everything (about 6 minutes): `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/run_all.sh`

**Scenarios** (`master_probe.py`). Unless noted, each uses the §11 option block literally:
`setting_sources=[]`, `disallowed_tools=["Agent","Task"]`, `allowed_tools=[mcp__shepherd__…]`,
`mcp_servers={"shepherd": create_sdk_mcp_server(...)}`, `can_use_tool=<probe authorize>`, `cwd=None`.
The process cwd is a throwaway dir.
`basic` = spec block as written · `tools_empty` = + `tools=[]` · `locked` = + `tools=[]` + `strict_mcp_config=True`
(also `locked-syscli`, which uses the PATH claude 2.1.270) · `deny` · `slow_approval` · `interrupt` ·
`interrupt_pending_approval` · `resume` (resume + fork) · `resume_other_cwd` · `isolation` (a project `CLAUDE.md` marker under three `setting_sources` values).
The in-process server `shepherd` declares `fleet_summary`, `spawn_session`, `kill_session` (left out of `allowed_tools`, so it goes through `can_use_tool`),
`fail_tool` (returns `is_error`) and `raise_tool` (raises).

**Safety record.** `~/.claude/settings.json` had the same sha256 before and after every run:

```text
{{settings_sha}}
```

No `~/.claude.json` or user settings were edited. Every `CLAUDE*`/`ANTHROPIC*`/`AI_AGENT` variable inherited from the
calling Claude Code session was deleted before the CLI was spawned. Every throwaway settings file had
`"enabledPlugins": {"cc10x@cc10x": false}`, and **cc10x did not register or fire**. The SDK runs report `"plugins": []` in every
`system/init`. The stdio run's debug log says:

```text
{{stdio_cc10x}}
```

Claude Code wrote its own transcripts for these throwaway sessions under `~/.claude/projects/-tmp-shp-sdk-*` and `-tmp-shp-mcp-*`.
The only directory removed was one this probe had created (`-tmp-shp-sdk-9IOKNs-work-resume-other-cwd-a`), deleted before its scenario was re-run.
No user transcript was read. No process this probe did not start was signalled.

---

## Agent SDK package and its bundled CLI

- **Produced by:** `pip install claude-agent-sdk` → claude-agent-sdk 0.2.152 (mcp 2.2.0, anyio 4.15.1), bundling Claude Code 2.1.259
- **Consumed by:** §5 Stack (spec line 406), §6 `MasterRuntime` / `AgentSDKMaster`, §11 Master configuration, §15 Packaging; D10, D30; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py`. Re-run: `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/introspect_sdk.py docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/sdk-install.txt`, plus `captures/pip-freeze.txt`)

```text
{{install}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `claude_agent_sdk.__version__` | str | always | `0.2.152` | |
| `_cli_version.__cli_version__` | str | always | `2.1.259` | version of the bundled binary |
| `claude_agent_sdk/_bundled/claude` | ELF, 216,677,784 bytes | always (Linux wheel) | 2.1.259 | the package is 208 MB on disk |
| `SubprocessCLITransport._find_cli()` order | — | — | bundled → `shutil.which("claude")` → `~/.npm-global/bin`, `/usr/local/bin`, `~/.local/bin`, … | `captures/introspect/internals-source.txt`; the bundled CLI always wins unless `cli_path=` is passed |

**Variants and edge cases:**
- The SDK spawns **its own** Claude Code, not the one on PATH. It was 2.1.259 here, while the tier-2 sessions use 2.1.270. `cli_path="/root/.local/bin/claude"` switches it; the `locked-syscli` run shows the same config working on 2.1.270.
- The transport always sets `CLAUDE_CODE_ENTRYPOINT=sdk-py` and `CLAUDE_AGENT_SDK_VERSION`, and removes `CLAUDECODE` from the child env (`captures/introspect/internals-source.txt`, `SubprocessCLITransport.connect`).
- On this host, python3 has no `ensurepip`, so the venv needs `--without-pip` plus `get-pip.py` (`run_all.sh`). That is relevant to §15 packaging.

**Spec alignment:**
- Spec line 406 lists `claude-agent-sdk` as a backend dependency but does not say the package ships a second Claude Code binary. In reality the master runs the bundled 2.1.259, and it will drift from the fleet's `claude` unless `AgentSDKMaster` pins `cli_path` (`captures/introspect/sdk-install.txt`, `captures/locked/meta.json` vs `captures/locked-syscli/meta.json`).

---

## `ClaudeAgentOptions` (as installed)

- **Produced by:** claude-agent-sdk 0.2.152, `claude_agent_sdk/types.py:1940`
- **Consumed by:** §11 Master configuration (spec lines 1525–1537), §6 `MasterRuntime.configure/resume`; D10, D19, D20, D30, D32; M4
- **Probe:** `introspect_sdk.py` → `captures/introspect/options-signature.txt`, `options-source.txt`. The CLI argv each option produces is in `captures/<scenario>/meta.json`. Re-run: as above, plus `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14 (signature from the installed source; the option→argv mapping and the behaviour of `tools`, `allowed_tools`, `disallowed_tools`, `setting_sources`, `strict_mcp_config`, `can_use_tool`, `resume`, `fork_session`, `cwd`, `settings`, `hooks`, `include_partial_messages`, `max_turns` and `cli_path` were exercised live)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-signature.txt`)

```text
{{options_sig}}
```

The docstrings that decide the semantics (trimmed; full capture: `captures/introspect/options-source.txt`):

```text
{{options_doc}}
```

The argv this becomes for the `locked` master (full capture: `captures/locked/meta.json`):

```text
{{argv_locked}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `tools` | `list[str] \| ToolsPreset \| None` | sometimes | `None` → no flag; `[]` → `--tools ""` | **the only option that removes built-in tools** |
| `allowed_tools` | `list[str]` | always (default `[]`) | `mcp__shepherd__…` | → `--allowedTools a,b`. **Auto-approve list, not an availability list** |
| `disallowed_tools` | `list[str]` | always (default `[]`) | `["Agent","Task"]` | → `--disallowedTools`. Removed `Agent` from `tools`; `TaskCreate/TaskGet/TaskList/TaskOutput/TaskStop/TaskUpdate` remain |
| `setting_sources` | `list["user","project","local"] \| None` | sometimes | `[]` → `--setting-sources=`; `None` → no flag | `None` loads everything (see the isolation schema) |
| `strict_mcp_config` | bool | always | `True` → `--strict-mcp-config` | drops the account's claude.ai connectors |
| `mcp_servers` | `dict[str, Stdio\|SSE\|Http\|Sdk config] \| str \| Path` | always | `{"shepherd": {"type":"sdk","name":"shepherd","instance":<Server>}}` | `instance` is stripped and the rest goes to `--mcp-config` as JSON |
| `can_use_tool` | `async (tool_name:str, input:dict, ToolPermissionContext) -> PermissionResultAllow\|PermissionResultDeny` | sometimes | probe callbacks | setting it adds `--permission-prompt-tool stdio` |
| `resume` / `fork_session` / `session_id` / `resume_session_at` | `str\|None` / bool / `str\|None` / `str\|None` | sometimes | uuid | `--resume=<id>`, `--fork-session` |
| `cwd` | `str\|Path\|None` | always | `None` (= process cwd) | also keys the transcript directory |
| `settings` | `str\|None` | sometimes | a file path | → `--settings` (flag layer, highest priority) |
| `permission_mode` | `default\|acceptEdits\|plan\|bypassPermissions\|dontAsk\|auto\|None` | never set by probe | init reported `"permissionMode": "default"` | |
| `effort`, `thinking`, `max_budget_usd`, `task_budget`, `session_store`, `skills`, `plugins`, `agents`, `output_format`, `sandbox` | see capture | never set by probe | — | present in 0.2.152; not exercised |

**Variants and edge cases:**
- When `can_use_tool` is set and `allowed_tools` names a whole tool, the SDK emits a warning at connect time (captured in `captures/locked/meta.json`):

```text
{{shadow_warning}}
```

- `system_prompt=None` still sends `--system-prompt ""`. A string replaces Claude Code's prompt entirely (`captures/introspect/internals-source.txt`, `_build_command`).
- `ClaudeSDKClient` has no `resume()` or `configure()` method. Resume and tool mounting are construction-time options, so each `resume` means a new CLI subprocess. Mid-session methods that exist: `interrupt`, `set_model`, `set_permission_mode`, `toggle_mcp_server(server_name, enabled)`, `reconnect_mcp_server`, `get_mcp_status`, `get_context_usage`, `stop_task`, `rewind_files` (`captures/introspect/client-api.txt`).

**Spec alignment:**
- Spec line 1540 says `allowed_tools` "stays a strict allowlist", and line 113 (D10) says "`allowed_tools` = orchestration MCP tools only". In reality `allowed_tools` only **auto-approves**. With the spec block as written, `system/init.tools` lists 32 built-ins (Bash, Read, Write, Edit, WebFetch, Skill, SendMessage, Workflow, …), plus 38 claude.ai connector tools (Gmail and Calendar are connected on this account), plus the 5 shepherd tools (`captures/basic/raw-stream.jsonl`). Restricting availability needs `tools=[]`, and dropping the account connectors additionally needs `strict_mcp_config=True` (`captures/tools_empty/`, `captures/locked/`).
- Spec lines 1542–1543 say "The master still has no Read, Write, Edit, Bash, or WebFetch". In reality the `basic` master ran `Bash` `echo hi` with **no** `can_use_tool` call, because Claude Code auto-allows read-only Bash (see "Built-in tools reachable from the spec-configured master" below).
- Spec line 1534 says `can_use_tool=authorize`. In reality the callback signature is `(tool_name: str, input: dict, ToolPermissionContext) -> PermissionResultAllow|PermissionResultDeny`, not `authorize(tool: ToolDef, args, ctx: CallerContext) -> Decision` (line 1728). It is **never invoked for tools listed in `allowed_tools`**: the SDK warns about exactly this, and `captures/locked/can-use-tool.jsonl` has only the one tool that was *not* in `allowed_tools`. So either `authorize()` runs inside the exporter's handler (`invoke()`, line 1464), which is the D32 design and makes line 1534 redundant, or `allowed_tools` must be empty for the gate to see anything.
- Spec line 1536 says `cwd=None  # it delegates; it does not edit`. `cwd=None` only means "the daemon's cwd". It does not remove editing tools (only `tools=[]` does), and it determines the `~/.claude/projects/<cwd-key>/` directory the master's transcript is written to.
- Spec line 1529 says `disallowed_tools=["Agent","Task"]`. That is aligned: no `Agent`/`Task` in `tools`. The subagent roster (`agents`: `claude, Explore, general-purpose, Plan, statusline-setup`) is still reported in `system/init`.

---

## Control protocol handshake (SDK ↔ CLI over stdio)

- **Produced by:** claude-agent-sdk 0.2.152 (request) / Claude Code 2.1.259 (response)
- **Consumed by:** `AgentSDKMaster` internals (§6, §11); D30 (seat), D32; M4
- **Probe:** `master_probe.py` (every scenario). Re-run: `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{{cp_initialize}}
{{cp_initialize_resp}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.subtype` | str | always | `initialize` | first line the SDK writes |
| `request.hooks.<Event>[].hookCallbackIds` | list[str] | when `hooks=` set | `hook_0`, `hook_1`, `hook_2` | the CLI later calls these back with `hook_callback` |
| `response.response.commands[]` | list | always | 50 slash commands even with `setting_sources=[]` | bundled skills and commands |
| `response.response.models[]` | list | always | `value`, `resolvedModel`, `displayName`, `supportedEffortLevels`, … | the account's model menu (`ModelProvider.models()` candidate) |
| `response.response.account` | dict | always | `email`, `organization` (redacted), `subscriptionType: "Claude Max"`, `apiProvider: "firstParty"` | seat evidence for D30 |
| `response.response.pid` | int | always | CLI pid | |
| `response.response.remote_control_available` | bool | always | `true` | |

**Variants and edge cases:**
- Line framing: one JSON object per line on both pipes. The SDK's user turns go out as `{"type":"user","message":{"role":"user","content":"…"},"parent_tool_use_id":null,"session_id":"default"}` (`_dir:"out"` lines in any `raw-stream.jsonl`).
- Other control subtypes observed from CLI → SDK: `mcp_message`, `hook_callback`, `can_use_tool`, `control_cancel_request`. From SDK → CLI: `initialize`, `interrupt`. All are shown in the schemas below.

**Spec alignment:** aligned. The spec treats this layer as `AgentSDKMaster`'s business and does not describe it.

---

## `system/init` message (`SystemMessage(subtype="init")`)

- **Produced by:** Claude Code 2.1.259 (bundled) and 2.1.270 (`locked-syscli`, `stdio-mcp`)
- **Consumed by:** §6 `MasterCapabilities`, §11 Master configuration / Connectors (health), §18 isolation test; D10, D20, D30; M4
- **Probe:** `master_probe.py` (all scenarios), `stdio/run_stdio_probe.sh`. Re-run: see run_all.sh
- **Status:** verified live 2026-09-14 (19 init messages across 12 runs)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{{system_init_locked}}
```

The same message for the spec's option block as written (`basic`; full capture: `captures/basic/raw-stream.jsonl`):

```json
{{system_init_basic}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `session_id` | str (uuid) | always | | the id to persist for `resume` |
| `tools` | list[str] | always | 5 (locked) … 75 (basic) | the definitive "what can the master call" list |
| `mcp_servers[]` | list[{name,status}] | always | `connected`, `needs-auth` | account connectors appear as `claude.ai <Name>` unless `strict_mcp_config` |
| `apiKeySource` | str | always | `none` | no API key in env; the seat was used |
| `claude_code_version` | str | always | `2.1.259`, `2.1.270` | |
| `model` | str | always | `claude-haiku-4-5-20251001` | |
| `permissionMode` | str | always | `default` | |
| `plugins` | list | always | `[]` | cc10x disabled by the flag settings |
| `skills` / `slash_commands` | list[str] | always | 17 / 50 | present even with `setting_sources=[]` and `tools=[]` |
| `agents` | list[str] | always | `claude, Explore, general-purpose, Plan, statusline-setup` | |
| `capabilities` | list[str] | always | `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `msg_lifecycle_v1` | |
| `memory_paths.auto` | str | always | `~/.claude/projects/<cwd-key>/memory/` | |
| `messaging_socket_path` | str | always | `/run/user/0/cc-socks/<pid>.sock` | every SDK-spawned CLI opens one |
| `cwd`, `output_style`, `terminal_slash_commands`, `analytics_disabled`, `product_feedback_disabled`, `fast_mode_state`, `fast_mode_disabled_reason`, `uuid` | | always | `fast_mode_disabled_reason: "sdk_opt_in_required"` | |

**Variants and edge cases:**
- A `system/init` is emitted **per turn**, not once per connection: the `interrupt` scenario has two, with the same `session_id`.
- `messaging_socket_path` means the master is itself a peer on the local messaging socket. Whether other sessions can address it was not probed.

**Spec alignment:**
- Spec line 1528 comments `setting_sources=[]` as "no CLAUDE.md, no cc10x, no skills". In reality `skills` has 17 entries and a `skill_listing` attachment is injected into the master's context. Project `CLAUDE.md` *is* excluded. See the isolation schema (`captures/locked/raw-stream.jsonl`, `captures/resume/transcript-*.jsonl`).
- Spec §11 Connectors rule 4 (lines 1600–1603) says health is polled. `system/init.mcp_servers[].status` and `ClaudeSDKClient.get_mcp_status()` are the SDK-side sources (`captures/introspect/client-api.txt`). Polling is not probed.

---

## `AssistantMessage` and its content blocks

- **Produced by:** Claude Code 2.1.259 stream-json → parsed by claude-agent-sdk 0.2.152
- **Consumed by:** §6 `MasterRuntime.send() -> AsyncIterator[Event]`, §12 Chat page; D30; M4
- **Probe:** `master_probe.py locked` (and all others). Re-run: as above
- **Status:** verified live 2026-09-14 (135 assistant objects; `text`, `thinking` and `tool_use` blocks seen. `ServerToolUseBlock`/`ServerToolResultBlock` are not observed)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{{assistant}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.content[]` | list, **exactly one block per stream line** | always | `thinking` / `text` / `tool_use` | one API message arrives as several `assistant` lines sharing `message.id` |
| `content[].type=thinking` → `thinking`, `signature` | str | 52/135 | `thinking: ""` | observed only as an empty string with a signature |
| `content[].type=text` → `text` | str | 49/135 | | |
| `content[].type=tool_use` → `id`, `name`, `input`, `caller` | str, str, dict, dict | 34/135 | `name: "mcp__shepherd__kill_session"`, `caller: {"type":"direct"}` | |
| `message.stop_reason` | null | always null on the wire | | the real stop reason is only on `result.stop_reason` |
| `message.usage` | dict | always | per-message token counts | |
| `session_id`, `uuid`, `timestamp`, `request_id`, `parent_tool_use_id` | | always | | |
| `tool_use_meta[]` | list[{id, display_name, server_display_name}] | 32/135 | `"Kill Session"`, `"shepherd"` | |
| `wire_tool_inputs` | dict | 11/135 | | |
| `aborted` | bool | 1/135 | `true` | the block that was streaming when `interrupt()` landed |

**Variants and edge cases:**
- Parsed SDK class `AssistantMessage(content, model, parent_tool_use_id, error, usage, message_id, stop_reason, session_id, uuid)` drops `timestamp`, `request_id`, `tool_use_meta` (`captures/locked/messages.jsonl`). `TextBlock` is serialised without its `type` (dataclass has no such field).

**Spec alignment:** aligned. The spec leaves `Event` abstract. Note for `send()`: the tool name the model emits is the MCP-prefixed name, never the bare `ToolDef.name`.

---

## `UserMessage` carrying tool results

- **Produced by:** Claude Code 2.1.259 → claude-agent-sdk 0.2.152 `UserMessage`
- **Consumed by:** §6 `send()` events, §11 "The cap returns a tool error the agent can read" (line 1722), §11 `authorize()` denial message (line 1743); D8, D32; M4
- **Probe:** `master_probe.py locked` and `deny`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `captures/deny/raw-stream.jsonl`). The five lines are: success, handler `is_error`, handler raised, schema validation failed, and `can_use_tool` denied.

```json
{{user_tool_results}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `message.content[].type` | str | always | `tool_result`, `text` | `text` only for interrupt notices |
| `message.content[].content` | list[{type,text}] **or** str | always | list on success; bare str on error | shape differs by outcome |
| `message.content[].is_error` | bool | 18/34 | `true`; `false` on Bash | absent on MCP successes |
| `tool_use_result` | list \| str \| dict | 34/36 | `"Error: <text>"` on errors; Bash gives `{stdout,stderr,interrupted,isImage,noOutputExpected}` | |
| `tool_result_meta[].non_execution_kind` | str | 3/36 | `permission-rule` (deny), `user-rejected` (interrupt during approval) | distinguishes "not run" from "ran and failed" |

**Variants and edge cases:** the interrupt variants (`[Request interrupted by user]`, `[Request interrupted by user for tool use]`) are in the interrupt schema.

**Spec alignment:** aligned with line 1722 (errors come back as readable `is_error` tool results) and with line 1743 (the deny message reaches the model verbatim: `"content": "you declined this"`).

---

## `ResultMessage` (end of turn)

- **Produced by:** Claude Code 2.1.259/2.1.270 `type:"result"` → claude-agent-sdk 0.2.152 `ResultMessage`
- **Consumed by:** §6 `MasterCapabilities` (billing_mode, context_window), D31 wake set (error outcomes), §12 Chat; D30; M4
- **Probe:** `master_probe.py basic`, `interrupt`, `interrupt_pending_approval`. Re-run: as above
- **Status:** verified live 2026-09-14 (19 results: 17 `success`, 2 `error_during_execution`. `error_max_turns`, `error_max_budget_usd` and API-error results were not provoked)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`)

```json
{{result_success}}
```

Interrupted turns (`captures/interrupt/raw-stream.jsonl`, `captures/interrupt_pending_approval/raw-stream.jsonl`):

```json
{{result_interrupted}}
```

What the SDK parser keeps (`captures/locked/messages.jsonl`):

```json
{{result_parsed}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `subtype` | str | always | `success`, `error_during_execution` | |
| `is_error` | bool | always | `false`, `true` | `true` for interrupts |
| `terminal_reason` | str | always | `completed`, `aborted_streaming`, `aborted_tools` | the reliable "why it ended" |
| `stop_reason` | str \| null | always | `end_turn`, `tool_use`, `null` | |
| `session_id` | str | always | | same as `system/init.session_id` |
| `num_turns` | int | always | 1–9 | counts model calls, not user turns |
| `duration_ms` / `duration_api_ms` | int | always | | |
| `total_cost_usd` | float | always | 0.000988–0.0593 | **list-price estimate even on a seat** |
| `usage` | dict | always | `input_tokens`, `cache_*`, `output_tokens`, `output_tokens_details.thinking_tokens`, `iterations[]`, … | |
| `modelUsage.<model>` | dict | always | `contextWindow: 200000`, `maxOutputTokens: 32000`, `costUSD`, `costBasis: "list"`, `provider: "firstParty"` | → `ModelUsage` in the SDK |
| `permission_denials[]` | list[{tool_name, tool_use_id, tool_input}] | always | `[]`; one entry on deny and on interrupt-during-approval | |
| `errors` | list[str] | on `error_during_execution` | `"[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"` | |
| `result` | str | on `success` | final text | |
| `api_error_status` | int \| null | on `success` | `null` | |
| `subagent_stats`, `ttft_ms`, `ttft_stream_ms`, `time_to_request_ms`, `queued_turn_count`, `fast_mode_*`, `uuid` | | always / on success | | `subagent_stats`, `ttft_*`, `time_to_request_ms`, `queued_turn_count`, `fast_mode_*` are dropped by the SDK parser |

**Variants and edge cases:**
- The billing evidence for D30 is in the handshake response and in `modelUsage` (full captures: `captures/locked/raw-stream.jsonl`, `captures/basic/raw-stream.jsonl`, `captures/auth-context.txt`):

```json
{{seat_account}}
{{seat_model_usage}}
```

```text
{{auth_context}}
```

**Spec alignment:**
- D30 (line 133) and spec line 1556 say "picks up local Claude Code credentials: the user's subscription". That is aligned: no API key in the environment, `apiKeySource: "none"`, `subscriptionType: "Claude Max"`, and every turn succeeded. `total_cost_usd`/`costUSD` are still non-zero with `costBasis: "list"`, so a UI that shows them for `billing_mode="seat"` would show a notional cost.
- Spec line 521 `MasterCapabilities.context_window: int` can be sourced from `modelUsage.<model>.contextWindow` (200000 observed), but only after the first turn. `supports_parallel_tool_calls` (line 520) was not observed: the model always made one call per step.

---

## Other stream objects: `rate_limit_event`, `system/status`, `system/thinking_tokens`, `stream_event`

- **Produced by:** Claude Code 2.1.259
- **Consumed by:** §6 `send()` event stream; §17 "plan-window pacing" (deferred); M4
- **Probe:** `master_probe.py resume` and `interrupt` (`include_partial_messages=True`). Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/raw-stream.jsonl`, `captures/interrupt/raw-stream.jsonl`)

```json
{{other_stream}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `rate_limit_info.status` | str | always | `allowed` | SDK literal also has `allowed_warning`, `rejected` |
| `rate_limit_info.rateLimitType` | str | always | `five_hour` | |
| `rate_limit_info.unifiedWindows.{five_hour,seven_day}.utilization` | float | always | 0.31–0.33, 0.07 | seat plan-window usage |
| `rate_limit_info.resetsAt`, `overageStatus`, `overageDisabledReason`, `isUsingOverage` | | always | `rejected`, `org_level_disabled`, `false` | |
| `system/status.status` | str | 2 seen | `requesting` | only seen with `include_partial_messages=True` |
| `system/thinking_tokens.estimated_tokens(_delta)` | int | 65 seen | | |
| `stream_event.event.type` | str | 35 seen | `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop` | raw Messages-API stream events; requires `include_partial_messages=True` |

**Variants and edge cases:** `RateLimitEvent` is parsed by the SDK. `system/status` and `system/thinking_tokens` arrive as a generic `SystemMessage(subtype, data)`.

**Spec alignment:** the spec does not reference these, so there is nothing to align. `rate_limit_event` is the seat-side input any future pacing (§17) would need.

---

## In-process MCP tool declaration (`@tool` + `create_sdk_mcp_server`) and the wire shape it produces

- **Produced by:** claude-agent-sdk 0.2.152 (`__init__.py:251`, `:491`); served to Claude Code 2.1.259 over the control protocol
- **Consumed by:** §11.0 exporter `to_sdk_mcp_server()` (line 1479), `ToolDef.input_schema` (line 1455), §11 Master configuration (line 1532); D32; M4
- **Probe:** `introspect_sdk.py` (source) and `master_probe.py locked` (wire). Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `captures/introspect/mcp-server-source.txt` and `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```text
{{mcp_source}}
```

The MCP `initialize` and `tools/list` exchange for the in-process server. It is tunnelled through the CLI as `control_request{subtype:"mcp_message"}`, and the SDK answers with `control_response{mcp_response}`:

```json
{{sdk_mcp_handshake}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `@tool(name, description, input_schema, annotations=None)` | decorator → `SdkMcpTool` | — | | handler must be `async def h(args: dict) -> dict` |
| `input_schema` given as JSON Schema | dict with str `type` **and** `properties` | — | `{"type":"object","properties":{}}` | passed through unchanged (key order re-sorted by pydantic on the wire) |
| `input_schema` given as `{name: pytype}` | dict | — | `{"id": str}` → `{"properties":{"id":{"type":"string"}},"required":["id"],"type":"object"}` | every key becomes required |
| `request.server_name` | str | always | `shepherd` | the `mcp_servers` dict key |
| `message.params.clientInfo.version` | str | always | `2.1.259` | |
| `message.params.protocolVersion` | str | always | `2025-11-25` | |
| `result.tools[].name` | str | always | bare `kill_session` | the model sees `mcp__shepherd__kill_session` (`system/init.tools`, `tool_use.name`) |
| `result.tools[].annotations`, `_meta` | | never (none declared) | | `ToolAnnotations(maxResultSizeChars=N)` → `_meta["anthropic/maxResultSizeChars"]` (`internals-source.txt`, `_build_meta`) |

**Variants and edge cases:**
- The dict-vs-JSON-Schema test is purely structural (`captures/introspect/internals-source.txt`, `_build_input_schema`). A JSON Schema **without** `"properties"`, such as `{"type":"object"}`, is treated as a `{name: type}` map, producing `properties: {"type": ...}` (read from source; not provoked live). The exporter must always emit `properties`.
- The server object is a real `mcp.server.Server`, but its traffic crosses the CLI's stdio pipe, so it is "in-process" only on the Python side.

**Spec alignment:**
- Spec line 1455 says `input_schema: dict  # plain JSON Schema`. That is aligned, provided the exporter always includes `type` and `properties` (see above).
- Spec line 1530 says `f"mcp__shepherd__{t}"`. That is aligned: `name` in the model's tool list and in `tool_use` is `mcp__<server key>__<tool name>`.
- Spec line 1694 describes `to_sdk_mcp_server()` as "in-process". That is aligned for the handler; the JSON-RPC still round-trips through the CLI subprocess.

---

## In-process MCP `tools/call`: what the handler receives, returns, and how errors look

- **Produced by:** Claude Code 2.1.259 (`tools/call`) / claude-agent-sdk 0.2.152 `run_tool` (result)
- **Consumed by:** §11.0 `invoke()` (line 1464) inside `to_sdk_mcp_server()`, recursion-cap errors (line 1722); D32; M4
- **Probe:** `master_probe.py locked`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`). The four pairs are: success, `is_error` returned, handler raised, and argument missing a required property.

```json
{{sdk_mcp_calls}}
```

What the Python handler actually received and returned (full capture: `captures/locked/handler-calls.jsonl`):

```json
{{handler_calls}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| handler argument | dict | always | `{}`, `{"project_id":"p1","task":"write tests"}` | exactly `params.arguments`; no context, no tool_use_id |
| `params._meta.claudecode/toolUseId` | str | always | `toolu_…` | only on the wire. **The handler does not get it** |
| `params._meta.progressToken` | int | always | 2–7 | |
| handler return `content[]` | list[{type:"text",text}\|{type:"image",data,mimeType}\|resource_link\|resource] | always | text | unknown block types are dropped with a warning (`internals-source.txt`, `_convert_tool_content`) |
| handler return `is_error` | bool | sometimes | `true` | → wire `isError` |
| wire `result.isError` | bool | always | `false`, `true` | the SDK always sets it |
| handler exception | — | — | `RuntimeError("handler exploded on purpose")` | → `isError:true`, text = `str(exc)`. **Never a JSON-RPC error** |
| schema violation | — | — | `Input validation error: 'task' is a required property` | the SDK validates with `jsonschema` **before** calling the handler; the CLI sent the invalid call unvalidated |

**Variants and edge cases:** an unknown tool name becomes `isError` `"Tool '<name>' not found"` (`captures/introspect/mcp-server-source.txt`; not provoked live).

**Spec alignment:**
- Spec lines 1464–1472 (`invoke()` returning `ToolResult.denied(reason)`) are aligned in shape: a denial or cap has to become `{"content":[{"type":"text","text":reason}],"is_error":True}`, and the model reads it (see `UserMessage`).
- Spec §11.0 `CallerContext` is silent on caller identity for the master binding. In reality the SDK handler receives only `arguments`; the `toolUseId` stays in `_meta`, which `create_sdk_mcp_server` does not pass on. Any per-call context (audit correlation to `tool_use_id`) needs a PreToolUse hook or a custom `mcp.server.Server` (`captures/locked/raw-stream.jsonl`, `handler-calls.jsonl`).

---

## `can_use_tool` permission callback (control request, callback input, allow and deny)

- **Produced by:** Claude Code 2.1.259/2.1.270 (`control_request{subtype:"can_use_tool"}`) / claude-agent-sdk 0.2.152 (`ToolPermissionContext`, `PermissionResultAllow|Deny`)
- **Consumed by:** §11 Master configuration `can_use_tool=authorize` (line 1534), §11 `authorize()` (lines 1725–1751); D8, D10; M4
- **Probe:** `master_probe.py locked`, `deny`, `slow_approval`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`, `captures/deny/raw-stream.jsonl`). The four lines are: request, allow response, request, deny response.

```json
{{can_use_tool_wire}}
```

What the Python callback received (full capture: `captures/locked/can-use-tool.jsonl`):

```json
{{can_use_tool_callback}}
```

A callback that blocks for 75 s (full capture: `captures/slow_approval/can-use-tool.jsonl`, `meta.json`):

```text
{{slow_approval_cb}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.tool_name` | str | always | `mcp__shepherd__kill_session` | prefixed name, not the `ToolDef.name` |
| `request.input` | dict | always | `{"id":"ses_a1"}` | → callback arg 2 |
| `request.display_name` | str | always | `Kill Session` | derived from the tool name |
| `request.permission_suggestions[]` | list | always | `addRules` → `localSettings` | → `context.suggestions` |
| `request.tool_use_id` | str | always | | → `context.tool_use_id` |
| `context.blocked_path`, `decision_reason`, `agent_id`, `title`, `description`, `signal` | | always (null) | `null` | |
| response `behavior` | str | always | `allow`, `deny` | |
| response `updatedInput` | dict | on allow | echo of input | the SDK renames `updated_input` → `updatedInput` |
| response `message` | str | on deny | `you declined this` | reaches the model as `tool_result.content`, `is_error:true` |
| `PermissionResultDeny.interrupt` | bool | never sent | `False` | exists in 0.2.152 (`captures/introspect/message-types.txt`) |

**Variants and edge cases:**
- **Blocking works**: the CLI waited 75 s for the callback and then ran the tool (`slow_approval`). A 600 s wait (spec line 1738) was not attempted.
- `interrupt()` while the callback is pending: the CLI sends `control_cancel_request` and the SDK **cancels the callback task** (`CancelledError`). See the interrupt schema.
- The callback is not consulted for `allowed_tools` entries, nor for tool calls Claude Code considers safe on its own (read-only Bash, next schema).

**Spec alignment:**
- Spec line 1534 vs line 1728: the signature does not match (see `ClaudeAgentOptions` above). The callback gets the prefixed MCP name and a raw dict, and must map them back to a `ToolDef` itself.
- Spec line 1747 says "The callback blocks the agent's turn while an approval is pending". That is aligned: 75 s observed. Spec line 1744's "approval timed out" deny is the callback's own job; no CLI-side timeout fired within 75 s.

---

## Built-in tools reachable from the spec-configured master

- **Produced by:** Claude Code 2.1.259 under the §11 option block
- **Consumed by:** §11 "The master still has no Read, Write, Edit, Bash, or WebFetch" (line 1542), D10, D19 isolation test (line 2193); M4
- **Probe:** `master_probe.py basic` vs `tools_empty` vs `locked`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`)

```json
{{bash_master}}
```

```text
{{bash_master_cu_count}}
```

| Configuration | `system/init.tools` | Bash `echo hi` asked for | Evidence |
|---|---|---|---|
| spec block (`basic`) | 32 built-ins + 38 claude.ai connector tools + 5 shepherd | **ran, no `can_use_tool` call**, output `hi` | `captures/basic/` |
| + `tools=[]` (`tools_empty`) | 38 connector tools + 5 shepherd | model: "I cannot execute bash commands" | `captures/tools_empty/` |
| + `tools=[]`, `strict_mcp_config=True` (`locked`) | 5 shepherd only | same | `captures/locked/`, `captures/locked-syscli/` (2.1.270) |

**Variants and edge cases:** in `basic`, the model first called `ToolSearch` to load the shepherd tools, because MCP tools are *deferred* when the tool list is large. With `tools=[]` there is no `ToolSearch` and the tools are called directly (`captures/tools_empty/raw-stream.jsonl`).

**Spec alignment:** lines 1540–1543 and 113 do not match reality (see `ClaudeAgentOptions`). The isolation test at line 2193 should assert on `system/init.tools` and `system/init.mcp_servers`, not on the option values.

---

## Python hook callbacks inside the SDK master (`hooks=` → `hook_callback`)

- **Produced by:** Claude Code 2.1.259 (`control_request{subtype:"hook_callback"}`)
- **Consumed by:** a possible `authorize()`/audit placement for the master (§11, lines 1725–1751); SDK docstring recommends PreToolUse for "gate every tool call"; M4
- **Probe:** `master_probe.py locked` (`PreToolUse`, `PostToolUse`, `PostToolUseFailure` registered with `matcher=None`). Re-run: as above
- **Status:** verified live 2026-09-14 (56 hook callbacks)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`; the same `input` objects as the callback saw them are in `captures/locked/hooks.jsonl`)

```json
{{sdk_hooks}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `request.callback_id` | str | always | `hook_0/1/2` | the ids announced in `initialize` |
| `input.hook_event_name` | str | always | `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | |
| `input.tool_name` | str | always | `mcp__shepherd__fleet_summary`, `Bash`, `ToolSearch` | |
| `input.tool_input` | dict | always | | |
| `input.tool_response` | list | PostToolUse | MCP content list | |
| `input.error`, `input.is_interrupt` | str, bool | PostToolUseFailure | the `isError` text; `false` | an MCP `isError:true` result fires **PostToolUseFailure**, not PostToolUse |
| `input.duration_ms` | int | Post* | 7–21 | |
| `input.session_id`, `transcript_path`, `cwd`, `prompt_id`, `permission_mode`, `tool_use_id` | | always | `permission_mode: "default"` | same common fields as shell hooks |

**Variants and edge cases:** hook callbacks fire for tools that bypass `can_use_tool` (the `basic` Bash call has a PreToolUse `hook_callback` but no `can_use_tool`), so a PreToolUse hook is the only SDK-side interception point that sees every call.

**Spec alignment:** the spec is silent on the master using hooks. The SDK's own docstring points to a PreToolUse hook for "gate every tool call" (`captures/introspect/options-source.txt`).

---

## `interrupt()`: request, receipt, and what the turn looks like afterwards

- **Produced by:** claude-agent-sdk 0.2.152 `ClaudeSDKClient.interrupt() -> None` / Claude Code 2.1.259
- **Consumed by:** §6 `MasterRuntime.interrupt() -> None` (line 448), §11 approvals (line 1747), D31; M4
- **Probe:** `master_probe.py interrupt` (during streaming text) and `interrupt_pending_approval` (while `can_use_tool` blocks). Re-run: as above
- **Status:** verified live 2026-09-14 (interrupt during a running *tool handler* was not provoked)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt/raw-stream.jsonl`)

```json
{{interrupt_wire}}
```

```text
{{interrupt_meta}}
```

While an approval is pending (full captures: `captures/interrupt_pending_approval/raw-stream.jsonl`, `can-use-tool.jsonl`):

```json
{{interrupt_pending}}
```

```json
{{interrupt_pending_cb}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| Python return | None | always | `None` | returns in about 3 ms; it does not wait for the turn to end |
| wire request | `{"subtype":"interrupt"}` | always | | |
| wire response `still_queued` | list | always | `[]` | receipt (`interrupt_receipt_v1` capability) |
| `control_cancel_request.request_id` | str | when an approval was pending | the `can_use_tool` request id | the SDK cancels the callback coroutine |
| user notice text | str | always | `[Request interrupted by user]`, `[Request interrupted by user for tool use]` | |
| `result.subtype` / `terminal_reason` | str | always | `error_during_execution` / `aborted_streaming`, `aborted_tools` | `is_error: true` |
| `result.permission_denials[]` | list | pending-approval case | the cancelled call | |

**Variants and edge cases:**
- The client stays usable: the next `query()` on the same `ClaudeSDKClient` answered `AFTER` with the same `session_id`.
- `interrupt()` when idle also returns `None` and the CLI acknowledges it with `still_queued: []` (no error).
- The partially streamed assistant block is delivered with `"aborted": true`.

**Spec alignment:**
- Spec line 448 `interrupt(self) -> None` is aligned (it is `async` in the SDK).
- Spec line 1747 says the approval blocks the turn. Reality adds a behaviour the spec does not handle: an interrupt **cancels the pending `authorize()` coroutine**, so the approval card created at line 1737 must be withdrawn on `CancelledError` or it will outlive the turn (`captures/interrupt_pending_approval/can-use-tool.jsonl`).

---

## `resume` and `fork_session`: session identity and transcript location

- **Produced by:** claude-agent-sdk 0.2.152 → Claude Code 2.1.259 `--resume=<id>` / `--fork-session`
- **Consumed by:** §6 `MasterRuntime.resume(master_session_id)` (line 447) and the paragraph at lines 524–534, §11 `resume=state.master_session_id` (line 1535), §9 `ask()` fork (D13, M3); D30; M4
- **Probe:** `master_probe.py resume`, `resume_other_cwd`. Re-run: as above
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/resume/meta.json`, `captures/resume_other_cwd/meta.json`, `captures/resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl`)

```text
{{resume_meta}}
```

```text
{{resume_argv}}
```

Resume from a different process cwd:

```text
{{resume_other_cwd}}
```

Context the harness injected into the master's own transcript even with `setting_sources=[]` (trimmed; full capture: `captures/resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl`):

```json
{{resume_transcript_attachments}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| resumed `session_id` | str | always | **same** as the original | the resumed turn remembered `PINEAPPLE-7` |
| forked `session_id` | str | always | **new** uuid | a new transcript file appears next to the original |
| transcript path | path | always | `~/.claude/projects/<cwd with / and _ → ->/<session_id>.jsonl` | |
| cross-cwd resume | — | — | succeeded; appended to the **original** cwd's directory | no directory was created for the new cwd |

**Variants and edge cases:**
- Every resume or fork is a new `claude` subprocess (a new `initialize`, `mcp_message initialize` and `tools/list`), so tools and the system prompt are re-sent on each resume.
- The transcript contains `attachment` entries for `deferred_tools_delta`, `skill_listing`, `session_context.userEmail`, `environment`, `model` and `date`. The master's context therefore contains the account e-mail and a skill list regardless of `setting_sources`.

**Spec alignment:**
- Spec lines 447 and 524–527 (an opaque id; the SDK resumes the transcript Claude Code already wrote; `owns_history=True`) are aligned. There is no `resume()` method: `resume` is a constructor option, so `AgentSDKMaster.resume()` must rebuild the client.
- Spec line 1535 (`resume=state.master_session_id`, which survives daemon restarts) is aligned for the id. It also survived a cwd change in this probe. Survival across a Claude Code upgrade was not tested.

---

## `setting_sources` isolation: what actually reaches the master

- **Produced by:** Claude Code 2.1.259 under `--setting-sources=` / `=project` / (no flag)
- **Consumed by:** §11 line 1528, §14 2b isolation test (lines 2193–2195), §18 risk row (line 2329); D10, D19; M4
- **Probe:** `master_probe.py isolation`: a `CLAUDE.md` in the throwaway cwd saying "end every reply with ZEBRA-MARKER-41". Re-run: as above
- **Status:** partially verified. Project `CLAUDE.md` exclusion was verified live. User-scope `~/.claude/CLAUDE.md` does not exist on this machine and creating one would edit user config. cc10x exclusion is not verifiable here, because the safety rules require disabling it via flag settings in every run.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/isolation/meta.json`)

```text
{{isolation_meta}}
```

```json
{{isolation_init}}
```

| `setting_sources` | argv | project `CLAUDE.md` obeyed? | account connectors mounted? | bundled skills listed? |
|---|---|---|---|---|
| `[]` | `--setting-sources=` | **no** (`Hello.`) | yes (6 `claude.ai …` servers) | yes (17) |
| `["project"]` | `--setting-sources=project` | yes | yes | yes |
| `None` | (flag absent) | yes | yes | yes |

**Variants and edge cases:** the only option that removed the connectors was `strict_mcp_config=True`. Neither `setting_sources` nor `tools=[]` removed skills from `system/init.skills`. `tools=[]` removes the `Skill` tool, so they become unreachable.

**Spec alignment:**
- Spec line 1528 (`# no CLAUDE.md, no cc10x, no skills`) is only partly right. "no CLAUDE.md" holds for project scope. "no skills" is wrong: 17 skills are listed and a `skill_listing` attachment is injected. "no cc10x" is unverified. Account connectors and the `userEmail` session context also reach the master (`captures/isolation/raw-stream.jsonl`, `captures/resume/transcript-*.jsonl`).
- Spec line 2329 (§18) says "do not trust it". That is confirmed: the isolation test needs `tools=[]` + `strict_mcp_config=True` and should assert on `system/init.tools`/`mcp_servers`/`skills`.

---

## Tier-2 stdio MCP: server process launch and environment

- **Produced by:** Claude Code 2.1.270 (`claude -p --mcp-config <file> --strict-mcp-config`)
- **Consumed by:** §11.0 `to_stdio_mcp_server()` / `shepherd-mcp` (line 1480), §11 Two bindings (line 1695), §11 "attributed to the calling session" (line 1619); D20, D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl` (first line), `captures/stdio-mcp/meta.txt`, `captures/stdio-mcp/mcp.json`)

```text
{{stdio_meta}}
```

```json
{{stdio_start}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| server parent | process | always | `claude` (the session's own pid) | spawned at session start, before the first prompt |
| server `cwd` | path | always | the session's cwd | |
| `CLAUDE_CODE_SESSION_ID` | env str | always | equals the session's `session_id` in `stream.jsonl` | **caller identity for `shepherd-mcp`** |
| `CLAUDE_PROJECT_DIR` | env str | always | session cwd | |
| `CLAUDE_CODE_ENTRYPOINT` | env str | always | `sdk-cli` | for `-p --output-format stream-json` |
| `CLAUDECODE` | env str | always | `1` | |
| `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN` | env str | always | values not logged | set by the session, not inherited (the probe scrubbed them) |
| `env` from `mcp.json` | env | always | `PROBE_MARKER=1` | passed through |

**Variants and edge cases:** the full parent environment is inherited as well (39 variable names; `captures/stdio-mcp/mcp-wire.jsonl`).

**Spec alignment:** spec line 1619 requires audit entries "attributed to the calling session" but does not say how `shepherd-mcp` learns the caller. Reality: `CLAUDE_CODE_SESSION_ID` in the server's environment is the calling session's id, so one `shepherd-mcp` process per session can attribute every call without trusting tool arguments.

---

## Tier-2 stdio MCP: `initialize` and `tools/list` (JSON-RPC as Claude Code speaks it)

- **Produced by:** Claude Code 2.1.270 (client) / probe server (responses)
- **Consumed by:** §11.0 `to_stdio_mcp_server()` (line 1480), line 1432 ("MCP over stdio is the contract it speaks"); D32; M4
- **Probe:** `stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`; `[in ]` = what Claude Code sent, `[out]` = what the server answered, one JSON-RPC message per newline-terminated line)

```json
{{stdio_handshake}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| framing | newline-delimited JSON | always | | compact separators from Claude Code |
| `initialize.params.protocolVersion` | str | always | `2025-11-25` | the server echoed it and was accepted |
| `initialize.params.capabilities` | dict | always | `roots.listChanged: true`, `elicitation: {}` | the in-process SDK path sends `{}` |
| `initialize.params.clientInfo` | dict | always | `name: claude-code`, `version: 2.1.270` | |
| `notifications/initialized` | notification | always | no `id` | |
| `tools/list` params | — | always | none (no cursor) | pagination not exercised |
| `result.tools[]` fields accepted | | always | `name`, `title`, `description`, `inputSchema` (with `additionalProperties`, `minimum`, `description`), `annotations.readOnlyHint`, `annotations.destructiveHint` | all four tools were listed in `system/init.tools` as `mcp__probe__<name>` |

**Variants and edge cases:** `title` and `annotations` did not change how permissions were handled. `danger_note` (`destructiveHint:true`) and `echo_note` (`readOnlyHint:true`) were gated purely by `--allowedTools`.

**Spec alignment:** aligned with line 1432 and D32. The binding is plain MCP over stdio, and the model sees `mcp__<server-key>__<tool>`. The spec's `shepherd-mcp` would be mounted with the key `shepherd`, so tier-2 names are `mcp__shepherd__<tool>`, identical to the master's.

---

## Tier-2 stdio MCP: `tools/call` requests, results, errors, and what the model sees

- **Produced by:** Claude Code 2.1.270 / probe server
- **Consumed by:** §11.0 `invoke()` behind `to_stdio_mcp_server()`, §11 recursion caps ("error the agent can read", line 1722), SESSION_TOOLS (lines 1701–1706); D32; M4
- **Probe:** `stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl`). The four pairs are: success, `isError` result, JSON-RPC error, and a call missing the required `text`.

```json
{{stdio_calls}}
```

What the session's stream showed for each (trimmed; full capture: `captures/stdio-mcp/stream.jsonl`). `danger_note` never reached the server:

```json
{{stdio_stream}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `params.name` | str | always | bare `echo_note` | |
| `params.arguments` | dict | always | `{"text":"hello","count":2}`, `{}`, `{"count":5}` | **not validated by Claude Code**: a call missing a `required` property was sent |
| `params._meta.claudecode/toolUseId` | str | always | `toolu_…` | a stdio server does receive it, so it can be correlated with hook `tool_use_id` |
| `params._meta.progressToken` | int | always | 2–5 | |
| result `isError: true` | | sometimes | | model sees `tool_result.content` = the text (a **string**), `is_error: true`; stream `tool_use_result: "Error: <text>"` |
| JSON-RPC `error {code,message}` | | sometimes | `-32603 "probe internal error"` | model sees exactly the same as `isError` (`content: "probe internal error"`) |
| not-allowed tool in `-p` | | sometimes | | never sent to the server; `system/permission_denied` + `result.permission_denials[]` |

**Variants and edge cases:** a tool outside `--allowedTools` in headless `-p` is denied immediately ("you haven't granted it yet"). In an interactive (tmux) tier-2 session the same call would raise a permission prompt; that case was not probed here.

**Spec alignment:**
- Spec line 1722 (caps return "a tool error the agent can read") is aligned: both `isError` and JSON-RPC errors reach the model as readable `is_error` text.
- Spec §11.0 / D32 assume `invoke()` receives valid `args`. Reality: on the stdio binding Claude Code forwards arguments that violate `inputSchema` (`{"count":5}` without required `text`), whereas the SDK binding validates before the handler. `to_stdio_mcp_server()` must validate against `ToolDef.input_schema` itself, or the two bindings will behave differently (`captures/stdio-mcp/mcp-wire.jsonl`, `captures/locked/raw-stream.jsonl`).

---

## MCP tools in shell-hook payloads (tier-2 session)

- **Produced by:** Claude Code 2.1.270 command hooks declared in `<tmpdir>/work/.claude/settings.json`
- **Consumed by:** §8 signals (PreToolUse/PostToolUse/PostToolUseFailure/PermissionRequest folding), §11 line 1684 ("`PermissionRequest` hook surfaces them into the Needs-You rail"); D24; M1 (hooks), M4 (MCP)
- **Probe:** `stdio/run_stdio_probe.sh` with `stdio/capture_hook.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14 (`PermissionDenied` did not fire for the `-p` denial; see below)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl`)

```json
{{stdio_hooks}}
```

```text
{{stdio_hook_counts}}
```

| Field | Type | Presence | Observed values | Notes |
|---|---|---|---|---|
| `payload.tool_name` | str | always | `mcp__probe__echo_note`, `mcp__probe__fail_note`, `mcp__probe__rpc_error_note`, `mcp__probe__danger_note` | prefixed form. Split on `__` to recover server and tool |
| `payload.tool_input` | dict | always | exactly the `arguments` sent (or about to be sent) | |
| `payload.tool_response` | list[{type,text}] | PostToolUse | MCP content array, unwrapped from `result` | |
| `payload.error` | str | PostToolUseFailure | the `isError` text **or** the JSON-RPC `error.message` | the two error kinds are indistinguishable here |
| `payload.is_interrupt` | bool | PostToolUseFailure | `false` | |
| `payload.duration_ms` | int | Post* | 4–8 | |
| `payload.permission_suggestions[]` | list | PermissionRequest | `addRules` for `mcp__probe__danger_note` → `localSettings` | |
| `payload.tool_use_id` | str | Pre/Post* | equals `params._meta.claudecode/toolUseId` on the MCP wire | **absent from PermissionRequest** |
| `_ancestry` | list | always | `capture_hook.sh` → `sh` → `claude` | hooks run via `sh -c` |

**Variants and edge cases:**
- PreToolUse fired 5 times, including for `danger_note`, which was then denied. PreToolUse therefore does not imply the tool ran.
- The `-p` denial produced `PermissionRequest` but **no `PermissionDenied` hook** (0 lines).

**Spec alignment:**
- Spec line 1684 is aligned: `PermissionRequest` fires for MCP tools with `tool_name`/`tool_input`. Its payload has no `tool_use_id`, so joining a permission card to the later PreToolUse/PostToolUse needs `(session_id, tool_name, tool_input)` or ordering.
- Spec line 917 lists `PermissionDenied` among the needs-you events, but it did not fire for a headless `-p` "not granted" denial of an MCP tool (`captures/stdio-mcp/hooks.jsonl`).
