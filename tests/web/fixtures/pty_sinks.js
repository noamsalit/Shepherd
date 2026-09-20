// Negative control for `tests/web/test_session_page.py`. Every scan in that
// module must trip on this file; a scan that stays quiet here is a scan that
// would stay quiet on the real thing.
//
// It is never served: `web/server.py` serves `web/static/` only, and the
// escaping suite's own module list would reject a stray file there.

export function openTerminal(sessionId, el) {
  const socket = new WebSocket(`ws://localhost/api/sessions/${sessionId}/terminal`);

  // 1. pty bytes straight into an HTML sink — §13 forbids this by name.
  socket.onmessage = (event) => {
    el.innerHTML = event.data;
  };

  // 2. a second sink, in the shape a "just a badge" edit reaches for.
  el.insertAdjacentHTML("beforeend", event.data);

  // 3. no try/catch around the vendor import: a missing file yields a blank
  //    pane and no message at all.
  const mod = await import("./vendor/xterm.js");
  mod.Terminal;

  // 4. the page re-deriving the server's order.
  rows.sort((a, b) => a.started_at.localeCompare(b.started_at));
}

// 5. review finding 4: the *degrade's* pane content — `body.data.text` is
//    `session_output`'s `runner.snapshot(...).decode(...)`, i.e. pty bytes —
//    into `setHTMLUnsafe`, a real WHATWG HTML-parsing sink that no deny-list
//    written before it existed would have named. The shipped `terminal.js`
//    line it replaces is `screen.textContent = ...`, and for one whole task
//    the scan's token list did not reach that line at all.
async function refreshScreenUnsafely(screen, sessionId) {
  const response = await fetch(`/api/sessions/${sessionId}/output`);
  const body = await response.json();
  screen.setHTMLUnsafe(body.data.text);
}
