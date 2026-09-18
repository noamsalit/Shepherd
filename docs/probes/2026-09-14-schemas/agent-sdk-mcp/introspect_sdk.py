"""Introspect the INSTALLED claude-agent-sdk (not docs).
Re-run: <venv>/bin/python introspect_sdk.py <outdir>
Writes: sdk-install.txt, options-signature.txt, options-source.txt, types-source-excerpts.txt,
        mcp-server-source.txt, client-api.txt, message-types.txt
"""
import dataclasses, inspect, json, subprocess, sys, pathlib, importlib.metadata as md, typing
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
import claude_agent_sdk as sdk
from claude_agent_sdk import types as T
pkg = pathlib.Path(sdk.__file__).parent

def w(name, text):
    (out / name).write_text(text)

# install record
lines = [f"python: {sys.version}", f"sys.executable: {sys.executable}"]
for d in ("claude-agent-sdk", "mcp", "mcp-types", "anyio", "pydantic"):
    try: lines.append(f"{d}=={md.version(d)}")
    except Exception as e: lines.append(f"{d}: {e}")
lines.append(f"claude_agent_sdk.__version__ = {sdk.__version__}")
from claude_agent_sdk import _cli_version
lines.append(f"bundled __cli_version__ = {_cli_version.__cli_version__}")
b = pkg / "_bundled" / "claude"
lines.append(f"bundled binary: {b} exists={b.exists()} size={b.stat().st_size if b.exists() else None}")
lines.append("bundled `claude --version`: " + subprocess.run([str(b), "--version"], capture_output=True, text=True).stdout.strip())
lines.append("PATH `claude --version`: " + subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip())
lines.append("__all__ = " + json.dumps(sorted(sdk.__all__)))
w("sdk-install.txt", "\n".join(lines) + "\n")

# ClaudeAgentOptions
O = T.ClaudeAgentOptions
sig = [f"inspect.signature(ClaudeAgentOptions) = {inspect.signature(O)}", "", "dataclasses.fields:"]
for f in dataclasses.fields(O):
    default = f.default if f.default is not dataclasses.MISSING else (f"factory:{f.default_factory.__name__}" if f.default_factory is not dataclasses.MISSING else "REQUIRED")
    sig.append(f"  {f.name}: {f.type}  = {default!r}")
w("options-signature.txt", "\n".join(sig) + "\n")
w("options-source.txt", f"# {inspect.getsourcefile(O)}:{inspect.getsourcelines(O)[1]}\n" + inspect.getsource(O))

# message / content types
names = ["SystemMessage","AssistantMessage","UserMessage","ResultMessage","StreamEvent","RateLimitEvent",
         "TaskStartedMessage","TaskProgressMessage","TaskNotificationMessage","TextBlock","ThinkingBlock",
         "ToolUseBlock","ToolResultBlock","ServerToolUseBlock","ServerToolResultBlock","PermissionResult",
         "McpSdkServerConfig","McpStdioServerConfig","SystemPromptPreset","PermissionMode","SettingSource",
         "HookMatcher","ToolPermissionContext","PermissionUpdate","AgentDefinition","SandboxSettings","ThinkingConfig",
         "RateLimitInfo","McpServerConfig","CanUseTool","ContextUsageResponse","PermissionResultAllow","PermissionResultDeny","McpSSEServerConfig","McpHttpServerConfig","ToolsPreset","SystemPromptFile","HookEventMessage","ModelUsage","DeferredToolUse","ToolAnnotations","ForkSessionResult","SDKSessionInfo"]
buf = []
for n in names:
    obj = getattr(T, n, None) or getattr(sdk, n, None)
    if obj is None:
        buf.append(f"### {n}: NOT PRESENT in installed package\n"); continue
    try:
        src = inspect.getsource(obj); loc = f"{inspect.getsourcefile(obj)}:{inspect.getsourcelines(obj)[1]}"
    except Exception:
        src = repr(obj); loc = "(alias)"
    buf.append(f"### {n}  [{loc}]\n{src}\n")
w("message-types.txt", "\n".join(buf))

# create_sdk_mcp_server / tool / SdkMcpTool
buf = []
for n in ("tool", "create_sdk_mcp_server", "SdkMcpTool"):
    obj = getattr(sdk, n)
    buf.append(f"### {n}  [{inspect.getsourcefile(obj)}:{inspect.getsourcelines(obj)[1]}]\n{inspect.getsource(obj)}\n")
w("mcp-server-source.txt", "\n".join(buf))

# client + query API
from claude_agent_sdk import ClaudeSDKClient, query
buf = [f"query{inspect.signature(query)}", ""]
for name, m in inspect.getmembers(ClaudeSDKClient, predicate=inspect.isfunction):
    if name.startswith("_") and name != "__init__": continue
    doc = (inspect.getdoc(m) or "").split("\n")
    buf.append(f"ClaudeSDKClient.{name}{inspect.signature(m)}\n    doc: " + "\n         ".join(doc[:12]))
buf.append("")
for n in ("interrupt",):
    buf.append(f"### source ClaudeSDKClient.{n}\n" + inspect.getsource(getattr(ClaudeSDKClient, n)))
for mod_name, fn in (("claude_agent_sdk._internal.query", "Query.interrupt"),):
    import importlib; mod = importlib.import_module(mod_name)
    cls, meth = fn.split(".")
    buf.append(f"### source {mod_name}.{fn}\n" + inspect.getsource(getattr(getattr(mod, cls), meth)))
# session helpers exported
for n in sorted(sdk.__all__):
    obj = getattr(sdk, n)
    if inspect.isfunction(obj) and any(k in n for k in ("session", "Session")):
        buf.append(f"{n}{inspect.signature(obj)}")
w("client-api.txt", "\n".join(buf) + "\n")
# internals whose behaviour the section cites
from claude_agent_sdk._internal.transport import subprocess_cli as _sc
import claude_agent_sdk.types as _types
buf = []
for label, obj in (("SubprocessCLITransport._find_cli", _sc.SubprocessCLITransport._find_cli),
                   ("SubprocessCLITransport._build_command", _sc.SubprocessCLITransport._build_command),
                   ("SubprocessCLITransport.connect", _sc.SubprocessCLITransport.connect),
                   ("claude_agent_sdk._build_input_schema", sdk._build_input_schema),
                   ("claude_agent_sdk._build_meta", sdk._build_meta),
                   ("claude_agent_sdk._tool_error_result", sdk._tool_error_result),
                   ("claude_agent_sdk._convert_tool_content", sdk._convert_tool_content),
                   ("types._configure_can_use_tool", _types._configure_can_use_tool)):
    buf.append(f"### {label}  [{inspect.getsourcefile(obj)}:{inspect.getsourcelines(obj)[1]}]\n{inspect.getsource(obj)}\n")
w("internals-source.txt", "\n".join(buf))
print("ok", out)
