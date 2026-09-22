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
// G-M3-6 — *"xterm.js draws the snapshot and the stream identically is
// unverified"* — was recorded because there was no browser on the build host.
// QA run 4 was the first browser, and it says the picture was wrong: the
// emulator was constructed with **no `cols` and no `rows`**, so it was xterm's
// default 80x24 at every viewport from 390 to 2560, inside a container that is
// `overflow: hidden` on both axes. At 1440 the rendered screen's right edge was
// at 1517 — outside the window — and at 390 there were 366px of pane that no
// scroll and no drag could reach. The bytes were re-wrapped at 80 columns, so a
// 160-column pane's box drawing broke.
//
// **The fit below is the fix, and its shape is a decision** (D6, lane B of QA
// remediation 4; the reasoning is in
// `docs/plans/projects-ui-blockers/qa-remfix-4-lane-b.md`). The emulator is
// sized from the container it is drawn in, at open and on every resize, using
// only public API — `term.resize`, `term.cols`, `term.rows` and the rendered
// box — so nothing new is vendored and `vendor/VERSION.txt`'s manifest is
// untouched.
//
// **What was rejected, and why it matters that it is said here.** The other
// branch was to wire `terminal_resize` — a registered `ToolDef` with no route —
// and make the *pane* match the window. That shows the real screen at any width
// and it is what a terminal client normally does, but it costs two things this
// build must not spend: `runner/local.py::resize` forces tmux's
// `window-size=manual`, so a later human attach is clipped (E-M3-22), and a
// viewport is then a **mutation of the work** — a glance from a phone would
// shrink a running agent's pane to 39 columns. This page declares itself as
// having no path from the browser to the pane (T19-c); a resize that travelled
// that way would be the first, arriving by accident of window size.
//
// So one residual survives the fit and is **said on the page** rather than left
// silent, which is the whole of what made the absent fit a defect: a pane wider
// than the window is re-wrapped here, at the window's width. `FIT_LIMITATION`
// below is that sentence, and `session.js` puts it beside `INPUT_UNAVAILABLE`.
//
// What this file still does NOT claim: that the *bytes* draw identically to a
// real terminal. Every byte up to `term.write` is asserted, and now the box
// they are drawn in is measured too; the glyphs are not.

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

// D6's residual, declared for the same reason T19-c is. The emulator is fitted
// to this window; the pane keeps its own geometry, because nothing here may
// resize it (see the head of this file). When the window is narrower than the
// pane the lines are re-wrapped at the window's width — visible and inside the
// box, rather than clipped away — and a reader is owed that fact, because
// re-wrapped box drawing looks like a broken agent rather than a narrow window.
export const FIT_LIMITATION =
  "the terminal is fitted to this window, not to the pane: a pane wider than " +
  "this window has its lines re-wrapped here";

// The floor. A container too small for these is a layout defect somewhere else,
// and an emulator of 0 columns would divide by zero on the next fit.
const MIN_COLS = 20;
const MIN_ROWS = 4;

// **The rows are not measured from the container, and that is not an oversight.**
//
// `#session-terminal` is `flex: none; min-height: 12rem` with no height of its
// own (`app.css`, a file this lane does not own), so its height is whatever the
// emulator draws inside it. Fitting rows to it is therefore circular, and the
// first build of this fix proved it the expensive way: rows from `clientHeight`
// grew the box, the box grew the rows, and the `ResizeObserver` rode the loop
// to a container **307 418 px** tall before the measurement was taken. The
// tests still passed, because every assertion of the form "the content fits
// inside the box" is vacuously true of a box that grew to fit it.
//
// So the vertical budget comes from the screen left below the pane's own top
// edge — and that edge is sampled **once, before the emulator draws anything**,
// which is the second half of the same lesson. Re-reading it on every fit was
// still circular, just more slowly: a taller emulator moves its own top inside
// the scrolling column, so the rows oscillated and the page was measured
// mid-swing (a rendered 23 against a declared 26, and 62 against 71). One
// sample of an empty container is a number no later fit can move.
const MAX_ROWS = 80;

// The stand-in for an emulator that does not exist yet, so the first fit can go
// through the same function every later one does. `cell()` reads `cols`/`rows`
// to decide whether there is a drawn box to measure; zero says there is not.
const EMPTY = { cols: 0, rows: 0 };

// The font the emulator is told to use, and the font the measurement uses. They
// are one constant because a fit computed against a different font than the one
// that draws is not a fit — it is a coincidence that holds on the machine it
// was written on.
const FONT_FAMILY =
  '"DejaVu Sans Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const FONT_SIZE = 13;
const LINE_HEIGHT = 1.15;

// How many characters the ruler is. One glyph's box is sub-pixel and rounds;
// a hundred of them divided by a hundred is the cell width to well under a
// pixel, which is the difference between 69 columns and 70 at 1440.
const RULER = 100;

// `{cols, rows}` for a container, measured rather than assumed.
//
// Exported because it is the whole of the decision this module makes about
// geometry, and a test that could only read it back off the emulator would be
// asserting that xterm agrees with itself.
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
  let observer = null;
  let top = 0;
  try {
    const vendor = await import(VENDOR_MODULE);
    el.replaceChildren();
    // Measured **before** the constructor, so the emulator is never 80x24 even
    // for one frame. `el` is empty at this point, which is what makes the
    // measurement the container's and not the content's.
    // Sampled while `el` is empty: this is the edge every later fit measures
    // down from, and the one number in the layout the emulator cannot move.
    top = el.getBoundingClientRect().top;
    const initial = fitGeometry(el, top, EMPTY);
    term = new vendor.Terminal({
      convertEol: false,
      // T19-c: no route carries a keystroke, so the emulator refuses them
      // rather than accepting bytes that go nowhere.
      disableStdin: true,
      scrollback: 2000,
      // D6. The four constructor arguments QA swept for and found absent; the
      // font is named here because `fitGeometry` measures that exact font.
      cols: initial.cols,
      rows: initial.rows,
      fontFamily: FONT_FAMILY,
      fontSize: FONT_SIZE,
      lineHeight: LINE_HEIGHT,
    });
    term.open(el);
    // The correction pass, once the emulator has a rendered box to measure.
    applyFit(term, el, top);
    // A window that changes size re-fits. `ResizeObserver` and not a resize
    // listener: the container is a flex child of a drill-down whose width
    // changes when a column opens, which is not a window resize at all.
    observer = new ResizeObserver(() => applyFit(term, el, top));
    observer.observe(el);
    socket = new WebSocket(socketUrl(sessionId));
  } catch (missing) {
    if (observer !== null) {
      observer.disconnect();
    }
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
    refresh: () => applyFit(term, el, top),
    close: () => {
      closing = true;
      // The observer holds a reference to a `term` whose socket is gone. It is
      // disconnected for the same reason the socket is closed: a session
      // re-opened in the same tab would otherwise leave one live observer per
      // open, all of them re-fitting an emulator nobody can see.
      observer.disconnect();
      socket.close();
    },
  };
}

// One cell, in CSS pixels, measured against the container.
//
// A `<span>` set to the emulator's own font — the same constants the
// constructor is handed, because a fit computed against a different font than
// the one that draws is a coincidence that holds on the machine it was written
// on. Used only before there is anything drawn to measure instead.
function rulerCell(el) {
  const ruler = document.createElement("span");
  ruler.setAttribute("aria-hidden", "true");
  ruler.style.position = "absolute";
  ruler.style.visibility = "hidden";
  ruler.style.whiteSpace = "pre";
  ruler.style.fontFamily = FONT_FAMILY;
  ruler.style.fontSize = `${FONT_SIZE}px`;
  ruler.style.lineHeight = String(LINE_HEIGHT);
  ruler.textContent = "W".repeat(RULER);
  el.appendChild(ruler);
  const box = ruler.getBoundingClientRect();
  ruler.remove();
  return { width: box.width / RULER, height: box.height };
}

// The cell xterm is **actually drawing**, when there is one, and the ruler's
// estimate when there is not.
//
// The two disagree, and by enough to matter: the ruler's line box came out at
// 14.95px against xterm's own 17px, which is 26 rows asked for where 23 fit.
// The first build of this fix used the ruler for the target and the drawn box
// only as a one-shot correction, and on a 390px phone the two never converged —
// the estimate asked for 26, the correction cut it to 23, and the next
// `ResizeObserver` callback asked for 26 again. Preferring the drawn metrics
// wherever they exist makes the fit **idempotent**: the second call is a no-op,
// which is the property a resize observer needs from the thing it calls.
function cell(el, term) {
  const screen = el.querySelector(".xterm-screen");
  if (screen !== null && term.cols > 0 && term.rows > 0) {
    const drawn = screen.getBoundingClientRect();
    if (drawn.width > 0 && drawn.height > 0) {
      return { width: drawn.width / term.cols, height: drawn.height / term.rows };
    }
  }
  return rulerCell(el);
}

// The width **is** the container's: it is set by the flex column the terminal
// sits in and the emulator cannot widen it, so there is no circularity here.
function columnsFor(el, cellWidth) {
  return Math.max(MIN_COLS, Math.floor(el.clientWidth / cellWidth));
}

// The height is the screen below `top`, the pane's edge as it was before
// anything was drawn in it — see `MAX_ROWS` above for why it is neither the
// container's own height nor a fresh reading of that edge. `MAX_ROWS` is the
// belt: a page scrolled so that the terminal's top is off the top of the
// window would otherwise ask for a viewport's worth of rows plus the scroll.
function rowsFor(top, cellHeight) {
  const available = window.innerHeight - top;
  const rows = Math.floor(available / cellHeight);
  return Math.min(MAX_ROWS, Math.max(MIN_ROWS, rows));
}

// `{cols, rows}` for a container and whatever is drawn in it, measured rather
// than assumed. Exported because it is the whole of the decision this module
// makes about geometry, and a test that could only read the answer back off the
// emulator would be asserting that xterm agrees with itself.
export function fitGeometry(el, top, term) {
  const size = cell(el, term);
  // A container with no layout yet (`display:none`, a detached node) measures
  // zero, and `Math.floor(x / 0)` is `Infinity` — an emulator asked for
  // Infinity columns is a hang, not a fallback. The floor is the honest answer.
  if (!(size.width > 0) || !(size.height > 0)) {
    return { cols: MIN_COLS, rows: MIN_ROWS };
  }
  return { cols: columnsFor(el, size.width), rows: rowsFor(top, size.height) };
}

// Size the emulator to its container, and settle.
//
// Two passes at most. The first may be measured against the ruler (nothing is
// drawn yet); the second is measured against what the first pass drew, which is
// xterm's own cell and therefore final. The loop **breaks on agreement**, so a
// steady-state call — which is every call after the first, including every
// `ResizeObserver` callback at an unchanged size — resizes nothing.
//
// The result is recorded on the element as `data-terminal-cols`/`-rows`. That
// is the page saying what geometry it chose, which is a fact no reader could
// otherwise get at without xterm's private render service.
function applyFit(term, el, top) {
  for (let pass = 0; pass < 2; pass += 1) {
    const target = fitGeometry(el, top, term);
    if (target.cols === term.cols && target.rows === term.rows) {
      break;
    }
    term.resize(target.cols, target.rows);
  }
  el.dataset.terminalCols = String(term.cols);
  el.dataset.terminalRows = String(term.rows);
}

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
