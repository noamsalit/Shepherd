#!/usr/bin/env python3
"""Shepherd gap-fill probe (2026-09-14): browser terminal transport vs "stdlib HTTP + SSE" (spec 1150 vs 406).
  1. which WebSocket-capable libraries import on the system python3
  2. a stdlib-only RFC 6455 handshake + one masked client frame + one server frame, over loopback,
     using http.server (server) and socket (client). Raw bytes on the wire are recorded.
Re-run:  python3 docs/probes/2026-09-14-schemas/gap-fill/probe_websocket.py
"""
import base64, hashlib, importlib, json, os, socket, struct, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gaplib import Run

R = Run("websocket")
imports = {}
for mod in ("websockets", "wsproto", "aiohttp", "tornado", "simple_websocket", "http.server", "asyncio", "ssl"):
    try:
        m = importlib.import_module(mod)
        imports[mod] = "ok " + str(getattr(m, "__version__", ""))
    except Exception as e:
        imports[mod] = f"{type(e).__name__}: {e}"
imports["_python"] = sys.version
imports["_pip"] = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True).stderr.strip() or "ok"
R.save("imports.json", json.dumps(imports, indent=1))

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
wire = []


def recv_exact(sock, n):
    b = b""
    while len(b) < n:
        c = sock.recv(n - len(b))
        if not c:
            break
        b += c
    return b


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self.send_error(400); return
        key = self.headers["Sec-WebSocket-Key"]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept); self.end_headers(); self.wfile.flush()
        s = self.connection
        h = recv_exact(s, 2); ln = h[1] & 0x7F; mask = recv_exact(s, 4); payload = bytearray(recv_exact(s, ln))
        for i in range(ln):
            payload[i] ^= mask[i % 4]
        wire.append({"server_received_frame_header_hex": h.hex(), "mask_hex": mask.hex(), "unmasked_payload": payload.decode()})
        out = b"echo:" + bytes(payload)
        s.sendall(bytes([0x81, len(out)]) + out)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
c = socket.create_connection(("127.0.0.1", port))
key = base64.b64encode(os.urandom(16)).decode()
req = (f"GET /sessions/shepherd_t1/pty HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
c.sendall(req)
resp = b""
while b"\r\n\r\n" not in resp:
    resp += c.recv(1)
expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
msg = b"\x1b[A"  # an Up-arrow keystroke, as xterm.js onData would emit it
mask = os.urandom(4)
frame = bytes([0x81, 0x80 | len(msg)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(msg))
c.sendall(frame)
h = recv_exact(c, 2); echoed = recv_exact(c, h[1] & 0x7F)
result = {"request": req.decode(), "response_head": resp.decode(), "expected_accept": expected,
          "accept_matches": f"Sec-WebSocket-Accept: {expected}" in resp.decode(),
          "client_frame_hex": frame.hex(), "server_frame_header_hex": h.hex(), "server_payload": echoed.decode("latin1"),
          "server_side": wire}
R.save("handshake.json", json.dumps(result, indent=1))
print(json.dumps(imports, indent=1)); print(json.dumps(result, indent=1))
srv.shutdown()
