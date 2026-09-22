// U13's Settings page: ten sections under two headings, four of them real.
//
// **Four are built and six are placeholders, and the page says which.** U13:
// *anything unbuilt carries a `not built` chip and says why in the panel*. Both
// halves matter — a chip with no explanation is a dead end, and an explanation
// with no chip reads as a feature that is merely empty today. The reason is in
// the `SECTIONS` table beside the section it excuses, so the two cannot drift.
//
// **This is where D65 and U6 moved things to.** The autonomy control is a
// Settings control and nothing else, and the audit tail is Settings → Data with
// D25's four-field whitelist intact. Neither was deleted; both were moved, and
// `test_chat_page.py` asserts the destination as well as the absence.
//
// **F6: the prototype's `panelHead` was an `innerHTML` assignment.** It is the
// one of the prototype's eight sinks that belongs to this module, and it is
// rewritten here as `createElement` + `textContent`. This file has no HTML sink
// at all (§13), which is what `test_the_settings_page_has_no_html_sink` asserts
// with a negative control beside it.
//
// **Nothing is on a timer.** §12 forbids polling and the rail's removal did not
// retire the rule: every read below is caused by the first paint or by a click.
// No timer or scheduler shape appears here — `test_no_polling_in_the_ui`
// enumerates them, and it reads comments too, so they are not named.
//
// **The CLI's removal verb is absent from the UI entirely** (U13). It is not a
// disabled row and not a `not built` chip: a destructive verb offered behind a
// disabled control is an invitation, and the CLI is where it stays. The verb
// itself is deliberately not written anywhere in this file — comments included,
// because a scan that excused comments would pass on a commented-out control.

import { GAP } from "./sse.js";

// Three reads and one write, all of them routes the server already declares.
// `/api/fleet` is here because it is the only thing on the wire that carries
// discovery's hook status and the daemon's own clock — the two facts Discovery
// and System show. No route was added for this page.
const AUDIT = "/api/audit";
const AUTONOMY = "/api/autonomy";
const FLEET = "/api/fleet";

const UNKNOWN = "—";

// U13's two headings, spelled once.
const YOURS = "Yours";
const INSTANCE = "This instance";

// D8's two levels, as `set_autonomy_level` enumerates them. They are integers
// because the route takes an integer; U12 is that they never reach the screen.
const LEVEL_ASK = 2;
const LEVEL_AUTO = 3;

// U12, in words. The scale starts at 2 for historical reasons the spec never
// justifies and the numbers mean nothing to a reader, so the options are
// sentences — and the second states that auto-approved is never unlogged,
// because "approve automatically" read alone sounds like "stop recording".
const AUTONOMY_OPTIONS = [
  {
    level: LEVEL_ASK,
    label: "Ask me before anything leaves this machine",
    note: "A call that changes something outside this machine waits for you, inline in the Shepherd conversation.",
  },
  {
    level: LEVEL_AUTO,
    label: "Approve automatically",
    note: "Nothing waits for you. Every automatic approval is still written to the audit log below, under Data — approving automatically is never the same as not recording it.",
  },
];

// U13's ten, in reading order. `built` is what this build can actually show;
// `why` is what the panel says when it cannot, and it is `null` for the four
// that can — there is nothing to excuse.
const SECTIONS = [
  {
    id: "account",
    group: YOURS,
    title: "Account",
    built: false,
    lead: "Who you are to this Shepherd.",
    why: "Shepherd has no accounts. It runs as you, on this machine, and every call it makes is already yours. Accounts arrive with the first remote client, and the four open questions about how they would be stored are unanswered.",
  },
  {
    id: "notifications",
    group: YOURS,
    title: "Notifications",
    built: false,
    lead: "How Shepherd reaches you when a turn is blocked.",
    why: "There is no delivery channel yet. The page tells you a turn is blocked while you are looking at it; reaching you when you are not is push, and nothing in this build can send one.",
  },
  {
    id: "api-keys",
    group: YOURS,
    title: "API keys",
    built: false,
    lead: "Credentials Shepherd uses on your behalf.",
    why: "Shepherd stores no credentials. The engine reads its own key from the environment it was started in, so there is nothing here to show and nothing here to leak.",
  },
  {
    id: "autonomy",
    group: INSTANCE,
    title: "Autonomy",
    built: true,
    lead: "What Shepherd may do without asking you first.",
    why: null,
  },
  {
    id: "shepherd",
    group: INSTANCE,
    title: "Shepherd",
    built: false,
    lead: "The orchestrator itself — its model, its prompt, its limits.",
    why: "The orchestrator's model and system prompt are fixed in this build. Making them configurable means deciding what happens to a turn that is already running when they change, and that has not been decided.",
  },
  {
    id: "discovery",
    group: INSTANCE,
    title: "Discovery",
    built: true,
    lead: "How Shepherd finds sessions it did not start.",
    why: null,
  },
  {
    id: "limits",
    group: INSTANCE,
    title: "Limits",
    built: false,
    lead: "Ceilings on what runs at once and for how long.",
    why: "The limits exist in the daemon's configuration and are not editable from here. A ceiling changed on a page while sessions are running against the old one needs a re-check rule, and there is not one yet.",
  },
  {
    id: "users",
    group: INSTANCE,
    title: "Users & access",
    built: false,
    lead: "Who else may drive this Shepherd.",
    why: "This build is single-user by construction: the server binds loopback and there is no authentication in front of it. Access control is the same open question as Account above, and it is answered there first.",
  },
  {
    id: "data",
    group: INSTANCE,
    title: "Data",
    built: true,
    lead: "What Shepherd has written down, and what it shows of it.",
    why: null,
  },
  {
    id: "system",
    group: INSTANCE,
    title: "System",
    built: true,
    lead: "What this daemon reports about itself.",
    why: null,
  },
];

// The chip's words, spelled once so the nav and the panel cannot disagree.
const NOT_BUILT = "not built";

const state = {
  section: SECTIONS[0].id,
  level: null,
  audit: null,
  fleet: null,
};

function slot(id) {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`no slot ${id}`);
  }
  return element;
}

// Principle 5's em dash, in one place: a datum nobody has read yet renders the
// same way everywhere and a render is never a bare `undefined` on the screen.
function textOf(value) {
  return value === null || value === undefined ? UNKNOWN : String(value);
}

function fill(id, value) {
  const element = slot(id);
  element.textContent = textOf(value);
}

// The one node constructor on this page. There is no second one and no HTML
// sink: a class and a string, both of them set as data (§13).
function el(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

// A `<button>` with no `type` inside a form submits it.
function control(tag, className, text) {
  const element = el(tag, className, text);
  element.type = "button";
  return element;
}

async function read(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await response.json();
  if (!body.ok) {
    return null;
  }
  return body.data;
}

async function write(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!body.ok) {
    return null;
  }
  return body.data;
}

// ----- the nav ----------------------------------------------------------------

function sectionById(id) {
  return SECTIONS.find((row) => row.id === id);
}

// U13's two headings with their sections under them. The chip is on the nav
// entry as well as in the panel, so you can see what is real without opening
// each one.
function renderNav() {
  const nav = slot("settings-nav");
  const nodes = [];
  for (const group of [YOURS, INSTANCE]) {
    nodes.push(el("div", "set-group", group));
    for (const row of SECTIONS.filter((section) => section.group === group)) {
      const item = control("button", "set-item", row.title);
      item.setAttribute("aria-current", String(row.id === state.section));
      if (!row.built) {
        item.appendChild(el("span", "soon", NOT_BUILT));
      }
      item.onclick = () => open(row.id);
      nodes.push(item);
    }
  }
  nav.replaceChildren(...nodes);
}

// F6: the prototype assigned this heading through `innerHTML`. It is nodes.
function panelHead(row) {
  const head = el("div", "col-head", row.title);
  if (!row.built) {
    head.appendChild(el("span", "soon", NOT_BUILT));
  }
  return head;
}

function renderPanel() {
  const panel = slot("settings-panel");
  const row = sectionById(state.section);
  const body = el("div", "set-body");
  body.appendChild(el("p", "set-lead", row.lead));
  if (row.built) {
    body.appendChild(PANELS[row.id]());
  } else {
    // U13: the chip says *that* it is unbuilt, the panel says *why*.
    const reason = el("div", "notbuilt");
    reason.appendChild(el("b", undefined, NOT_BUILT));
    reason.appendChild(el("span", undefined, row.why));
    body.appendChild(reason);
  }
  panel.replaceChildren(panelHead(row), body);
}

// The phone drill-down. `.panes2` shows the list or the panel and never both
// under 760px; above it the attribute is inert and the grid shows the two.
function showDetail() {
  const root = slot("page-settings");
  root.dataset.level = "detail";
}

function showList() {
  const root = slot("page-settings");
  root.dataset.level = "list";
}

function open(id) {
  state.section = id;
  renderNav();
  renderPanel();
  showDetail();
}

// ----- a row, which is most of this page --------------------------------------

function settingRow(name, note, control_) {
  const row = el("div", "row");
  const text = el("div", "row-text");
  text.appendChild(el("div", "row-name", name));
  text.appendChild(el("div", "row-note", note));
  row.appendChild(text);
  const side = el("div", "row-ctl");
  side.appendChild(control_);
  row.appendChild(side);
  return row;
}

function facts(pairs) {
  const list = el("dl", "facts");
  for (const [term, value] of pairs) {
    list.appendChild(el("dt", undefined, term));
    list.appendChild(el("dd", undefined, textOf(value)));
  }
  return list;
}

// ----- Autonomy (D65, U12) -----------------------------------------------------

async function choose(level) {
  const data = await write(AUTONOMY, { level });
  if (data === null) {
    return;
  }
  state.level = data.level;
  renderPanel();
}

function autonomyPanel() {
  const rows = el("div", "rows");
  for (const option of AUTONOMY_OPTIONS) {
    const pick = control("button", "opt", option.label);
    pick.setAttribute("aria-pressed", String(state.level === option.level));
    pick.onclick = () => choose(option.level);
    rows.appendChild(settingRow(option.label, option.note, pick));
  }
  return rows;
}

// ----- Discovery ----------------------------------------------------------------

// `fleet_summary` whitelists `app_state["discovery_status"]` into these, and an
// unread shape becomes the em dash there rather than here (F16).
function discoveryPanel() {
  const found = state.fleet === null ? null : state.fleet.discovery;
  const wrap = el("div", "src");

  const head = el("div", "src-head");
  const provider = el("div", "src-provider");
  const dot = el("span", "src-dot");
  dot.setAttribute("data-on", String(found !== null && found.hooks === "installed"));
  provider.appendChild(dot);
  provider.appendChild(el("span", undefined, "Claude Code hooks"));
  head.appendChild(provider);
  head.appendChild(el("span", "src-state", found === null ? UNKNOWN : found.hooks));
  wrap.appendChild(head);

  wrap.appendChild(
    facts([
      ["scan interval", found === null ? null : found.scan_interval_s],
      ["last scan", found === null ? null : found.last_scan_at],
      ["from the registry", found === null ? null : found.registry_sessions],
      ["reconciled", found === null ? null : found.sdk_cli_reconciled],
      ["missed", found === null ? null : found.sdk_cli_missed],
      ["unknown status", found === null ? null : found.unknown_status],
    ]),
  );
  return wrap;
}

// ----- Data: U6's tail, with D25's whitelist ------------------------------------

// An explicit field whitelist, at the sink (§13), unchanged by the move from
// `chat.js`. `args` are deliberately absent: the record carries them redacted
// for the *log*, and a page is a wider audience than a log.
function auditRow(record) {
  const row = el("div", "audit-row");
  row.appendChild(el("span", "audit-when", textOf(record.at)));
  row.appendChild(el("span", "audit-what", textOf(record.tool)));
  const allowed = record.decision === "allow";
  row.appendChild(
    el("span", allowed ? "audit-yes" : "audit-no", textOf(record.decision)),
  );
  row.appendChild(el("span", "audit-when", textOf(record.approved_by)));
  return row;
}

function dataPanel() {
  const wrap = el("div", "rows");
  const tail = el("div", "audit");
  if (state.audit === null) {
    tail.appendChild(el("div", "audit-row", UNKNOWN));
  }
  for (const record of state.audit === null ? [] : state.audit) {
    tail.appendChild(auditRow(record));
  }
  wrap.appendChild(tail);
  return wrap;
}

// ----- System -------------------------------------------------------------------

function systemPanel() {
  const found = state.fleet;
  return facts([
    ["server time", found === null ? null : found.now],
    ["sessions known", found === null ? null : found.session_count],
    ["unclassified stops", found === null ? null : found.unclassified],
  ]);
}

const PANELS = {
  autonomy: autonomyPanel,
  discovery: discoveryPanel,
  data: dataPanel,
  system: systemPanel,
};

// ----- the stream ---------------------------------------------------------------

// Settings is not a live page and says so: a gap on the stream means the
// numbers below may be behind, and the page states it rather than showing a
// figure it cannot vouch for. Nothing here re-reads — that would be polling
// driven by the stream, which is the same defect wearing a different hat.
export function onSettingsEvent(envelope) {
  if (envelope.type === GAP) {
    fill("settings-note", "the stream dropped events — these numbers may be behind");
  }
}

// ----- the first paint -----------------------------------------------------------

export async function loadSettings() {
  const [autonomy, audit, fleet] = await Promise.all([
    read(AUTONOMY),
    read(AUDIT),
    read(FLEET),
  ]);
  if (autonomy !== null) {
    state.level = autonomy.level;
  }
  if (audit !== null) {
    state.audit = audit.records;
  }
  if (fleet !== null) {
    state.fleet = fleet;
  }
  renderNav();
  renderPanel();
}

// The shell owns the navigation and calls this once.
export function mountSettings() {
  const view = slot("page-settings");
  const back = slot("settings-back");
  back.onclick = () => showList();
  renderNav();
  renderPanel();
  return view;
}
