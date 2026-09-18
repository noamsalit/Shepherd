#!/usr/bin/env python3
"""Scriptable local stand-in for the Anthropic Messages API (gap-fill probes, 2026-09-14).
Bound to 127.0.0.1. Used with an isolated CLAUDE_CONFIG_DIR and a fake ANTHROPIC_API_KEY so the real CLI
produces real hook payloads, transcripts and dialogs without touching the user's account.

Usage: mock_api2.py <port> <rules.json> <requests.jsonl>
rules.json: {"rules": [ {"match": "<substring of the last user text or tool_result>",
                          "match_body": "<substring anywhere in the request body>",
                          "tool_use": {"name": "...", "input": {...}} | "text": "..." | "hang_s": 600,
                          "input_tokens": 10, "once": true}, ... ],
             "default_text": "OK-MOCK"}
"require_tools": true skips side requests that carry no tools (e.g. the session-title request).
Rules are tried in order; the first match wins. A request whose last message is a tool_result gets
"default_after_tool" (default "OK-AFTER-TOOL") unless a rule matches it.
Logged per request (no headers except anthropic-beta, never the API key): path, model, top-level body keys,
thinking, output_config, effort-like keys, max_tokens, tool names, n_messages, last user text (first 300 chars),
system text length, matched rule index.
"""
import json, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, RULES, LOG = int(sys.argv[1]), sys.argv[2], sys.argv[3]
LOCK = threading.Lock()
USED = set()


def load_rules():
    try:
        return json.load(open(RULES))
    except Exception:
        return {"rules": []}


def last_user_text(req):
    msgs = req.get("messages") or []
    for m in reversed(msgs):
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            return c, False
        parts, is_tool = [], False
        for b in c or []:
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif b.get("type") == "tool_result":
                is_tool = True
                cc = b.get("content")
                parts.append(json.dumps(cc) if not isinstance(cc, str) else cc)
        # the CLI appends <system-reminder> text blocks; keep the whole joined text
        return "\n".join(parts), is_tool
    return "", False


def sse(events):
    return b"".join(f"event: {n}\ndata: {json.dumps(d)}\n\n".encode() for n, d in events)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _write_log(self, obj):
        with LOCK, open(LOG, "a") as f:
            f.write(json.dumps(obj) + "\n")

    def do_GET(self):
        self._write_log({"t": round(time.time(), 3), "method": "GET", "path": self.path})
        b = b'{"type":"error","error":{"type":"not_found_error","message":"not found"}}'
        self.send_response(404); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_HEAD(self):
        self.send_response(200); self.send_header("content-length", "0"); self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw)
        except Exception:
            req = {}
        if "count_tokens" in self.path:
            ct = load_rules().get("count_tokens", 10)
            self._write_log({"t": round(time.time(), 3), "method": "POST", "path": self.path, "count_tokens_returned": ct,
                             "n_messages": len(req.get("messages") or [])})
            b = json.dumps({"input_tokens": ct}).encode()
            self.send_response(200); self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        text, is_tool = last_user_text(req)
        cfg = load_rules()
        body_s = raw.decode("utf-8", "replace")
        chosen, idx = None, None
        for i, r in enumerate(cfg.get("rules", [])):
            if r.get("once") and i in USED:
                continue
            if "match" in r and r["match"] not in text:
                continue
            if "match_body" in r and r["match_body"] not in body_s:
                continue
            if r.get("require_tools") and not req.get("tools"):
                continue
            if r.get("only_tool_result") and not is_tool:
                continue
            if r.get("not_tool_result") and is_tool:
                continue
            chosen, idx = r, i
            USED.add(i)
            break
        sys_txt = req.get("system")
        sys_len = len(json.dumps(sys_txt)) if sys_txt is not None else 0
        entry = {"t": round(time.time(), 3), "method": "POST", "path": self.path, "model": req.get("model"),
                 "body_keys": sorted(req.keys()), "thinking": req.get("thinking"), "output_config": req.get("output_config"),
                 "effort_like": {k: v for k, v in req.items() if "effort" in k.lower()},
                 "max_tokens": req.get("max_tokens"), "stream": req.get("stream"),
                 "tools": [t.get("name") for t in (req.get("tools") or [])], "n_messages": len(req.get("messages") or []),
                 "last_user_text": text[:300], "last_is_tool_result": is_tool, "system_len": sys_len,
                 "anthropic_beta": self.headers.get("anthropic-beta"), "rule": idx}
        self._write_log(entry)
        if chosen and chosen.get("hang_s"):
            time.sleep(chosen["hang_s"])
        model = req.get("model", "claude-haiku-4-5-20251001")
        in_tok = (chosen or {}).get("input_tokens", 10)
        msg = {"id": f"msg_mock_{int(time.time()*1000)}", "type": "message", "role": "assistant", "model": model,
               "content": [], "stop_reason": None, "stop_sequence": None,
               "usage": {"input_tokens": in_tok, "output_tokens": 1}}
        if chosen and chosen.get("tool_use"):
            tu = chosen["tool_use"]
            blocks = [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": f"toolu_mock_{int(time.time()*1000)}", "name": tu["name"], "input": {}}}),
                      ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(tu.get("input", {}))}}),
                      ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                      ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"input_tokens": in_tok, "output_tokens": 20}})]
        else:
            if chosen and "text" in chosen:
                t = chosen["text"]
            elif is_tool:
                t = cfg.get("default_after_tool", "OK-AFTER-TOOL")
            else:
                t = cfg.get("default_text", "OK-MOCK")
            blocks = [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                      ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}}),
                      ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                      ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"input_tokens": in_tok, "output_tokens": 20}})]
        payload = sse([("message_start", {"type": "message_start", "message": msg})] + blocks + [("message_stop", {"type": "message_stop"})])
        try:
            self.send_response(200); self.send_header("content-type", "text/event-stream")
            self.send_header("request-id", "req_mock"); self.send_header("content-length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        except Exception as e:
            self._write_log({"t": round(time.time(), 3), "write_error": repr(e)})


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
