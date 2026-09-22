// **D67: this is the Flock's third pane, not a fourth page.** §12's page 3, the
// part that is not the terminal: the header band, D21's `next_actions[]`, the
// rename affordance and the `local only` marker.
//
// The view **relocated**; it was not deleted. `terminal.js` and the vendored
// emulator stay reachable from here, and the module's contracts are unchanged.
// What moved *in* is the stopped-row logic that used to live in `fleet.js`:
// U7 fixes the session card at four items — glyph and colour, title, the ask,
// relative time — so D21's list has nowhere on the card to be, and §12 always
// said it renders in the Session view header. Every rule the list carried moved
// with it rather than being quietly dropped: RD6's labelled-and-inert kinds,
// N10's honest `[why?]`, §14's `nothing to do` and G-M2-7's targetless
// `external`. A relocation that loses the rules is a deletion with a better
// name.
//
// Every value below lands in a slot with `textContent`. There is no HTML sink in
// this file and no string concatenated into markup: §13's rule has no exception
// to make on a page whose fields are a title a human typed, a `why` a classifier
// wrote and a session id.
//
// The order is the server's (§16, `fleet_sort_key`) and `next_actions[]` arrives
// already ordered from `project_action`. Nothing here sorts, and
// `test_the_page_does_not_re_derive_the_order` is what keeps it that way.
//
// `renderSession` is reached from `app.js`, which listens for a click on a fleet
// row. That edge is the whole reason this module runs at all: for one task
// nothing imported it, and eight tests asserting its contents all passed against
// code no browser ever loaded (`test_session_wiring.py`).

import { element, showLevel } from "./flock.js";
import { openTerminal, INPUT_UNAVAILABLE } from "./terminal.js";

// §9, verbatim. An `attached` session has no pty of ours: it was started in the
// user's own terminal, on the user's own tmux socket. Rendering a live terminal
// for one would be offering a write path into a pane K6 says we never touch —
// so the banner is a refusal, not a decoration.
const READ_ONLY_BANNER =
  "read-only — this session wasn't started here. Open it in the platform to get a terminal.";

// D29/RD9: exactly §12's words. "local only" is the difference between a
// degrade and a lie, and the string is what a reviewer greps for when DP1 is
// decided.
const LOCAL_ONLY_MARKER = "local only";

// Principle 5, and `flock.js` says the same word for the same reason: a field
// the payload did not carry is *shown* as unknown, never rendered as a blank
// button nobody can read and nobody counted.
const UNKNOWN = "unknown";

// D29's local rename. The engine write-back (`drive_engine_rename`) ships
// **disabled** by plan decision DP1 — the ceiling is `can_set_title`, it is
// `False`, and the decision lives server-side in `orchestration/rename.py`.
// Nothing here can flip it, and the `local only` marker above is exactly what
// tells the human which half happened.
const RENAME_PATH = "/api/sessions/{session_id}/rename";
const RENAME_FAILED = "rename failed";
const RENAME_UNREACHABLE = "rename failed: the request did not reach the server";

// D29, and `store/models.py:238` states the same rule on the column itself:
// `title_synced_at` is stamped only from a read-back of the engine's own
// `nameSource:"user"`, so a user title with no stamp is a rename that never
// left this machine. It is a **conjunction**: under `||` the marker would light
// for every unsynced row, including one the engine itself titled, which is a
// false claim about where a name came from rather than an honest degrade.
//
// Blocker T19-b: `project_session` carries neither field today, so this returns
// `false` for every row the API currently serves. The rule is written where it
// belongs rather than guessed at from a field that does not exist — and the
// rename response *does* carry `local_only`, so `applyRename` below can light
// the marker for real.
export function localOnly(row) {
  return row.title_source === "user" && !row.title_synced_at;
}

// The terminal currently on the page. A second `renderSession` with the first
// socket still open would hold a `pipe-pane` alive for the life of the tab,
// which is the thing `close()` exists to prevent.
let attached = null;

function slot(id) {
  return document.getElementById(id);
}

function fill(id, value) {
  // Named `node`, not `element`: the shared node helper is imported under that
  // name above, and a local binding that shadowed it would make every later
  // `element(...)` in this file a call on a DOM node instead.
  const node = slot(id);
  node.textContent = value === null || value === undefined ? "—" : String(value);
  return node;
}

function path(template, sessionId) {
  return template.replace("{session_id}", encodeURIComponent(sessionId));
}

// `project_action` (`toolsurface/tools_m1.py`) emits exactly `text`, `kind`,
// `target` and `source`. This page read `action.label` — a field that exists
// nowhere in the projection layer — so D21's buttons rendered empty and, with
// no fallback, nothing counted the unknown either. `flock.js` reads the same
// payload the same way, which is the point: one payload, one reading.
function actionText(action) {
  return typeof action.text === "string" && action.text !== "" ? action.text : UNKNOWN;
}

function actionKind(action) {
  return typeof action.kind === "string" && action.kind !== "" ? action.kind : UNKNOWN;
}

// N10 / D34. The model verdict lane is **not built** at M2, so `[why?]` expands
// the heuristic evidence and says so in words. A control that implied a verdict
// nobody computed would be worse than no control at all.
const MODEL_LANE_NOTE =
  "Heuristic evidence only — the model verdict lane is not built in this build, so no model looked at this stop.";

// RD6: an action whose capability lands later renders **labelled and inert**,
// with the milestone named. §12 says the row is never a dead end, and an
// unlabelled dead button *is* the dead end. This table arrived with the list
// when D67 moved it off the card; it is not new and it is not optional.
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

// Why an action cannot be honoured today, or `null` when it can be. The two
// cases are different facts and say so: a kind this build knows but has not
// built yet names its milestone (RD6), and a kind from a newer build names its
// own unfamiliarity. Neither is ever a silently clickable button.
function notYetReason(kind) {
  const milestone = ACTION_MILESTONE[kind];
  if (milestone !== undefined) {
    return `not yet — ${kind} lands at ${milestone}`;
  }
  if (!(kind in LIVE_KINDS)) {
    return `not yet — this build does not know the action kind ${kind}`;
  }
  return null;
}

function actionButton(action) {
  const kind = actionKind(action);
  const text = actionText(action);

  // §12's `[↗]`. A link needs nothing of ours, so it is live at M2 — but only
  // when there is somewhere to go: G-M2-7's `Chase — what it is waiting on is
  // not recorded` has no url, and must not pretend to one.
  if (kind === "external" && typeof action.target === "string" && action.target !== "") {
    const link = element("a", "session-action action-link", `${text} ↗`);
    link.href = action.target;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  // One inert path, two reasons. Writing `disabled` in each branch would be the
  // same render performed twice, and `test_render_session_performs_every_
  // assignment_the_spec_requires` refuses a duplicated render precisely because
  // a second copy is where the two eventually stop agreeing.
  const reason = notYetReason(kind);
  const button = element(
    "button",
    reason === null ? "session-action" : "session-action action-not-yet",
    text,
  );
  button.type = "button";
  button.dataset.kind = kind;
  if (reason !== null) {
    button.disabled = true;
    button.title = reason;
    button.appendChild(element("span", "action-badge", "not yet"));
  }
  return button;
}

// D21's list, in the pane's header — **every** action, with its ordinal and the
// source it came from. The collapsed fleet row rendered `actions[0]` because it
// had space for one; the pane has space for the list, which is the property the
// redesign keeps and the retired card test could not.
//
// Nothing here sorts: `next_actions[]` arrives already ordered from
// `project_action`, and the order is `default_actions`' own.
function actionList(row) {
  const list = element("ol", "session-actions-list");
  const actions = Array.isArray(row.next_actions) ? row.next_actions : [];
  if (actions.length === 0) {
    // §14: an empty list is only ever a *confident* `completed`. Anything else
    // with no actions is a rule bug, and the classifier's own tests say so.
    list.appendChild(element("li", "session-no-action", "nothing to do"));
    return list;
  }
  actions.forEach((action, index) => {
    const item = element("li", "session-action-row");
    item.appendChild(element("span", "action-ordinal", `${index + 1}`));
    item.appendChild(actionButton(action));
    item.appendChild(element("span", "action-source", action.source || UNKNOWN));
    list.appendChild(item);
  });
  return list;
}

// N10's `[why?]`: a native disclosure, never a button. It expands the evidence
// the row already carries and names the lane that did not look at this stop.
// Nothing here opens a log, a transcript or a second endpoint (K14/D25).
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

// D29's marker, after a rename that has been answered. `local_only` is the
// server's own verdict (`toolsurface/tools_rename.py::project_rename`), not a
// re-derivation: the page renders the answer it was given.
function applyRename(data) {
  fill("session-title", data.title);
  const marker = slot("session-local-only");
  marker.textContent = data.local_only ? LOCAL_ONLY_MARKER : "";
  marker.hidden = !data.local_only;
}

async function commitRename(row, title) {
  const status = slot("session-rename-status");
  status.textContent = "";
  try {
    const response = await fetch(path(RENAME_PATH, row.session_id), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ title: title }),
    });
    const body = await response.json();
    if (!body.ok) {
      status.textContent = `${RENAME_FAILED}: ${body.error} (${body.correlation_id})`;
      return;
    }
    if (!body.data.renamed) {
      // `project_rename` answers `renamed: false` with a `reason` — a session
      // that is not there. Principle 5: the reason is shown, not swallowed.
      status.textContent = `${RENAME_FAILED}: ${body.data.reason}`;
      return;
    }
    applyRename(body.data);
  } catch (unreachable) {
    status.textContent = RENAME_UNREACHABLE;
  }
}

// D29's click-to-edit. The affordance has been in `index.html` since T19 and
// nothing wired it; `POST /api/sessions/{id}/rename` has been in the route
// table since T18.
function beginRename(row) {
  const input = document.createElement("input");
  input.className = "session-rename-input";
  input.type = "text";
  input.value = row.title === null || row.title === undefined ? "" : String(row.title);
  slot("session-title").replaceChildren(input);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      commitRename(row, input.value);
    }
    if (event.key === "Escape") {
      fill("session-title", row.title);
    }
  });
  input.focus();
}

function closeAttached() {
  if (attached === null) {
    return;
  }
  const closing = attached;
  attached = null;
  closing.then((handle) => handle.close());
}

// `renderSession(row)` — one session projection in, page 3 out. The row is
// whatever `/api/sessions/{id}` handed back; this function reads it and never
// asks a second source, so the page cannot show two different answers.
export function renderSession(row) {
  closeAttached();

  // The section ships `hidden` in static markup — an empty terminal frame on
  // the fleet page would be a pane nobody asked for — so opening the page is
  // this line, and for one task nothing in the tree contained it.
  const view = slot("session-view");
  view.hidden = false;
  // D67: opening a session walks the Flock's drill-down to its third level. On
  // a wide screen all three columns are up already and this changes nothing; on
  // a phone it is the navigation. `app.css` owns what the level reveals, and
  // `flock.js` owns the attribute — this module only says which level it is.
  showLevel("detail");

  showing = row.session_id;

  fill("session-title", row.title);
  fill("session-chip", row.bucket);
  fill("session-state", row.state);
  fill("session-ownership", row.ownership);
  fill("session-model", row.model);

  const rename = slot("session-rename");
  rename.onclick = () => beginRename(row);
  fill("session-rename-status", "");

  // The stopped band (D21): the bucket, the `why`, and `next_actions[]` as an
  // ordered list. `why` is null on a session nobody classified, which renders as
  // the em dash `fill` uses everywhere — an unknown shown, not hidden
  // (principle 5) — with the honest `[why?]` disclosure beside it.
  fill("session-why", row.why);
  slot("session-actions").replaceChildren(actionList(row), whyNote(row));

  // U17's card. Not awaited: the terminal below is what this function returns,
  // and a card that waited on the network would hold the pane's whole render
  // behind one read of a pane.
  renderDecision(row);

  const marker = slot("session-local-only");
  marker.textContent = localOnly(row) ? LOCAL_ONLY_MARKER : "";
  marker.hidden = !localOnly(row);

  const banner = slot("session-banner");
  const terminal = slot("session-terminal");
  const note = slot("session-input-note");
  if (row.ownership === "attached") {
    banner.textContent = READ_ONLY_BANNER;
    banner.hidden = false;
    terminal.replaceChildren();
    terminal.hidden = true;
    note.textContent = "";
    return null;
  }

  banner.textContent = "";
  banner.hidden = true;
  terminal.hidden = false;
  note.textContent = INPUT_UNAVAILABLE;
  attached = openTerminal(row.session_id, terminal);
  return attached;
}

// ---- U17's decision card ----------------------------------------------------
//
// **The engine's own prompt, with its numbered choices, verbatim** (U11). Not
// flattened to approve/reject: choice 2 of the captured permission dialog is
// *"Yes, and always allow access to /tmp/… from this project"* — it carries the
// **scope**, it is usually the one you want, and a flattened card cannot reach
// it at all.
//
// Nothing here parses a screen. `read_decision` (`runner/pane.py`) is a pure
// function over a real capture and the route is a read; this module renders the
// answer it was given, and `textContent` is the only sink it uses.
//
// Three degradations, and they are the point rather than the edges:
//
//  1. an **attached** session renders read-only and says so — we have no pty of
//     theirs, and three buttons that go nowhere is worse than one sentence;
//  2. anything the parser could not read degrades to the ask **verbatim** plus
//     the two universal options, labelled and inert, and says it could not read
//     the choices. It never invents the engine's list;
//  3. `trust_dialog` is named, and the card says in words that Enter there
//     answers *"No, exit"*. `read_decision` reports the cursor and refuses to
//     interpret it; this file does not interpret it either.
const DECISION_PATH = "/api/sessions/{session_id}/decision";

// U11's own word for the bucket that owes a card. Keyed on the bucket the
// server derived — never re-derived here — so an idle session gets no card and
// no pane read at all (E20).
const NEEDS_YOU = "needs_you";

// The trust screen, by the name the projection carries (`PaneKind.value`). It
// is matched by name rather than by anything on the screen, because the whole
// C15 lesson is that this dialog *looks* like the other one.
const TRUST_DIALOG = "trust_dialog";

const DECISION_READ_ONLY =
  "read-only — this session wasn't started here, so Shepherd has no pane to answer on. Answer it in the terminal it was started in.";

const DECISION_UNREADABLE =
  "could not read the choices on this screen — the ask above is what the pane says, verbatim. Nothing here is guessed.";

const TRUST_WARNING =
  'workspace trust — Enter on this screen answers "No, exit" and ends the session. The cursor is reported, never interpreted.';

// RD6's shape, for a capability that is not built: labelled and inert, with the
// reason in words. `POST /api/sessions/{id}/permission` exists in the route
// table and nothing on any page calls it; a card that pretended otherwise would
// be the silent dead button one file over already refuses to ship.
const DECISION_INERT =
  "answering from Shepherd is not built in this build — press the option in the session's own terminal.";

// The two options every dialog has whatever else is on it. They are rendered
// **without numbers**, because a number is a key the engine drew and these are
// not: sending `1` for an unparsed screen is positional, and positional is how
// a digit reaches a tool nobody approved.
const UNIVERSAL_CHOICES = [
  { number: null, label: "approve", selected: false },
  { number: null, label: "reject", selected: false },
];

const CURSOR_NOTE = "the cursor is on this line";
const NO_DIALOG = "this session is waiting on you, but its pane is not showing a dialog right now.";
const DECISION_FAILED = "could not read the decision";
const DECISION_UNREACHABLE = "could not read the decision: the request did not reach the server";

// The session whose card is on the page. A second `renderSession` while a fetch
// is in flight would otherwise paint the first session's dialog into the second
// session's pane — and a decision card showing the wrong session's ask is the
// worst kind of wrong this page can be.
let showing = null;

function choiceRow(choice) {
  const row = element("li", "choice choice-inert");
  if (choice.selected) {
    row.classList.add("choice-1");
  }
  const number = choice.number === null || choice.number === undefined;
  row.appendChild(element("span", "choice-n", number ? "·" : String(choice.number)));
  const label = element("span", "choice-text", choice.label);
  if (choice.selected) {
    label.appendChild(element("span", "choice-note", CURSOR_NOTE));
  }
  row.appendChild(label);
  return row;
}

function decisionNote(text) {
  return element("p", "decision-readonly", text);
}

function decisionCard(data) {
  const card = element("section", "decision");
  const head = element("div", "decision-head", "needs you");
  head.appendChild(element("span", "decision-src", data.pane_kind || UNKNOWN));
  card.appendChild(head);

  const ask = element("div", "decision-ask");
  ask.appendChild(element("pre", "decision-body", data.text === null ? UNKNOWN : data.text));
  card.appendChild(ask);

  if (data.pane_kind === TRUST_DIALOG) {
    card.appendChild(decisionNote(TRUST_WARNING));
  }

  const list = element("ul", "choices");
  const choices = data.readable && Array.isArray(data.choices) ? data.choices : UNIVERSAL_CHOICES;
  choices.forEach((choice) => list.appendChild(choiceRow(choice)));
  card.appendChild(list);
  if (!data.readable) {
    card.appendChild(decisionNote(DECISION_UNREADABLE));
  }
  card.appendChild(decisionNote(DECISION_INERT));
  return card;
}

// E18. Built from the row's own `ownership`, the same field the terminal branch
// reads, rather than from the absence of a payload: "we have no pane of theirs"
// is a fact about the session, and asking the server for one we know is not
// there would turn it into a failure message.
function readOnlyCard(row) {
  const card = element("section", "decision");
  const head = element("div", "decision-head", "needs you");
  head.appendChild(element("span", "decision-src", row.ownership || UNKNOWN));
  card.appendChild(head);
  card.appendChild(element("pre", "decision-body", row.needs_you_reason || UNKNOWN));
  card.appendChild(decisionNote(DECISION_READ_ONLY));
  return card;
}

async function renderDecision(row) {
  const host = slot("session-decision");
  host.replaceChildren();
  host.hidden = true;
  if (row.bucket !== NEEDS_YOU) {
    return null;
  }
  host.hidden = false;
  if (row.ownership === "attached") {
    host.replaceChildren(readOnlyCard(row));
    return null;
  }
  try {
    const response = await fetch(path(DECISION_PATH, row.session_id), {
      headers: { Accept: "application/json" },
    });
    const body = await response.json();
    if (showing !== row.session_id) {
      return null;
    }
    if (!body.ok) {
      host.replaceChildren(decisionNote(`${DECISION_FAILED}: ${body.error} (${body.correlation_id})`));
      return null;
    }
    if (!body.data.ok) {
      host.replaceChildren(decisionNote(body.data.reason));
      return null;
    }
    if (!body.data.asking) {
      host.replaceChildren(decisionNote(NO_DIALOG));
      return null;
    }
    host.replaceChildren(decisionCard(body.data));
  } catch (unreachable) {
    if (showing === row.session_id) {
      host.replaceChildren(decisionNote(DECISION_UNREACHABLE));
    }
  }
  return null;
}
