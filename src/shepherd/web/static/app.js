// The page's one bootstrap: load the tree, then let the stream drive it.
//
// Every fetch here is caused by something — the first paint, an event that
// arrived, or a click. Nothing is on a timer (§12: no polling anywhere in the
// UI), and the only reason this file knows any URL is that the route table on
// the server is the API's public shape.

import { hideChat, loadChat, mountChat, onChatEvent } from "./chat.js";
import { render, renderStatus } from "./fleet.js";
import { renderRail } from "./rail.js";
import { renderSession } from "./session.js";
import { connect } from "./sse.js";

const FLEET = "/api/fleet";
// §16's order is computed server-side by `fleet_sort_key` and arrives already
// grouped workspace -> session. The page renders it; it never re-derives it.
const TREE = "/api/fleet/tree";
const SESSIONS = "/api/sessions";

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
  renderRail(view.fleet, document.getElementById("rail"));
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

// §12's page 3, and the edge the plan never assigned to a task: without it
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

// §12's two pages in one document. There is no router and no second page load:
// the nav reveals one view and hides the other, and the rail above both stays
// where it is because it is the shell rather than a page.
//
// **Chat is the default landing** (§12 page 1). The static markup ships the
// fleet visible and the chat hidden, so a page whose module graph failed to
// load shows the M1 surface rather than an empty conversation — the honest
// degrade, and the direction `hidden` should fail in.
function showChat() {
  mountChat();
  document.getElementById("fleet-view").hidden = true;
}

function showFleet() {
  hideChat();
  document.getElementById("fleet-view").hidden = false;
}

// An event says something changed; re-reading the tree is a response to it, not
// a schedule. The expanded rollups are dropped so a re-read cannot show a stale
// subagent line beside a fresh session row.
function onEnvelope(envelope) {
  renderStatus(envelope.type);
  // Page 1 reads the same stream: `master.*` is the conversation and
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
document.getElementById("nav-chat").addEventListener("click", showChat);
document.getElementById("nav-fleet").addEventListener("click", showFleet);
showChat();
// Both pages read on the first paint: the fleet because the rail is on every
// page, the chat because it is the one being shown.
loadFleet();
loadChat();
connect(onEnvelope, renderStatus);
