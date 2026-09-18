"""Shepherd M4 Task 1 probes P1-P4: the four Agent SDK questions M4's design depends on.

Run one probe per invocation:

    .venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p1
    .venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p2
    .venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p3
    .venv/bin/python docs/probes/2026-09-17-m4-sdk/probe_m4.py p4

Each run writes `docs/probes/2026-09-17-m4-sdk/<name>-<UTC>/`.

This is a COPY of the 2026-09-14 harness
(`docs/probes/2026-09-14-schemas/agent-sdk-mcp/master_probe.py`), which is frozen evidence and was
not edited. Two defects named by the M4 plan are fixed in this copy:

  1. the original pins the model id `claude-haiku-4-5-20251001`. This copy resolves the model at
     run time (`--model`, default `claude-haiku-4-5`) and P1 records what both ids do against the
     PATH CLI in `model-resolution.txt`.
  2. the original writes flag settings containing `{"enabledPlugins": {"cc10x@cc10x": false}}`.
     That is exactly what P4 must not do, so the plugin-disabling layer is now opt-in per probe:
     P1-P3 pass `disable_plugins=True`, P4 passes `disable_plugins=False` and writes `{}`.

SAFETY, in the order it is enforced:

  * every `CLAUDE*` / `ANTHROPIC*` / `AI_AGENT` variable inherited from the calling session is
    deleted before the SDK spawns a CLI, so no API key is present and the child is not nested;
  * the process cwd is a throwaway `mkdtemp` directory, never the repo and never a user path;
  * every run passes an explicit `settings=` file inside that throwaway directory. Nothing under
    `~/.claude/` is ever written, and `~/.claude/settings.json`'s sha256 is recorded before and
    after every run into `settings-sha256.txt`;
  * every scenario is wrapped in `anyio.fail_after` and every subprocess call has a timeout;
  * the probe mounts INERT tools only. They return literals. This module never imports
    `shepherd.toolsurface` and never mounts a real handler, so a probe master cannot act on the
    fleet;
  * P1 asserts the isolation lock (`tools=[]` + `strict_mcp_config=True` leaves only the probe's
    own tools in `system/init.tools`) from its own capture. `tests/test_m4_probes.py` re-asserts it
    from the committed file. P2-P4 are scheduled after P1 for that reason;
  * a pid ledger of `claude` processes is taken before and after each run (pids only, never
    cmdlines) and written to `pids.txt`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import warnings

REPO = pathlib.Path(__file__).resolve().parents[3]
PROBE_ROOT = pathlib.Path(__file__).resolve().parent
USER_SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"

PROBE_NAMES = {"p1": "p1-versions", "p2": "p2-interrupt", "p3": "p3-shadow", "p4": "p4-plugins"}

_argv = sys.argv[1:]
if not _argv or _argv[0] not in PROBE_NAMES:
    raise SystemExit(f"usage: probe_m4.py {{{'|'.join(PROBE_NAMES)}}} [--model ID] [--cli PATH]")
PROBE = _argv[0]
MODEL = _argv[_argv.index("--model") + 1] if "--model" in _argv else "claude-haiku-4-5"
PATH_CLI = _argv[_argv.index("--cli") + 1] if "--cli" in _argv else shutil.which("claude")

UTC = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
CAP = PROBE_ROOT / f"{PROBE_NAMES[PROBE]}-{UTC}"
CAP.mkdir(parents=True)
TMP = pathlib.Path(tempfile.mkdtemp(prefix="shp-m4-"))
WORK = TMP / f"work-{PROBE}"
WORK.mkdir(parents=True)
# The process cwd is the throwaway directory, never the repo. The first run of this harness
# omitted this line: P4's `setting_sources=None` run then loaded the repo's project scope and
# wrote its transcript into the repo's own Claude Code project directory. Both the chdir and the
# explicit `cwd=` below exist so the only settings scope that can differ between P4's two runs is
# the USER scope, which is what G-M4-4 asks about.
os.chdir(WORK)

class _StderrTee:
    """Mirror the probe process's own stderr into the capture folder.

    The SDK reports a tool still blocked outside the event loop at client close by writing to this
    process's stderr, not to the CLI's. Without this tee that line is a claim in prose; with it, it
    is `probe-stderr.txt`.
    """

    def __init__(self, stream: object, path: pathlib.Path) -> None:
        self._stream = stream
        self._fh = open(path, "a", buffering=1)

    def write(self, data: str) -> int:
        self._fh.write(data)
        return self._stream.write(data)  # type: ignore[attr-defined,no-any-return]

    def flush(self) -> None:
        self._fh.flush()
        self._stream.flush()  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


sys.stderr = _StderrTee(sys.stderr, CAP / "probe-stderr.txt")  # type: ignore[assignment]

SCRUBBED = sorted(k for k in os.environ if k.startswith(("CLAUDE", "ANTHROPIC")) or k == "AI_AGENT")
for _k in SCRUBBED:
    del os.environ[_k]

import anyio  # noqa: E402  (imported after the env scrub, as the original harness does)
import anyio.to_thread  # noqa: E402
import claude_agent_sdk as sdk  # noqa: E402
from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk import _cli_version  # noqa: E402
from claude_agent_sdk._internal.transport import subprocess_cli as sc  # noqa: E402

META: dict[str, object] = {
    "probe": PROBE,
    "run": CAP.name,
    "model_requested": MODEL,
    "sdk_version": sdk.__version__,
    "bundled_cli_version": _cli_version.__cli_version__,
    "scrubbed_env_names": SCRUBBED,
    "tmpdir": str(TMP),
    "argv": [],
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z"


def append(name: str, obj: object, sub: str = "") -> None:
    d = CAP / sub if sub else CAP
    d.mkdir(parents=True, exist_ok=True)
    with open(d / name, "a") as fh:
        fh.write(json.dumps(obj, default=repr) + "\n")


def sha_user_settings() -> str:
    if not USER_SETTINGS.is_file():
        return "ABSENT"
    return hashlib.sha256(USER_SETTINGS.read_bytes()).hexdigest()


def claude_pids() -> set[int]:
    """pids of every running `claude` process. Pids only -- no cmdlines are ever recorded."""
    r = subprocess.run(["pgrep", "-x", "claude"], capture_output=True, text=True, timeout=30)
    return {int(x) for x in r.stdout.split()}


# ---- raw wire logging: patch the transport class, keep the SDK's own code path ----
_orig_write = sc.SubprocessCLITransport.write
_orig_read = sc.SubprocessCLITransport.read_messages
_orig_build = sc.SubprocessCLITransport._build_command
_SUB = {"dir": ""}  # which sub-capture-folder the current run writes into


async def _write(self, data):  # type: ignore[no-untyped-def]
    for line in data.splitlines():
        if line.strip():
            try:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line": json.loads(line)}, _SUB["dir"])
            except Exception:
                append("raw-stream.jsonl", {"_dir": "out", "_ts": now(), "line_text": line}, _SUB["dir"])
    return await _orig_write(self, data)


def _read(self):  # type: ignore[no-untyped-def]
    async def gen():
        async for msg in _orig_read(self):
            append("raw-stream.jsonl", {"_dir": "in", "_ts": now(), "line": msg}, _SUB["dir"])
            yield msg

    return gen()


def _build(self):  # type: ignore[no-untyped-def]
    cmd = _orig_build(self)
    META["argv"].append(cmd)  # type: ignore[union-attr]
    META["cli_path"] = cmd[0]
    ver = subprocess.run([cmd[0], "--version"], capture_output=True, text=True, timeout=120).stdout.strip()
    # one entry per spawned CLI: P1 spawns the bundled binary twice and the PATH binary once, and a
    # single scalar here would report only the last of the three
    spawned = META.setdefault("cli_versions_spawned", [])
    if [cmd[0], ver] not in spawned:
        spawned.append([cmd[0], ver])  # type: ignore[union-attr]
    return cmd


sc.SubprocessCLITransport.write = _write
sc.SubprocessCLITransport.read_messages = _read
sc.SubprocessCLITransport._build_command = _build


def stderr_cb(line: str) -> None:
    d = CAP / _SUB["dir"] if _SUB["dir"] else CAP
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "stderr.txt", "a") as fh:
        fh.write(line.rstrip("\n") + "\n")


def log_message(msg: object, label: str = "") -> None:
    d = dataclasses.asdict(msg) if dataclasses.is_dataclass(msg) else {"repr": repr(msg)}
    append("messages.jsonl", {"_ts": now(), "_label": label, "_class": type(msg).__name__, "fields": d}, _SUB["dir"])


# ---- inert probe tools: literals only, no Shepherd import, no real handler ----
async def _record(name: str, args: object, result: dict) -> dict:
    append("handler-calls.jsonl", {"_ts": now(), "tool": name, "received": args, "returned": result}, _SUB["dir"])
    return result


@tool("fleet_summary", "Return counts of sessions by bucket. Takes no arguments.",
      {"type": "object", "properties": {}})
async def fleet_summary(args):  # type: ignore[no-untyped-def]
    return await _record("fleet_summary", args, {"content": [{"type": "text", "text": json.dumps(
        {"running": 2, "needs_you": ["ses_a1"], "stopped": 1})}]})


@tool("spawn_session", "Spawn a session in a project with a task.",
      {"type": "object",
       "properties": {"project_id": {"type": "string"}, "task": {"type": "string"},
                      "model": {"type": ["string", "null"]}},
       "required": ["project_id", "task"]})
async def spawn_session(args):  # type: ignore[no-untyped-def]
    return await _record("spawn_session", args, {"content": [{"type": "text", "text": "ses_new42"}]})


@tool("shadow_tool", "A tool deliberately left out of allowed_tools.", {"id": str})
async def shadow_tool(args):  # type: ignore[no-untyped-def]
    return await _record("shadow_tool", args,
                         {"content": [{"type": "text", "text": "shadow_tool ran for " + str(args.get("id"))}]})


@tool("fail_tool", "A tool that always reports an error result.", {"reason": str})
async def fail_tool(args):  # type: ignore[no-untyped-def]
    return await _record("fail_tool", args, {
        "content": [{"type": "text", "text": "max_children_per_session=5 reached"}], "is_error": True})


@tool("raise_tool", "A tool whose handler raises an exception.", {"type": "object", "properties": {}})
async def raise_tool(args):  # type: ignore[no-untyped-def]
    append("handler-calls.jsonl",
           {"_ts": now(), "tool": "raise_tool", "received": args, "returned": "RAISES RuntimeError"}, _SUB["dir"])
    raise RuntimeError("handler exploded on purpose")


SLOW_SECONDS = 20


@tool("slow_tool", "A tool whose handler blocks a worker thread for 20 seconds.", {"id": str})
async def slow_tool(args):  # type: ignore[no-untyped-def]
    """P2's subject. The blocking work runs off the event loop exactly as ADR-M4-3 plans it:
    `anyio.to_thread.run_sync`, whose `abandon_on_cancel` default is False."""
    append("handler-calls.jsonl", {"_ts": now(), "tool": "slow_tool", "phase": "entered", "received": args}, _SUB["dir"])

    def blocking() -> str:
        for i in range(SLOW_SECONDS):
            time.sleep(1)
            append("handler-calls.jsonl",
                   {"_ts": now(), "tool": "slow_tool", "phase": "thread_tick", "second": i + 1}, _SUB["dir"])
        return "worker thread ran to completion"

    try:
        outcome = await anyio.to_thread.run_sync(blocking)
    except BaseException as exc:  # noqa: BLE001 -- the whole point is which class arrives
        append("handler-calls.jsonl",
               {"_ts": now(), "tool": "slow_tool", "phase": "await_raised",
                "exc": f"{type(exc).__name__}: {exc}"}, _SUB["dir"])
        raise
    append("handler-calls.jsonl",
           {"_ts": now(), "tool": "slow_tool", "phase": "await_returned", "outcome": outcome}, _SUB["dir"])
    return {"content": [{"type": "text", "text": outcome}]}


async def authorize(tool_name, tool_input, context):  # type: ignore[no-untyped-def]
    decision = {"behavior": "allow", "updated_input": tool_input}
    append("can-use-tool.jsonl",
           {"_ts": now(), "tool_name": tool_name, "tool_input": tool_input,
            "context": dataclasses.asdict(context) if dataclasses.is_dataclass(context) else repr(context),
            "returned": decision}, _SUB["dir"])
    return PermissionResultAllow(updated_input=tool_input)


async def hook_cb(input_data, tool_use_id, context):  # type: ignore[no-untyped-def]
    append("hooks.jsonl", {"_ts": now(), "tool_use_id": tool_use_id, "input_data": input_data,
                           "context": repr(context)}, _SUB["dir"])
    return {}


def settings_file(name: str, *, disable_plugins: bool) -> str:
    """An explicit flag-settings file inside the throwaway tmpdir.

    `disable_plugins=False` writes `{}` -- P4's whole question is what happens with no
    `enabledPlugins` override at all, which is the defect fixed in this copy of the harness.
    """
    body = {"enabledPlugins": {"cc10x@cc10x": False}} if disable_plugins else {}
    p = TMP / f"flag-settings-{name}.json"
    p.write_text(json.dumps(body))
    return str(p)


def base_options(label: str, *, disable_plugins: bool = True, **over):  # type: ignore[no-untyped-def]
    o: dict[str, object] = dict(
        model=MODEL,
        system_prompt="You are a probe orchestrator. Follow the user's instructions literally and briefly.",
        setting_sources=[],
        disallowed_tools=["Agent", "Task"],
        allowed_tools=["mcp__shepherd__fleet_summary", "mcp__shepherd__spawn_session",
                       "mcp__shepherd__fail_tool", "mcp__shepherd__raise_tool"],
        mcp_servers={"shepherd": create_sdk_mcp_server(
            name="shepherd", tools=[fleet_summary, spawn_session, shadow_tool, fail_tool, raise_tool])},
        can_use_tool=authorize,
        hooks={ev: [HookMatcher(matcher=None, hooks=[hook_cb])]
               for ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure")},
        cwd=str(WORK),
        settings=settings_file(label, disable_plugins=disable_plugins),
        stderr=stderr_cb,
        max_turns=14,
    )
    o.update(over)
    return ClaudeAgentOptions(**o)  # type: ignore[arg-type]


async def run_turn(client, prompt, label):  # type: ignore[no-untyped-def]
    t0 = time.time()
    await client.query(prompt)
    result = None
    async for m in client.receive_response():
        log_message(m, label)
        if isinstance(m, ResultMessage):
            result = m
    META.setdefault("turns", []).append(  # type: ignore[union-attr]
        {"label": label, "wall_s": round(time.time() - t0, 2),
         "session_id": getattr(result, "session_id", None),
         "subtype": getattr(result, "subtype", None),
         "terminal_reason": getattr(result, "terminal_reason", None)})
    return result


BASIC_PROMPT = (
    "Do these steps in order, one tool call at a time, then reply with the single word DONE:\n"
    "1. call mcp__shepherd__fleet_summary\n"
    "2. call mcp__shepherd__spawn_session with project_id='p1' and task='write tests'\n"
    "3. call mcp__shepherd__shadow_tool with id='ses_a1'\n"
    "4. call mcp__shepherd__fail_tool with reason='probe'\n"
    "5. call mcp__shepherd__raise_tool\n"
    "6. call mcp__shepherd__spawn_session with ONLY project_id='p2' and no task argument at all\n"
    "7. run the Bash command: echo hi\n"
)


# ---------------------------------------------------------------- P1
#: The field names data-schemas.md (pinned at 0.2.152 / 2.1.259 / 2.1.270) records for each shape.
#: P1 diffs the observed key sets against these. A key here that is absent live, or a key live that
#: is absent here, is drift and becomes a row in FINDINGS.md.
EXPECTED_FIELDS: dict[str, list[str]] = {
    "system/init": [
        "type", "subtype", "cwd", "session_id", "tools", "mcp_servers", "model", "permissionMode",
        "slash_commands", "terminal_slash_commands", "apiKeySource", "claude_code_version",
        "output_style", "agents", "skills", "plugins", "capabilities", "analytics_disabled",
        "product_feedback_disabled", "uuid", "memory_paths", "messaging_socket_path",
        "fast_mode_state", "fast_mode_disabled_reason",
    ],
    "tools/list result.tools[]": ["name", "description", "inputSchema"],
    "tools/call result": ["content", "isError"],
    "can_use_tool request": [
        "subtype", "tool_name", "display_name", "input", "permission_suggestions", "tool_use_id"],
    "ResultMessage": [
        "type", "subtype", "is_error", "terminal_reason", "stop_reason", "session_id", "num_turns",
        "duration_ms", "duration_api_ms", "total_cost_usd", "usage", "modelUsage",
        "permission_denials", "result", "api_error_status", "subagent_stats", "ttft_ms",
        "ttft_stream_ms", "time_to_request_ms", "queued_turn_count", "fast_mode_state",
        "fast_mode_disabled_reason", "uuid",
    ],
}


def _observed_fields(sub: str) -> dict[str, dict[str, object]]:
    """Read back the capture just written and pull the key set of each pinned shape."""
    path = (CAP / sub / "raw-stream.jsonl") if sub else (CAP / "raw-stream.jsonl")
    out: dict[str, dict[str, object]] = {}
    for raw in path.read_text().splitlines():
        rec = json.loads(raw)
        line = rec.get("line")
        if not isinstance(line, dict):
            continue
        if line.get("type") == "system" and line.get("subtype") == "init":
            out.setdefault("system/init", {"keys": sorted(line)})
        if line.get("type") == "result":
            out.setdefault("ResultMessage", {"keys": sorted(line)})
        req = line.get("request")
        if isinstance(req, dict) and req.get("subtype") == "can_use_tool":
            out.setdefault("can_use_tool request", {"keys": sorted(req)})
        resp = line.get("response")
        if isinstance(resp, dict):
            mcp = (resp.get("response") or {}).get("mcp_response") if isinstance(resp.get("response"), dict) else None
            if isinstance(mcp, dict) and isinstance(mcp.get("result"), dict):
                res = mcp["result"]
                if "tools" in res and res["tools"]:
                    out.setdefault("tools/list result.tools[]", {"keys": sorted(res["tools"][0])})
                if "content" in res:
                    out.setdefault("tools/call result", {"keys": sorted(res)})
    return out


def _init_tools(sub: str) -> list[str]:
    path = (CAP / sub / "raw-stream.jsonl") if sub else (CAP / "raw-stream.jsonl")
    for raw in path.read_text().splitlines():
        line = json.loads(raw).get("line")
        if isinstance(line, dict) and line.get("type") == "system" and line.get("subtype") == "init":
            return list(line.get("tools", []))
    return []


def _init_servers(sub: str) -> list[object]:
    path = (CAP / sub / "raw-stream.jsonl") if sub else (CAP / "raw-stream.jsonl")
    for raw in path.read_text().splitlines():
        line = json.loads(raw).get("line")
        if isinstance(line, dict) and line.get("type") == "system" and line.get("subtype") == "init":
            return list(line.get("mcp_servers", []))
    return []


def model_resolution() -> None:
    """Defect 1 of the copied harness: record what the original's pinned model id actually does."""
    if not PATH_CLI:
        (CAP / "model-resolution.txt").write_text("no `claude` on PATH; not checked\n")
        return
    lines = []
    settings = settings_file("model-check", disable_plugins=True)
    for mid in ("claude-haiku-4-5-20251001", MODEL):
        cmd = [PATH_CLI, "-p", "--model", mid, "--settings", settings,
               "--setting-sources=", "--strict-mcp-config", "say OK"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(WORK))
            lines.append(f"model={mid} rc={r.returncode} stdout={r.stdout.strip()[:200]!r} "
                         f"stderr={r.stderr.strip()[:300]!r}")
        except subprocess.TimeoutExpired:
            lines.append(f"model={mid} TIMEOUT after 180 s")
    (CAP / "model-resolution.txt").write_text(
        f"PATH claude: {PATH_CLI}\n" + "\n".join(lines) + "\n")


async def probe_p1() -> None:
    """Re-pin the shapes at the installed versions, and assert the isolation lock."""
    model_resolution()

    runs = [
        ("", dict(tools=[], strict_mcp_config=True)),                      # `locked`, at the root
        ("deny", dict(tools=[], strict_mcp_config=True, can_use_tool=None)),
        ("locked-syscli", dict(tools=[], strict_mcp_config=True)),
    ]
    for sub, extra in runs:
        _SUB["dir"] = sub
        label = sub or "locked"
        if sub == "deny":
            async def deny_authorize(tool_name, tool_input, context):  # type: ignore[no-untyped-def]
                d = PermissionResultDeny(message="you declined this")
                append("can-use-tool.jsonl", {"_ts": now(), "tool_name": tool_name,
                                              "tool_input": tool_input,
                                              "returned": dataclasses.asdict(d)}, _SUB["dir"])
                return d
            extra["can_use_tool"] = deny_authorize
            prompt = ("Call mcp__shepherd__shadow_tool with id='ses_x'. "
                      "If it fails, reply with the exact error text you received.")
        else:
            prompt = BASIC_PROMPT
        if sub == "locked-syscli":
            if not PATH_CLI:
                continue
            extra["cli_path"] = PATH_CLI
        async with ClaudeSDKClient(options=base_options(label, **extra)) as client:
            await run_turn(client, prompt, label)

    _SUB["dir"] = ""
    # --- the isolation lock, asserted from this run's own capture, before P2-P4 mount anything ---
    lock: dict[str, object] = {}
    for sub, label in (("", "locked"), ("locked-syscli", "locked-syscli")):
        p = (CAP / sub / "raw-stream.jsonl") if sub else (CAP / "raw-stream.jsonl")
        if not p.is_file():
            continue
        tools = _init_tools(sub)
        servers = _init_servers(sub)
        expected = {"mcp__shepherd__fleet_summary", "mcp__shepherd__spawn_session",
                    "mcp__shepherd__shadow_tool", "mcp__shepherd__fail_tool",
                    "mcp__shepherd__raise_tool"}
        lock[label] = {
            "system/init.tools": sorted(tools),
            "equals_probe_tools_exactly": set(tools) == expected,
            "unexpected_tools": sorted(set(tools) - expected),
            "system/init.mcp_servers": servers,
            "only_shepherd_server": [s.get("name") for s in servers if isinstance(s, dict)] == ["shepherd"],
        }
    (CAP / "isolation-lock.json").write_text(json.dumps(lock, indent=2))
    META["isolation_lock"] = lock

    # --- the field diff against data-schemas.md's pinned tables ---
    report = []
    for sub, label in (("", "locked"), ("deny", "deny"), ("locked-syscli", "locked-syscli")):
        p = (CAP / sub / "raw-stream.jsonl") if sub else (CAP / "raw-stream.jsonl")
        if not p.is_file():
            continue
        obs = _observed_fields(sub)
        report.append(f"=== {label} ===")
        for shape, expected in EXPECTED_FIELDS.items():
            if shape not in obs:
                report.append(f"{shape}: NOT OBSERVED in this run")
                continue
            keys = set(obs[shape]["keys"])  # type: ignore[arg-type]
            added = sorted(keys - set(expected))
            removed = sorted(set(expected) - keys)
            verdict = "IDENTICAL" if not added and not removed else "DRIFT"
            report.append(f"{shape}: {verdict}")
            if added:
                report.append(f"    added since 2026-09-14: {added}")
            if removed:
                report.append(f"    absent that 2026-09-14 recorded: {removed}")
        report.append("")
    (CAP / "field-diff.txt").write_text("\n".join(report) + "\n")


# ---------------------------------------------------------------- P2
async def probe_p2() -> None:
    """interrupt() while an in-process MCP tool handler is running in a worker thread."""
    opts = base_options(
        "p2", tools=[], strict_mcp_config=True, max_turns=4,
        mcp_servers={"shepherd": create_sdk_mcp_server(name="shepherd", tools=[slow_tool])},
        allowed_tools=["mcp__shepherd__slow_tool"])
    async with ClaudeSDKClient(options=opts) as client:
        t0 = time.time()
        await client.query("Call mcp__shepherd__slow_tool with id='ses_slow'. "
                           "Then reply with the tool's result text only.")

        async def killer() -> None:
            await anyio.sleep(5)
            ti = time.time()
            rv = await client.interrupt()
            META["interrupt"] = {"since_query_s": round(ti - t0, 2), "returned": repr(rv),
                                 "call_s": round(time.time() - ti, 3)}
            append("messages.jsonl", {"_ts": now(), "_label": "PROBE", "_class": "interrupt() returned",
                                      "fields": {"repr": repr(rv)}})

        async with anyio.create_task_group() as tg:
            tg.start_soon(killer)
            async for m in client.receive_response():
                log_message(m, "p2")
        META["turn_wall_s"] = round(time.time() - t0, 2)
        r = await run_turn(client, "Reply with only the word AFTER.", "after-interrupt")
        META["client_still_usable"] = {
            "result": getattr(r, "result", None), "session_id": getattr(r, "session_id", None),
            "subtype": getattr(r, "subtype", None)}

    # The worker thread can outlive the client. Settle before reading the log back, or the
    # answer file records a half-written capture (observed on the first run of this probe).
    settle_deadline = time.time() + SLOW_SECONDS + 10
    last = -1
    while time.time() < settle_deadline:
        size = (CAP / "handler-calls.jsonl").stat().st_size
        if size == last:
            break
        last = size
        await anyio.sleep(2)

    # answer the question in one machine-readable place
    calls = [json.loads(x) for x in (CAP / "handler-calls.jsonl").read_text().splitlines()]
    ticks = [c for c in calls if c.get("phase") == "thread_tick"]
    raised = [c for c in calls if c.get("phase") == "await_raised"]
    returned = [c for c in calls if c.get("phase") == "await_returned"]
    cancels = [json.loads(x) for x in (CAP / "raw-stream.jsonl").read_text().splitlines()
               if json.loads(x).get("line", {}).get("type") == "control_cancel_request"]
    (CAP / "answer.json").write_text(json.dumps({
        "worker_thread_ticks_observed": len(ticks),
        "worker_thread_ran_to_completion": len(ticks) == SLOW_SECONDS,
        "await_raised": raised,
        "await_returned": returned,
        "control_cancel_request_lines": cancels,
        "interrupted_turn_result": [
            {k: line.get(k) for k in ("subtype", "terminal_reason", "is_error", "stop_reason",
                                      "permission_denials", "errors", "result")}
            for line in (json.loads(x).get("line") for x in
                         (CAP / "raw-stream.jsonl").read_text().splitlines())
            if isinstance(line, dict) and line.get("type") == "result"
        ],
        "interrupt": META.get("interrupt"),
        "turn_wall_s": META.get("turn_wall_s"),
        "client_still_usable": META.get("client_still_usable"),
    }, indent=2, default=repr))


# ---------------------------------------------------------------- P3
async def probe_p3() -> None:
    """What reaches can_use_tool for a tool outside allowed_tools, under the isolation lock."""
    opts = base_options(
        "p3", tools=[], strict_mcp_config=True, max_turns=6,
        mcp_servers={"shepherd": create_sdk_mcp_server(name="shepherd",
                                                       tools=[fleet_summary, shadow_tool])},
        allowed_tools=["mcp__shepherd__fleet_summary"])
    caught: list[str] = []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        async with ClaudeSDKClient(options=opts) as client:
            await run_turn(client,
                           "Do these in order, one tool call at a time, then reply DONE:\n"
                           "1. call mcp__shepherd__fleet_summary\n"
                           "2. call mcp__shepherd__shadow_tool with id='ses_shadow'\n", "p3")
        caught = [f"{x.category.__name__}: {x.message}" for x in w]
    META["warnings"] = caught

    seen = [json.loads(x) for x in (CAP / "can-use-tool.jsonl").read_text().splitlines()] \
        if (CAP / "can-use-tool.jsonl").is_file() else []
    (CAP / "answer.json").write_text(json.dumps({
        "allowed_tools": ["mcp__shepherd__fleet_summary"],
        "mounted_tools": ["mcp__shepherd__fleet_summary", "mcp__shepherd__shadow_tool"],
        "can_use_tool_calls": [c.get("tool_name") for c in seen],
        "shadow_tool_reached_can_use_tool": any(
            c.get("tool_name") == "mcp__shepherd__shadow_tool" for c in seen),
        "allowlisted_tool_reached_can_use_tool": any(
            c.get("tool_name") == "mcp__shepherd__fleet_summary" for c in seen),
        "warnings": caught,
        "shadowed_warning_emitted": any("CanUseToolShadowedWarning" in x for x in caught),
    }, indent=2, default=repr))
    (CAP / "warnings.txt").write_text("\n".join(caught) + "\n" if caught else "(no warnings)\n")


# ---------------------------------------------------------------- P4
async def probe_p4() -> None:
    """cc10x under setting_sources=[] versus None, with NO flag-settings enabledPlugins override."""
    results: dict[str, object] = {}
    for sub, ss in (("setting-sources-empty", []), ("setting-sources-none", None)):
        _SUB["dir"] = sub
        opts = base_options(sub, disable_plugins=False, setting_sources=ss,
                            tools=[], strict_mcp_config=True, max_turns=2,
                            mcp_servers={"shepherd": create_sdk_mcp_server(
                                name="shepherd", tools=[fleet_summary])},
                            allowed_tools=["mcp__shepherd__fleet_summary"])
        async with ClaudeSDKClient(options=opts) as client:
            r = await run_turn(client, "Say hello in one word.", sub)
        init = None
        for raw in (CAP / sub / "raw-stream.jsonl").read_text().splitlines():
            line = json.loads(raw).get("line")
            if isinstance(line, dict) and line.get("type") == "system" and line.get("subtype") == "init":
                init = line
                break
        session_id = getattr(r, "session_id", None)
        transcript = None
        if session_id:
            # our own throwaway session's transcript, copied for the attachment question
            for d in (pathlib.Path.home() / ".claude" / "projects").glob("*"):
                cand = d / f"{session_id}.jsonl"
                if cand.is_file():
                    shutil.copy(cand, CAP / sub / f"transcript-{session_id}.jsonl")
                    transcript = str(cand)
                    break
        attachments = []
        if transcript:
            for raw in pathlib.Path(transcript).read_text().splitlines():
                try:
                    e = json.loads(raw)
                except Exception:
                    continue
                if e.get("type") == "attachment":
                    a = e.get("attachment") or {}
                    attachments.append({"subtype": a.get("type") or a.get("subtype"),
                                        "keys": sorted(a)[:12]})
        results[sub] = {
            "setting_sources": ss,
            "flag_settings_body": "{}",
            "plugins": (init or {}).get("plugins"),
            "skills_count": len((init or {}).get("skills") or []),
            "skills": (init or {}).get("skills"),
            "slash_commands_count": len((init or {}).get("slash_commands") or []),
            "tools": (init or {}).get("tools"),
            "mcp_servers": (init or {}).get("mcp_servers"),
            "result": getattr(r, "result", None),
            "transcript": transcript,
            "attachment_subtypes": attachments,
        }
    _SUB["dir"] = ""
    (CAP / "answer.json").write_text(json.dumps(results, indent=2, default=repr))
    META["p4"] = {k: {"plugins": v["plugins"], "skills_count": v["skills_count"]}  # type: ignore[index]
                  for k, v in results.items()}


PROBES = {"p1": (probe_p1, 900), "p2": (probe_p2, 300), "p3": (probe_p3, 300), "p4": (probe_p4, 300)}


async def main() -> None:
    fn, budget = PROBES[PROBE]
    META["settings_sha256_before"] = sha_user_settings()
    pids_before = claude_pids()
    META["started_at"] = now()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            with anyio.fail_after(budget):
                await fn()
            META["status"] = "ok"
        except BaseException as e:  # noqa: BLE001 -- a probe records its own failure
            META["status"] = f"error: {type(e).__name__}: {e}"
            META["traceback"] = traceback.format_exc()
        META.setdefault("warnings", [f"{x.category.__name__}: {x.message}" for x in w])
    META["finished_at"] = now()
    META["settings_sha256_after"] = sha_user_settings()
    META["user_settings_unchanged"] = META["settings_sha256_before"] == META["settings_sha256_after"]
    time.sleep(2)
    pids_after = claude_pids()
    survivors = sorted(pids_after - pids_before)
    META["claude_pids_before_count"] = len(pids_before)
    META["claude_pids_after_count"] = len(pids_after)
    META["claude_pids_new_after"] = survivors

    (CAP / "settings-sha256.txt").write_text(
        f"{META['settings_sha256_before']}  ~/.claude/settings.json (before)\n"
        f"{META['settings_sha256_after']}  ~/.claude/settings.json (after)\n"
        f"unchanged: {META['user_settings_unchanged']}\n")
    (CAP / "pids.txt").write_text(
        f"claude pids before: {len(pids_before)}\n"
        f"claude pids after: {len(pids_after)}\n"
        f"new claude pids surviving this probe: {survivors or 'none'}\n")
    (CAP / "versions.txt").write_text(
        f"probe: {PROBE_NAMES[PROBE]}\n"
        f"claude_agent_sdk.__version__: {sdk.__version__}\n"
        f"bundled __cli_version__: {_cli_version.__cli_version__}\n"
        f"PATH claude --version: "
        f"{subprocess.run([PATH_CLI, '--version'], capture_output=True, text=True, timeout=120).stdout.strip() if PATH_CLI else 'absent'}\n"
        + "".join(f"cli spawned by this run: {pth} -> {ver}\n"
                  for pth, ver in META.get("cli_versions_spawned", []))  # type: ignore[union-attr]
        + f"python: {sys.version.split()[0]}\n"
        f"model requested: {MODEL}\n"
        f"run: {CAP.name}\n")
    key = str(WORK).replace("/", "-").replace(".", "-").replace("_", "-")
    proj = pathlib.Path.home() / ".claude" / "projects"
    residue = sorted(str(d) for d in proj.glob(key + "*"))
    META["engine_owned_residue"] = residue
    (CAP / "residue.txt").write_text(
        "Engine-owned directories this probe caused Claude Code to create.\n"
        "Recorded, not deleted (K3: the probe removes only what it created itself).\n"
        + ("\n".join(residue) if residue else "(none)") + "\n")
    (CAP / "meta.json").write_text(json.dumps(META, indent=2, default=repr))
    shutil.rmtree(TMP, ignore_errors=True)
    print(PROBE, META["status"], "->", CAP)


anyio.run(main)
