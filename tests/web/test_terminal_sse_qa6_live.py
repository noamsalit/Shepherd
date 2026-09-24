"""qa6 P15 — BC-10 (the snapshot opens readable) and BC-35 (a refused stream says so).

**BC-10.** QA run 6's U10 opened an owned session and read the emulator's DOM
rows: `rows_text` was all blanks, with `ws_frames 1` — the snapshot had arrived,
and it contained the marker. Screenshot `2-live-line.png` shows the next two live
lines at the bottom, the first one **mid-row**. The hypothesis the plan asks RED
to confirm before any fix: frame 1 is `capture-pane -e -p` output, which ends its
lines with a bare LF and pads a mostly empty pane with a run of empty lines. With
`convertEol: false` a bare LF moves down without returning to column 0, and the
run of LFs scrolls every line of text off an emulator shorter than the pane — so
the visible rows are the blank tail, and the cursor is left at the column the
last text line ended on.

The fixture is the capture U10's fake pane prints — `01-prompt-ready-normal-screen.ansi`
from `docs/probes/2026-09-20-macos-pane/` (read, never edited): a 45-row pane
with text on its first 14 rows and 31 empty ones below. The socket is a fake in
the page, so the frames are exactly the capture's bytes and then one live chunk;
the emulator is the shipped `terminal.js` driving the real vendored xterm.

**BC-35.** U40 answered `/api/events` with 403 for good and `#stream-status`
read `reconnecting` forever. A 403 is not retried by `EventSource`: the source
goes to `CLOSED`, and nothing will ever arrive. The status vocabulary already
has the word for that (`app.js`, `live` / `reconnecting` / `unreadable`).

Skipped, not failed, where chromium is absent: an absent browser is an
environment fact, not a code defect.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from web.conftest import Client, MasterDoubles

from shepherd.store.db import Store

playwright_api = pytest.importorskip("playwright.sync_api")

PANE = Path(__file__).resolve().parents[2] / "docs" / "probes" / "2026-09-20-macos-pane"
CAPTURE = PANE / "01-prompt-ready-normal-screen.ansi"
#: `#{pane_width}|#{pane_height}` are fields 4 and 5 of the capture's `-fmt.txt`.
PANE_ROWS = int((PANE / "01-prompt-ready-normal-screen-fmt.txt").read_text().split("|")[5])

#: The capture's last line of text — the one a person would look for first.
MARKER = "manual mode on"
LIVE = "QA6-LIVE-LINE"

HARNESS_PATH = "/__qa6_p15_terminal_harness"
#: A box pinned to the top of a short window, so the emulator is fitted to far
#: fewer rows than the pane's 45 — the shape U10 had.
HARNESS = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/vendor/xterm.css">
<style>body{margin:0} #host{position:absolute;top:0;left:0;width:900px}</style>
</head><body><div id="host"></div></body></html>"""

#: The socket, replaced before any module runs. Frames are handed in by the test.
FAKE_SOCKET = """
(() => {
  window.__sockets = [];
  class FakeSocket {
    constructor(url) { this.url = url; this.binaryType = "blob"; window.__sockets.push(this); }
    deliver(bytes) {
      const data = new Uint8Array(bytes).buffer;
      this.onmessage({ data });
    }
    close() {}
  }
  window.WebSocket = FakeSocket;
})();
"""

MOUNT = """
async () => {
  const terminal = await import("/static/terminal.js");
  await terminal.openTerminal("eng-live", document.getElementById("host"));
  return window.__sockets.length;
}
"""

#: What xterm's DOM renderer put in the visible rows, one string per row.
ROWS = """
() => [...document.querySelectorAll('#host .xterm-rows > div')]
  .map((row) => (row.textContent || '').replace(/\\u00a0/g, ' '))
"""


def _chromium(play: object) -> object:
    try:
        return play.chromium.launch()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - an absent browser is not a defect
        play.stop()  # type: ignore[attr-defined]
        pytest.skip(f"chromium is not available: {exc}")


@pytest.fixture()
def browser() -> Iterator[object]:
    from playwright.sync_api import sync_playwright

    play = sync_playwright().start()
    launched = _chromium(play)
    try:
        yield launched
    finally:
        launched.close()  # type: ignore[attr-defined]
        play.stop()


def _rows_after(page: object, needle: str) -> list[str]:
    """The visible rows once `needle` has had a chance to render (xterm paints
    on an animation frame); returned either way, so a miss is asserted on."""
    try:
        page.wait_for_function(  # type: ignore[attr-defined]
            f"() => ({ROWS})().some((row) => row.includes({needle!r}))", timeout=2000
        )
    except Exception:  # noqa: BLE001 - the assertion below reports what was drawn
        pass
    rows: list[str] = page.evaluate(ROWS)  # type: ignore[attr-defined]
    return rows


def test_the_snapshot_text_is_visible_on_open(
    client: Client, store: Store, master_doubles: MasterDoubles, browser: object
) -> None:
    """U10's `ui.xterm_rows_show_the_marker`, against the capture U10's pane prints."""
    page = browser.new_page(viewport={"width": 1000, "height": 320})  # type: ignore[attr-defined]
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.route(
        f"{client.origin}{HARNESS_PATH}",
        lambda route: route.fulfill(status=200, content_type="text/html", body=HARNESS),
    )
    page.add_init_script(FAKE_SOCKET)
    page.goto(f"{client.origin}{HARNESS_PATH}")
    assert page.evaluate(MOUNT) == 1
    declared_rows = int(page.evaluate("() => document.getElementById('host').dataset.terminalRows"))
    # The precondition that makes this U10's shape: the pane is taller than the
    # emulator, so a snapshot that ends in a run of empty lines scrolls its text away.
    assert declared_rows < PANE_ROWS, (declared_rows, PANE_ROWS)

    page.evaluate("(bytes) => window.__sockets[0].deliver(bytes)", list(CAPTURE.read_bytes()))
    rows = _rows_after(page, MARKER)
    assert any(MARKER in row for row in rows), rows
    # …and it is the capture's text, not a stray fragment: its header is on screen too.
    assert any("Claude Code v2.1.278" in row for row in rows), rows

    # The next live chunk is `pipe-pane`'s bytes, written unchanged; it must
    # start at column 0 rather than where the snapshot's last line ended.
    page.evaluate(
        "(bytes) => window.__sockets[0].deliver(bytes)", list(f"{LIVE}\r\n".encode())
    )
    rows = _rows_after(page, LIVE)
    live_rows = [row for row in rows if LIVE in row]
    assert live_rows, rows
    assert live_rows[0].startswith(LIVE), live_rows
    # The snapshot did not scroll away under the live line.
    assert any(MARKER in row for row in rows), rows
    assert errors == [], errors


def test_a_forbidden_stream_reads_unreadable(
    client: Client, store: Store, master_doubles: MasterDoubles, browser: object
) -> None:
    """U40's `ui.status_neither_live_nor_reconnecting`: a 403 is final, and says so."""
    page = browser.new_page(viewport={"width": 1440, "height": 900})  # type: ignore[attr-defined]
    page.route(
        re.compile(r".*/api/events(\?.*)?$"),
        lambda route: route.fulfill(status=403, content_type="text/plain", body="forbidden"),
    )
    page.goto(f"{client.origin}/")
    try:
        page.wait_for_function(
            "() => document.getElementById('stream-status').textContent === 'unreadable'",
            timeout=5000,
        )
    except Exception:  # noqa: BLE001 - the assertion below reports what was read
        pass
    status = page.evaluate("() => document.getElementById('stream-status').textContent")
    assert status == "unreadable", status
