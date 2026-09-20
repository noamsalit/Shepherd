#!/usr/bin/env python3
"""Minimal stdio MCP server for the gap-fill probes (2026-09-14). Stands in for `shepherd-mcp`.
Tools:
  ping      -> text "pong"
  ask_form  -> sends elicitation/create (form mode) to the client, returns the client's answer
  ask_url   -> sends elicitation/create (url mode) to the client, returns the client's answer
Every JSON-RPC message in and out is appended to argv[1] or $SHP_MCP_LOG (if set) with a timestamp and this pid.
"""
import json, os, sys, time

LOG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHP_MCP_LOG")


def log(direction, msg):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "pid": os.getpid(), "dir": direction, "msg": msg}) + "\n")


def send(msg):
    log("out", msg)
    sys.stdout.write(json.dumps(msg) + "\n"); sys.stdout.flush()


pending = {}
n = 0
log("start", {"argv": sys.argv, "ppid": os.getppid()})
for line in sys.stdin:
    try:
        m = json.loads(line)
    except Exception:
        continue
    log("in", m)
    meth = m.get("method")
    if meth == "initialize":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {
            "protocolVersion": m.get("params", {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}}, "serverInfo": {"name": "shepherd-stub", "version": "0.1"}}})
    elif meth == "tools/list":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [
            {"name": "ping", "description": "Returns pong.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "ask_form", "description": "Asks the user a question via a form elicitation.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "ask_url", "description": "Asks the user to visit a URL via a url elicitation.", "inputSchema": {"type": "object", "properties": {}}}]}})
    elif meth == "tools/call":
        name = m["params"]["name"]
        if name == "ping":
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"content": [{"type": "text", "text": "pong"}]}})
        else:
            n += 1
            eid = f"elicit-{n}"
            pending[eid] = m["id"]
            if name == "ask_form":
                params = {"mode": "form", "message": "Which queue should the probe use?",
                          "requestedSchema": {"type": "object", "properties": {"queue": {"type": "string"}}, "required": ["queue"]}}
            else:
                params = {"mode": "url", "message": "Approve the probe in your browser.",
                          "url": "https://example.invalid/shepherd-probe/approve", "elicitationId": f"shp-{n}"}
            send({"jsonrpc": "2.0", "id": eid, "method": "elicitation/create", "params": params})
    elif "id" in m and m.get("id") in pending and not meth:
        send({"jsonrpc": "2.0", "id": pending.pop(m["id"]), "result": {"content": [
            {"type": "text", "text": "elicitation answer: " + json.dumps(m.get("result") or m.get("error"))}]}})
    elif "id" in m and meth:
        send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
