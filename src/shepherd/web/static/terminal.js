// §12's page 3: the pane's real bytes, in a real terminal emulator.
//
// One socket, one emulator, and nothing in between that looks at the bytes.
// The first frame the server sends is the snapshot `capture-pane -e -p -S -2000`
// returned and every frame after it is `pipe-pane`'s output in order, so this
// file's whole job is to hand each frame to `term.write` unchanged. §9: "the
// real terminal bytes — not a re-render of a transcript".
//
// §13, and it is the reason there is not a single HTML sink below: terminal
// output is untrusted text. It reaches `term.write` or a `textContent` slot and
// nothing else — `tests/web/test_session_page.py::test_pty_bytes_never_reach_
// innerHTML` scans every line that touches a byte, and its negative fixture
// proves the scan bites. **There are two such paths, not one**: the socket's
// frames and the degrade's screen text, which is `session_output`'s
// `runner.snapshot(...).decode(...)`. The scan's token list reached only the
// first for a whole task, which is review finding 4.
//
// Principle 5 runs through every failure below. A pane that cannot be read, a
// stream that never delivered a frame, a stream that stopped, a vendored file
// that is not in the wheel: each is a sentence on the page. None of them is an
// empty box, because an empty box is indistinguishable from an empty pane.
//
// What this file does NOT claim: that any of it draws. There is no browser on
// the build host (G-M3-6), so xterm.js rendering the snapshot and the stream
// identically is unverified and acceptance clause 11 says so in words. Every
// byte up to `term.write` is asserted; the picture is not.

const TERMINAL_PATH = "/api/sessions/{session_id}/terminal";
const OUTPUT_PATH = "/api/sessions/{session_id}/output";

// The one runtime dependency (K8), vendored and never fetched at runtime (D51).
// `vendor/VERSION.txt` records the version, the source URL and the sha256.
const VENDOR_MODULE = "./vendor/xterm.js";

// T19-a step 3. A vendored file can still be missing from an installed wheel —
// that is exactly the defect M1 shipped once (T16-2) — and a blank pane would
// be the silent failure this project's principle 5 exists to prevent.
const DEGRADE_MESSAGE = "live terminal unavailable: xterm.js is not vendored";

// Principle 5, on the half of page 3 that is not built yet. `POST_ROUTES` has no
// path for `terminal_write` and the server never reads the upgraded socket, so
// there is no browser-to-pane path in this build at all (blocker T19-c). A
// terminal that quietly swallowed keystrokes would be a lie about what happened
// to them, so input is disabled in the emulator and the reason is on the page.
export const INPUT_UNAVAILABLE =
  "input is not wired yet: no route carries a keystroke to the pane (T19-c)";

// The degrade's own three outcomes (review finding 5). The old code had one —
// `""` — for all three, and an unhandled rejection for the first.
const SCREEN_READING = "reading the pane…";
const SCREEN_UNREADABLE = "the pane's text could not be read";
const SCREEN_ABSENT = "no screen: this session has no pane we can read from";

// The socket's two (review finding 6). `web/server.py` answers 404 for an
// orphaned owned row (T12's orphan), which a browser reports as an error and a
// close with no frame ever delivered — the likelier failure of the two, and the
// one that had no message at all.
const STREAM_LOST = "the terminal stream stopped — no more bytes will arrive";
const STREAM_NEVER_ARRIVED =
  "no terminal stream: there is no pane to attach to (the session may have ended)";

function path(template, sessionId) {
  return template.replace("{session_id}", encodeURIComponent(sessionId));
}

function socketUrl(sessionId) {
  const url = new URL(path(TERMINAL_PATH, sessionId), location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return url.href;
}

// One line of prose beneath the pane. `textContent`, like everything else here.
function notice(el, message) {
  const line = document.createElement("p");
  line.className = "terminal-degraded";
  line.textContent = message;
  el.appendChild(line);
  return line;
}

// `openTerminal(sessionId, el)` — the task's published surface. It resolves to
// a handle with `close()`, because the server tears the pane's `pipe-pane` down
// with the last client and a page that never closed its socket would hold one
// open for the life of the tab.
//
// It is the **first** function in this file on purpose: the degrade's structural
// test asks whether the first `try` guards the vendor import, and everything
// below is hoisted anyway.
export async function openTerminal(sessionId, el) {
  let term = null;
  let socket = null;
  try {
    const vendor = await import(VENDOR_MODULE);
    term = new vendor.Terminal({
      convertEol: false,
      // T19-c: no route carries a keystroke, so the emulator refuses them
      // rather than accepting bytes that go nowhere.
      disableStdin: true,
      scrollback: 2000,
    });
    el.replaceChildren();
    term.open(el);
    socket = new WebSocket(socketUrl(sessionId));
  } catch (missing) {
    // The import is the one failure that happens on a correctly-built host, but
    // a constructor or an upgrade that throws leaves the same empty box, and
    // the degrade is a real product state for all of them.
    return degrade(el, sessionId);
  }

  let frames = 0;
  let closing = false;
  socket.binaryType = "arraybuffer";
  socket.onmessage = (event) => {
    const payload = new Uint8Array(event.data);
    frames += 1;
    term.write(payload);
  };
  socket.onerror = () => {
    notice(el, STREAM_LOST);
  };
  socket.onclose = () => {
    // Never a frame is a different fact from stopped after some: the first is
    // T12's orphan (a 404 upgrade), the second is a pane that ended.
    if (!closing) {
      notice(el, frames === 0 ? STREAM_NEVER_ARRIVED : STREAM_LOST);
    }
  };

  return {
    refresh: () => {},
    close: () => {
      closing = true;
      socket.close();
    },
  };
}

// The honest degrade: the screen as text in a `<pre>`, filled with textContent,
// plus one line saying why there is no live terminal. A product state, not a
// stub — `get_session_output` is a registered read tool and answers with the
// pane's screen for an owned session (N12).
export function degrade(el, sessionId) {
  const reason = document.createElement("p");
  reason.className = "terminal-degraded";
  reason.textContent = DEGRADE_MESSAGE;
  const screen = document.createElement("pre");
  screen.className = "terminal-screen";
  screen.textContent = SCREEN_READING;
  el.replaceChildren(reason, screen);
  refreshScreen(screen, sessionId);
  return { refresh: () => refreshScreen(screen, sessionId), close: () => {} };
}

// Review finding 5: this is the degrade's own failure path, and it used to be
// the blank pane the degrade exists to prevent. It never rejects — the caller
// is a fire-and-forget in `degrade`, and an unhandled rejection is a pane that
// stays empty forever with nothing on the page to say why.
async function refreshScreen(screen, sessionId) {
  try {
    const response = await fetch(path(OUTPUT_PATH, sessionId), {
      headers: { Accept: "application/json" },
    });
    const body = await response.json();
    if (!body.ok) {
      screen.textContent = `${SCREEN_UNREADABLE}: ${body.error} (${body.correlation_id})`;
      return;
    }
    // `found: false` is a **value** (`tools_terminal.py::session_output`
    // answers `{"found": False, "text": None}`), so it gets a sentence. It used
    // to render `""`, which no human can tell from a pane that really is blank.
    screen.textContent = body.data.found ? body.data.text : SCREEN_ABSENT;
  } catch (unreachable) {
    screen.textContent = SCREEN_UNREADABLE;
  }
}
