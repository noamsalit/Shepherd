#!/usr/bin/env python3
"""Tiny local stand-in for the Anthropic Messages API, used ONLY to provoke
StopFailure error classes that cannot be provoked safely against the real API
(2026-09-14). Bound to 127.0.0.1, started and stopped by run_probes.py.

Usage: mock_api.py <port> <mode> <requests.log>
modes: http401 http403 http429 http529 http500 http400 http404 http402 prompt_too_long max_tokens autocompact
Request headers are NOT logged (only method, path, and body length), so no
credential is ever written to disk.
"""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, MODE, LOG = int(sys.argv[1]), sys.argv[2], sys.argv[3]

ERRORS = {
    "http401": (401, "authentication_error", "invalid x-api-key"),
    "http403": (403, "permission_error", "Your API key does not have permission to use the specified resource."),
    "http429": (429, "rate_limit_error", "Number of request tokens has exceeded your per-minute rate limit"),
    "http529": (529, "overloaded_error", "Overloaded"),
    "http500": (500, "api_error", "Internal server error"),
    "http400": (400, "invalid_request_error", "messages: field required"),
    "http404": (404, "not_found_error", "model: claude-haiku-4-5-20251001"),
    "http402": (400, "invalid_request_error", "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."),
    "prompt_too_long": (400, "invalid_request_error", "prompt is too long: 250000 tokens > 200000 maximum"),
}


def sse(events):
    out = b""
    for name, data in events:
        out += f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _log(self, n):
        with open(LOG, "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path, "body_len": n, "mode": MODE}) + "\n")

    def do_GET(self):
        self._log(0)
        self.send_response(404)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"type":"error","error":{"type":"not_found_error","message":"not found"}}')

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n)
        self._log(n)
        if "count_tokens" in self.path:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"input_tokens":10}')
            return
        if MODE == "autocompact":
            # 1st call: a tool_use claiming a near-full context window; later calls: short end_turn text.
            try:
                req = json.loads(body)
            except Exception:
                req = {}
            model = req.get("model", "claude-haiku-4-5-20251001")
            n_msgs = len(req.get("messages", []))
            first = n_msgs <= 1
            with open(LOG, "a") as f:
                f.write(json.dumps({"autocompact_call": True, "n_messages": n_msgs, "first": first}) + "\n")
            msg = {"id": "msg_mock", "type": "message", "role": "assistant", "model": model, "content": [],
                   "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 195000 if first else 50, "output_tokens": 1}}
            if first:
                blocks = [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_mock1", "name": "Bash", "input": {}}}),
                          ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{\"command\": \"echo hi\", \"description\": \"echo\"}"}}),
                          ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                          ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"input_tokens": 195000, "output_tokens": 20}})]
            else:
                blocks = [("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                          ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "<summary>Probe summary: the user asked to echo hi.</summary> OK"}}),
                          ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                          ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 20}})]
            payload = sse([("message_start", {"type": "message_start", "message": msg})] + blocks + [("message_stop", {"type": "message_stop"})])
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if MODE == "max_tokens":
            try:
                model = json.loads(body).get("model", "claude-haiku-4-5-20251001")
            except Exception:
                model = "claude-haiku-4-5-20251001"
            msg = {"id": "msg_mock", "type": "message", "role": "assistant", "model": model, "content": [],
                   "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}
            payload = sse([
                ("message_start", {"type": "message_start", "message": msg}),
                ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "This answer is cut off mid"}}),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "max_tokens", "stop_sequence": None}, "usage": {"output_tokens": 32000}}),
                ("message_stop", {"type": "message_stop"}),
            ])
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        code, etype, emsg = ERRORS[MODE]
        b = json.dumps({"type": "error", "error": {"type": etype, "message": emsg}, "request_id": "req_mock"}).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("request-id", "req_mock")
        self.send_header("x-should-retry", "false")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
