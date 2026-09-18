"""Shepherd schema probe (2026-09-14): a minimal Agent SDK master against the local claude login.

Re-run (needs a venv with claude-agent-sdk; see run_all.sh):
    <venv>/bin/python master_probe.py <scenario> <evidence_captures_dir> <throwaway_tmpdir> [--cli PATH]
Scenarios: basic | tools_empty | locked | resume | interrupt | isolation | slow_approval | interrupt_pending_approval | deny | resume_other_cwd

Safety: every CLAUDE*/ANTHROPIC*/AI_AGENT env var inherited from the calling session is removed
before the SDK spawns the CLI (so NO API key is present and the child does not think it is nested).
cwd is a throwaway dir under /tmp. Throwaway flag-settings disable the cc10x user plugin.
Model: claude-haiku-4-5-20251001. Every scenario is wrapped in anyio.fail_after.

Outputs in <captures>/<scenario>/:
  raw-stream.jsonl   every JSON object the CLI wrote to stdout (dir="in") and every line the SDK
                     wrote to CLI stdin (dir="out"), verbatim, with a probe timestamp
  messages.jsonl     the parsed SDK message objects (class name + dataclasses.asdict)
  handler-calls.jsonl  what each in-process MCP tool handler received and returned
  can-use-tool.jsonl what the can_use_tool callback received and returned
  hooks.jsonl        what Python PreToolUse/PostToolUse/PostToolUseFailure hook callbacks received
  stderr.txt, meta.json (sdk version, cli path, `claude --version`, argv, scrubbed env names)
"""
import asyncio, dataclasses, json, os, pathlib, shutil, subprocess, sys, time, traceback, warnings

SCEN = sys.argv[1]
CAP = pathlib.Path(sys.argv[2]) / SCEN
TMP = pathlib.Path(sys.argv[3])
CLI = sys.argv[sys.argv.index("--cli") + 1] if "--cli" in sys.argv else None
if CLI:
    CAP = CAP.with_name(SCEN + "-syscli")  # same scenario against a non-bundled claude binary
CAP.mkdir(parents=True, exist_ok=True)
for f in CAP.glob("*"):
    if f.is_file():
        f.unlink()
WORK = TMP / f"work-{SCEN}"
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
MODEL = "claude-haiku-4-5-20251001"

scrubbed = sorted(k for k in os.environ if k.startswith(("CLAUDE", "ANTHROPIC")) or k in ("AI_AGENT",))
for k in scrubbed:
    del os.environ[k]

import anyio
import claude_agent_sdk as sdk
from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, tool,
                              create_sdk_mcp_server, ResultMessage)
from claude_agent_sdk._internal.transport import subprocess_cli as sc

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time()*1000)%1000:03d}Z"

def append(name, obj):
    with open(CAP / name, "a") as fh:
        fh.write(json.dumps(obj, default=repr) + "\n")

# ---- raw wire logging (patch the transport class, keep the SDK's own code path) ----
_orig_write = sc.SubprocessCLITransport.write
_orig_read = sc.SubprocessCLITransport.read_messages
_orig_build = sc.SubprocessCLITransport._build_command
META = {"scenario": SCEN, "sdk_version": sdk.__version__, "model": MODEL, "scrubbed_env_names": scrubbed,
        "cwd_process": str(WORK), "started_at": now(), "argv": []}

async def _write(self, data):
    for line in data.splitlines():
        if line.strip():
            try:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line": json.loads(line)})
            except Exception:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line_text": line})
    return await _orig_write(self, data)

def _read(self):
    async def gen():
        async for msg in _orig_read(self):
            append("raw-stream.jsonl", {"_dir": "in", "_ts": now(), "line": msg})
            yield msg
    return gen()

def _build(self):
    cmd = _orig_build(self)
    META["argv"].append(cmd)
    META["cli_path"] = cmd[0]
    META["claude_version"] = subprocess.run([cmd[0], "--version"], capture_output=True, text=True).stdout.strip()
    return cmd

sc.SubprocessCLITransport.write = _write
sc.SubprocessCLITransport.read_messages = _read
sc.SubprocessCLITransport._build_command = _build

def stderr_cb(line):
    with open(CAP / "stderr.txt", "a") as fh:
        fh.write(line.rstrip("\n") + "\n")

def log_message(msg, label=""):
    d = dataclasses.asdict(msg) if dataclasses.is_dataclass(msg) else {"repr": repr(msg)}
    append("messages.jsonl", {"_ts": now(), "_label": label, "_class": type(msg).__name__, "fields": d})

# ---- in-process MCP server: the §11 `shepherd` shape ----
async def _record(name, args, result):
    append("handler-calls.jsonl", {"_ts": now(), "tool": name, "received": args, "returned": result})
    return result

@tool("fleet_summary", "Return counts of sessions by bucket. Takes no arguments.",
      {"type": "object", "properties": {}})
async def fleet_summary(args):
    return await _record("fleet_summary", args,
                         {"content": [{"type": "text", "text": json.dumps({"running": 2, "needs_you": ["ses_a1"], "stopped": 1})}]})

@tool("spawn_session", "Spawn a session in a project with a task.",
      {"type": "object",
       "properties": {"project_id": {"type": "string"}, "task": {"type": "string"},
                      "model": {"type": ["string", "null"]}},
       "required": ["project_id", "task"]})
async def spawn_session(args):
    return await _record("spawn_session", args, {"content": [{"type": "text", "text": "ses_new42"}]})

@tool("kill_session", "Kill a session by id.", {"id": str})
async def kill_session(args):
    return await _record("kill_session", args, {"content": [{"type": "text", "text": "killed " + args["id"]}]})

@tool("fail_tool", "A tool that always reports an error result.", {"reason": str})
async def fail_tool(args):
    return await _record("fail_tool", args,
                         {"content": [{"type": "text", "text": "max_children_per_session=5 reached"}], "is_error": True})

@tool("raise_tool", "A tool whose handler raises an exception.", {"type": "object", "properties": {}})
async def raise_tool(args):
    append("handler-calls.jsonl", {"_ts": now(), "tool": "raise_tool", "received": args, "returned": "RAISES RuntimeError"})
    raise RuntimeError("handler exploded on purpose")

ALL_TOOLS = [fleet_summary, spawn_session, kill_session, fail_tool, raise_tool]

async def authorize(tool_name, tool_input, context):
    decision = {"behavior": "allow", "updated_input": tool_input}
    if tool_name == "Bash":
        decision = {"behavior": "deny", "message": "master may not use Bash (probe authorize)"}
    append("can-use-tool.jsonl", {"_ts": now(), "tool_name": tool_name, "tool_input": tool_input,
                                  "context": dataclasses.asdict(context) if dataclasses.is_dataclass(context) else repr(context),
                                  "returned": decision})
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    if decision["behavior"] == "allow":
        return PermissionResultAllow(updated_input=tool_input)
    return PermissionResultDeny(message=decision["message"])

async def hook_cb(input_data, tool_use_id, context):
    append("hooks.jsonl", {"_ts": now(), "tool_use_id": tool_use_id, "input_data": input_data,
                           "context": repr(context)})
    return {}

def settings_file():
    p = TMP / "flag-settings.json"
    p.write_text(json.dumps({"enabledPlugins": {"cc10x@cc10x": False}}))
    return str(p)

def base_options(**over):
    o = dict(
        model=MODEL,
        system_prompt="You are a probe orchestrator. Follow the user's instructions literally and briefly.",
        setting_sources=[],
        disallowed_tools=["Agent", "Task"],
        allowed_tools=["mcp__shepherd__fleet_summary", "mcp__shepherd__spawn_session",
                       "mcp__shepherd__fail_tool", "mcp__shepherd__raise_tool"],
        mcp_servers={"shepherd": create_sdk_mcp_server(name="shepherd", tools=ALL_TOOLS)},
        can_use_tool=authorize,
        hooks={ev: [HookMatcher(matcher=None, hooks=[hook_cb])] for ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure")},
        cwd=None,
        settings=settings_file(),
        stderr=stderr_cb,
        max_turns=14,
    )
    if CLI:
        o["cli_path"] = CLI
    o.update(over)
    return ClaudeAgentOptions(**o)

async def run_turn(client, prompt, label):
    t0 = time.time()
    await client.query(prompt)
    result = None
    async for m in client.receive_response():
        log_message(m, label)
        if isinstance(m, ResultMessage):
            result = m
    META.setdefault("turns", []).append({"label": label, "wall_s": round(time.time() - t0, 2),
                                         "session_id": getattr(result, "session_id", None)})
    return result

BASIC_PROMPT = (
    "Do these steps in order, one tool call at a time, then reply with the single word DONE:\n"
    "1. call mcp__shepherd__fleet_summary\n"
    "2. call mcp__shepherd__spawn_session with project_id='p1' and task='write tests'\n"
    "3. call mcp__shepherd__kill_session with id='ses_a1'\n"
    "4. call mcp__shepherd__fail_tool with reason='probe'\n"
    "5. call mcp__shepherd__raise_tool\n"
    "6. call mcp__shepherd__spawn_session with ONLY project_id='p2' and no task argument at all\n"
    "7. run the Bash command: echo hi\n"
)

async def scenario():
    os.chdir(WORK)
    if SCEN in ("basic", "tools_empty", "locked"):
        extra = {"basic": {}, "tools_empty": {"tools": []},
                 "locked": {"tools": [], "strict_mcp_config": True}}[SCEN]
        async with ClaudeSDKClient(options=base_options(**extra)) as client:
            await run_turn(client, BASIC_PROMPT, "turn1")
    elif SCEN == "resume":
        async with ClaudeSDKClient(options=base_options()) as c1:
            r1 = await run_turn(c1, "Remember this code word: PINEAPPLE-7. Reply with only OK.", "turn1")
        sid = r1.session_id
        META["first_session_id"] = sid
        async with ClaudeSDKClient(options=base_options(resume=sid)) as c2:
            r2 = await run_turn(c2, "What was the code word? Reply with only the code word.", "resumed")
        META["resumed_session_id"] = r2.session_id
        async with ClaudeSDKClient(options=base_options(resume=sid, fork_session=True)) as c3:
            r3 = await run_turn(c3, "Repeat the code word once more, then the word FORK.", "forked")
        META["forked_session_id"] = r3.session_id
        key = str(WORK).replace("/", "-").replace(".", "-")
        proj = pathlib.Path.home() / ".claude" / "projects" / key
        META["transcript_dir"] = str(proj)
        META["transcript_files"] = sorted(p.name for p in proj.glob("*.jsonl")) if proj.exists() else None
        for p in (proj.glob("*.jsonl") if proj.exists() else []):
            shutil.copy(p, CAP / f"transcript-{p.name}")
    elif SCEN == "interrupt":
        opts = base_options(include_partial_messages=True, max_turns=3)
        async with ClaudeSDKClient(options=opts) as client:
            await client.query("Write the numbers from one to three hundred spelled out in English words, one per line. No tools.")
            t0 = time.time(); n_stream = 0; interrupted = False
            async for m in client.receive_response():
                log_message(m, "long")
                if type(m).__name__ == "StreamEvent":
                    n_stream += 1
                if not interrupted and n_stream >= 25:
                    ti = time.time()
                    rv = await client.interrupt()
                    interrupted = True
                    META["interrupt"] = {"after_stream_events": n_stream, "since_query_s": round(ti - t0, 2),
                                         "returned": repr(rv), "call_s": round(time.time() - ti, 3)}
                    append("messages.jsonl", {"_ts": now(), "_label": "PROBE", "_class": "interrupt() returned", "fields": {"repr": repr(rv)}})
            r = await run_turn(client, "Reply with only the word AFTER.", "after-interrupt")
            META["after_interrupt_session_id"] = r.session_id if r else None
            try:
                rv2 = await client.interrupt()
                META["interrupt_when_idle"] = {"returned": repr(rv2)}
            except Exception as e:
                META["interrupt_when_idle"] = {"raised": f"{type(e).__name__}: {e}"}
    elif SCEN == "isolation":
        (WORK / "CLAUDE.md").write_text("PROBE RULE: end every reply with the exact token ZEBRA-MARKER-41.\n")
        res = {}
        for label, ss in (("setting_sources_empty", []), ("setting_sources_project", ["project"]), ("setting_sources_none", None)):
            async with ClaudeSDKClient(options=base_options(setting_sources=ss, max_turns=2)) as client:
                r = await run_turn(client, "Say hello in one word.", label)
                res[label] = r.result if r else None
        META["isolation_results"] = res
    elif SCEN in ("slow_approval", "interrupt_pending_approval"):
        # authorize() blocks (spec §11: await_decision up to 600 s). Does the CLI wait? Can interrupt cancel it?
        delay = 75 if SCEN == "slow_approval" else 60
        async def slow_authorize(tool_name, tool_input, context):
            append("can-use-tool.jsonl", {"_ts": now(), "phase": "entered", "tool_name": tool_name, "tool_input": tool_input})
            try:
                await anyio.sleep(delay)
            except BaseException as e:
                append("can-use-tool.jsonl", {"_ts": now(), "phase": "cancelled", "exc": f"{type(e).__name__}: {e}"})
                raise
            append("can-use-tool.jsonl", {"_ts": now(), "phase": "returning allow after sleep", "slept_s": delay})
            from claude_agent_sdk import PermissionResultAllow
            return PermissionResultAllow(updated_input=tool_input)
        opts = base_options(can_use_tool=slow_authorize, tools=[], strict_mcp_config=True, max_turns=4)
        async with ClaudeSDKClient(options=opts) as client:
            t0 = time.time()
            await client.query("Call mcp__shepherd__kill_session with id='ses_slow'. Then reply with the tool's result text only.")
            interrupted = False
            async def killer():
                await anyio.sleep(8)
                ti = time.time()
                rv = await client.interrupt()
                META["interrupt"] = {"since_query_s": round(ti - t0, 2), "returned": repr(rv)}
                append("messages.jsonl", {"_ts": now(), "_label": "PROBE", "_class": "interrupt() returned", "fields": {"repr": repr(rv)}})
            async with anyio.create_task_group() as tg:
                if SCEN == "interrupt_pending_approval":
                    tg.start_soon(killer)
                async for m in client.receive_response():
                    log_message(m, SCEN)
            META["turn_wall_s"] = round(time.time() - t0, 2)
            if SCEN == "interrupt_pending_approval":
                r = await run_turn(client, "Reply with only the word AFTER.", "after-interrupt")
    elif SCEN == "deny":
        async def deny_authorize(tool_name, tool_input, context):
            from claude_agent_sdk import PermissionResultDeny
            d = PermissionResultDeny(message="you declined this")
            append("can-use-tool.jsonl", {"_ts": now(), "tool_name": tool_name, "tool_input": tool_input, "returned": dataclasses.asdict(d)})
            return d
        opts = base_options(can_use_tool=deny_authorize, tools=[], strict_mcp_config=True, max_turns=4)
        async with ClaudeSDKClient(options=opts) as client:
            await run_turn(client, "Call mcp__shepherd__kill_session with id='ses_x'. If it fails, reply with the exact error text you received.", "deny")
    elif SCEN == "resume_other_cwd":
        a = WORK / "a"; b = WORK / "b"; a.mkdir(); b.mkdir()
        async with ClaudeSDKClient(options=base_options(cwd=str(a), tools=[], strict_mcp_config=True)) as c1:
            r1 = await run_turn(c1, "Remember this code word: MANGO-3. Reply with only OK.", "turn1-cwd-a")
        META["first_session_id"] = r1.session_id
        try:
            async with ClaudeSDKClient(options=base_options(cwd=str(b), resume=r1.session_id, tools=[], strict_mcp_config=True)) as c2:
                r2 = await run_turn(c2, "What was the code word? Reply with only the code word, or UNKNOWN.", "resume-from-cwd-b")
            META["resume_from_b"] = {"session_id": getattr(r2, "session_id", None), "result": getattr(r2, "result", None),
                                     "subtype": getattr(r2, "subtype", None), "is_error": getattr(r2, "is_error", None)}
        except Exception as e:
            META["resume_from_b"] = {"raised": f"{type(e).__name__}: {e}"}
        proj = pathlib.Path.home() / ".claude" / "projects"
        META["transcript_dirs_after_resume_from_b"] = {
            d.name: sorted(p.name for p in d.glob("*.jsonl"))
            for d in sorted(proj.glob(str(WORK).replace("/", "-").replace(".", "-").replace("_", "-") + "*"))}
    else:
        raise SystemExit(f"unknown scenario {SCEN}")

async def main():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            with anyio.fail_after(240):
                await scenario()
            META["status"] = "ok"
        except BaseException as e:
            META["status"] = f"error: {type(e).__name__}: {e}"
            META["traceback"] = traceback.format_exc()
        META["warnings"] = [f"{x.category.__name__}: {x.message}" for x in w]
    META["finished_at"] = now()
    (CAP / "meta.json").write_text(json.dumps(META, indent=2, default=repr))
    print(SCEN, META["status"])

anyio.run(main)
