<!-- Rendered by build_section.py from SECTION.tmpl.md. Every fenced example is pulled from a capture
     file under docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/ and checked byte-for-byte against
     it before trimming; trims are marked "...". Do not hand-edit SECTION.md; edit the template and rebuild.
     AUDIT 2026-09-14: this file was then edited directly by the auditor (build_section.py / SECTION.tmpl.md were NOT
     updated, so a rebuild would undo these edits): (1) JSON excerpts re-rendered so every omitted key run or list run
     carries a "..." marker at the position it was cut, and kept keys are in capture order (every "..."-delimited
     fragment is now a byte substring of its source capture line); (2) two computed count blocks moved out of fences
     into prose; (3) Status lines for ResultMessage and interrupt() lowered to "partially verified"; (4) spec-alignment
     bullets that are omissions rather than contradictions relabelled as gaps. -->

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
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
375e53220773a12f0a2a7a666740f7fb20d31b2989b250e4076957d026b5d6ac  /root/.claude/settings.json
```

No `~/.claude.json` or user settings were edited. Every `CLAUDE*`/`ANTHROPIC*`/`AI_AGENT` variable inherited from the
calling Claude Code session was deleted before the CLI was spawned. Every throwaway settings file had
`"enabledPlugins": {"cc10x@cc10x": false}`, and **cc10x did not register or fire**. The SDK runs report `"plugins": []` in every
`system/init`. The stdio run's debug log says:

```text
2026-09-14T16:14:50.086Z [DEBUG] Read hooks.json for plugin cc10x (enabled=false; will NOT register, plugin is disabled): /root/src/cc10x-qa/plugins/cc10x/hooks/hooks.json
2026-09-14T16:14:50.114Z [DEBUG] Found 1 plugins (0 enabled, 1 disabled)
...
2026-09-14T16:14:50.118Z [DEBUG] Registered 0 hooks from 0 plugins
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
python: 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
sys.executable: /tmp/shp-sdk-9IOKNs/venv/bin/python
claude-agent-sdk==0.2.152
mcp==2.2.0
mcp-types==2.2.0
anyio==4.15.1
pydantic==2.13.5
claude_agent_sdk.__version__ = 0.2.152
bundled __cli_version__ = 2.1.259
bundled binary: /tmp/shp-sdk-9IOKNs/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude exists=True size=216677784
bundled `claude --version`: 2.1.259 (Claude Code)
PATH `claude --version`: 2.1.270 (Claude Code)
__all__ = ["AgentDefinition", "AssistantMessage", "BaseHookInput", "CLIConnectionError", "CLIJSONDecodeError", "CLINotFoundError", "CanUseTool", "CanUseToolShad...
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
- Gap, not a contradiction: spec line 406 lists `claude-agent-sdk` as a backend dependency but does not say the package ships a second Claude Code binary. In reality the master runs the bundled 2.1.259, and it will drift from the fleet's `claude` unless `AgentSDKMaster` pins `cli_path` (`captures/introspect/sdk-install.txt`, `captures/locked/meta.json` vs `captures/locked-syscli/meta.json`).

---

## `ClaudeAgentOptions` (as installed)

- **Produced by:** claude-agent-sdk 0.2.152, `claude_agent_sdk/types.py:1940`
- **Consumed by:** §11 Master configuration (spec lines 1525–1537), §6 `MasterRuntime.configure/resume`; D10, D19, D20, D30, D32; M4
- **Probe:** `introspect_sdk.py` → `captures/introspect/options-signature.txt`, `options-source.txt`. The CLI argv each option produces is in `captures/<scenario>/meta.json`. Re-run: as above, plus `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14 (signature from the installed source; the option→argv mapping and the behaviour of `tools`, `allowed_tools`, `disallowed_tools`, `setting_sources`, `strict_mcp_config`, `can_use_tool`, `resume`, `fork_session`, `cwd`, `settings`, `hooks`, `include_partial_messages`, `max_turns` and `cli_path` were exercised live)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/introspect/options-signature.txt`)

```text
dataclasses.fields:
  tools: list[str] | claude_agent_sdk.types.ToolsPreset | None  = None
  allowed_tools: list[str]  = 'factory:list'
  system_prompt: str | claude_agent_sdk.types.SystemPromptPreset | claude_agent_sdk.types.SystemPromptFile | None  = None
  mcp_servers: dict[str, claude_agent_sdk.types.McpStdioServerConfig | claude_agent_sdk.types.McpSSEServerConfig | claude_agent_sdk.types.McpHttpServerConfig | claude_agent_sdk.types.McpSdkServerConfig] | str | pathlib.Path  = 'fa...
  strict_mcp_config: <class 'bool'>  = False
  permission_mode: typing.Optional[typing.Literal['default', 'acceptEdits', 'plan', 'bypassPermissions', 'dontAsk', 'auto']]  = None
...
  resume: str | None  = None
  session_id: str | None  = None
  max_turns: int | None  = None
...
  disallowed_tools: list[str]  = 'factory:list'
  model: str | None  = None
...
  cwd: str | pathlib.Path | None  = None
  cli_path: str | pathlib.Path | None  = None
  settings: str | None  = None
...
  env: dict[str, str]  = 'factory:dict'
...
  can_use_tool: collections.abc.Callable[[str, dict[str, typing.Any], claude_agent_sdk.types.ToolPermissionContext], collections.abc.Awaitable[claude_agent_sdk.types.PermissionResultAllow | claude_agent_sdk.types.PermissionResultD...
  hooks: dict[typing.Union[typing.Literal['PreToolUse'], typing.Literal['PostToolUse'], typing.Literal['PostToolUseFailure'], typing.Literal['UserPromptSubmit'], typing.Literal['Stop'], typing.Literal['SubagentStop'], typing.Liter...
...
  include_partial_messages: <class 'bool'>  = False
...
  fork_session: <class 'bool'>  = False
...
  setting_sources: list[typing.Literal['user', 'project', 'local']] | None  = None
  skills: typing.Union[list[str], typing.Literal['all'], NoneType]  = None
...
  effort: typing.Optional[typing.Literal['low', 'medium', 'high', 'xhigh', 'max']]  = None
```

The docstrings that decide the semantics (trimmed; full capture: `captures/introspect/options-source.txt`):

```text
    tools: list[str] | ToolsPreset | None = None
    """Specify the base set of available built-in tools.
...
    - ``[]`` (empty list) — Disable all built-in tools.
...
    allowed_tools: list[str] = field(default_factory=list)
    """Tool names that are auto-allowed without prompting for permission.
...
    To restrict which tools are available at all, use ``tools``.
...
    strict_mcp_config: bool = False
    """When ``True``, only use MCP servers passed via :attr:`mcp_servers`,
    ignoring all other MCP configurations the CLI would otherwise load (e.g.
...
    can_use_tool: CanUseTool | None = None
...
    it is the SDK replacement for the interactive permission prompt. It is *not*
    invoked for tool calls already permitted by ``allowed_tools``,
    ``permission_mode`` (e.g. ``"acceptEdits"`` / ``"bypassPermissions"``), or
    ``permissions.allow`` rules in settings, since those never reach a prompt.
...
    setting_sources: list[SettingSource] | None = None
```

The argv this becomes for the `locked` master (full capture: `captures/locked/meta.json`):

```text
  "argv": [
    [
      "/tmp/shp-sdk-9IOKNs/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude",
      "--output-format",
      "stream-json",
      "--verbose",
      "--system-prompt",
      "You are a probe orchestrator. Follow the user's instructions literally and briefly.",
      "--tools",
      "",
      "--allowedTools",
      "mcp__shepherd__fleet_summary,mcp__shepherd__spawn_session,mcp__shepherd__fail_tool,mcp__shepherd__raise_tool",
      "--max-turns",
      "14",
      "--disallowedTools",
      "Agent,Task",
      "--model",
      "claude-haiku-4-5-20251001",
      "--permission-prompt-tool",
      "stdio",
      "--settings",
      "/tmp/shp-sdk-9IOKNs/flag-settings.json",
      "--mcp-config",
      "{\"mcpServers\": {\"shepherd\": {\"type\": \"sdk\", \"name\": \"shepherd\"}}}",
      "--strict-mcp-config",
      "--setting-sources=",
      "--input-format",
      "stream-json"
    ]
  ],
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
    "CanUseToolShadowedWarning: can_use_tool will not be invoked for: mcp__shepherd__fleet_summary, mcp__shepherd__spawn_session, mcp__shepherd__fail_tool, mcp__shepherd__raise_tool. An allowed_tools entry that allows a whole tool auto-approves it before the callback is consulted. To gate every tool call, use a PreToolUse hook; or narrow the entry so calls fall through to can_use_tool. Allow rules...
```

- `system_prompt=None` still sends `--system-prompt ""`. A string replaces Claude Code's prompt entirely (`captures/introspect/internals-source.txt`, `_build_command`).
- `ClaudeSDKClient` has no `resume()` or `configure()` method. Resume and tool mounting are construction-time options, so each `resume` means a new CLI subprocess. Mid-session methods that exist: `interrupt`, `set_model`, `set_permission_mode`, `toggle_mcp_server(server_name, enabled)`, `reconnect_mcp_server`, `get_mcp_status`, `get_context_usage`, `stop_task`, `rewind_files` (`captures/introspect/client-api.txt`).

**Spec alignment:**
- Spec line 1540 says `allowed_tools` "stays a strict allowlist", and line 113 (D10) says "`allowed_tools` = orchestration MCP tools only". In reality `allowed_tools` only **auto-approves**. With the spec block as written, `system/init.tools` lists 32 built-ins (Bash, Read, Write, Edit, WebFetch, Skill, SendMessage, Workflow, …), plus 38 claude.ai connector tools (Gmail and Calendar are connected on this account), plus the 5 shepherd tools (`captures/basic/raw-stream.jsonl`). Restricting availability needs `tools=[]`, and dropping the account connectors additionally needs `strict_mcp_config=True` (`captures/tools_empty/`, `captures/locked/`).
- Spec lines 1542–1543 say "The master still has no Read, Write, Edit, Bash, or WebFetch". In reality the `basic` master ran `Bash` `echo hi` with **no** `can_use_tool` call. The likely cause is that Claude Code auto-allows read-only Bash; this is inferred, not proven. The flag settings held only `enabledPlugins`, and `~/.claude/settings.json` has no `permissions` block (see "Built-in tools reachable from the spec-configured master" below).
- Spec line 1534 says `can_use_tool=authorize`. In reality the callback signature is `(tool_name: str, input: dict, ToolPermissionContext) -> PermissionResultAllow|PermissionResultDeny`, not `authorize(tool: ToolDef, args, ctx: CallerContext) -> Decision` (line 1728). It is **never invoked for tools listed in `allowed_tools`**: the SDK warns about exactly this, and `captures/locked/can-use-tool.jsonl` has only the one tool that was *not* in `allowed_tools`. So either `authorize()` runs inside the exporter's handler (`invoke()`, line 1464), which is the D32 design and makes line 1534 redundant, or `allowed_tools` must be empty for the gate to see anything. (Only tools mounted from `SHEPHERD_TOOLS` but left out of `ORCHESTRATOR_TOOLS` at line 1530, and built-ins Claude Code does not auto-allow, would still reach the callback.)
- Gap, not a contradiction: spec line 1536 says `cwd=None  # it delegates; it does not edit`. The comment gives a reason; it does not claim that `cwd=None` removes tools (that claim is at lines 1542–1543, above). Still, `cwd=None` only means "the daemon's cwd". It does not remove editing tools (only `tools=[]` does), and it determines the `~/.claude/projects/<cwd-key>/` directory the master's transcript is written to.
- Spec line 1529 says `disallowed_tools=["Agent","Task"]`. That is aligned: no `Agent`/`Task` in `tools`. The subagent roster (`agents`: `claude, Explore, general-purpose, Plan, statusline-setup`) is still reported in `system/init`.

---

## Control protocol handshake (SDK ↔ CLI over stdio)

- **Produced by:** claude-agent-sdk 0.2.152 (request) / Claude Code 2.1.259 (response)
- **Consumed by:** `AgentSDKMaster` internals (§6, §11); D30 (seat), D32; M4
- **Probe:** `master_probe.py` (every scenario). Re-run: `<venv>/bin/python docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py locked docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures <tmpdir>`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{"type": "control_request", "request_id": "req_1_9b098ea6", "request": {"subtype": "initialize", "hooks": {"PreToolUse": [{"matcher": null, "hookCallbackIds": ["hook_0"]}], "PostToolUse": [{"matcher": null, "hookCallbackIds": ["hook_1"]}], "PostToolUseFailure": [{"matcher": null, "hookCallbackIds": ["hook_2"]}]}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "req_1_9b098ea6", "response": {"commands": [{"name": "deep-research", "description": "Deep research harness \u2014 fan-out web searches, fetch sources, adversarially verify claims, ...", "argumentHint": ""}, "..."], "agents": [{"name": "claude", "description": "Catch-all for any task that doesn't fit a more specific agent. FleetView's default when no..."}, "..."], "...": "...", "models": [{"value": "default", "resolvedModel": "claude-opus-5[1m]", "displayName": "Default (recommended)", "description": "Opus 5 with 1M context \u00b7 Best for everyday, complex tasks", "supportsEffort": true, "supportedEffortLevels": ["low", "..."], "supportsAdaptiveThinking": true, "supportsFastMode": true, "supportsAutoMode": true}, "..."], "account": {"email": "<redacted>", "organization": "<redacted>", "subscriptionType": "Claude Max", "apiProvider": "firstParty"}, "pid": 4045135, "current_permission_mode": "default", "hooks_applied": true, "analytics_disabled": false, "...": "...", "remote_control_available": true, "...": "...", "session_state": "idle"}}}
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
{"type": "system", "subtype": "init", "cwd": "/tmp/shp-sdk-9IOKNs/work-locked", "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "tools": ["mcp__shepherd__fail_tool", "mcp__shepherd__fleet_summary", "mcp__shepherd__kill_session", "..."], "mcp_servers": [{"name": "shepherd", "status": "connected"}], "model": "claude-haiku-4-5-20251001", "permissionMode": "default", "slash_commands": ["deep-research", "design-sync", "dataviz", "..."], "terminal_slash_commands": ["doctor", "color"], "apiKeySource": "none", "claude_code_version": "2.1.259", "output_style": "default", "agents": ["claude", "Explore", "general-purpose", "..."], "skills": ["deep-research", "design-sync", "dataviz", "..."], "plugins": [], "capabilities": ["interrupt_receipt_v1", "interrupt_cancel_queued_v1", "msg_lifecycle_v1"], "analytics_disabled": false, "product_feedback_disabled": false, "uuid": "df5960b8-e361-42ae-80f8-1ee7b6cbd5c2", "memory_paths": {"auto": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-locked/memory/"}, "messaging_socket_path": "/run/user/0/cc-socks/4045135.sock", "fast_mode_state": "off", "fast_mode_disabled_reason": "sdk_opt_in_required"}
```

The same message for the spec's option block as written (`basic`; full capture: `captures/basic/raw-stream.jsonl`):

```json
{"type": "system", "subtype": "init", "...": "...", "tools": ["AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList", "DesignSync", "Edit", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree", "ListAgents", "Monitor", "NotebookEdit", "PushNotification", "Read", "RemoteTrigger", "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "ToolSearch", "WebFetch", "WebSearch", "Workflow", "Write", "mcp__claude_ai_Gmail__apply_sensitive_message_label", "...", "mcp__shepherd__fail_tool", "mcp__shepherd__fleet_summary", "mcp__shepherd__kill_session", "mcp__shepherd__raise_tool", "mcp__shepherd__spawn_session"], "mcp_servers": [{"name": "claude.ai Google Drive", "status": "needs-auth"}, {"name": "claude.ai Slack", "status": "needs-auth"}, {"name": "claude.ai Notion", "status": "needs-auth"}, {"name": "claude.ai Google Calendar", "status": "connected"}, {"name": "claude.ai Atlassian Rovo", "status": "needs-auth"}, {"name": "claude.ai Gmail", "status": "connected"}, {"name": "shepherd", "status": "connected"}], "...": "...", "apiKeySource": "none", "...": "...", "plugins": [], "...": "..."}
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
- Spec line 1528 comments `setting_sources=[]` as "no CLAUDE.md, no cc10x, no skills". In reality `skills` has 17 entries and a `skill_listing` attachment is injected into the master's context. All 17 are skills bundled with Claude Code (`deep-research`, `dataviz`, `code-review`, `loop`, …). No user or plugin skill appeared, but the cc10x plugin was also disabled by flag settings, so that exclusion is not isolated. Project `CLAUDE.md` *is* excluded. See the isolation schema (`captures/locked/raw-stream.jsonl`, `captures/resume/transcript-*.jsonl`).
- Spec §11 Connectors rule 4 (lines 1600–1603) says health is polled. `system/init.mcp_servers[].status` and `ClaudeSDKClient.get_mcp_status()` are the SDK-side sources (`captures/introspect/client-api.txt`). Polling is not probed.

---

## `AssistantMessage` and its content blocks

- **Produced by:** Claude Code 2.1.259 stream-json → parsed by claude-agent-sdk 0.2.152
- **Consumed by:** §6 `MasterRuntime.send() -> AsyncIterator[Event]`, §12 Chat page; D30; M4
- **Probe:** `master_probe.py locked` (and all others). Re-run: as above
- **Status:** verified live 2026-09-14 (135 assistant objects; `text`, `thinking` and `tool_use` blocks seen. `ServerToolUseBlock`/`ServerToolResultBlock` are not observed)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/locked/raw-stream.jsonl`)

```json
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckNHZssSyZTFkaHLFL", "type": "message", "role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "EoQHCrIBCBEYAipAyHNEJCwDQjsYH2xXHaVSsP06ht46PFO0c9Qdx1DfzMm7..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1488, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 3, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "c5473659-b8a3-4b17-9960-a3dcdca30139", "timestamp": "2026-09-14T16:05:25.311Z", "request_id": "req_011Cf3ckMo4DB2bT48CVxwJh"}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckNHZssSyZTFkaHLFL", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "I'll execute these steps in order, one at a time.\n\n**Step 1:..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1488, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 3, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "f5b93b58-413f-445f-86c5-4764261d738a", "timestamp": "2026-09-14T16:05:25.518Z", "request_id": "req_011Cf3ckMo4DB2bT48CVxwJh"}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3ckcrBdsdaV3aCbSiCW", "type": "message", "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "name": "mcp__shepherd__kill_session", "input": {"id": "ses_a1"}, "caller": {"type": "direct"}}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 1975, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "...": "...", "output_tokens": 8, "service_tier": "standard", "...": "..."}, "diagnostics": null, "context_management": null}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "7f544a12-9897-45ef-b829-248ea4af579a", "timestamp": "2026-09-14T16:05:27.989Z", "request_id": "req_011Cf3ckcNtpqVt9B3d6ZTpt", "tool_use_meta": [{"id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "display_name": "Kill Session", "server_display_name": "shepherd"}]}
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
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "type": "tool_result", "content": [{"type": "text", "text": "killed ses_a1"}]}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "8c817b6b-78d8-4a76-83b7-f0f46a2b56fc", "timestamp": "2026-09-14T16:05:28.026Z", "tool_use_result": [{"type": "text", "text": "killed ses_a1"}]}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "max_children_per_session=5 reached", "is_error": true, "tool_use_id": "toolu_012FdXhQgMDRg25WPkfmz7iw"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "7f08c489-2a2f-409c-b9d2-7424e879d08c", "timestamp": "2026-09-14T16:05:29.089Z", "tool_use_result": "Error: max_children_per_session=5 reached"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "handler exploded on purpose", "is_error": true, "tool_use_id": "toolu_01RYM214S5Pymkp8hiN7UKVw"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "f2d35dec-e5b0-42a7-95b3-da228c79e6de", "timestamp": "2026-09-14T16:05:30.469Z", "tool_use_result": "Error: handler exploded on purpose"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Input validation error: 'task' is a required property", "is_error": true, "tool_use_id": "toolu_019wiReaC5V2GxjuEChfoGmC"}]}, "parent_tool_use_id": null, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "uuid": "70dd4cde-0408-4e59-b82d-b502d06e858b", "timestamp": "2026-09-14T16:05:31.603Z", "tool_use_result": "Error: Input validation error: 'task' is a required property"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "you declined this", "is_error": true, "tool_use_id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM"}]}, "parent_tool_use_id": null, "session_id": "29135891-805b-46d1-8b1a-a9281447720f", "uuid": "08d8d444-18ad-4444-b13d-427c98124c47", "timestamp": "2026-09-14T16:09:34.002Z", "tool_use_result": "Error: you declined this", "tool_result_meta": [{"id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM", "non_execution_kind": "permission-rule"}]}
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
- **Status:** partially verified (live 2026-09-14: 19 results, 17 `success`, 2 `error_during_execution`. The subtypes `error_max_turns`, `error_max_budget_usd`, API-error results with `api_error_status` set, and `structured_output` were not provoked, so their shapes are not verified)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/basic/raw-stream.jsonl`)

```json
{"duration_api_ms": 30789, "stop_reason": "end_turn", "session_id": "38678603-2eef-404b-9504-d92993fb025f", "total_cost_usd": 0.05933240000000001, "usage": {"input_tokens": 81, "cache_creation_input_tokens": 16800, "cache_read_input_tokens": 120664, "output_tokens": 2497, "...": "...", "service_tier": "standard", "...": "..."}, "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 1121, "outputTokens": 2509, "cacheReadInputTokens": 120664, "cacheCreationInputTokens": 16800, "webSearchRequests": 0, "costUSD": 0.05933240000000001, "contextWindow": 200000, "maxOutputTokens": 32000, "thinkingTokens": 1895, "canonicalModel": "claude-haiku-4-5", "provider": "firstParty", "costBasis": "list"}}, "permission_denials": [], "terminal_reason": "completed", "fast_mode_state": "off", "fast_mode_disabled_reason": "sdk_opt_in_required", "subagent_stats": {"spawned": 0, "...": "...", "max_depth": 0, "...": "..."}, "is_error": false, "num_turns": 9, "subtype": "success", "api_error_status": null, "result": "DONE", "ttft_ms": 5932, "type": "result", "duration_ms": 30276, "uuid": "e6a97abf-2153-4e31-a024-4ff58461c270", "ttft_stream_ms": 636, "time_to_request_ms": 66, "queued_turn_count": 0}
```

Interrupted turns (`captures/interrupt/raw-stream.jsonl`, `captures/interrupt_pending_approval/raw-stream.jsonl`):

```json
{"duration_api_ms": 751, "stop_reason": null, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "total_cost_usd": 0.000988, "...": "...", "permission_denials": [], "terminal_reason": "aborted_streaming", "...": "...", "is_error": true, "num_turns": 2, "subtype": "error_during_execution", "errors": ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=null"], "type": "result", "duration_ms": 7121, "uuid": "7ec13d9a-5153-45a0-b188-0d6615f93b20", "queued_turn_count": 0}
{"duration_api_ms": 2255, "stop_reason": "tool_use", "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "total_cost_usd": 0.0029430000000000003, "...": "...", "permission_denials": [{"tool_name": "mcp__shepherd__kill_session", "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F", "tool_input": {"id": "ses_slow"}}], "terminal_reason": "aborted_tools", "...": "...", "is_error": true, "num_turns": 3, "subtype": "error_during_execution", "errors": ["[ede_diagnostic] result_type=user last_content_type=n/a stop_reason=tool_use"], "type": "result", "duration_ms": 7933, "uuid": "2c46ad1e-cfe7-470a-92c9-681d35fcb263", "queued_turn_count": 0}
```

What the SDK parser keeps (`captures/locked/messages.jsonl`):

```json
{"_ts": "2026-09-14T16:05:34.233Z", "_label": "turn1", "_class": "ResultMessage", "fields": {"subtype": "success", "duration_ms": 10746, "duration_api_ms": 11614, "is_error": false, "num_turns": 7, "session_id": "15014424-acaa-4260-976f-1c7d410304c9", "stop_reason": "end_turn", "total_cost_usd": 0.020229, "usage": {"input_tokens": 14699, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 886, "output_tokens_details": {"thinking_tokens": 427}, "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}, "service_tier": "standard", "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0}, "inference_geo": "not_available", "iter...
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
{"type": "control_response", "response": {"...": "...", "response": {"...": "...", "account": {"email": "<redacted>", "organization": "<redacted>", "subscriptionType": "Claude Max", "apiProvider": "firstParty"}, "...": "..."}}}
{"...": "...", "total_cost_usd": 0.05933240000000001, "...": "...", "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 1121, "outputTokens": 2509, "cacheReadInputTokens": 120664, "cacheCreationInputTokens": 16800, "webSearchRequests": 0, "costUSD": 0.05933240000000001, "contextWindow": 200000, "maxOutputTokens": 32000, "thinkingTokens": 1895, "canonicalModel": "claude-haiku-4-5", "provider": "firstParty", "costBasis": "list"}}, "...": "..."}
```

```text
date: 2026-09-14T16:15:25Z
PATH claude --version: 2.1.270 (Claude Code)
~/.claude/.credentials.json exists: yes
ANTHROPIC_* env names in the calling shell: 
(master_probe.py additionally deletes every CLAUDE*/ANTHROPIC*/AI_AGENT var before spawning the CLI)
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
{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1789414800, "rateLimitType": "five_hour", "overageStatus": "rejected", "overageDisabledReason": "org_level_disabled", "isUsingOverage": false, "unifiedWindows": {"five_hour": {"utilization": 0.31, "resetsAt": 1789414800}, "seven_day": {"utilization": 0.07, "resetsAt": 1789934400}}}, "uuid": "ea0afbd7-e7ea-4e4f-9d9a-e6dada520b6a", "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"}
{"type": "system", "subtype": "status", "status": "requesting", "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "3732a84f-5e62-45db-b0d2-7136dbec491f"}
{"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 50, "estimated_tokens_delta": 50, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "bebaace1-bebe-4b01-ba3c-b45ac9cfa728"}
{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "", "estimated_tokens": 50}}, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "parent_tool_use_id": null, "uuid": "8e4a6c7b-21a1-4892-9870-097bebb90562"}
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
def tool(
    name: str,
    description: str,
    input_schema: type | dict[str, Any],
    annotations: _McpToolAnnotations | None = None,
) -> Callable[[Callable[[Any], Awaitable[dict[str, Any]]]], SdkMcpTool[Any]]:
...
def create_sdk_mcp_server(
    name: str, version: str = "1.0.0", tools: list[SdkMcpTool[Any]] | None = None
) -> McpSdkServerConfig:
...
        >>> config = McpSdkServerConfig(type="sdk", name="mine", instance=my_server)
...
                jsonschema.validate(instance=arguments, schema=schemas[tool_name])
...
                return _tool_error_result(f"Input validation error: {e.message}")
...
                    "isError": result.get("is_error", False),
...
        except Exception as e:
            return _tool_error_result(str(e))
...
    return McpSdkServerConfig(type="sdk", name=name, instance=server)
...
    annotations: _McpToolAnnotations | None = None
```

The MCP `initialize` and `tools/list` exchange for the in-process server. It is tunnelled through the CLI as `control_request{subtype:"mcp_message"}`, and the SDK answers with `control_response{mcp_response}`:

```json
{"type": "control_request", "request_id": "b01c57e3-ec06-4af7-96a4-8d182e7bf7ed", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "claude-code", "title": "Claude Code", "version": "2.1.259", "description": "Anthropic's agentic coding tool", "websiteUrl": "https://claude.com/claude-code"}}, "jsonrpc": "2.0", "id": 0}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "b01c57e3-ec06-4af7-96a4-8d182e7bf7ed", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 0, "result": {"capabilities": {"experimental": {}, "tools": {"listChanged": false}}, "protocolVersion": "2025-11-25", "serverInfo": {"name": "shepherd", "version": "1.0.0"}}}}}}
{"type": "control_request", "request_id": "ca720a2f-f404-4391-8c4f-153cdb2db690", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/list", "jsonrpc": "2.0", "id": 1}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "ca720a2f-f404-4391-8c4f-153cdb2db690", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"description": "Return counts of sessions by bucket. Takes no arguments.", "inputSchema": {"properties": {}, "type": "object"}, "name": "fleet_summary"}, {"description": "Spawn a session in a project with a task.", "inputSchema": {"properties": {"project_id": {"type": "string"}, "task": {"type": "string"}, "model": {"type": ["string", "null"]}}, "required": ["project_id", "task"], "type": "object"}, "name": "spawn_session"}, {"description": "Kill a session by id.", "inputSchema": {"properties": {"id": {"type": "string"}}, "required": ["id"], "type": "object"}, "name": "kill_session"}, {"description": "A tool that always reports an error result.", "inputSchema": {"properties": {"reason": {"type": "string"}}, "required": ["reason"], "type": "object"}, "name": "fail_tool"}, {"description": "A tool whose handler raises an exception.", "inputSchema": {"properties": {}, "type": "object"}, "name": "raise_tool"}]}}}}}
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
{"type": "control_request", "request_id": "9ac59657-09da-4203-b9e6-31a2dd1050f5", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "kill_session", "arguments": {"id": "ses_a1"}, "_meta": {"claudecode/toolUseId": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "progressToken": 4}}, "jsonrpc": "2.0", "id": 4}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "9ac59657-09da-4203-b9e6-31a2dd1050f5", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 4, "result": {"content": [{"text": "killed ses_a1", "type": "text"}], "isError": false}}}}}
{"type": "control_request", "request_id": "23d45692-70a7-4c45-a0a8-717a7db770f0", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "fail_tool", "arguments": {"reason": "probe"}, "_meta": {"claudecode/toolUseId": "toolu_012FdXhQgMDRg25WPkfmz7iw", "progressToken": 5}}, "jsonrpc": "2.0", "id": 5}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "23d45692-70a7-4c45-a0a8-717a7db770f0", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 5, "result": {"content": [{"text": "max_children_per_session=5 reached", "type": "text"}], "isError": true}}}}}
{"type": "control_request", "request_id": "a8aa4e0c-42a1-4bee-9006-a5e81f5fa7d5", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "raise_tool", "arguments": {}, "_meta": {"claudecode/toolUseId": "toolu_01RYM214S5Pymkp8hiN7UKVw", "progressToken": 6}}, "jsonrpc": "2.0", "id": 6}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "a8aa4e0c-42a1-4bee-9006-a5e81f5fa7d5", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 6, "result": {"content": [{"text": "handler exploded on purpose", "type": "text"}], "isError": true}}}}}
{"type": "control_request", "request_id": "a3d2b8cb-d8ec-4dda-a2a6-406f58c46138", "request": {"subtype": "mcp_message", "server_name": "shepherd", "message": {"method": "tools/call", "params": {"name": "spawn_session", "arguments": {"project_id": "p2"}, "_meta": {"claudecode/toolUseId": "toolu_019wiReaC5V2GxjuEChfoGmC", "progressToken": 7}}, "jsonrpc": "2.0", "id": 7}}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "a3d2b8cb-d8ec-4dda-a2a6-406f58c46138", "response": {"mcp_response": {"jsonrpc": "2.0", "id": 7, "result": {"content": [{"text": "Input validation error: 'task' is a required property", "type": "text"}], "isError": true}}}}}
```

What the Python handler actually received and returned (full capture: `captures/locked/handler-calls.jsonl`):

```json
{"_ts": "2026-09-14T16:05:25.616Z", "tool": "fleet_summary", "received": {}, "returned": {"content": [{"type": "text", "text": "{\"running\": 2, \"needs_you\": [\"ses_a1\"], \"stopped\": 1}"}]}}
{"_ts": "2026-09-14T16:05:26.878Z", "tool": "spawn_session", "received": {"project_id": "p1", "task": "write tests"}, "returned": {"content": [{"type": "text", "text": "ses_new42"}]}}
{"_ts": "2026-09-14T16:05:28.016Z", "tool": "kill_session", "received": {"id": "ses_a1"}, "returned": {"content": [{"type": "text", "text": "killed ses_a1"}]}}
{"_ts": "2026-09-14T16:05:29.019Z", "tool": "fail_tool", "received": {"reason": "probe"}, "returned": {"content": [{"type": "text", "text": "max_children_per_session=5 reached"}], "is_error": true}}
{"_ts": "2026-09-14T16:05:30.461Z", "tool": "raise_tool", "received": {}, "returned": "RAISES RuntimeError"}
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
{"type": "control_request", "request_id": "15010c03-fdae-4d46-91e5-7625b8c75f43", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_a1"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "15010c03-fdae-4d46-91e5-7625b8c75f43", "response": {"behavior": "allow", "updatedInput": {"id": "ses_a1"}}}}
{"type": "control_request", "request_id": "24d91a79-57b6-457a-a76a-c39575ae194e", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_x"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_01Pr6kGMH2yKsGGgfJggVXFM"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "24d91a79-57b6-457a-a76a-c39575ae194e", "response": {"behavior": "deny", "message": "you declined this"}}}
```

What the Python callback received (full capture: `captures/locked/can-use-tool.jsonl`):

```json
{"_ts": "2026-09-14T16:05:28.001Z", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_a1"}, "context": {"signal": null, "suggestions": [{"type": "addRules", "rules": [{"tool_name": "mcp__shepherd__kill_session", "rule_content": null}], "behavior": "allow", "mode": null, "directories": null, "destination": "localSettings"}], "tool_use_id": "toolu_01VcYQNKad4ejYQGSP4eZ3ov", "agent_id": null, "blocked_path": null, "decision_reason": null, "title": null, "display_name": "Kill Session", "description": null}, "returned": {"behavior": "allow", "updated_input": {"id": "ses_a1"}}}
```

A callback that blocks for 75 s (full capture: `captures/slow_approval/can-use-tool.jsonl`, `meta.json`):

```text
{"_ts": "2026-09-14T16:07:18.944Z", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T16:08:34.014Z", "phase": "returning allow after sleep", "slept_s": 75}
  "turn_wall_s": 77.29,
  "status": "ok",
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
{"type": "assistant", "message": {"...": "...", "content": [{"type": "tool_use", "id": "toolu_0143BWgWYJE8531p4aCq84rp", "name": "Bash", "input": {"command": "echo hi"}, "caller": {"type": "direct"}}], "...": "..."}, "...": "..."}
{"type": "control_request", "request_id": "9206de57-5623-4705-b1c8-e92a8d53f981", "request": {"subtype": "hook_callback", "callback_id": "hook_0", "input": {"session_id": "38678603-2eef-404b-9504-d92993fb025f", "transcript_path": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-basic/38678603-2eef-404b-9504-d92993fb025f.jsonl", "cwd": "/tmp/shp-sdk-9IOKNs/work-basic", "prompt_id": "c6200a3f-0b7d-4d62-aa8a-1734e9bd1598", "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "echo hi"}, "tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp"}, "tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp"}}
{"type": "user", "message": {"role": "user", "content": [{"tool_use_id": "toolu_0143BWgWYJE8531p4aCq84rp", "type": "tool_result", "content": "hi", "is_error": false}]}, "parent_tool_use_id": null, "session_id": "38678603-2eef-404b-9504-d92993fb025f", "uuid": "ea8740ca-2ab5-49ef-b180-7d77cbad87e1", "timestamp": "2026-09-14T16:04:28.191Z", "tool_use_result": {"stdout": "hi", "stderr": "", "interrupted": false, "isImage": false, "noOutputExpected": false}}
```

Count (computed, not an excerpt): `captures/basic/raw-stream.jsonl` contains exactly 1 `can_use_tool` control_request, for `mcp__shepherd__kill_session`; `captures/basic/can-use-tool.jsonl` has 1 line. There is none for `Bash`.

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
{"type": "control_request", "request_id": "f320ce58-9979-4275-8380-3e37723f049d", "request": {"subtype": "hook_callback", "callback_id": "hook_0", "input": {"session_id": "15014424-acaa-4260-976f-1c7d410304c9", "transcript_path": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-locked/15014424-acaa-4260-976f-1c7d410304c9.jsonl", "cwd": "/tmp/shp-sdk-9IOKNs/work-locked", "prompt_id": "4d869e92-a674-4cba-a091-2ea9014b19db", "permission_mode": "default", "hook_event_name": "PreToolUse", "tool_name": "mcp__shepherd__fleet_summary", "tool_input": {}, "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX"}, "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX"}}
{"type": "control_request", "...": "...", "request": {"subtype": "hook_callback", "callback_id": "hook_1", "input": {"...": "...", "permission_mode": "default", "hook_event_name": "PostToolUse", "tool_name": "mcp__shepherd__fleet_summary", "tool_input": {}, "tool_response": [{"type": "text", "text": "{\"running\": 2, \"needs_you\": [\"ses_a1\"], \"stopped\": 1}"}], "tool_use_id": "toolu_01MAsS4rbdbtGJsAFQKVstgX", "duration_ms": 16}, "...": "..."}}
{"type": "control_request", "...": "...", "request": {"subtype": "hook_callback", "callback_id": "hook_2", "input": {"...": "...", "permission_mode": "default", "hook_event_name": "PostToolUseFailure", "tool_name": "mcp__shepherd__fail_tool", "tool_input": {"reason": "probe"}, "tool_use_id": "toolu_012FdXhQgMDRg25WPkfmz7iw", "error": "max_children_per_session=5 reached", "is_interrupt": false, "duration_ms": 21}, "...": "..."}}
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
- **Status:** partially verified (live 2026-09-14 for an interrupt during streaming text, while idle, and while `can_use_tool` was pending. An interrupt during a running in-process *tool handler* was not provoked)

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/interrupt/raw-stream.jsonl`)

```json
{"type": "control_request", "request_id": "req_2_6b2188ca", "request": {"subtype": "interrupt"}}
{"type": "control_response", "response": {"subtype": "success", "request_id": "req_2_6b2188ca", "response": {"still_queued": []}}}
{"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001", "id": "msg_011Cf3coQy8nNHYY62ewP3xA", "type": "message", "role": "assistant", "content": [{"type": "text", "text": "one\ntwo\nthree\nfour\nfive\nsix\nseven\neight\nnine\nten\neleven\ntwel..."}], "container": null, "stop_reason": null, "stop_sequence": null, "stop_details": null, "usage": {"input_tokens": 10, "cache_creation_input_tokens": 3288, "cache_read_input_tokens": 10196, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 3288}, "output_tokens": 4, "service_tier": "standard", "inference_geo": "not_available"}, "diagnostics": null, "context_management": null}, "...": "...", "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "...": "...", "aborted": true}
{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}, "parent_tool_use_id": null, "session_id": "6438769d-8836-42e2-a469-8b84200d0660", "uuid": "106c3ad9-83f3-49f0-8e56-341cd6c0bd86", "timestamp": "2026-09-14T16:06:11.779Z"}
```

```text
  "scenario": "interrupt",
...
  "interrupt": {
    "after_stream_events": 25,
    "since_query_s": 7.74,
    "returned": "None",
    "call_s": 0.003
  },
...
  "interrupt_when_idle": {
    "returned": "None"
  },
```

While an approval is pending (full captures: `captures/interrupt_pending_approval/raw-stream.jsonl`, `can-use-tool.jsonl`):

```json
{"type": "control_request", "request_id": "6b846e87-4806-4ab0-9ec8-07fa202e4806", "request": {"subtype": "can_use_tool", "tool_name": "mcp__shepherd__kill_session", "display_name": "Kill Session", "input": {"id": "ses_slow"}, "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "mcp__shepherd__kill_session"}], "behavior": "allow", "destination": "localSettings"}], "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F"}}
{"type": "control_request", "request_id": "req_2_a5299970", "request": {"subtype": "interrupt"}}
{"type": "control_cancel_request", "request_id": "6b846e87-4806-4ab0-9ec8-07fa202e4806"}
{"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). STOP wha...", "is_error": true, "tool_use_id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F"}]}, "parent_tool_use_id": null, "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "uuid": "4a5d3b19-b22a-4234-982a-a7f187e5ff3e", "timestamp": "2026-09-14T16:08:45.160Z", "tool_use_result": "User rejected tool use", "tool_result_meta": [{"id": "toolu_013kVAXAVbKLKYf9S3ZtMd8F", "non_execution_kind": "user-rejected"}]}
{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user for tool use]"}]}, "parent_tool_use_id": null, "session_id": "920f6ed2-84e6-4a36-97e6-470322ac539b", "uuid": "e4b3744f-a718-4116-a2ff-4145d3da1302", "timestamp": "2026-09-14T16:08:45.162Z"}
```

```json
{"_ts": "2026-09-14T16:08:38.734Z", "phase": "entered", "tool_name": "mcp__shepherd__kill_session", "tool_input": {"id": "ses_slow"}}
{"_ts": "2026-09-14T16:08:45.152Z", "phase": "cancelled", "exc": "CancelledError: "}
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
  "turns": [
    {
      "label": "turn1",
      "wall_s": 1.8,
      "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
    },
    {
      "label": "resumed",
      "wall_s": 1.58,
      "session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
    },
    {
      "label": "forked",
      "wall_s": 1.77,
      "session_id": "081dd12b-fad0-4789-ae46-972b7e977a5e"
    }
  ],
  "first_session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
  "resumed_session_id": "e6fed1a4-c0b1-41d6-be36-b445e606c5a1",
  "forked_session_id": "081dd12b-fad0-4789-ae46-972b7e977a5e",
  "transcript_dir": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-resume",
  "transcript_files": [
    "081dd12b-fad0-4789-ae46-972b7e977a5e.jsonl",
    "e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl"
  ],
```

```text
"--fork-session"
"--resume=e6fed1a4-c0b1-41d6-be36-b445e606c5a1"
```

Resume from a different process cwd:

```text
  "turns": [
    {
      "label": "turn1-cwd-a",
      "wall_s": 1.39,
      "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3"
    },
    {
      "label": "resume-from-cwd-b",
      "wall_s": 2.67,
      "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3"
    }
  ],
  "resume_from_b": {
    "session_id": "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3",
    "result": "MANGO-3",
    "subtype": "success",
    "is_error": false
  },
  "transcript_dirs_after_resume_from_b": {
    "-tmp-shp-sdk-9IOKNs-work-resume-other-cwd-a": [
      "1285a7ff-ef36-45ac-814f-3e76f9d2c9a3.jsonl"
    ]
  },
```

Context the harness injected into the master's own transcript even with `setting_sources=[]` (trimmed; full capture: `captures/resume/transcript-e6fed1a4-c0b1-41d6-be36-b445e606c5a1.jsonl`):

```json
{"...":"...","attachment":{"type":"deferred_tools_delta","addedNames":["CronCreate","CronDelete","CronList","DesignSync","..."],"addedLines":["CronCreate","CronDelete","CronList","DesignSync","..."],"removedNames":[],"wireHiddenNames":[],"readdedNames":[],"pendingMcpServers":[],"needsAuthMcpServers":["claude.ai Atlassian Rovo","claude.ai Google Drive","claude.ai Notion","claude.ai Slack"],"failedMcpServers":[]},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
{"...":"...","attachment":{"type":"skill_listing","content":"- dataviz: Use this skill whenever you are about to create ANY chart, graph, plot, dashboard, or dat...","skillCount":13,"isInitial":true,"names":["dataviz","update-config","keybindings-help","code-review","..."]},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
{"...":"...","attachment":{"type":"session_context","context":{"userEmail":"The user's email address is <redacted>. Use it only to identify the user, such as for authorship, at..."}},"type":"attachment","...":"...","entrypoint":"sdk-py","...":"...","sessionId":"e6fed1a4-c0b1-41d6-be36-b445e606c5a1","version":"2.1.259","...":"..."}
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
      "--setting-sources=",
...
      "--setting-sources=project",
...
  "isolation_results": {
    "setting_sources_empty": "Hello.",
    "setting_sources_project": "Howdy ZEBRA-MARKER-41",
    "setting_sources_none": "Hello.\n\nZEBRA-MARKER-41"
  },
```

```json
{"type": "system", "subtype": "init", "...": "...", "mcp_servers": [{"name": "claude.ai Google Drive", "status": "needs-auth"}, {"name": "claude.ai Slack", "status": "needs-auth"}, {"name": "claude.ai Notion", "status": "needs-auth"}, {"name": "claude.ai Google Calendar", "status": "connected"}, {"name": "claude.ai Atlassian Rovo", "status": "needs-auth"}, {"name": "claude.ai Gmail", "status": "connected"}, {"name": "shepherd", "status": "connected"}], "...": "...", "skills": ["deep-research", "design-sync", "dataviz", "..."], "plugins": [], "...": "...", "memory_paths": {"auto": "/root/.claude/projects/-tmp-shp-sdk-9IOKNs-work-isolation/memory/"}, "...": "..."}
```

| `setting_sources` | argv | project `CLAUDE.md` obeyed? | account connectors mounted? | bundled skills listed? |
|---|---|---|---|---|
| `[]` | `--setting-sources=` | **no** (`Hello.`) | yes (6 `claude.ai …` servers) | yes (17) |
| `["project"]` | `--setting-sources=project` | yes | yes | yes |
| `None` | (flag absent) | yes | yes | yes |

**Variants and edge cases:** the only option that removed the connectors was `strict_mcp_config=True`. Neither `setting_sources` nor `tools=[]` removed skills from `system/init.skills`. `tools=[]` removes the `Skill` tool, so they become unreachable.

**Spec alignment:**
- Spec line 1528 (`# no CLAUDE.md, no cc10x, no skills`) is only partly right. "no CLAUDE.md" holds for project scope. "no skills" is wrong for Claude Code's bundled skills: 17 are listed and a `skill_listing` attachment is injected (the attachment was captured in the `resume` run, which did not set `tools=[]`). "no cc10x" is unverified. Account connectors and the `userEmail` session context also reach the master (`captures/isolation/raw-stream.jsonl`, `captures/resume/transcript-*.jsonl`).
- Spec line 2329 (§18) says "do not trust it". That is confirmed: the isolation test needs `tools=[]` + `strict_mcp_config=True` and should assert on `system/init.tools`/`mcp_servers`/`skills`.

---

## Tier-2 stdio MCP: server process launch and environment

- **Produced by:** Claude Code 2.1.270 (`claude -p --mcp-config <file> --strict-mcp-config`)
- **Consumed by:** §11.0 `to_stdio_mcp_server()` / `shepherd-mcp` (line 1480), §11 Two bindings (line 1695), §11 "attributed to the calling session" (line 1619); D20, D32; M4
- **Probe:** `docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`. Re-run: `bash docs/probes/2026-09-14-schemas/agent-sdk-mcp/stdio/run_stdio_probe.sh`
- **Status:** verified live 2026-09-14

**Real example** (trimmed; full captures: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/mcp-wire.jsonl` (first line), `captures/stdio-mcp/meta.txt`, `captures/stdio-mcp/mcp.json`)

```text
claude_bin=/root/.local/bin/claude
claude_version=2.1.270 (Claude Code)
tmpdir=/tmp/shp-mcp-AY6vTM
scrubbed=-u CLAUDE_CODE_CHILD_SESSION -u AI_AGENT -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_BRIDGE_SESSION_ID -u CLAUDECODE -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_EXECPATH -u CLAUDE_CODE_MESSAGING_TOKEN 
started=2026-09-14T16:14:49Z
/root/.local/bin/claude -p $'Do these steps in order, one tool call per step, then reply DONE:\n1. call mcp__probe__echo_note with text="hello" and count=2\n2. call mcp__probe__fail_note with reason="probe"\n3. call mcp__probe__rpc_error_note\n4. call mcp__probe__danger_note with target="x"\n5. call...
exit=0
finished=2026-09-14T16:15:03Z
```

```json
{"_dir": "start", "pid": 4047192, "...": "...", "cwd": "/tmp/shp-mcp-AY6vTM/work", "env_names": ["...", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR", "...", "PROBE_MARKER", "...", "SHP_CLAUDE_VERSION", "..."], "env_values_allowlisted": {"CLAUDE_CODE_SESSION_ID": "b94c6873-915c-45f1-9c53-5e9be3acdc35", "CLAUDE_PROJECT_DIR": "/tmp/shp-mcp-AY6vTM/work", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "CLAUDECODE": "1", "PROBE_MARKER": "1", "SHP_CLAUDE_VERSION": "2.1.270 (Claude Code)"}, "secret_env_names_present_values_not_logged": ["CLAUDE_CODE_MESSAGING_TOKEN"], "ancestry": [{"pid": 4047192, "comm": "python3", "ppid": 4047179}, {"pid": 4047179, "comm": "claude", "ppid": 4047178}, {"pid": 4047178, "comm": "timeout", "ppid": 4047177}, {"pid": 4047177, "comm": "bash", "ppid": 4047154}, {"pid": 4047154, "comm": "bash", "ppid": 4047150}, {"pid": 4047150, "comm": "bash", "ppid": 3971404}, {"pid": 3971404, "comm": "claude", "ppid": 3971392}, {"pid": 3971392, "comm": "bash", "ppid": 3971391}, {"pid": 3971391, "comm": "tmux: server", "ppid": 1}]}
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
[in ] {"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{"roots":{"listChanged":true},"elicitation":{}},"clientInfo":{"name":"claude-code","title":"Claude Code","version":"2.1.270","description":"Anthropic's agentic coding tool","websiteUrl":"https://claude.com/claude-code"}},"jsonrpc":"2.0","id":0}
[out] {"jsonrpc": "2.0", "id": 0, "result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": false}}, "serverInfo": {"name": "probe-logger", "version": "0.0.1"}}}
[in ] {"jsonrpc":"2.0","method":"notifications/initialized"}
[in ] {"method":"tools/list","jsonrpc":"2.0","id":1}
[out] {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "echo_note", "title": "Echo Note", "description": "Echo a note back. Probe tool.", "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "the note"}, "count": {"type": "integer", "minimum": 1}}, "required": ["text"], "additionalProperties": false}, "annotations": {"readOnlyHint": true}}, {"name": "fail_note", "description": "Always returns a tool-level error result (isError).", "inputSchema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}, {"name": "rpc_error_note", "description": "Always returns a JSON-RPC protocol error.", "inputSchema": {"type": "object", "properties": {}}}, {"name": "danger_note", "description": "A destructive probe tool that is not pre-allowed.", "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}, "annotations": {"destructiveHint": true}}]}}
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
[in ] {"method":"tools/call","params":{"name":"echo_note","arguments":{"text":"hello","count":2},"_meta":{"claudecode/toolUseId":"toolu_013516j4ARBNwtSPj9RWtTxG","progressToken":2}},"jsonrpc":"2.0","id":2}
[out] {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "echo: 'hello' count=2"}], "isError": false}}
[in ] {"method":"tools/call","params":{"name":"fail_note","arguments":{"reason":"probe"},"_meta":{"claudecode/toolUseId":"toolu_01FsXNbwyhCiEBnL8GQh2JZG","progressToken":3}},"jsonrpc":"2.0","id":3}
[out] {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "max_session_depth=3 reached; refusing"}], "isError": true}}
[in ] {"method":"tools/call","params":{"name":"rpc_error_note","arguments":{},"_meta":{"claudecode/toolUseId":"toolu_01Ad55LkgJbpQSZDx13o2E7w","progressToken":4}},"jsonrpc":"2.0","id":4}
[out] {"jsonrpc": "2.0", "id": 4, "error": {"code": -32603, "message": "probe internal error"}}
[in ] {"method":"tools/call","params":{"name":"echo_note","arguments":{"count":5},"_meta":{"claudecode/toolUseId":"toolu_01LTSw8eSCWywBV57sUW38kn","progressToken":5}},"jsonrpc":"2.0","id":5}
[out] {"jsonrpc": "2.0", "id": 5, "result": {"content": [{"type": "text", "text": "echo: None count=5"}], "isError": false}}
```

What the session's stream showed for each (trimmed; full capture: `captures/stdio-mcp/stream.jsonl`). `danger_note` never reached the server:

```json
{"type":"system","subtype":"init","...":"...","tools":["mcp__probe__danger_note","mcp__probe__echo_note","mcp__probe__fail_note","mcp__probe__rpc_error_note"],"mcp_servers":[{"name":"probe","status":"connected"}],"...":"...","apiKeySource":"none","claude_code_version":"2.1.270","...":"..."}
{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG","type":"tool_result","content":[{"type":"text","text":"echo: 'hello' count=2"}]}]},"...":"...","tool_use_result":[{"type":"text","text":"echo: 'hello' count=2"}]}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"max_session_depth=3 reached; refusing","is_error":true,"tool_use_id":"toolu_01FsXNbwyhCiEBnL8GQh2JZG"}]},"...":"...","tool_use_result":"Error: max_session_depth=3 reached; refusing"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"probe internal error","is_error":true,"tool_use_id":"toolu_01Ad55LkgJbpQSZDx13o2E7w"}]},"...":"...","tool_use_result":"Error: probe internal error"}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","content":"Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","is_error":true,"tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9"}]},"...":"...","tool_use_result":"Error: Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","...":"..."}
{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01LTSw8eSCWywBV57sUW38kn","type":"tool_result","content":[{"type":"text","text":"echo: None count=5"}]}]},"...":"...","tool_use_result":[{"type":"text","text":"echo: None count=5"}]}
{"type":"system","subtype":"permission_denied","tool_name":"mcp__probe__danger_note","tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9","message":"Claude requested permissions to use mcp__probe__danger_note, but you haven't granted it yet.","uuid":"82c78e8c-cfcf-4540-899a-6ada5eed7c95","session_id":"b94c6873-915c-45f1-9c53-5e9be3acdc35"}
{"...":"...","permission_denials":[{"tool_name":"mcp__probe__danger_note","tool_use_id":"toolu_019uPT8ahHwoDyzKJ8BcDTz9","tool_input":{"target":"x"}}],"terminal_reason":"completed","...":"...","is_error":false,"...":"...","subtype":"success","...":"...","type":"result","...":"..."}
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
- **Status:** verified live 2026-09-14 for `PreToolUse`, `PostToolUse`, `PostToolUseFailure` and `PermissionRequest` in a headless `-p` session. `PermissionDenied` never fired, so its payload is not verified. The interactive (tmux) session was not probed.

**Real example** (trimmed; full capture: `docs/probes/2026-09-14-schemas/agent-sdk-mcp/captures/stdio-mcp/hooks.jsonl`)

```json
{"_event":"PreToolUse","_captured_at":"2026-09-14T16:14:53.311Z","_claude_version":"2.1.270 (Claude Code)","_ancestry":[{"pid":4047209,"comm":"capture_hook.sh","ppid":4047208},{"pid":4047208,"comm":"sh","ppid":4047179},{"pid":4047179,"comm":"claude","ppid":4047178},"..."],"payload":{"session_id":"b94c6873-915c-45f1-9c53-5e9be3acdc35","transcript_path":"/root/.claude/projects/-tmp-shp-mcp-AY6vTM-work/b94c6873-915c-45f1-9c53-5e9be3acdc35.jsonl","cwd":"/tmp/shp-mcp-AY6vTM/work","prompt_id":"6086eddb-1546-4789-97e9-afdf7d1ea1c1","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"mcp__probe__echo_note","tool_input":{"text":"hello","count":2},"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG"}}
{"_event":"PostToolUse","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUse","tool_name":"mcp__probe__echo_note","tool_input":{"text":"hello","count":2},"tool_response":[{"type":"text","text":"echo: 'hello' count=2"}],"tool_use_id":"toolu_013516j4ARBNwtSPj9RWtTxG","duration_ms":8}}
{"_event":"PostToolUseFailure","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"mcp__probe__fail_note","tool_input":{"reason":"probe"},"tool_use_id":"toolu_01FsXNbwyhCiEBnL8GQh2JZG","error":"max_session_depth=3 reached; refusing","is_interrupt":false,"duration_ms":4}}
{"_event":"PostToolUseFailure","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PostToolUseFailure","tool_name":"mcp__probe__rpc_error_note","tool_input":{},"tool_use_id":"toolu_01Ad55LkgJbpQSZDx13o2E7w","error":"probe internal error","is_interrupt":false,"duration_ms":6}}
{"_event":"PermissionRequest","...":"...","_claude_version":"2.1.270 (Claude Code)","...":"...","payload":{"...":"...","permission_mode":"default","hook_event_name":"PermissionRequest","tool_name":"mcp__probe__danger_note","tool_input":{"target":"x"},"permission_suggestions":[{"type":"addRules","rules":[{"toolName":"mcp__probe__danger_note"}],"behavior":"allow","destination":"localSettings"}]}}
```

Line counts per `_event` in `captures/stdio-mcp/hooks.jsonl` (computed, not an excerpt): PreToolUse 5, PostToolUse 2, PostToolUseFailure 2, PermissionRequest 1, PermissionDenied 0. A `PermissionDenied` hook was declared (`captures/stdio-mcp/settings.json`).

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
- Caveat, not a contradiction: spec line 917 only puts `PermissionDenied` in the needs-you group; it does not say which denials fire it. In this probe it did not fire for a headless `-p` "not granted" denial of an MCP tool, so a consumer cannot rely on it to see that kind of denial. Use `PermissionRequest`, or `system/permission_denied` / `result.permission_denials` in the stream (`captures/stdio-mcp/hooks.jsonl`, `captures/stdio-mcp/stream.jsonl`).
