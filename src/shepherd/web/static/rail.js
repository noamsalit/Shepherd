// §12's Needs-You rail: the one element that is on **every page**, and is never
// a page you navigate to.
//
// It renders the `needs_you` list `fleet_summary` already returns and **composes
// nothing**. The ask in each row is `needs_you_reason`, which the normaliser
// wrote at the moment the session blocked — `payments-api · permission: Bash(…)`.
// A rail that summarises the ask into a category ("this one wants something")
// is a rail you have to open a session to act on, which is the thing this
// element exists to avoid — and the scan in `tests/web/test_rail.py` fails the
// build on that wording appearing anywhere in this file, comments included.
//
// **C21 is surfaced here, not softened.** `idle_prompt` flips an idle TUI to
// `needs_you` 60 s after a `Stop`, so idle sessions *will* appear in this rail
// on a real machine. The wording `idle — waiting for your next instruction` is
// the difference between a rail that is wrong and a rail that is precise.
//
// No timer, no fetch, no stream of its own (§12: no polling anywhere in the UI).
// The rail is redrawn by the same render pass an arriving event drives.
//
// M4 adds approvals and, behind a user setting, a notification on the empty ->
// non-empty transition (RD9). The transition has an obvious place: it is the
// branch below, and nothing else in this module would have to move.

import { element } from "./fleet.js";

// Principle 5: a session can block without the reason ever being recorded — a
// lost hook, a build older than the normaliser. The row still renders, and it
// says that the ask is missing rather than inventing one or leaving a blank.
const RAIL_UNKNOWN_ASK = "waiting on you — the ask was not recorded";

function askOf(row) {
  const reason = row.needs_you_reason;
  return typeof reason === "string" && reason.trim() !== "" ? reason : RAIL_UNKNOWN_ASK;
}

function titleOf(row) {
  const title = row.title;
  if (typeof title === "string" && title.trim() !== "") {
    return title;
  }
  const workspace = row.workspace_name;
  return typeof workspace === "string" && workspace.trim() !== "" ? workspace : "untitled";
}

export function renderRail(summary, slot) {
  slot.replaceChildren();

  // Principle 5, applied to the rail's own state. The green line *asserts* that
  // nothing is waiting on you; before the first summary lands — or after a read
  // that failed — nobody has established that, and a third state says so rather
  // than claiming the good news by default.
  if (!summary || !Array.isArray(summary.needs_you)) {
    slot.className = "rail rail-unknown";
    slot.setAttribute("aria-label", "the fleet has not been read yet");
    return;
  }

  const rows = summary.needs_you;
  if (rows.length === 0) {
    // Collapsed: a 4 px green line (`app.css`). Nothing is waiting on you, and
    // the rail says that by taking almost no room rather than by saying "0".
    slot.className = "rail rail-empty";
    slot.setAttribute("aria-label", "nothing needs you");
    return;
  }

  slot.className = "rail rail-active";
  slot.setAttribute("aria-label", `${rows.length} waiting on you`);
  slot.appendChild(
    element("span", "rail-count", rows.length === 1 ? "1 needs you" : `${rows.length} need you`),
  );

  const list = element("ul", "rail-rows");
  for (const row of rows) {
    const item = element("li", "rail-row");
    item.appendChild(element("span", "rail-title", titleOf(row)));
    // The actual ask, verbatim. Untrusted text into `textContent` (§13).
    item.appendChild(element("span", "rail-ask", askOf(row)));
    list.appendChild(item);
  }
  slot.appendChild(list);
}
