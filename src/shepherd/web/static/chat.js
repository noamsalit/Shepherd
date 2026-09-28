// The **Shepherd** page: the orchestrator conversation (U6, U11, U12).
//
// **The module is still `chat.js` and that is deliberate.** The page was
// renamed from "chat" to "Shepherd"; the file was not. `chat.js` is the one
// static file created after the step-0b baseline and claimed by T24's rebase,
// so renaming it would make `moved_paths` report it un-moved while
// `regenerated_paths` still declares it — an equality with no repair available.
// A module filename is not a user-facing label.
//
// **What T7.1 removed from this page, and where each went.** Neither was
// deleted, and the tests assert the destination as well as the absence:
//
// * **D65 — the autonomy control is a Settings control and nothing else.**
//   §12 used to place it here, "visible at all times". The level is still
//   legible from behaviour — at the asking level you get cards, at the auto
//   level you do not — so what was lost is display, not information.
// * **U6 — the audit tail is in Settings → Data**, with D25's four-field
//   whitelist intact. Pending approvals stay *here*, inline at the blocked
//   turn, because that is where the decision belongs.
//
// Three rules this file keeps, each one the repo has already paid for:
//
// * **Nothing is on a timer.** §12 forbids polling: every read below is caused
//   by the first paint, by a click, or by an event that arrived on the one
//   stream. The approval card in particular is built from `approval.created`
//   as it arrives — a card discovered by asking again on a schedule would be a
//   card that appears late and a turn that stays blocked meanwhile. The rule
//   covers every timer and scheduler shape `test_no_polling_in_the_ui`
//   enumerates — they are not named here, because that scan reads comments too
//   and a rule stated by writing the forbidden token would fail it. The
//   composer grows and the thread scrolls inside the handler that caused them.
// * **Every value the master or a tool produced is untrusted text** (§13). The
//   nodes are built with `createElement` and filled with `textContent`; this
//   file has no HTML sink at all, which is what
//   `test_the_chat_page_has_no_html_sink` asserts with a negative control.
// * **The unknown is displayed** (principle 5). A datum nobody has read yet is
//   an em dash, never a guess, and a master event whose kind this build has
//   never seen is still rendered with its kind rather than dropped.

import { GAP } from "./sse.js";

// The API's public shape is the server's route table. Two paths, now that the
// other two left with the controls that used them.
const APPROVALS = "/api/approvals";
const MASTER_SEND = "/api/master/send";

// §12's event vocabulary on the one stream. `master.` is the prefix
// `orchestration/master_turn.py` publishes every `MasterEvent` kind under, so
// a kind this page was never written to expect still reaches the transcript.
const MASTER_PREFIX = "master.";
const APPROVAL_CREATED = "approval.created";
const APPROVAL_DECIDED = "approval.decided";

const UNKNOWN = "—";
const SHEPHERD = "Shepherd";

// The two words `decide_approval` accepts, with the label and the class each
// wears. A page that invented a third would get a `ToolArgumentRefused` the
// human could do nothing about.
const APPROVE = "approve";
const REJECT = "reject";
const CHOICES = [
  [APPROVE, "Approve", "btn btn-primary"],
  [REJECT, "Reject", "btn"],
];

// `.composer textarea` caps at `max-height: 9rem` in `app.css`; past that the
// textarea scrolls instead of growing. The number is the stylesheet's, in
// pixels at the 16px root the page never overrides.
const COMPOSER_MAX = 144;

// Enter sends, Shift+Enter is a newline — the shape every chat composer has, so
// a person who has used one does not have to be told.
const ENTER = "Enter";

// Principle 5: a gap on the stream means this transcript is missing something,
// and the page says so rather than showing a history that looks complete.
const GAP_NOTE = "the stream dropped events — this conversation is incomplete";

// `steps` is BC-06a's pairing: a call's step body and its turn, by the
// `tool_use_id` its result will name, until that result arrives or the turn
// ends. `lastText` is BC-06c's: the
// last thing each turn said, by turn id, so a final text equal to it is shown
// once. Both are keyed rather than "the latest", because a result or an ending
// that arrives for another turn must not be matched to this one.
const state = {
  approvals: [],
  steps: new Map(),
  lastText: new Map(),
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

// A `<button>` with no `type` inside a form submits it. Every control on this
// page goes through here so none can be missed.
function control(tag, className, text) {
  const element = el(tag, className, text);
  element.type = "button";
  return element;
}

//: A `fetch` that **rejected** rather than answered — `controld` stopped, the
//: socket refused. `await response.json()` below only ever runs on a resolved
//: response, so without this the rejection walks past every refusal path this
//: module has and the page silently does nothing (QA defect 2, the systemic
//: one: four of six modules had the same hole, and
//: `tests/web/test_frontend_unreachable_daemon.py` is now the gate over all of
//: them). This is the page where it is worst: a prompt that was typed, sent
//: nowhere, and not reported.
const UNREACHABLE =
  "The request did not reach the server — Shepherd may not be running.";

// Every body is `{ok, data, error, correlation_id}`, and §13 gives a failure
// the generic literal plus the id and nothing else.
async function read(path) {
  try {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    const body = await response.json();
    if (!body.ok) {
      fill("shepherd-status", `${body.error} (${body.correlation_id})`);
      return null;
    }
    return body.data;
  } catch (unreachable) {
    fill("shepherd-status", UNREACHABLE);
    return null;
  }
}

async function post(path, payload) {
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!body.ok) {
      fill("shepherd-status", `${body.error} (${body.correlation_id})`);
      return null;
    }
    return body.data;
  } catch (unreachable) {
    fill("shepherd-status", UNREACHABLE);
    return null;
  }
}

// ----- the conversation ------------------------------------------------------

function thread() {
  return slot("shepherd-thread");
}

// A turn that arrives below the fold is a turn nobody reads. This is caused by
// an append — never by a schedule — so it is here rather than on a timer.
function append(node) {
  thread().appendChild(node);
  const scroll = slot("shepherd-scroll");
  scroll.scrollTop = scroll.scrollHeight;
}

// What you said: a bubble, right-aligned, and nothing else. `.bubble` wraps an
// unbroken token, which is the difference between a pasted path and a
// conversation pane that scrolls sideways at 390px.
function youSays(text) {
  const turn = el("div", "turn turn-you");
  turn.appendChild(el("div", "bubble", text));
  append(turn);
}

// What Shepherd said: a byline and then verbatim prose. The byline is on the
// turn rather than on every paragraph, so a long answer reads as one voice.
function shepherdTurn() {
  const turn = el("div", "turn turn-shepherd");
  const byline = el("div", "byline");
  byline.appendChild(el("span", "byline-mark"));
  byline.appendChild(el("span", undefined, SHEPHERD));
  turn.appendChild(byline);
  return turn;
}

function shepherdSays(text) {
  const turn = shepherdTurn();
  turn.appendChild(el("p", "prose", text));
  append(turn);
}

// A tool step, folded. `<details>` is closed by default, which is the whole
// point: the conversation reads as prose and the mechanism is one click away.
// A step with nothing to show still renders — *that the master called a tool*
// is the fact, and a step that vanished when its detail was empty would be a
// call the transcript silently omitted. The body is returned, because the
// call's result lands inside it (BC-06a) rather than in a step of its own.
function shepherdStep(toolName, body) {
  const turn = shepherdTurn();
  const step = el("details", "step");
  const head = el("summary", undefined);
  head.appendChild(el("span", "step-chevron", "›"));
  head.appendChild(el("span", "step-tool", textOf(toolName)));
  head.appendChild(el("span", "step-time", UNKNOWN));
  step.appendChild(head);
  const content = el("div", "step-body", body);
  step.appendChild(content);
  turn.appendChild(step);
  append(turn);
  return content;
}

// What a step's body says, always a string (BC-06: `detail` is an object, and
// an object handed to `textContent` is `[object Object]`). A call names its
// argument **keys** and never their values — the same rule the approval card
// keeps for raw arguments, which are not redacted. Anything else with a tool
// name (a result) is its text, and says so when there was none.
const TOOL_CALL = "tool_call";
const TOOL_RESULT = "tool_result";
const NO_ARGUMENTS = "(no arguments)";
const NO_RESULT_TEXT = "(no result text)";

function argumentKeys(detail) {
  const input = detail !== null && typeof detail === "object" ? detail.input : undefined;
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return UNKNOWN;
  }
  const keys = Object.keys(input).sort();
  return keys.length === 0 ? NO_ARGUMENTS : `arguments: ${keys.join(", ")}`;
}

// A failed result says so on its own line (the SDK's `is_error`), because a
// step that reads like a success when the tool refused is a wrong transcript.
const FAILED = "error · ";

function stepBody(kind, data) {
  if (kind === TOOL_CALL) {
    return argumentKeys(data.detail);
  }
  const text = typeof data.text === "string" && data.text !== "" ? data.text : NO_RESULT_TEXT;
  return detailOf(data).is_error === true ? `${FAILED}${text}` : text;
}

// The runtime's own payload, which `project_to_stream` nests under `detail`.
// Anything that is not an object reads as empty, so a missing key is a missing
// datum (principle 5) and never a throw.
function detailOf(data) {
  const detail = data.detail;
  return detail !== null && typeof detail === "object" ? detail : {};
}

function useIdOf(data) {
  const useId = detailOf(data).tool_use_id;
  return typeof useId === "string" && useId !== "" ? useId : null;
}

// BC-06a (ruling 2): a call and its result are one step — the call is the
// title, the result is inside, under the call's argument keys. A result whose
// call this page never saw (it opened mid-turn, or the call had no id) is not
// dropped: it renders as a step of its own, titled with its tool name.
function fillStep(data) {
  const useId = useIdOf(data);
  if (useId === null || !state.steps.has(useId)) {
    return false;
  }
  state.steps.get(useId).content.append("\n", stepBody(TOOL_RESULT, data));
  state.steps.delete(useId);
  return true;
}

function openStep(kind, data) {
  const content = shepherdStep(data.tool_name, stepBody(kind, data));
  const useId = useIdOf(data);
  if (kind === TOOL_CALL && useId !== null) {
    state.steps.set(useId, { content, turnId: data.turn_id });
  }
}

// BC-06b (ruling 3): a turn's bookkeeping is not the conversation. It goes to
// the event line beside the status slot — never into the thread, and never
// over `#shepherd-status`, whose turn id, refusal or approval word a reader is
// looking at (plan revision 4, B1). The line is a polite live region, so it is
// announced without taking focus. BC-06c (ruling 4): every SDK ending carries
// the final text, which is normally the turn's last text again; it enters the
// thread only when it says something the turn has not. A turn that failed
// (`error`) still says so in the thread: its kind word stands in for a
// repeated text, so the failure is never only on the event line.
const TEXT = "text";
const TURN_ENDED = "turn_ended";
const ERROR = "error";
const RATE_LIMIT = "rate_limit";
const RATE_LIMIT_STOPS = "rejected";

// A result for a call whose turn is over is not this turn's any more.
function closeSteps(turnId) {
  for (const [useId, open] of state.steps) {
    if (open.turnId === turnId) {
      state.steps.delete(useId);
    }
  }
}

function newText(data, said) {
  return typeof data.text === "string" && data.text !== "" && data.text !== said ? data.text : null;
}

function turnEnded(kind, data) {
  const said = state.lastText.get(data.turn_id);
  state.lastText.delete(data.turn_id);
  closeSteps(data.turn_id);
  const failed = kind === ERROR;
  const outcome = failed ? ERROR : textOf(detailOf(data).outcome);
  fill("shepherd-event", `turn ended · ${outcome}`);
  const text = newText(data, said);
  if (text !== null || failed) {
    shepherdSays(text !== null ? text : ERROR);
  }
}

// RD-4: the SDK's `rejected` is the rate limit that stops the turn, and a turn
// that stopped is part of the conversation, so it is in the thread as well.
function rateLimited(data) {
  const limit = detailOf(data).rate_limit;
  const status = limit !== null && typeof limit === "object" ? limit.status : undefined;
  const line = `rate limit · ${textOf(status)}`;
  fill("shepherd-event", line);
  if (status === RATE_LIMIT_STOPS) {
    shepherdSays(line);
  }
}

function onMasterEvent(kind, data) {
  if (kind === TOOL_RESULT && fillStep(data)) {
    return;
  }
  if (typeof data.tool_name === "string" && data.tool_name !== "") {
    openStep(kind, data);
    return;
  }
  if (kind === TURN_ENDED || kind === ERROR) {
    turnEnded(kind, data);
    return;
  }
  if (kind === RATE_LIMIT) {
    rateLimited(data);
    return;
  }
  if (kind === TEXT && typeof data.text === "string") {
    state.lastText.set(data.turn_id, data.text);
  }
  shepherdSays(eventText(kind, data));
}

// One `MasterEvent` kind is one line. `text` is what the master said; anything
// with no text is announced by its own kind, because a class of output silently
// dropped is the defect `MASTER_EVENT_KINDS` is enumerated to prevent.
function eventText(kind, data) {
  if (typeof data.text === "string" && data.text !== "") {
    return data.text;
  }
  return kind;
}

// ----- U6's card, inline at the blocked turn ----------------------------------

// §12's card, and D25's whitelist at the sink: the tool, the summary
// `describe()` already redacted, and the deadline. The raw arguments are not
// here and must not be — they are not redacted and a card is a page.
function approvalCard(approval) {
  const card = el("div", "approval");
  card.dataset.approvalId = approval.approval_id;

  const head = el("div", "approval-head", "needs you");
  card.appendChild(head);

  card.appendChild(el("div", "approval-tool", textOf(approval.tool)));

  const meta = el("div", "approval-meta");
  meta.appendChild(el("span", undefined, textOf(approval.summary)));
  meta.appendChild(el("span", undefined, textOf(approval.deadline_at)));
  card.appendChild(meta);

  const acts = el("div", "approval-acts");
  for (const [choice, label, className] of CHOICES) {
    const button = control("button", className, label);
    button.onclick = () => decide(approval.approval_id, choice);
    acts.appendChild(button);
  }
  card.appendChild(acts);
  return card;
}

// The card, built from the **stream event's** own keys — the same four
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

// One card per approval (BC-26): the load read and the stream can both carry
// the same one. Compared by `dataset` rather than by a built selector, so an id
// is never interpreted as selector syntax.
function shown(approvalId) {
  if (state.approvals.some((known) => known.approval_id === approvalId)) {
    return true;
  }
  const cards = thread().querySelectorAll("[data-approval-id]");
  return [...cards].some((card) => card.dataset.approvalId === approvalId);
}

function without(approvals, approvalId) {
  return approvals.filter((approval) => approval.approval_id !== approvalId);
}

// A decided card keeps its place in the transcript and loses its buttons: the
// turn it blocked is still readable, and the outcome is beside it. Replacing
// the whole card would delete the reason the turn stopped.
function settle(approvalId, outcome) {
  const cards = thread().querySelectorAll("[data-approval-id]");
  for (const card of cards) {
    if (card.dataset.approvalId !== approvalId) {
      continue;
    }
    const acts = card.querySelector(".approval-acts");
    if (acts !== null) {
      acts.replaceChildren(el("span", "decided", textOf(outcome)));
    }
  }
}

async function decide(approvalId, choice) {
  const data = await post(`${APPROVALS}/${encodeURIComponent(approvalId)}`, { choice });
  if (data === null) {
    return;
  }
  // The compare-and-set loser is told it lost (E-M4-1): a second click, or a
  // click that raced the deadline, did not decide anything and says so.
  fill("shepherd-status", data.decided ? data.outcome : "already decided");
}

// ----- the composer ----------------------------------------------------------

// U6's growing composer. `auto` first, because a textarea's `scrollHeight` never
// shrinks while an explicit height is still set — measuring without the reset
// grows monotonically and never comes back down when the text is deleted.
function grow(input) {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, COMPOSER_MAX)}px`;
}

// BC-25: an Enter that commits an IME composition is the input method's, not a
// send — posting then would send half-composed text.
function onComposerKey(event) {
  if (event.isComposing) {
    return;
  }
  if (event.key === ENTER && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
}

async function submit() {
  const input = slot("shepherd-input");
  const text = input.value;
  // BC-25: nothing to say is not a turn. The check is trimmed, the text is not —
  // a multi-line message posts exactly as typed.
  if (text.trim() === "") {
    return;
  }
  input.value = "";
  grow(input);
  youSays(text);
  // The last turn's ending is not this turn's. Cleared before the POST, since a
  // fast turn's own ending can arrive on the stream before the POST answers.
  fill("shepherd-event", "");
  const data = await post(MASTER_SEND, { text });
  if (data === null) {
    return;
  }
  // RD7: a refused turn is a **result**, not an error — one turn at a time, and
  // the reason is readable.
  fill("shepherd-status", data.started ? data.turn_id : data.reason);
}

// ----- the stream ------------------------------------------------------------

// The whole page after the first paint. Nothing here asks again: an approval
// card exists because `approval.created` arrived, and it is settled because
// `approval.decided` did.
export function onShepherdEvent(envelope) {
  const data = envelope.data;
  if (envelope.type === GAP) {
    shepherdSays(GAP_NOTE);
    return;
  }
  if (envelope.type.startsWith(MASTER_PREFIX)) {
    onMasterEvent(envelope.type.slice(MASTER_PREFIX.length), data);
    return;
  }
  if (envelope.type === APPROVAL_CREATED) {
    const raised = cardFrom(data);
    // BC-26: the first-paint read may already have painted this card.
    if (shown(raised.approval_id)) {
      return;
    }
    state.approvals = [...state.approvals, raised];
    // U6: the card appears inline in the conversation at the blocked turn, and
    // nowhere else — the rail is gone and U2 keeps it gone.
    append(approvalCard(raised));
    return;
  }
  if (envelope.type === APPROVAL_DECIDED) {
    state.approvals = without(state.approvals, data.approval_id);
    settle(data.approval_id, data.outcome);
  }
}

// ----- the first paint -------------------------------------------------------

// A card raised before this page was opened has no event left to arrive, so the
// undecided list is read exactly once, here. A second read site is how a
// stream-fed conversation quietly becomes a polled one.
export async function loadShepherd() {
  const approvals = await read(APPROVALS);
  if (approvals === null) {
    return;
  }
  // BC-26: an `approval.created` that arrived while this read was in flight
  // already painted its card; the read must not paint it a second time.
  const unseen = approvals.approvals.filter((approval) => !shown(approval.approval_id));
  state.approvals = approvals.approvals;
  for (const approval of unseen) {
    append(approvalCard(approval));
  }
}

// The shell owns the navigation and calls this once; the listeners are wired
// here because the elements are this page's.
export function mountShepherd() {
  const view = slot("page-shepherd");
  const input = slot("shepherd-input");
  const send = slot("shepherd-send");
  input.oninput = () => grow(input);
  input.onkeydown = (event) => onComposerKey(event);
  send.onclick = () => submit();
  return view;
}
