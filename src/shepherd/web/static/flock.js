// The Flock: three panes — projects -> session cards -> the session (U9).
//
// This file is the M5 successor to `fleet.js`. Four rules shape every function
// in it, and each one is a gate rather than a habit.
//
// **§13 — no HTML sink.** Nothing here touches `innerHTML`, `outerHTML` or
// `insertAdjacentHTML`. Every value that came from a session — a title, an ask,
// a project name — is untrusted text and reaches the page through `textContent`
// only. The two icons this page draws (the legend's `ⓘ` and the back chevron)
// are built with `document.createElementNS`, not concatenated markup: the
// prototype assigned both through `innerHTML` and both are findings.
// `tests/web/test_frontend_escaping.py` fails the build on a sink appearing
// here.
//
// **§16 — the server orders, the page renders.** `fleet_tree` already orders by
// `fleet_bucket_sort_key`. This file never sorts, never compares names and never
// reads a timestamp to decide position. `.sort(`, `localeCompare` and
// `BUCKET_ORDER` are banned by name in `test_palette.py`.
//
// **U7 — a card carries four things and no more:** bucket glyph and colour,
// title, the ask verbatim (only when stopped or waiting), and relative time.
// Progress is a 2px hairline on the bottom edge, never a text line. Model,
// ownership, session id, confidence and workspace path are all real and all
// deliberately out — none of them changes which card you tap.
//
// **Principle 5 — the unknown rate is counted and displayed, never hidden.**
// The stop-summary strip sits in the Flock header beside the legend.

// §4's eight buckets. Every one carries a **glyph as well as a colour** (the
// colour is `--bucket-colour` in `app.css`): amber and red are the two chips a
// colourblind reader most needs to tell apart, and in greyscale they are the
// same grey. `tests/web/test_palette.py` reads these tables back out of this
// file and compares them to `core.stops.PALETTE`, so there is one source of
// truth and the copy here is checked rather than trusted.
//
// The *order* is not here. It arrives with the payload — `fleet_bucket_sort_key`
// server-side — because the demotion `bucket_of` applies compares
// `last_event_at` against the liveness window, which is a thing only L2 can do.
export const BUCKET_LABEL = {
  needs_you: "needs you",
  error: "error",
  unfinished: "stranded",
  running: "running",
  paused: "limit exceeded",
  blocked: "blocked",
  finished: "finished",
  unclassified: "unknown",
};

export const BUCKET_MARK = {
  needs_you: "⏸",
  error: "✕",
  unfinished: "◑",
  running: "●",
  paused: "⏱",
  blocked: "⏳",
  finished: "✓",
  unclassified: "?",
};

// U10: the `acts:` line, **verbatim from `PALETTE.who_acts`** — the field that
// already exists and is the thing that actually distinguishes the buckets.
// Compared back to `PALETTE` by `test_palette.py`, exactly as the two above are.
const BUCKET_ACTS = {
  needs_you: "you, now",
  error: "you, fix it",
  unfinished: "you, when ready",
  running: "nobody",
  paused: "nobody, wait",
  blocked: "someone else",
  finished: "nobody",
  unclassified: "nobody yet",
};

// U1's sheet: eight explanations, read together. These are page prose and have
// **no counterpart in `PALETTE`** — `BucketStyle` carries a colour, a glyph, a
// label and `who_acts`, and nothing longer. Said here rather than left to be
// discovered: this is the one table on this page that nothing server-side can
// check, which is why the other three are compared and this one is reviewed.
const BUCKET_BLURB = {
  needs_you:
    "Stopped and waiting on a decision only you can make — a permission prompt, a question, or a TUI idle for 60 seconds. The card carries the ask verbatim.",
  error:
    "Failed and will not continue on its own: a bad request, a server error, a failed login, or a tool that never came back.",
  unfinished:
    "Ended without finishing — out of context, you exited, the transcript was cleared. Nothing is broken; it needs restarting.",
  running:
    "Working right now, including while it waits on its own subagents. Demoted automatically if it goes quiet past the liveness window.",
  paused:
    "Stopped by a limit that clears on its own: rate limited, or out of quota. Nothing to do but wait.",
  blocked:
    "Waiting on something outside this session. Real, visible, and not yours to act on — which is why it is desaturated.",
  finished:
    "Ended cleanly with the work closed. Completions the heuristics could not verify are counted separately, not folded in here.",
  unclassified:
    "Stopped, but no verdict ever reached disk. Counted and shown rather than guessed at.",
};

// The two buckets whose ask is shouted rather than said. `error` and `needs_you`
// are the only ones where not reading the line has a cost.
const LOUD = { needs_you: true, error: true };

// Principle 5: a datum we do not have is shown as unknown, never invented.
const UNKNOWN = "unknown";
const UNTITLED = "untitled";

//: U8's scale, in seconds. `year` first so the loop never has to compare.
const SCALE = [
  [31536000, "year"],
  [2592000, "month"],
  [604800, "week"],
  [86400, "day"],
  [3600, "hour"],
  [60, "minute"],
];

//: E19 / U8. A session we have never seen tick says so rather than claiming
//: `just now` — which would be a *newer* timestamp than the truth, and the one
//: direction a missing datum must never be rounded in.
const NEVER_SEEN = "never seen";

const SVG_NS = "http://www.w3.org/2000/svg";

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

// The two icons this page draws, built as nodes rather than as markup. The
// prototype assigned both through `innerHTML` (`renderLegend` at 2520,
// `BACK_BUTTON` at 2858); §13 permits a sink only when its right-hand side is a
// single quoted literal with no concatenation, and neither of those was one.
// `createElementNS` is required rather than `createElement`: an `<svg>` built
// in the HTML namespace renders as nothing at all.
function svgIcon(className, paths, width) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", width);
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  if (className) {
    svg.setAttribute("class", className);
  }
  for (const description of paths) {
    const node = document.createElementNS(SVG_NS, description.tag);
    for (const key of Object.keys(description.attributes)) {
      node.setAttribute(key, description.attributes[key]);
    }
    svg.appendChild(node);
  }
  return svg;
}

function infoIcon() {
  return svgIcon(null, [
    { tag: "circle", attributes: { cx: "12", cy: "12", r: "9" } },
    { tag: "path", attributes: { d: "M12 16v-4" } },
    { tag: "path", attributes: { d: "M12 8h.01" } },
  ], "2");
}

function chevronIcon() {
  return svgIcon(null, [{ tag: "path", attributes: { d: "M15 18l-6-6 6-6" } }], "2.2");
}

// U9's phone behaviour: one level at a time, with a back chevron. The level is
// a data attribute on the page root and the CSS decides which columns show, so
// a wide screen keeps all three and nothing here measures a viewport.
export function backButton(level) {
  const button = element("button", "back");
  button.type = "button";
  button.setAttribute("aria-label", "Back");
  button.dataset.level = level;
  button.appendChild(chevronIcon());
  return button;
}

// ----- U8: relative time, spelled out, scaling to years ----------------------

// `timestamp` is the payload's ISO-8601 `last_event_at` and `now` is a
// millisecond clock handed in — never read from `Date.now()` inside, so a test
// can state the instant it is asking about.
export function ago(timestamp, now) {
  if (timestamp === null || timestamp === undefined || timestamp === "") {
    return NEVER_SEEN;
  }
  const then = Date.parse(timestamp);
  if (Number.isNaN(then)) {
    // A timestamp we cannot read is a timestamp we do not have. Saying
    // `just now` for it would be inventing the one thing E19 is about.
    return NEVER_SEEN;
  }
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) {
    return "just now";
  }
  for (const [size, unit] of SCALE) {
    if (seconds >= size) {
      const count = Math.floor(seconds / size);
      return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

// A row from a build older than M2 carries no bucket at all, and a value this
// page has never heard of is not a crash: both land on `unclassified`, which is
// grey, counted, and honest about being a thing nobody classified.
export function bucketOf(row) {
  const bucket = row.bucket;
  return typeof bucket === "string" && bucket in BUCKET_LABEL ? bucket : "unclassified";
}

// ----- U10 / U1: the legend, and the sheet that explains all eight -----------

// Hover and keyboard focus give a single key its own popover; a **tap** opens
// the sheet instead. A key that did nothing on tap would be a dead control, and
// eight explanations read better together than one at a time on a phone (U1).
let tip = null;

function hideTip() {
  if (tip !== null) {
    tip.remove();
    tip = null;
  }
}

function showTip(anchor, bucket) {
  hideTip();
  tip = element("div", `tip bucket-${bucket}`);
  tip.setAttribute("role", "tooltip");

  const head = element("div", "tip-head");
  head.appendChild(element("span", "tip-mark", BUCKET_MARK[bucket]));
  head.appendChild(element("span", "tip-label", BUCKET_LABEL[bucket]));
  tip.appendChild(head);
  tip.appendChild(element("p", "tip-who", `acts: ${BUCKET_ACTS[bucket]}`));
  tip.appendChild(element("p", "tip-body", BUCKET_BLURB[bucket]));
  document.body.appendChild(tip);

  const box = anchor.getBoundingClientRect();
  const size = tip.getBoundingClientRect();
  let left = box.left;
  if (left + size.width > window.innerWidth - 12) {
    left = window.innerWidth - size.width - 12;
  }
  if (left < 12) {
    left = 12;
  }
  let top = box.bottom + 8;
  if (top + size.height > window.innerHeight - 12) {
    top = box.top - size.height - 8;
  }
  tip.style.left = `${left}px`;
  tip.style.top = `${Math.max(12, top)}px`;
}

function openLegendSheet() {
  hideTip();
  // `dlg-legend-list`, not `sheet-list`: the shipped shell spells it that way
  // and the dialog is the shell's, not this page's. Aligning to the id that
  // exists is a smaller contract than asking for a rename of one that does.
  const host = document.getElementById("dlg-legend-list");
  host.replaceChildren();
  for (const bucket of Object.keys(BUCKET_LABEL)) {
    const row = element("div", `sheet-row bucket-${bucket}`);
    row.appendChild(element("span", "sheet-glyph", BUCKET_MARK[bucket]));
    const name = element("div", "sheet-name");
    name.appendChild(element("span", "sheet-label", BUCKET_LABEL[bucket]));
    name.appendChild(element("span", "sheet-acts", `acts: ${BUCKET_ACTS[bucket]}`));
    row.appendChild(name);
    row.appendChild(element("p", "sheet-text", BUCKET_BLURB[bucket]));
    host.appendChild(row);
  }
  document.getElementById("dlg-legend").showModal();
}

// U16: the legend is the glyph plus coloured text. The colour is `--b`, set by
// the `.bucket-*` class in `app.css` — never a hex written here, which is the
// drift `test_palette_matches_core_stops` exists to catch.
function renderLegend() {
  const host = document.getElementById("flock-legend");
  host.replaceChildren();
  for (const bucket of Object.keys(BUCKET_LABEL)) {
    const key = element("button", `legend-key bucket-${bucket}`);
    key.type = "button";
    key.dataset.bucket = bucket;
    key.appendChild(element("span", "legend-mark", BUCKET_MARK[bucket]));
    key.appendChild(element("span", "legend-label", BUCKET_LABEL[bucket]));
    key.addEventListener("mouseenter", () => showTip(key, bucket));
    key.addEventListener("mouseleave", hideTip);
    key.addEventListener("focus", () => showTip(key, bucket));
    key.addEventListener("blur", hideTip);
    key.addEventListener("click", openLegendSheet);
    host.appendChild(key);
  }

  const info = element("button", "legend-info");
  info.type = "button";
  info.setAttribute("aria-label", "What the colours mean");
  info.appendChild(infoIcon());
  info.appendChild(element("span", "legend-info-text", "what these mean"));
  info.addEventListener("click", openLegendSheet);
  host.appendChild(info);
}

// ----- principle 5: the stop summary, in the Flock header --------------------

// DP10 / principle 5 / B3. Three numbers, three meanings, none folded into
// another. The rate is a percentage of *classified* stops; a fresh install
// divides by zero on the server, which answers 0.0 rather than NaN.
//
// The strip stayed when the rail went (D66): the unknown rate is counted and
// displayed, and a page that hid it would be hiding the one number that says
// how much of the rest of the page is a guess.
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

// ----- pane 1: projects ------------------------------------------------------

// The projects are the payload's `workspaces`, in the order it sent them. E21:
// `Unassigned` is one of them — migration 004 seeds it and `fleet_tree` groups
// into it, so a session that matched no declared project has a home on this
// page rather than vanishing from it.
function titleOf(session) {
  const title = session.title;
  return typeof title === "string" && title.trim() !== "" ? title : UNTITLED;
}

function projectButton(workspace, view, handlers) {
  const button = element("button", "project");
  button.type = "button";
  // D22: a project **is** a workspace, and the consumer-facing key is
  // `project_id`. `fleet_tree`'s workspace entries carry that spelling while
  // the session rows inside them carry `workspace_id`; reading the row's
  // spelling off the workspace renders a list of `undefined` projects that
  // select nothing, which is the one bug a source scan cannot see.
  button.dataset.projectId = workspace.project_id;
  button.setAttribute(
    "aria-current",
    workspace.project_id === view.projectId ? "true" : "false",
  );
  button.appendChild(element("span", "project-name", workspace.name || UNKNOWN));
  button.appendChild(
    element("span", "project-n", String((workspace.sessions || []).length)),
  );
  button.addEventListener("click", () => handlers.onOpenProject(workspace.project_id));
  return button;
}

function renderProjects(view, handlers) {
  const host = document.getElementById("flock-projects");
  host.replaceChildren();
  for (const workspace of view.workspaces) {
    host.appendChild(projectButton(workspace, view, handlers));
  }
}

// ----- pane 2: the session cards ---------------------------------------------

// U7's four items and no more. The class carries the colour: every card is
// `.card` **plus** one of the eight `.bucket-*` classes, because `--b` falls
// back to the unclassified grey and a card that forgot its class would render
// as a plausible `unknown` session rather than as an obvious mistake.
//
// D21's `next_actions` list is deliberately **not** here. It renders in the
// session pane's header, which is where §12 already placed it (D67).
function sessionCard(session, view, handlers, now) {
  const bucket = bucketOf(session);
  const card = element("button", `card bucket-${bucket}`);
  card.type = "button";
  card.dataset.sessionId = session.session_id;
  card.setAttribute(
    "aria-current",
    session.session_id === view.sessionId ? "true" : "false",
  );

  const top = element("div", "card-top");
  top.appendChild(element("span", "card-mark", BUCKET_MARK[bucket]));
  top.appendChild(element("span", "card-title", titleOf(session)));
  top.appendChild(element("span", "card-age", ago(session.last_event_at, now)));
  card.appendChild(top);

  // The ask, verbatim from the fold — never "session needs attention", and only
  // when there is one. A waiting session has `needs_you_reason`; a stopped one
  // has the classifier's `why`. Both are the actual ask; neither is invented.
  const ask = askOf(session);
  if (ask !== null) {
    const line = element("span", "card-ask", ask);
    if (LOUD[bucket]) {
      line.dataset.tone = "loud";
    }
    card.appendChild(line);
  }

  // U7: progress is a hairline, never a text line. `2/5 tasks` was a fifth item
  // on a card that carries four.
  const bar = progressBar(session);
  if (bar !== null) {
    card.appendChild(bar);
  }

  card.addEventListener("click", () => handlers.onOpenSession(session.session_id));
  return card;
}

function askOf(session) {
  const reason = session.needs_you_reason;
  if (typeof reason === "string" && reason.trim() !== "") {
    return reason;
  }
  const why = session.why;
  if (typeof why === "string" && why.trim() !== "") {
    return why;
  }
  return null;
}

function progressBar(session) {
  const done = Number.isInteger(session.tasks_done) ? session.tasks_done : null;
  const total = Number.isInteger(session.tasks_total) ? session.tasks_total : null;
  if (done === null || total === null || total === 0) {
    return null;
  }
  const bar = element("div", "card-bar");
  const fill = element("span", "card-bar-fill");
  fill.style.width = `${Math.round((done / total) * 100)}%`;
  bar.appendChild(fill);
  return bar;
}

function currentProject(view) {
  for (const workspace of view.workspaces) {
    if (workspace.project_id === view.projectId) {
      return workspace;
    }
  }
  return null;
}

function renderCards(view, handlers, now) {
  const project = currentProject(view);
  document.getElementById("flock-sessions-head").textContent =
    project === null ? "Sessions" : project.name || UNKNOWN;
  const host = document.getElementById("flock-cards");
  host.replaceChildren();
  if (project === null) {
    return;
  }
  // The order arrives with the payload (`fleet_bucket_sort_key`, §16). This
  // loop renders an order it was handed rather than learning one.
  for (const session of project.sessions || []) {
    host.appendChild(sessionCard(session, view, handlers, now));
  }
}

// ----- F16: the first thing anyone sees on a fresh install -------------------

// It names what discovery can actually see rather than leaving a blank area.
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

// ----- the page ---------------------------------------------------------------

// `mountFlock(handlers)` wires the parts of the page that do not change with
// the payload: the legend, the sheet, and the back chevrons U9's drill-down
// needs. It is called once. `renderFlock(view)` is called on every arriving
// event and touches only the three panes.
export function mountFlock(handlers) {
  renderLegend();
  const page = document.getElementById("page-flock");
  for (const button of page.querySelectorAll(".back[data-level]")) {
    button.addEventListener("click", () => {
      page.dataset.level = button.dataset.level;
    });
  }
  for (const button of document.querySelectorAll("[data-close=\"dlg-legend\"]")) {
    button.addEventListener("click", () => document.getElementById("dlg-legend").close());
  }
  window.addEventListener("scroll", hideTip, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideTip();
    }
  });
  return handlers;
}

export function renderFlock(view, handlers, now) {
  renderStopSummary(view);

  if (view.workspaces.length === 0) {
    renderProjects(view, handlers);
    renderCards(view, handlers, now);
    renderEmptyState(view);
    return;
  }
  document.getElementById("empty-state").hidden = true;
  renderProjects(view, handlers);
  renderCards(view, handlers, now);
}

// U9's drill-down: the level the page is showing. A wide screen shows all three
// columns whatever this says; a phone shows one, and the chevron walks back.
export function showLevel(level) {
  document.getElementById("page-flock").dataset.level = level;
}

export function renderStatus(status) {
  const node = document.getElementById("stream-status");
  node.textContent = status;
}
