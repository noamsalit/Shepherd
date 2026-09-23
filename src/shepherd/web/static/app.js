// The page's one bootstrap: the shell, the routing, and the one stream.
//
// Every fetch here is caused by something — the first paint, an event that
// arrived, or a click. Nothing is on a timer (§12: no polling anywhere in the
// UI), and the only reason this file knows any URL is that the route table on
// the server is the API's public shape.
//
// **The Needs-You rail is gone (D66).** It was the one element that lived in
// the shell and was drawn on every page; the owner reversed that, and if it
// returns it lives on the Flock page alone (U2). `project_needs_you` and
// `fleet_summary`'s `needs_you` list are untouched — only the renderer left.
//
// **Four pages were built in parallel worktrees and this file is the join.**
// Each of them ships a `mount…` that wires its own controls once, and most of
// them a `load…` that performs the one read its first paint needs. Importing a
// page module is not enough and the reachability walk cannot tell the
// difference: `flock.js` was *reached* through `session.js` for a whole phase
// while the page never drew, because this file called a `render` it had
// imported from a module that no longer shipped. **Loaded is not driven**, and
// `tests/web/test_session_wiring.py::test_the_bootstrap_drives_every_page_it_
// loads` is the assertion that can see it.

import { loadShepherd, mountShepherd, onShepherdEvent } from "./chat.js";
import { mountFlock, renderFlock, renderStatus, showLevel } from "./flock.js";
import { mountProjects } from "./projects.js";
import { renderSession } from "./session.js";
import { loadSettings, mountSettings, onSettingsEvent } from "./settings.js";
import { connect } from "./sse.js";

const FLEET = "/api/fleet";
// §16's order is computed server-side by `fleet_sort_key` and arrives already
// grouped workspace -> session. The page renders it; it never re-derives it.
const TREE = "/api/fleet/tree";
const SESSIONS = "/api/sessions";

// The six page roots and the six nav entries are **read out of the document**
// rather than listed here. `index.html` is the one definition site, and
// `tests/web/test_shell.py` checks it against `tools/render_check.py`'s own
// constants; a list in this file would be a third spelling of the same six
// names, which is how a nav entry ends up pointing at a root that is not there.
const PAGE_ROOT = '[id^="page-"]';
const NAV_ITEM = ".nav-item";
const PAGE_LINK = "[data-page]";
const DEFAULT_PAGE = "shepherd";

const shell = document.getElementById("shell");

// What the Flock is currently showing. `projectId` and `sessionId` are the
// selection — `flock.js` reads both to mark the open project and the open card
// with `aria-current`, and neither is derived from DOM order.
//
// `openSessionId` is not part of that selection: it is the **intent**, the
// session this page was last asked to open, and it is written synchronously at
// the tap while `sessionId` is written only once an answer for it has arrived.
// Two slots because they are two facts — see `openSession` (DUP-1).
const view = {
  fleet: null,
  workspaces: [],
  sessionCount: 0,
  projectId: null,
  sessionId: null,
  openSessionId: null,
};

//: The sentence for a `fetch` that **rejected** rather than answered —
//: `controld` stopped, the socket refused. `session.js` had this copy and this
//: pattern; four of the six modules did not, and this was one of them: the
//: `await response.json()` below ran only on a resolved response, so with the
//: daemon down the page silently stopped updating and left an unhandled
//: `Failed to fetch` on a console nobody has open (defect 2).
const UNREACHABLE =
  "The request did not reach the server — Shepherd may not be running.";

// ---------------------------------------------------------------------------
// Two slots, because they are two facts (defect 5).
//
// `renderStatus` is the **stream's** state and nothing else writes it. It is
// handed to `connect()` and to no other caller: `live`, `reconnecting`,
// `unreadable`, and `connecting` from the markup before the first frame.
//
// `#stream-message` is what a call had to say. It persists until another error
// replaces it or the dismiss button clears it — an error is not superseded by
// the fact that time passed, and the correlation id in it is the whole of what
// §13 leaves behind after a failed tool call.
// ---------------------------------------------------------------------------

const message = document.getElementById("stream-message");

function showError(text) {
  document.getElementById("stream-message-text").textContent = text;
  message.hidden = false;
}

document.getElementById("stream-message-dismiss").addEventListener("click", () => {
  document.getElementById("stream-message-text").textContent = "";
  message.hidden = true;
});

// Every body is `{ok, data, error, correlation_id}`. On a failure the page shows
// the generic literal and the id — §13 gives it nothing else, deliberately.
async function read(path) {
  // The **whole** call is inside the `try`, which is `session.js`'s shape and
  // the one this tree already had twice: a body that is not JSON is a reply
  // this page cannot read either, and splitting the two would mean two
  // sentences for one fact — "Shepherd did not answer".
  try {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    const body = await response.json();
    if (!body.ok) {
      showError(`${body.error} (${body.correlation_id})`);
      return null;
    }
    return body.data;
  } catch (unreachable) {
    showError(UNREACHABLE);
    return null;
  }
}

function drawFlock() {
  renderFlock(view, handlers, Date.now());
}

async function loadFleet() {
  const [fleet, tree] = await Promise.all([read(FLEET), read(TREE)]);
  if (fleet) {
    view.fleet = fleet;
  }
  if (tree) {
    view.workspaces = tree.workspaces;
    view.sessionCount = tree.session_count;
  }
  // The first payload decides the opening project: a three-pane page whose
  // middle column is empty until somebody clicks is a page that looks broken on
  // arrival. It is the payload's own first workspace, never a sorted one (§16).
  if (view.projectId === null && view.workspaces.length > 0) {
    view.projectId = view.workspaces[0].project_id;
  }
  drawFlock();
}

// D67's third pane. The id comes off the card's own `data-session-id` rather
// than a closure or a position, because `flock.js` builds the cards and this
// file owns the navigation.
//
// **`get_session` answers `{found, session, subagents}`, not a row**, and the
// bootstrap handed the whole envelope to `renderSession` — so every field it
// read was `undefined` and `openTerminal` opened a socket at
// `/api/sessions/undefined/terminal`. That is what the shipped page did before
// this pass too; nothing could see it, because no test had ever executed
// `renderSession`. It took a browser on the served page to find, which is the
// whole reason this pass drives one.
//
// `found: false` is a real answer and not an error: a session that has been
// swept while its card was on screen is principle 5's unknown, and the page
// says so on the stream line rather than throwing.
//
// **DUP-1, and it is BC-1 one file over.** The pane belongs to the last card
// *asked for*, not to the last read that *resolved*. Neither caller awaits this
// function — the delegated listener on `#flock-cards` and the Projects page's
// session anchor both start it and return — so two taps in quick succession
// leave two reads in flight, and before `openSessionId` the pane settled on
// whichever one came back last. A slow first tap and a quick second opened the
// **first** session: the wrong pane, the wrong `aria-current`, and a terminal
// socket attached to a pane nobody asked to see.
//
// Ordering the requests would not close it, for the same reason it did not in
// `projects.js`: the two reads are started by two different controls and the
// stale one is sometimes the one issued later. Only a recorded intent can say
// which answer the page still wants, so the intent is written here,
// synchronously, before the await — and a read that no longer matches it is
// dropped whole. It paints nothing, it selects nothing, and it says nothing on
// the stream line: "no such session" about a session the reader has already
// left is a sentence about a pane that is not on screen.
async function openSession(sessionId) {
  view.openSessionId = sessionId;
  const answer = await read(`${SESSIONS}/${encodeURIComponent(sessionId)}`);
  if (view.openSessionId !== sessionId) {
    return;
  }
  if (answer === null) {
    return;
  }
  if (!answer.found || answer.session === null) {
    showError(`no such session: ${sessionId}`);
    return;
  }
  view.sessionId = sessionId;
  drawFlock();
  renderSession(answer.session);
}

function openProject(projectId) {
  view.projectId = projectId;
  showLevel("sessions");
  drawFlock();
}

const handlers = { onOpenProject: openProject, onOpenSession: openSession };

function onCardClick(event) {
  const card = event.target.closest("[data-session-id]");
  if (card === null) {
    return;
  }
  openSession(card.dataset.sessionId);
}

// ---------------------------------------------------------------------------
// The shell: six roots, one open at a time.
//
// **U18, and it is the reason `app.css` carries `[hidden] { display: none
// !important }`.** Every root sets `display` from a class (`.scroll`, `.herd`,
// `.panes2`, `.detail`) and an author class rule beats the browser's own
// `[hidden]`, so without that line this function hides nothing and all six
// render on top of one another.
//
// There is no router and no second page load. **Shepherd is the default
// landing** (§12 page 1); the static markup ships the *Flock* visible instead,
// so a page whose module graph failed to load shows the M1 surface that needs
// no orchestrator rather than an empty conversation frame — the honest degrade,
// and the direction `hidden` should fail in.
//
// Every page is mounted once, before any of them is shown, so nothing may
// depend on being visible at mount time. `hidden` is the shell's and the
// shell's alone: no page module has a `hide…` of its own, which is why T7.1
// dropped `hideChat` rather than renaming it.
// ---------------------------------------------------------------------------

function navItemFor(name) {
  for (const item of document.querySelectorAll(NAV_ITEM)) {
    if (item.dataset.page === name) {
      return item;
    }
  }
  return null;
}

function showPage(name) {
  for (const root of document.querySelectorAll(PAGE_ROOT)) {
    root.hidden = root.id !== `page-${name}`;
  }
  for (const item of document.querySelectorAll(NAV_ITEM)) {
    if (item.dataset.page === name) {
      item.setAttribute("aria-current", "page");
    } else {
      item.removeAttribute("aria-current");
    }
  }

  // The heading is the nav entry's own label, read back rather than re-spelled:
  // a second table of six page titles is a table that drifts from the nav.
  const item = navItemFor(name);
  document.getElementById("topbar-title").textContent = item === null ? "" : item.textContent.trim();

  shell.removeAttribute("data-drawer");
}

// One listener per entry, bound by the entry's own id rather than by event
// delegation. §12's two original controls keep the ids they have always had —
// `#nav-chat` opens Shepherd and `#nav-fleet` opens the Flock — because they
// are the same two controls under a six-entry nav, and the rule that *the
// bootstrap which owns routing wires them by name* is still the rule.
//
// The cost is stated rather than hidden: the six names are spelled here as well
// as in `index.html`. The benefit is that a disagreement is **loud** —
// `getElementById` returns `null` and the page throws on load, which
// `tools/render_check.py` reports as a page error — where delegation would have
// silently bound nothing. `data-page` is still the attribute the checker
// drives, and `tests/web/test_shell.py` asserts the markup carries it for all
// six, so neither spelling can drift alone.
const NAV = {
  "nav-chat": "shepherd",
  "nav-fleet": "flock",
  "nav-queues": "queues",
  "nav-projects": "projects",
  "nav-kanban": "kanban",
  "nav-settings": "settings",
};

// The re-read every envelope causes, **coalesced** (defect 8).
//
// QA measured 1/10/100 envelopes producing 4/40/400 requests — perfectly
// linear, about 115 a second from one tab, against a store with a single
// writer thread. Every envelope started a fresh `loadFleet()` (two reads) and
// `projects.reload()` (two more) with no idea that three were already in
// flight, and the page rendered each answer in whatever order they landed.
//
// A refresh that arrives while one is running does not start a second one: it
// marks the running one stale, and the loop goes round once more when it
// finishes. So a burst of N costs two passes rather than N, the last pass is
// always after the last envelope, and there is still **no timer** — §12's rule
// is that nothing is on a schedule, not that nothing is merged.
const refresh = { running: false, stale: false };

async function refreshAll() {
  if (refresh.running) {
    refresh.stale = true;
    return;
  }
  refresh.running = true;
  try {
    do {
      refresh.stale = false;
      await loadFleet();
      if (projects !== null) {
        // The Projects page lists each project's sessions, so it follows the
        // same event rather than a timer of its own (§12: no polling).
        // `mountProjects()` hands back the one function that re-reads.
        await projects.reload();
      }
    } while (refresh.stale);
  } finally {
    refresh.running = false;
  }
}

// An event says something changed; re-reading the tree is a response to it, not
// a schedule.
function onEnvelope(envelope) {
  // §12's page 1 reads the same stream: `master.*` is the conversation and
  // `approval.*` is the card. One subscription, three views — Settings takes
  // the same envelope to say its numbers may be behind after a gap.
  //
  // **The envelope's `type` is not written to `#stream-status`.** It was, and
  // it was the third vocabulary in a slot that already had two: the connection
  // indicator was overwritten by the raw kind of whatever arrived last, which
  // is a fact no reader of that line was looking for (defect 5).
  onShepherdEvent(envelope);
  onSettingsEvent(envelope);
  refreshAll();
}

document.getElementById("flock-cards").addEventListener("click", onCardClick);

// T9.1's contract point 5. The Projects page renders each session as a real
// anchor — `focus`, middle-click, a visible target — and performs no navigation
// of its own, so a click on a `[data-page]` link is the shell's to honour and
// it is honoured exactly the way a nav entry is: show that page, then select
// what the link named. Delegated on the document because the links are built by
// a module, on a root this file clears and rebuilds.
document.addEventListener("click", (event) => {
  const link = event.target.closest(PAGE_LINK);
  if (link === null || link.classList.contains("nav-item")) {
    return;
  }
  event.preventDefault();
  showPage(link.dataset.page);
  if (link.dataset.sessionId) {
    openSession(link.dataset.sessionId);
  }
});

for (const entry of Object.keys(NAV)) {
  document.getElementById(entry).addEventListener("click", () => showPage(NAV[entry]));
}

// The pane's two width controls. Wired here rather than shipped inert: an
// element the markup ships and nothing wires is how `#session-rename` was a
// button with no behaviour for a whole task.
document.getElementById("drawer-open").addEventListener("click", () => {
  if (shell.getAttribute("data-drawer") === "open") {
    shell.removeAttribute("data-drawer");
  } else {
    shell.setAttribute("data-drawer", "open");
  }
});
document.getElementById("collapse").addEventListener("click", () => {
  shell.dataset.rail = "collapsed";
});
document.getElementById("mark").addEventListener("click", () => {
  if (shell.dataset.rail === "collapsed") {
    shell.dataset.rail = "open";
  }
});

// Mount every page before any of them is shown, then route. A page mounted on
// first reveal would make the arrival order part of its contract.
mountFlock(handlers);
mountShepherd();
mountSettings();
const projects = mountProjects();

showPage(DEFAULT_PAGE);

// Each page's first read, caused by the first paint and by nothing else. The
// Flock reads even though it is not the landing page: its counts are the
// shell's headline numbers and principle 5's unknown rate is on that strip.
loadFleet();
loadShepherd();
loadSettings();
connect(onEnvelope, renderStatus);
