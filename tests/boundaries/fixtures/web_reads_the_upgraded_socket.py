"""A fixture, never shipped and never imported: `_terminal` with a read loop.

This is `web/server.py` as it would look the day the browser→pane keystroke path
is built — the thing `test_ws_read_path.py` must go red on. It is written in
**four different spellings** of the same import, because a rule that sees only
the spelling its author used is a rule its defeater has never met:

* `from shepherd.web import ws` … `ws.parse_frame(...)`
* `from shepherd.web.ws import WebSocketClosed` — a bare name, no dotted chain
* `import shepherd.web.ws` … the full chain
* `from shepherd.web.ws import Frame as WireFrame` — aliased away entirely
"""

from __future__ import annotations

import shepherd.web.ws
from shepherd.web import ws
from shepherd.web.ws import Frame as WireFrame
from shepherd.web.ws import WebSocketClosed


def read_client_frames(sock: object) -> list[WireFrame]:
    """The loop `parse_frame`'s "read more and ask again" contract describes."""
    buffer = b""
    frames: list[WireFrame] = []
    while True:
        try:
            frame, consumed = ws.parse_frame(buffer)
        except WebSocketClosed as closed:
            raise SystemExit(closed.code) from closed
        if frame is None:
            chunk = sock.recv(65536)  # type: ignore[attr-defined]
            if not chunk:
                return frames
            buffer += chunk
            continue
        buffer = buffer[consumed:]
        if shepherd.web.ws.close_code(frame) is not None:
            return frames
        frames.append(frame)
