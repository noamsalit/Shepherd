"""Shepherd gap-fill probe (2026-09-14): Agent SDK master.

Scenarios:
  approval_timeout  can_use_tool blocks for 630 s (> spec's await_decision(timeout_s=600)); does the CLI or the
                    SDK give up first, and what does the turn look like? (spec 1737-1749)
  server_info       initialize response: every key of models[] (spec 453 ModelProvider.models(), 2287) and the
                    effort levels per model (spec 552). No model turn is sent.

Re-run (needs a venv with claude-agent-sdk, e.g. the one built by agent-sdk-mcp/run_all.sh):
  <venv>/bin/python docs/probes/2026-09-14-schemas/gap-fill/sdk_probe.py <scenario> [--cli PATH]
Output: docs/probes/2026-09-14-schemas/gap-fill/sdk-<scenario>[-syscli]-<stamp>/

Safety: CLAUDE*/ANTHROPIC* env vars from the calling session are removed; cwd is a mktemp dir under /tmp;
flag settings disable the cc10x plugin; setting_sources=[]; model claude-haiku-4-5-20251001; hard fail_after.
"""
import dataclasses, datetime, json, os, pathlib, subprocess, sys, tempfile, time, traceback

SCEN = sys.argv[1]
CLI = sys.argv[sys.argv.index("--cli") + 1] if "--cli" in sys.argv else None
HERE = pathlib.Path(__file__).resolve().parent
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
CAP = HERE / f"sdk-{SCEN}{'-syscli' if CLI else ''}-{STAMP}"
CAP.mkdir()
WORK = pathlib.Path(tempfile.mkdtemp(prefix=f"shp-gap-sdk-{SCEN}-", dir="/tmp"))
MODEL = "claude-haiku-4-5-20251001"
scrubbed = sorted(k for k in os.environ if k.startswith(("CLAUDE", "ANTHROPIC")) or k == "AI_AGENT")
for k in scrubbed:
    del os.environ[k]

import anyio
import claude_agent_sdk as sdk
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, tool, create_sdk_mcp_server
from claude_agent_sdk._internal.transport import subprocess_cli as sc


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def append(name, obj):
    with open(CAP / name, "a") as fh:
        fh.write(json.dumps(obj, default=repr) + "\n")


META = {"scenario": SCEN, "sdk_version": sdk.__version__, "model": MODEL, "scrubbed_env_names": scrubbed,
        "cwd": str(WORK), "started_at": now(), "argv": []}
_ow, _or, _ob = sc.SubprocessCLITransport.write, sc.SubprocessCLITransport.read_messages, sc.SubprocessCLITransport._build_command


async def _write(self, data):
    for line in data.splitlines():
        if line.strip():
            try:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line": json.loads(line)})
            except Exception:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line_text": line})
    return await _ow(self, data)


def _read(self):
    async def gen():
        async for msg in _or(self):
            append("raw-stream.jsonl", {"_dir": "in", "_ts": now(), "line": msg})
            yield msg
    return gen()


def _build(self):
    cmd = _ob(self)
    META["argv"].append(cmd)
    META["cli_path"] = cmd[0]
    META["claude_version"] = subprocess.run([cmd[0], "--version"], capture_output=True, text=True).stdout.strip()
    return cmd


sc.SubprocessCLITransport.write, sc.SubprocessCLITransport.read_messages, sc.SubprocessCLITransport._build_command = _write, _read, _build


def stderr_cb(line):
    with open(CAP / "stderr.txt", "a") as fh:
        fh.write(line.rstrip("\n") + "\n")


@tool("kill_session", "Kill a session by id.", {"id": str})
async def kill_session(args):
    append("handler-calls.jsonl", {"_ts": now(), "tool": "kill_session", "received": args})
    return {"content": [{"type": "text", "text": "killed " + args["id"]}]}


def options(**over):
    p = WORK / "flag-settings.json"
    p.write_text(json.dumps({"enabledPlugins": {"cc10x@cc10x": False}}))
    o = dict(model=MODEL, system_prompt="You are a probe orchestrator. Follow instructions literally and briefly.",
             setting_sources=[], disallowed_tools=["Agent", "Task"], tools=[], strict_mcp_config=True,
             mcp_servers={"shepherd": create_sdk_mcp_server(name="shepherd", tools=[kill_session])},
             cwd=str(WORK), settings=str(p), stderr=stderr_cb, max_turns=4)
    if CLI:
        o["cli_path"] = CLI
    o.update(over)
    return ClaudeAgentOptions(**o)


def log_message(m, label):
    d = dataclasses.asdict(m) if dataclasses.is_dataclass(m) else {"repr": repr(m)}
    append("messages.jsonl", {"_ts": now(), "_label": label, "_class": type(m).__name__, "fields": d})


DELAY = 630


async def scenario():
    if SCEN == "server_info":
        async with ClaudeSDKClient(options=options()) as c:
            info = await c.get_server_info()
            (CAP / "server-info.json").write_text(json.dumps(info, indent=1, default=repr))
    elif SCEN == "approval_timeout":
        async def slow(tool_name, tool_input, context):
            append("can-use-tool.jsonl", {"_ts": now(), "phase": "entered", "tool_name": tool_name, "tool_input": tool_input})
            t0 = time.time()
            try:
                await anyio.sleep(DELAY)
            except BaseException as e:
                append("can-use-tool.jsonl", {"_ts": now(), "phase": "cancelled", "after_s": round(time.time() - t0, 1), "exc": f"{type(e).__name__}: {e}"})
                raise
            append("can-use-tool.jsonl", {"_ts": now(), "phase": "returning allow", "after_s": round(time.time() - t0, 1)})
            from claude_agent_sdk import PermissionResultAllow
            return PermissionResultAllow(updated_input=tool_input)
        async with ClaudeSDKClient(options=options(can_use_tool=slow)) as c:
            t0 = time.time()
            await c.query("Call mcp__shepherd__kill_session with id='ses_slow'. Then reply with the tool's result text only.")
            async for m in c.receive_response():
                log_message(m, "turn")
                append("progress.jsonl", {"_ts": now(), "since_query_s": round(time.time() - t0, 1), "class": type(m).__name__})
            META["turn_wall_s"] = round(time.time() - t0, 1)


async def main():
    try:
        with anyio.fail_after(900):
            await scenario()
        META["status"] = "ok"
    except BaseException as e:
        META["status"] = f"error: {type(e).__name__}: {e}"
        META["traceback"] = traceback.format_exc()
    META["finished_at"] = now()
    (CAP / "meta.json").write_text(json.dumps(META, indent=2, default=repr))
    subprocess.run([sys.executable, str(HERE / "redact_account.py")] + [str(p) for p in CAP.glob("*.json*")], capture_output=True)
    print(SCEN, META["status"], CAP)

anyio.run(main)
