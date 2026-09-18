// The fleet tree: workspace -> session -> subagent (§12 Page 2).
//
// Two rules shape every function here.
//
// **§13.** Nothing in this file touches `innerHTML`, `outerHTML` or
// `insertAdjacentHTML`. Every value that came from a session — a title, a
// brief, a needs-you reason, a subagent description — is untrusted text, and it
// reaches the page through `textContent` only. `tests/web/test_frontend_escaping.py`
// fails the build on a sink appearing here, so this is a gate, not a habit.
//
// **§16.** Ordering is derived from state, and it is derived *server-side* by
// `fleet_sort_key`. This file renders the order it was handed and never sorts,
// never compares names and never looks at a timestamp to decide position.

// §4's eight buckets. Every one carries a **glyph as well as a colour** (the
// colour is `--bucket-colour` in `app.css`): amber and red are the two chips a
// colourblind reader most needs to tell apart, and in greyscale they are the
// same grey. `tests/web/test_palette.py` reads both tables back out of this
// file and compares them to `core.stops.PALETTE`, so there is one source of
// truth and the copy here is checked rather than trusted.
//
// The *order* is not here. It arrives with the payload — `fleet_bucket_sort_key`
// server-side for the rows, and `by_bucket`'s key order for the counts — because
// the demotion `bucket_of` applies compares `last_event_at` against the liveness
// window, which is a thing only L2 can do.
const BUCKET_LABEL = {
  needs_you: "needs you",
  error: "error",
  unfinished: "unfinished",
  running: "running",
  paused: "paused",
  blocked: "blocked",
  finished: "finished",
  unclassified: "not classified",
};

const BUCKET_MARK = {
  needs_you: "⏸",
  error: "✕",
  unfinished: "◑",
  running: "●",
  paused: "⏱",
  blocked: "⏳",
  finished: "✓",
  unclassified: "?",
};

// Principle 5: a datum we do not have is shown as unknown, never invented.
const UNKNOWN = "unknown";
const UNTITLED = "untitled";

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

// A row from a build older than M2 carries no bucket at all, and a value this
// page has never heard of is not a crash: both land on `unclassified`, which is
// grey, counted, and honest about being a thing nobody classified.
function bucketOf(row) {
  const bucket = row.bucket;
  return typeof bucket === "string" && bucket in BUCKET_LABEL ? bucket : "unclassified";
}

export function bucketChip(row) {
  const bucket = bucketOf(row);
  const node = element("span", `chip bucket-${bucket}`);
  node.appendChild(element("span", "chip-mark", BUCKET_MARK[bucket]));
  node.appendChild(element("span", "chip-label", BUCKET_LABEL[bucket]));
  return node;
}

// ----- §12's stopped row: "so what do I do", without reading a transcript ----
//
// Everything below is drawn from the row the tool already sent. Nothing here
// opens a log, a transcript or a second endpoint (K14/D25): the classifier read
// the transcript once, at the stop, and the verdict it wrote is what this page
// renders.

// N10 / D34. The model verdict lane is **not built** at M2, so `[why?]` expands
// the heuristic evidence and says so in words. A control that implied a verdict
// nobody computed would be worse than no control at all.
const MODEL_LANE_NOTE =
  "Heuristic evidence only — the model verdict lane is not built in this build, so no model looked at this stop.";

// RD6: an action whose capability lands later renders **labelled and inert**,
// with the milestone named. §12 says the row is never a dead end, and an
// unlabelled dead button *is* the dead end.
const ACTION_MILESTONE = {
  resume: "M3",
  respawn: "M3",
  retry: "M3",
  escalate: "M4",
  requeue: "M4",
  reauth: "M4",
};

// The kinds this build can honour today: `external` is a link when it has a
// target, `inspect` is the expansion itself, and `none` names no capability at
// all ("Resumes by itself — nothing to do"). Every kind the store can hold is
// in one table or the other; one in neither is the silent dead button.
const LIVE_KINDS = {
  inspect: true,
  external: true,
  none: true,
};

function isStopped(row) {
  return row.state === "stopped" || typeof row.stop_reason === "string";
}

function actionsOf(row) {
  return Array.isArray(row.next_actions) ? row.next_actions : [];
}

function whyOf(row) {
  const why = row.why;
  if (typeof why === "string" && why.trim() !== "") {
    return why;
  }
  if (typeof row.stop_reason === "string") {
    return row.stop_reason;
  }
  // E-M2-4 / D-4: the stop whose record never arrived. Counted, and said.
  return "no verdict — this stop was never classified";
}

export function actionButton(action) {
  const kind = typeof action.kind === "string" ? action.kind : "none";
  const text = typeof action.text === "string" && action.text !== "" ? action.text : UNKNOWN;

  // §12's `[↗]`. A link needs nothing of ours, so it is live at M2 — but only
  // when there is somewhere to go: G-M2-7's `Chase — what it is waiting on is
  // not recorded` has no url, and must not pretend to one.
  if (kind === "external" && typeof action.target === "string" && action.target !== "") {
    const link = element("a", "action action-link", `${text} ↗`);
    link.href = action.target;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  const milestone = ACTION_MILESTONE[kind];
  const button = element("button", milestone ? "action action-not-yet" : "action", text);
  button.type = "button";
  if (milestone) {
    button.disabled = true;
    button.title = `not yet — ${kind} lands at ${milestone}`;
    button.appendChild(element("span", "action-badge", "not yet"));
  } else if (!(kind in LIVE_KINDS)) {
    // A kind from a newer build: inert, labelled, and never silently clickable.
    button.disabled = true;
    button.title = `not yet — this build does not know the action kind ${kind}`;
    button.appendChild(element("span", "action-badge", "not yet"));
  }
  return button;
}

function whyNote(row) {
  const note = element("details", "why-note");
  note.appendChild(element("summary", "why-summary", "why?"));
  const decided = typeof row.decided_by === "string" ? row.decided_by : UNKNOWN;
  const confidence = typeof row.confidence === "number" ? row.confidence : null;
  note.appendChild(
    element(
      "p",
      "why-evidence",
      `decided by ${decided} · confidence ${confidence === null ? UNKNOWN : confidence}`,
    ),
  );
  note.appendChild(element("p", "why-lane", MODEL_LANE_NOTE));
  return note;
}

function sourceFooter(actions) {
  // Insertion order, which is the order the payload arrived in. Nothing here
  // sorts: the page renders the order it was handed.
  const counts = new Map();
  for (const action of actions) {
    const source = typeof action.source === "string" ? action.source : UNKNOWN;
    counts.set(source, (counts.get(source) || 0) + 1);
  }
  const footer = element("div", "stop-sources");
  for (const [source, total] of counts) {
    footer.appendChild(element("span", "stop-source", `${total} ${source}`));
  }
  return footer;
}

function stoppedRow(row) {
  const line = element("div", "session-stop");
  line.appendChild(element("span", "session-why", whyOf(row)));
  const actions = actionsOf(row);
  if (actions.length > 0) {
    line.appendChild(actionButton(actions[0]));
  } else {
    // §14: an empty list is only ever a *confident* `completed`. Anything else
    // with no actions is a rule bug, and the classifier's own tests say so.
    line.appendChild(element("span", "session-no-action", "nothing to do"));
  }
  line.appendChild(whyNote(row));
  return line;
}

function expansion(row) {
  const panel = element("div", "stop-expansion");
  const list = element("ol", "stop-actions");
  actionsOf(row).forEach((action, index) => {
    const item = element("li", "stop-action");
    item.appendChild(element("span", "action-ordinal", `${index + 1}`));
    item.appendChild(actionButton(action));
    item.appendChild(element("span", "action-source", action.source || UNKNOWN));
    list.appendChild(item);
  });
  panel.appendChild(list);
  // At M2 this always reads `N heuristic`, which is itself the honest signal
  // that D34's model lane is off.
  panel.appendChild(sourceFooter(actionsOf(row)));
  return panel;
}

// A missing title degrades honestly: the title carrier is still landing, and an
// untitled session must render, not crash.
function titleOf(session) {
  const title = session.title;
  return typeof title === "string" && title.trim() !== "" ? title : UNTITLED;
}

function progressOf(session) {
  const done = Number.isInteger(session.tasks_done) ? session.tasks_done : null;
  const total = Number.isInteger(session.tasks_total) ? session.tasks_total : null;
  if (done === null || total === null || total === 0) {
    return null;
  }
  return `${done}/${total} tasks`;
}

function subagentSummary(session) {
  const active = Number.isInteger(session.active_subagents) ? session.active_subagents : 0;
  return active === 1 ? "1 subagent" : `${active} subagents`;
}

function metaLine(session) {
  const line = element("div", "session-meta");
  const parts = [session.ownership, session.model, progressOf(session)];
  for (const part of parts) {
    if (typeof part === "string" && part !== "") {
      line.appendChild(element("span", "meta-part", part));
    }
  }
  return line;
}

function subagentLine(subagent) {
  const line = element("li", "subagent");
  line.appendChild(element("span", "subagent-state", subagent.state || UNKNOWN));
  line.appendChild(element("span", "subagent-type", subagent.agent_type || UNKNOWN));
  line.appendChild(element("span", "subagent-description", subagent.description || ""));
  return line;
}

function subagentPanel(rollup) {
  const panel = element("ul", "subagents");
  if (!rollup) {
    panel.appendChild(element("li", "subagent-empty", "loading…"));
    return panel;
  }
  if (!rollup.transcript_found) {
    // E26: an announced transcript that was never written is a *value*.
    panel.appendChild(
      element("li", "subagent-empty", "no transcript yet · 0 subagents"),
    );
    return panel;
  }
  if (rollup.subagents.length === 0) {
    panel.appendChild(element("li", "subagent-empty", "0 subagents"));
    return panel;
  }
  for (const subagent of rollup.subagents) {
    panel.appendChild(subagentLine(subagent));
  }
  return panel;
}

function sessionRow(session, view, onExpand) {
  const row = element("li", "session");
  // §12 page 3 is opened from here. `app.js` owns the navigation and this file
  // owns the rows, so the row carries its own identity rather than the two
  // sides agreeing on a position in a list either of them may re-order.
  row.dataset.sessionId = session.session_id;
  const header = element("div", "session-header");
  header.appendChild(bucketChip(session));
  header.appendChild(element("span", "session-title", titleOf(session)));

  const reason = session.needs_you_reason;
  if (typeof reason === "string" && reason !== "") {
    // The actual ask, verbatim from the fold — never "session needs attention".
    header.appendChild(element("span", "session-ask", reason));
  }

  const expanded = view.expanded.has(session.session_id);
  const toggle = element("button", "session-toggle", subagentSummary(session));
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  toggle.addEventListener("click", () => onExpand(session.session_id));
  header.appendChild(toggle);

  row.appendChild(header);
  row.appendChild(metaLine(session));
  if (isStopped(session)) {
    row.appendChild(stoppedRow(session));
    if (expanded) {
      row.appendChild(expansion(session));
    }
  }
  if (expanded) {
    row.appendChild(subagentPanel(view.subagents.get(session.session_id)));
  }
  return row;
}

// Both the grouping and the order arrive with the payload: `fleet_tree` groups
// workspace -> session and orders by `fleet_sort_key` (§16), which is the only
// place §8's read-time demotion can be applied. This file renders what it was
// handed — it never sorts, compares names, or reads a timestamp for position.
function workspaceBlock(view, workspace, onExpand) {
  const sessions = workspace.sessions || [];
  const block = element("section", "workspace");
  const header = element("div", "workspace-header");
  header.appendChild(element("h2", "workspace-name", workspace.name || UNKNOWN));
  header.appendChild(element("span", "workspace-count", `${sessions.length} sessions`));
  block.appendChild(header);

  const list = element("ul", "sessions");
  for (const session of sessions) {
    list.appendChild(sessionRow(session, view, onExpand));
  }
  block.appendChild(list);
  return block;
}

// The eight counts, in the order the server sent them — `by_bucket`'s keys are
// §12's display order, so this loop renders an order it was handed rather than
// learning one. A bucket at zero is still a bucket shown (principle 5).
function renderCounts(view) {
  const host = document.getElementById("counts");
  host.replaceChildren();
  const counts = (view.fleet && view.fleet.by_bucket) || {};
  for (const bucket of Object.keys(counts)) {
    if (!(bucket in BUCKET_LABEL)) {
      continue;
    }
    const total = Number.isInteger(counts[bucket]) ? counts[bucket] : 0;
    const part = element("span", `count bucket-${bucket}`);
    part.appendChild(element("span", "count-mark", BUCKET_MARK[bucket]));
    part.appendChild(element("span", "count-value", total));
    part.appendChild(element("span", "count-label", BUCKET_LABEL[bucket]));
    host.appendChild(part);
  }
}

// DP10 / principle 5. Three numbers, three meanings, none folded into another.
// The rate is rendered as a percentage of *classified* stops; a fresh install
// divides by zero on the server, which answers 0.0 rather than NaN.
function renderStopSummary(view) {
  const fleet = view.fleet || {};
  const rate = typeof fleet.unknown_rate === "number" ? fleet.unknown_rate : null;
  const low = Number.isInteger(fleet.completed_low_confidence)
    ? fleet.completed_low_confidence
    : null;
  const never = Number.isInteger(fleet.unclassified) ? fleet.unclassified : null;
  // Slots are static markup filled with textContent (§13) — no sink to escape.
  document.getElementById("unknown-rate").textContent =
    rate === null ? UNKNOWN : `${Math.round(rate * 100)}%`;
  document.getElementById("low-confidence").textContent = low === null ? UNKNOWN : String(low);
  document.getElementById("unclassified").textContent = never === null ? UNKNOWN : String(never);
}

// F16: the first thing anyone sees on a fresh install. It names what discovery
// can actually see rather than leaving a blank area or raising.
function renderEmptyState(view) {
  const panel = document.getElementById("empty-state");
  const discovery = (view.fleet && view.fleet.discovery) || {};
  const hooks = typeof discovery.hooks === "string" ? discovery.hooks : UNKNOWN;
  const registry = Number.isInteger(discovery.registry_sessions)
    ? discovery.registry_sessions
    : 0;
  const sources = document.getElementById("empty-state-sources");
  sources.replaceChildren();
  sources.appendChild(element("span", "source", `hooks: ${hooks}`));
  sources.appendChild(element("span", "source", `registry: ${registry} sessions`));
  panel.hidden = false;
}

export function render(view, onExpand) {
  renderCounts(view);
  renderStopSummary(view);
  const host = document.getElementById("fleet");
  host.replaceChildren();

  if (view.workspaces.length === 0) {
    renderEmptyState(view);
    return;
  }
  document.getElementById("empty-state").hidden = true;

  for (const workspace of view.workspaces) {
    host.appendChild(workspaceBlock(view, workspace, onExpand));
  }
}

export function renderStatus(status) {
  const node = document.getElementById("stream-status");
  node.textContent = status;
}
