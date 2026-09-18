// §12's page 1: the conversation, the live sidebar, the approval card, the
// autonomy toggle — built from mechanisms `web/` already has (ADR-M4-7).
//
// Three rules this file keeps, each of them a rule the repo has already paid
// for somewhere else:
//
// * **Nothing is on a timer.** §12 forbids polling: every read below is caused
//   by the first paint, by a click, or by an event that arrived on the one
//   stream. The approval card in particular is built from `approval.created`
//   as it arrives — a card discovered by asking again on a schedule would be a
//   card that appears late and a turn that stays blocked meanwhile.
// * **Every value the master or a tool produced is untrusted text** (§13). The
//   markup is static and the slots are filled with `textContent`; this file has
//   no HTML sink at all, which is what `test_the_chat_page_has_no_html_sink`
//   asserts with a negative control beside it.
// * **The unknown is displayed** (principle 5). A level nobody has read yet is
//   an em dash, never a guessed `2`, and a master event whose kind this build
//   has never seen is still rendered with its kind rather than dropped.

import { GAP } from "./sse.js";

// The API's public shape is the server's route table; these are the five paths
// T24 added to it and nothing else.
const APPROVALS = "/api/approvals";
const AUDIT = "/api/audit";
const AUTONOMY = "/api/autonomy";
const MASTER_SEND = "/api/master/send";

// §12's event vocabulary on the one stream. `master.` is the prefix
// `orchestration/master_turn.py` publishes every `MasterEvent` kind under, so
// a kind this page was never written to expect still reaches the transcript.
const MASTER_PREFIX = "master.";
const APPROVAL_CREATED = "approval.created";
const APPROVAL_DECIDED = "approval.decided";

const UNKNOWN = "—";
const YOU = "you";
const SHEPHERD = "shepherd";

// The two words `decide_approval` accepts. A page that invented a third would
// get a `ToolArgumentRefused` the human could do nothing about.
const APPROVE = "approve";
const REJECT = "reject";

// D8's two levels, as `set_autonomy_level` enumerates them. The toggle offers
// the level you are not on, so there is one control and no state to remember.
const LEVELS = [2, 3];

// Principle 5, again: a gap on the stream means this transcript is missing
// something, and the page says so rather than showing a history that looks
// complete.
const GAP_NOTE = "the stream dropped events — this conversation is incomplete";

const state = {
  level: null,
  approvals: [],
};

function slot(id) {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`no slot ${id}`);
  }
  return element;
}

// Principle 5's em dash, in one place. Every slot on this page goes through it,
// so "the datum is missing" renders the same way everywhere and a render can
// never be a bare `undefined` on the screen.
function textOf(value) {
  return value === null || value === undefined ? UNKNOWN : String(value);
}

function fill(id, value) {
  const element = slot(id);
  element.textContent = textOf(value);
}

function clear(element) {
  element.replaceChildren();
}

function line(className, text) {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text;
  return element;
}

// Every body is `{ok, data, error, correlation_id}`, and §13 gives a failure
// the generic literal plus the id and nothing else.
async function read(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await response.json();
  if (!body.ok) {
    fill("chat-status", `${body.error} (${body.correlation_id})`);
    return null;
  }
  return body.data;
}

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!body.ok) {
    fill("chat-status", `${body.error} (${body.correlation_id})`);
    return null;
  }
  return body.data;
}

// ----- the conversation ------------------------------------------------------

// One `MasterEvent` kind is one line. `text` is what the master said; a
// `tool_call` has no text and names a tool instead; anything else is announced
// by its own kind, because a class of output silently dropped is the defect
// `MASTER_EVENT_KINDS` is enumerated to prevent.
function eventText(kind, data) {
  if (typeof data.text === "string" && data.text !== "") {
    return data.text;
  }
  if (typeof data.tool_name === "string" && data.tool_name !== "") {
    return `${kind}: ${data.tool_name}`;
  }
  return kind;
}

function say(who, text) {
  const log = slot("chat-log");
  log.appendChild(line(`chat-line chat-${who}`, `${who}: ${text}`));
}

// ----- the approval rail -----------------------------------------------------

// §12's card, and D25's whitelist at the sink: the tool, the summary
// `describe()` already redacted, and the deadline. The raw arguments are not
// here and must not be — they are not redacted and a card is a page.
function approvalCard(approval) {
  const card = document.createElement("div");
  card.className = "approval-card";
  card.dataset.approvalId = approval.approval_id;

  const tool = document.createElement("p");
  tool.className = "approval-tool";
  tool.textContent = textOf(approval.tool);
  card.appendChild(tool);

  const summary = document.createElement("p");
  summary.className = "approval-summary";
  summary.textContent = textOf(approval.summary);
  card.appendChild(summary);

  const deadline = document.createElement("p");
  deadline.className = "approval-deadline";
  deadline.textContent = textOf(approval.deadline_at);
  card.appendChild(deadline);

  for (const choice of [APPROVE, REJECT]) {
    const button = document.createElement("button");
    button.className = `approval-choice approval-${choice}`;
    button.type = "button";
    button.textContent = choice;
    button.onclick = () => decide(approval.approval_id, choice);
    card.appendChild(button);
  }
  return card;
}

// The rail row, built from the **stream event's** own keys — the same four
// `list_approvals` projects, because the two producers describe one card and a
// page that read a fifth from either would be reading a field nobody emits
// (M3's `action.label`).
function cardFrom(data) {
  return {
    approval_id: data.approval_id,
    tool: data.tool,
    summary: data.summary,
    deadline_at: data.deadline_at,
  };
}

function without(approvals, approvalId) {
  return approvals.filter((approval) => approval.approval_id !== approvalId);
}

function renderApprovals() {
  const rail = slot("chat-approvals");
  clear(rail);
  for (const approval of state.approvals) {
    rail.appendChild(approvalCard(approval));
  }
  fill("chat-approval-count", state.approvals.length);
}

async function decide(approvalId, choice) {
  const data = await post(`${APPROVALS}/${encodeURIComponent(approvalId)}`, { choice });
  if (data === null) {
    return;
  }
  // The compare-and-set loser is told it lost (E-M4-1): a second click, or a
  // click that raced the deadline, did not decide anything and says so.
  fill("chat-status", data.decided ? `${data.outcome}` : "already decided");
  // A decision writes an audit record; re-reading the tail is a response to the
  // click, not a schedule.
  await loadAudit();
}

// ----- D8's toggle -----------------------------------------------------------

function renderAutonomy() {
  fill("chat-autonomy-level", state.level);
  const next = slot("chat-autonomy-next");
  next.textContent = state.level === null ? UNKNOWN : String(otherLevel(state.level));
  next.disabled = state.level === null;
}

function otherLevel(level) {
  return level === LEVELS[0] ? LEVELS[1] : LEVELS[0];
}

async function toggleAutonomy() {
  if (state.level === null) {
    return;
  }
  const data = await post(AUTONOMY, { level: otherLevel(state.level) });
  if (data === null) {
    return;
  }
  state.level = data.level;
  renderAutonomy();
}

// ----- D25's literal tail ----------------------------------------------------

// An explicit field whitelist, at the sink (§13). `args` are deliberately
// absent: the record carries them redacted for the *log*, and a page is a
// wider audience than a log.
function auditLine(record) {
  const at = textOf(record.at);
  const tool = textOf(record.tool);
  const decision = textOf(record.decision);
  const by = textOf(record.approved_by);
  return `${at}  ${tool}  ${decision}  ${by}`;
}

async function loadAudit() {
  const data = await read(AUDIT);
  if (data === null) {
    return;
  }
  const tail = slot("chat-audit");
  clear(tail);
  for (const record of data.records) {
    tail.appendChild(line("audit-line", auditLine(record)));
  }
}

// ----- the composer ----------------------------------------------------------

async function send() {
  const input = slot("chat-input");
  const text = input.value;
  if (text === "") {
    return;
  }
  input.value = "";
  say(YOU, text);
  const data = await post(MASTER_SEND, { text });
  if (data === null) {
    return;
  }
  // RD7: a refused turn is a **result**, not an error — one turn at a time, and
  // the reason is readable.
  fill("chat-status", data.started ? data.turn_id : data.reason);
}

// ----- the stream ------------------------------------------------------------

// The whole page after the first paint. Nothing here asks again: an approval
// card exists because `approval.created` arrived, and it goes away because
// `approval.decided` did.
export function onChatEvent(envelope) {
  const data = envelope.data;
  if (envelope.type === GAP) {
    say(SHEPHERD, GAP_NOTE);
    return;
  }
  if (envelope.type.startsWith(MASTER_PREFIX)) {
    say(SHEPHERD, eventText(envelope.type.slice(MASTER_PREFIX.length), data));
    return;
  }
  if (envelope.type === APPROVAL_CREATED) {
    const raised = cardFrom(data);
    state.approvals = [...state.approvals, raised];
    renderApprovals();
    // §12: the card appears in the sidebar **and** inline in the chat at the
    // blocked turn.
    slot("chat-log").appendChild(approvalCard(raised));
    return;
  }
  if (envelope.type === APPROVAL_DECIDED) {
    state.approvals = without(state.approvals, data.approval_id);
    renderApprovals();
  }
}

// ----- the first paint -------------------------------------------------------

export async function loadChat() {
  const [approvals, autonomy] = await Promise.all([read(APPROVALS), read(AUTONOMY)]);
  if (approvals !== null) {
    state.approvals = approvals.approvals;
  }
  if (autonomy !== null) {
    state.level = autonomy.level;
  }
  renderApprovals();
  renderAutonomy();
  await loadAudit();
}

// `app.js` owns the navigation and calls this once; the listeners are wired
// here because the elements are this page's.
export function mountChat() {
  const view = slot("chat-view");
  const sendButton = slot("chat-send");
  const toggle = slot("chat-autonomy-next");
  view.hidden = false;
  sendButton.onclick = () => send();
  toggle.onclick = () => toggleAutonomy();
  return view;
}

export function hideChat() {
  const view = slot("chat-view");
  view.hidden = true;
  return view;
}
