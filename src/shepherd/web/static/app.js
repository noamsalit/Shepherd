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

import { hideChat, loadChat, mountChat, onChatEvent } from "./chat.js";
import { render, renderStatus } from "./fleet.js";
import { renderSession } from "./session.js";
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
const DEFAULT_PAGE = "shepherd";

const shell = document.getElementById("shell");

const view = {
  fleet: null,
  workspaces: [],
  sessionCount: 0,
  subagents: new Map(),
  expanded: new Set(),
};

// Every body is `{ok, data, error, correlation_id}`. On a failure the page shows
// the generic literal and the id — §13 gives it nothing else, deliberately.
async function read(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await response.json();
  if (!body.ok) {
    renderStatus(`${body.error} (${body.correlation_id})`);
    return null;
  }
  return body.data;
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
  render(view, onExpand);
}

async function loadSubagents(sessionId) {
  const rollup = await read(`${SESSIONS}/${encodeURIComponent(sessionId)}/subagents`);
  if (rollup) {
    view.subagents.set(sessionId, rollup);
  }
  render(view, onExpand);
}

function onExpand(sessionId) {
  if (view.expanded.has(sessionId)) {
    view.expanded.delete(sessionId);
    render(view, onExpand);
    return;
  }
  view.expanded.add(sessionId);
  render(view, onExpand);
  loadSubagents(sessionId);
}

// D67's third pane, and the edge the plan never assigned to a task: without it
// `session.js`, `terminal.js` and the vendored emulator are code the page never
// loads. The id comes off the row's own `data-session-id` rather than a closure
// or a position, because `fleet.js` builds the rows and this file owns the
// navigation.
async function openSession(sessionId) {
  const row = await read(`${SESSIONS}/${encodeURIComponent(sessionId)}`);
  if (row) {
    renderSession(row);
  }
}

function onFleetClick(event) {
  // The row's own controls — the subagent toggle, D21's action buttons and
  // links — have handlers of their own, and a click on one of them is not a
  // request to open the session.
  if (event.target.closest("button, a, summary") !== null) {
    return;
  }
  const row = event.target.closest("li.session[data-session-id]");
  if (row === null) {
    return;
  }
  openSession(row.dataset.sessionId);
}

// ---------------------------------------------------------------------------
// The shell: six roots, one open at a time.
//
// **U18, and it is the reason `app.css` carries `[hidden] { display: none
// !important }`.** Every root sets `display` from a class (`.scroll`, `.herd`,
// `.panes2`) and an author class rule beats the browser's own `[hidden]`, so
// without that line this function hides nothing and all six render on top of
// one another. The shipped page had that bug before the redesign:
// `.chat-view` was `display: grid` and stayed hidden only because the script
// also set a class.
//
// There is no router and no second page load. **Chat is the default landing**
// (§12 page 1); the static markup ships the *Flock* visible instead, so a page
// whose module graph failed to load shows the M1 surface that needs no
// orchestrator rather than an empty conversation frame — the honest degrade,
// and the direction `hidden` should fail in.
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

  // §12's page 1 and the Flock keep the pairing they have always had, and the
  // conversation is mounted only while it is on screen.
  if (name === DEFAULT_PAGE) {
    mountChat();
    document.getElementById("fleet-view").hidden = true;
  } else {
    hideChat();
    document.getElementById("fleet-view").hidden = false;
  }

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

// An event says something changed; re-reading the tree is a response to it, not
// a schedule. The expanded rollups are dropped so a re-read cannot show a stale
// subagent line beside a fresh session row.
function onEnvelope(envelope) {
  renderStatus(envelope.type);
  // §12's page 1 reads the same stream: `master.*` is the conversation and
  // `approval.*` is the card. One subscription, two views.
  onChatEvent(envelope);
  view.subagents.clear();
  loadFleet().then(() => {
    for (const sessionId of view.expanded) {
      loadSubagents(sessionId);
    }
  });
}

document.getElementById("fleet").addEventListener("click", onFleetClick);
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

showPage(DEFAULT_PAGE);
// Both pages read on the first paint: the Flock because its counts are the
// shell's headline numbers, the chat because it is the one being shown.
loadFleet();
loadChat();
connect(onEnvelope, renderStatus);
