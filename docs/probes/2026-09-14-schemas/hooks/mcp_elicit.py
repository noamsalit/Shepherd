#!/usr/bin/env python3
"""Minimal stdio MCP server whose one tool asks the client for input via
elicitation/create, to provoke the Elicitation / ElicitationResult hooks (2026-09-14).
Logs every JSON-RPC message it sends/receives to $SHP_MCP_LOG if set (no secrets involved).
"""
import json, os, sys

LOG = os.environ.get("SHP_MCP_LOG")


def log(direction, msg):
    if LOG:
        with open(LOG, "a") as f:
            f.write(json.dumps({"dir": direction, "msg": msg}) + "\n")


def send(msg):
    log("out", msg)
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def read():
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    msg = json.loads(line)
    log("in", msg)
    return msg


client_caps = {}
pending_call = None
while True:
    m = read()
    meth = m.get("method")
    if meth == "initialize":
        client_caps = m.get("params", {}).get("capabilities", {})
        send({"jsonrpc": "2.0", "id": m["id"], "result": {
            "protocolVersion": m.get("params", {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}}, "serverInfo": {"name": "shpelicit", "version": "0.1"}}})
    elif meth == "tools/list":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [{
            "name": "ask_name", "description": "Asks the user for a name via elicitation.",
            "inputSchema": {"type": "object", "properties": {}}}]}})
    elif meth == "tools/call":
        pending_call = m["id"]
        send({"jsonrpc": "2.0", "id": "elicit-1", "method": "elicitation/create", "params": {
            "message": "What name should the probe use?",
            "requestedSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}})
    elif m.get("id") == "elicit-1" and pending_call is not None:
        send({"jsonrpc": "2.0", "id": pending_call, "result": {"content": [
            {"type": "text", "text": "elicitation response: " + json.dumps(m.get("result") or m.get("error"))}]}})
        pending_call = None
    elif "id" in m and meth:
        send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
