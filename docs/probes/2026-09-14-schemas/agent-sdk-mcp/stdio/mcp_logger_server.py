#!/usr/bin/env python3
"""Tiny stdlib-only stdio MCP server that logs every JSON-RPC message it receives and sends.
Usage (as an MCP stdio command): python3 mcp_logger_server.py <log.jsonl>
Wire format assumed: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport).
Tools: echo_note(text, count?) ok; fail_note(reason) -> result isError:true;
       rpc_error_note() -> JSON-RPC error -32603; danger_note(target) (left out of --allowedTools).
"""
import json, os, sys, time

LOG = sys.argv[1]
T0 = time.time()

def ancestry():
    out, pid = [], os.getpid()
    for _ in range(10):
        try:
            st = open(f"/proc/{pid}/status").read()
            comm = [l.split("\t", 1)[1] for l in st.splitlines() if l.startswith("Name:")][0]
            ppid = int([l.split("\t", 1)[1] for l in st.splitlines() if l.startswith("PPid:")][0])
        except Exception:
            break
        out.append({"pid": pid, "comm": comm, "ppid": ppid})
        if ppid <= 1:
            break
        pid = ppid
    return out

def log(direction, raw):
    rec = {"_dir": direction, "_ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time()*1000)%1000:03d}Z",
           "_t": round(time.time() - T0, 3)}
    rec["raw"] = raw  # the exact line as read from / written to the pipe (newline stripped)
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")

with open(LOG, "a") as fh:
    fh.write(json.dumps({"_dir": "start", "pid": os.getpid(), "argv": sys.argv, "cwd": os.getcwd(),
                         "env_names": sorted(os.environ),
                         "env_values_allowlisted": {k: os.environ.get(k) for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR", "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE", "PROBE_MARKER", "SHP_CLAUDE_VERSION")},
                         "secret_env_names_present_values_not_logged": [k for k in sorted(os.environ) if "TOKEN" in k or "KEY" in k or "SECRET" in k],
                         "ancestry": ancestry()}) + "\n")

TOOLS = [
    {"name": "echo_note", "title": "Echo Note", "description": "Echo a note back. Probe tool.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string", "description": "the note"},
                                                      "count": {"type": "integer", "minimum": 1}},
                     "required": ["text"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "fail_note", "description": "Always returns a tool-level error result (isError).",
     "inputSchema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}},
    {"name": "rpc_error_note", "description": "Always returns a JSON-RPC protocol error.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "danger_note", "description": "A destructive probe tool that is not pre-allowed.",
     "inputSchema": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
     "annotations": {"destructiveHint": True}},
]

def send(obj):
    line = json.dumps(obj)
    log("out", line)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()

for raw in sys.stdin:
    raw = raw.rstrip("\n")
    if not raw.strip():
        continue
    log("in", raw)
    try:
        msg = json.loads(raw)
    except Exception:
        continue
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        continue  # notification
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "probe-logger", "version": "0.0.1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name == "echo_note":
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"echo: {args.get('text')!r} count={args.get('count')!r}"}], "isError": False}})
        elif name == "fail_note":
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "max_session_depth=3 reached; refusing"}], "isError": True}})
        elif name == "rpc_error_note":
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "probe internal error"}})
        elif name == "danger_note":
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "danger done"}]}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}})
