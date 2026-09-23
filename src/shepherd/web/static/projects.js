// The Projects page (§12 page 4, U14) — D57's seven verbs, driven from a page.
//
// Three rules shape this file.
//
// **§13.** Nothing here touches `innerHTML`, `outerHTML` or
// `insertAdjacentHTML`. Every value that came from the store — a project name,
// a description, a repo path, a session title, a refusal reason — is untrusted
// text and reaches the page through `textContent` only. The prototype's one
// sink in this file (`BACK_BUTTON_P`, line 3101, an inline `<svg>` string) is
// rewritten below with `createElementNS`, which is the same picture with no
// parser involved. `tests/web/test_frontend_escaping.py` fails the build on a
// sink appearing here, so this is a gate rather than a habit.
//
// **D57/D59.** A project is a workspace; `Unassigned` is reserved. It is pinned
// last, marked `data-reserved`, and its rename / delete / add-repo controls are
// **absent rather than disabled** — a disabled button still says "this is a
// thing you may one day do here", and for the reserved project it is not.
//
// **D61.** The delete is a record, never an exception, and the dialog is drawn
// out of the refusal the server sent. Default-refuse is unskippable by
// omission: the first POST carries **no** `on_running` at all.

const API = "/api/projects";

//: `OnRunning` in `store/models.py`, hardcoded because no route exposes a tool
//: schema and the page cannot learn the values at run time. Spelled
//: `kill_sessions`, never `kill`: tmux prefix-resolves `kill` to `kill-server`,
//: so `tests/boundaries/test_tmux_blast_radius.py` refuses the bare word in
//: `src/` and the enum member was renamed round it. The plan still carries the
//: stale `["refuse", "kill", "orphan"]`; the enum is the source of truth, and
//: `"kill"` is what the tool's own negative test feeds it.
const ON_RUNNING = { kill: "kill_sessions", orphan: "orphan" };

//: D22/D58, verbatim from the prototype. It is true: `_registered_roots` is
//: what a spawn is validated against, so a path added here widens it.
const ALLOWLIST_WARNING =
  "A path here widens where Shepherd may start sessions. Agents in this " +
  "project will be admitted to run under it.";

const UNASSIGNED = "unassigned";

//: The sentence for a `fetch` that **rejected** — `controld` stopped, the
//: socket refused, DNS gone. `envelope()` only ever ran on a *resolved*
//: response, so before this pass a rejection walked past every refusal path
//: this page has: the dialog stayed open, `#p-refusal` stayed hidden and empty,
//: and the only trace was an unhandled `Failed to fetch` on the console. The
//: copy is `session.js`'s, which had the pattern first and was one of two
//: modules out of six that did.
const UNREACHABLE =
  "The request did not reach the server — Shepherd may not be running.";

//: Principle 5 over `required`: the browser accepts a single space, and the
//: handler then trimmed it to "" and returned with no message at all.
const NEEDS_NAME = "A project needs a name — this one is only whitespace.";

// Principle 5: a datum we do not have is shown as unknown, never invented.
const NO_DESCRIPTION = "No description.";
const NO_PATHS = "No paths yet — no session can be started here.";
const UNTITLED = "untitled";

const view = {
  projects: [],
  openId: null,
  detail: null,
  status: null,
};

// ----- DOM helpers ------------------------------------------------------------

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

// Defect 11. Every one of these is inside a fixed-width box with
// `text-overflow: ellipsis`, and QA measured a 935px repo path in a 334px one:
// the ellipsised half of a §13 allowlist path could not be read at all, by any
// means the page offered. A `title` is the cheapest thing that is not a second
// layout — no width, survives a phone, and it is the string the node already
// holds, so it cannot disagree with what is on screen.
function titled(tag, className, text) {
  const node = element(tag, className, text);
  node.title = node.textContent;
  return node;
}

function button(className, text) {
  const node = element("button", className, text);
  node.type = "button";
  return node;
}

// The prototype's `BACK_BUTTON_P()` (line 3101) without its `innerHTML`: the
// same chevron, built as SVG nodes. `createElementNS` is required — an `<svg>`
// made by `createElement` lands in the HTML namespace and renders nothing.
function backButton() {
  const node = button("back");
  node.setAttribute("aria-label", "Back");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2.2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M15 18l-6-6 6-6");
  svg.appendChild(path);
  node.appendChild(svg);
  node.addEventListener("click", () => {
    root().dataset.level = "list";
  });
  return node;
}

function root() {
  return document.getElementById("page-projects");
}

// ----- the transport ----------------------------------------------------------
//
// Every body is `{ok, data, error, correlation_id}`. On a failure the page
// shows the generic literal and the id and nothing else — §13 gives it nothing
// else, deliberately (E14, `registry.py:69` and `:318-319`).

async function envelope(response) {
  const body = await response.json();
  if (!body.ok) {
    view.status = `${body.error} (${body.correlation_id})`;
    return null;
  }
  view.status = null;
  return body.data;
}

// Both halves answer `null` for *every* failure and leave the sentence in
// `view.status`, so a caller has one branch to write. A rejection is a failure
// like a refusal is: the difference is which sentence, never whether there is
// one.
async function read(path) {
  try {
    return envelope(await fetch(path, { headers: { Accept: "application/json" } }));
  } catch (unreachable) {
    view.status = UNREACHABLE;
    return null;
  }
}

async function write(path, payload) {
  try {
    return envelope(
      await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    );
  } catch (unreachable) {
    view.status = UNREACHABLE;
    return null;
  }
}

const idOf = (project) => encodeURIComponent(project.project_id);

// ----- loading ----------------------------------------------------------------

async function loadList() {
  const data = await read(API);
  if (data) {
    view.projects = data.projects;
  }
  renderList();
  renderDetail();
}

//: **BC-1. The pane belongs to the last project ASKED for, not to the last
//: read that resolved.** `view.openId` is that intent and it is written
//: synchronously — at the click, at the create — so a read that comes back for
//: a project the page has since navigated away from is dropped whole: it
//: writes no `view.detail` and it paints nothing.
//:
//: Ordering the *requests* would not have done it, and that is the part worth
//: keeping. `projectRow`'s click handler starts a read and does not await it,
//: and `submitProject`'s create branch issues a read of its own **after** that
//: click has already landed — so the stale answer is sometimes the one
//: requested later. Only the recorded intent can say which answer the page
//: still wants.
//:
//: The symptom QA round 5 measured (S33, and the settle bolted onto S19 and
//: S32) was one full-suite run in four where the detail pane settled on a
//: project the user had left, taking `#proj-edit`'s closure — captured at
//: render time, `renderDetail` below — with it: Edit opened the dialog on the
//: wrong workspace and the draft path list never reached the clicked project's
//: repos. Render and closure are the same project by construction, so both
//: halves are closed by the same guard rather than by two.
async function loadDetail(projectId) {
  view.openId = projectId;
  await refreshDetail(projectId);
}

//: The read half, with no claim on the pane. It exists for the one caller that
//: declared its intent a whole round trip earlier: re-asserting `openId` there
//: would let a deferred navigation overwrite a click the user made in the
//: meantime, which is the defect rather than the fix.
async function refreshDetail(projectId) {
  const data = await read(`${API}/${encodeURIComponent(projectId)}`);
  if (view.openId !== projectId) {
    return;
  }
  // `found` is a value, not an exception (principle 5): a project deleted in
  // another tab renders as "no such project" rather than as a crash.
  view.detail = data && data.found ? data.project : null;
  renderDetail();
}

async function reload() {
  await loadList();
  if (view.openId !== null) {
    await loadDetail(view.openId);
  }
}

// ----- the list pane ----------------------------------------------------------

//: D59's pin. `list_projects` returns the reserved project among the others;
//: the page moves it to the end rather than sorting, because every other order
//: on this page is the server's.
function ordered(projects) {
  return projects
    .filter((project) => project.project_id !== UNASSIGNED)
    .concat(projects.filter((project) => project.project_id === UNASSIGNED));
}

//: Whether this project's name identifies it in the list that is on screen.
function unique(project) {
  return (
    view.projects.filter((row) => row.name === project.name).length === 1
  );
}

function countLabel(n, one, many) {
  return n === 1 ? `1 ${one}` : `${n} ${many}`;
}

function projectRow(project) {
  const row = button("proj-row");
  const reserved = project.project_id === UNASSIGNED;
  if (reserved) {
    row.dataset.reserved = "true";
  }
  row.dataset.projectId = project.project_id;
  row.setAttribute("aria-current", project.project_id === view.openId ? "true" : "false");
  row.appendChild(titled("span", "proj-name", project.name));
  const meta = element("div", "proj-meta");
  // Defect 6. `create_project` is deliberately never keyed by name (E1), so two
  // rows may read the same word and be different projects. The id is shown on
  // exactly those rows: always would be noise, never was two rows separable
  // only by "0 repos" and "no activity yet".
  if (!unique(project)) {
    meta.appendChild(titled("span", "proj-id", project.project_id));
  }
  if (!reserved) {
    meta.appendChild(element("span", null, countLabel(project.repo_count, "repo", "repos")));
  }
  meta.appendChild(
    element(
      "span",
      null,
      project.last_activity_at === null
        ? "no activity yet"
        : `last activity ${project.last_activity_at}`
    )
  );
  row.appendChild(meta);
  row.addEventListener("click", () => {
    root().dataset.level = "detail";
    loadDetail(project.project_id);
    renderList();
  });
  return row;
}

function renderList() {
  const host = document.getElementById("proj-list");
  if (host === null) {
    return;
  }
  host.replaceChildren();
  for (const project of ordered(view.projects)) {
    host.appendChild(projectRow(project));
  }
}

// ----- the detail pane --------------------------------------------------------

function sectionLabel(text, note) {
  const label = element("p", "field-label", text);
  if (note) {
    label.appendChild(element("span", "soon", note));
  }
  return label;
}

function section(...children) {
  const node = element("div", "section");
  for (const child of children) {
    node.appendChild(child);
  }
  return node;
}

// A session on a project is a link into the Flock (§12 page 2), not a dead
// line. The shell owns the navigation: `data-page` is the vocabulary its nav
// already uses, and the `href` is there so the row is a real link — middle
// click, focus ring, and a visible target — rather than a div that listens.
function sessionLink(row) {
  const line = element("div", "mini");
  const bucket = typeof row.bucket === "string" ? row.bucket : "unclassified";
  line.classList.add(`bucket-${bucket}`);
  line.appendChild(element("span", "mini-mark", "●"));
  const link = element("a", "mini-open");
  link.dataset.page = "flock";
  link.dataset.sessionId = row.session_id;
  link.href = `#flock/session/${row.session_id}`;
  link.appendChild(titled("span", "mini-title", row.title || UNTITLED));
  link.appendChild(
    element("span", "mini-age", row.ended_at === null ? "running" : "ended")
  );
  line.appendChild(link);
  return line;
}

function pathRow(repo) {
  const row = element("div", "path");
  // §13's allowlist, in full: a basename or an ellipsis would hide exactly the
  // part of the string that decides where a session may be started.
  row.appendChild(titled("code", "path-text", repo.root_path));
  return row;
}

function renderDetail() {
  const host = document.getElementById("proj-detail");
  if (host === null) {
    return;
  }
  host.replaceChildren();
  const project = view.detail;
  if (project === null) {
    host.appendChild(element("div", "col-head", "detail"));
    if (view.status !== null) {
      host.appendChild(errorLine(view.status));
    }
    return;
  }
  const reserved = project.project_id === UNASSIGNED;

  const band = element("div", "proj-band");
  band.appendChild(backButton());
  band.appendChild(titled("h2", "proj-title", project.name));
  if (!reserved) {
    // D59: the reserved project gets no `.proj-acts` at all. Absent, not
    // disabled — the store refuses rename, delete and add_repo on it (E7/E8/E9).
    const acts = element("div", "proj-acts");
    const edit = button("ghost", "Edit");
    edit.id = "proj-edit";
    edit.addEventListener("click", () => openProjectDialog(project));
    acts.appendChild(edit);
    const drop = button("ghost", "Delete");
    drop.id = "proj-delete";
    drop.dataset.danger = "true";
    drop.addEventListener("click", () => openDeleteDialog(project));
    acts.appendChild(drop);
    band.appendChild(acts);
  }
  host.appendChild(band);

  const body = element("div", "proj-body");

  if (reserved) {
    body.appendChild(
      section(
        element(
          "p",
          "desc",
          "Sessions that matched no declared project. Nothing is ever dropped — " +
            "they stay here until a repo path claims them."
        )
      )
    );
  } else {
    const text = element("p", "desc", project.description || NO_DESCRIPTION);
    if (!project.description) {
      text.dataset.empty = "true";
    }
    body.appendChild(section(sectionLabel("Description"), text));

    const paths = element("div", "paths");
    if (project.repos.length === 0) {
      paths.appendChild(element("p", "desc", NO_PATHS));
    }
    for (const repo of project.repos) {
      paths.appendChild(pathRow(repo));
    }
    body.appendChild(section(sectionLabel("Repository paths"), paths));

    // D63/D64, W3: M5's `queue` table does not exist, so there is nothing
    // behind a provider picker. RD6 — a capability that lands later renders
    // labelled and inert — and here the label is the whole control.
    body.appendChild(
      section(
        sectionLabel("Work source", "not built"),
        element(
          "p",
          "desc",
          "Ticketing-system configuration is declared but not built in this " +
            "build: nothing reads it, so nothing is offered."
        )
      )
    );
  }

  const list = element("div", "sess-mini");
  for (const row of project.sessions) {
    list.appendChild(sessionLink(row));
  }
  if (project.sessions.length === 0) {
    list.appendChild(element("p", "desc", "No sessions have run here."));
  }
  body.appendChild(section(sectionLabel("Sessions"), list));
  host.appendChild(body);
}

function errorLine(text) {
  // E14: the generic literal and the correlation id, which is all §13 gives a
  // page. It is shown rather than swallowed — an id a person can quote is the
  // whole of what a failed tool call leaves behind.
  const node = element("p", "desc", text);
  node.dataset.error = "true";
  return node;
}

// ----- `#dlg-project`: create and edit ---------------------------------------
//
// Create and edit are one dialog because they are one form. They are **not**
// one verb: `create_project` takes name and description, `rename_project`
// takes a name, `set_project_description` takes a description, and the two
// repo verbs act one path at a time against a project that already exists. So
// the paths section is live only when editing — there is no id to add a path
// to before the project is made — and Save issues **only the verbs whose field
// changed**, because a rename is an audited write and re-issuing one for a
// field nobody touched is a record of something that did not happen.
//
// **Defect 3.** The description field used to be `disabled` when editing,
// under the note "no verb changes it in this build". That was false —
// `set_project_description` is built (`tools_projects.py:177`), routed
// (`routes.py:116`) and registered — and the sentence told a person that fixing
// a typo meant deleting the project, which is the one destructive verb here.

const draft = { project: null, repos: [] };

function projectDialog() {
  const dialog = document.createElement("dialog");
  dialog.id = "dlg-project";
  const form = element("form", "dlg");
  form.id = "form-project";
  form.method = "dialog";

  const title = element("h3", null, "New project");
  title.id = "dlg-project-title";
  form.appendChild(title);

  const nameLabel = element("label", null, "Name");
  const name = document.createElement("input");
  name.type = "text";
  name.id = "p-name";
  name.required = true;
  nameLabel.appendChild(name);
  form.appendChild(nameLabel);

  const descLabel = element("label", null, "Description");
  const desc = document.createElement("textarea");
  desc.id = "p-desc";
  desc.rows = 2;
  descLabel.appendChild(desc);
  const descNote = element("small", "dlg-note");
  descNote.id = "p-desc-note";
  descLabel.appendChild(descNote);
  form.appendChild(descLabel);

  const paths = section();
  paths.id = "p-paths-section";
  paths.appendChild(sectionLabel("Repository paths"));
  const pathList = element("div", "paths");
  pathList.id = "p-paths";
  paths.appendChild(pathList);
  const add = element("div", "path-add");
  const newPath = document.createElement("input");
  newPath.type = "text";
  newPath.className = "mono";
  newPath.id = "p-new-path";
  newPath.setAttribute("aria-label", "absolute path");
  newPath.placeholder = "/code/acme/payments-api";
  newPath.addEventListener("keydown", (event) => {
    // Enter adds the path; it must not submit the form and close the dialog.
    if (event.key === "Enter") {
      event.preventDefault();
      addDraftPath();
    }
  });
  add.appendChild(newPath);
  const addButton = button("ghost", "Add");
  addButton.id = "p-add-path";
  addButton.addEventListener("click", addDraftPath);
  add.appendChild(addButton);
  paths.appendChild(add);
  const warn = element("div", "dlg-warn");
  warn.appendChild(element("span", null, "⚠"));
  warn.appendChild(element("span", null, ALLOWLIST_WARNING));
  paths.appendChild(warn);
  form.appendChild(paths);

  const source = section(
    sectionLabel("Work source", "not built"),
    element("p", "desc", "Declared by D63/D64; nothing behind it in this build.")
  );
  form.appendChild(source);

  const refusal = element("p", "desc");
  refusal.id = "p-refusal";
  refusal.dataset.error = "true";
  refusal.hidden = true;
  form.appendChild(refusal);

  const acts = element("div", "dlg-acts");
  const cancel = button("ghost", "Cancel");
  cancel.addEventListener("click", () => dialog.close());
  acts.appendChild(cancel);
  const save = element("button", "btn btn-primary", "Create");
  save.type = "submit";
  save.id = "p-save";
  acts.appendChild(save);
  form.appendChild(acts);

  form.addEventListener("submit", onProjectSubmit);
  dialog.appendChild(form);
  return dialog;
}

function showRefusal(id, text) {
  const node = document.getElementById(id);
  node.textContent = text === null ? "" : text;
  node.hidden = text === null;
}

async function openProjectDialog(project) {
  draft.project = project;
  draft.repos = [];
  const editing = project !== null;
  document.getElementById("dlg-project-title").textContent = editing
    ? "Edit project"
    : "New project";
  document.getElementById("p-save").textContent = editing ? "Save" : "Create";
  document.getElementById("p-name").value = editing ? project.name : "";
  const desc = document.getElementById("p-desc");
  desc.value = editing ? project.description || "" : "";
  desc.disabled = false;
  document.getElementById("p-desc-note").textContent = editing
    ? "Saved by set_project_description when you press Save."
    : "";
  duplicate.armed = null;
  document.getElementById("p-new-path").value = "";
  document.getElementById("p-paths-section").hidden = !editing;
  showRefusal("p-refusal", null);
  document.getElementById("dlg-project").showModal();
  if (editing) {
    await loadDraftPaths();
  }
}

// The dialog reads its own path list over `list_repos` rather than off the
// detail it was opened from: add and remove act one at a time against the
// store, and a list that was a copy would disagree with the allowlist the
// moment either of them refused.
async function loadDraftPaths() {
  const data = await read(`${API}/${idOf(draft.project)}/repos`);
  draft.repos = data ? data.repos : [];
  renderDraftPaths();
}

function renderDraftPaths() {
  const host = document.getElementById("p-paths");
  host.replaceChildren();
  if (draft.repos.length === 0) {
    host.appendChild(element("p", "desc", NO_PATHS));
  }
  for (const repo of draft.repos) {
    const row = pathRow(repo);
    const drop = button("ghost", "Remove");
    drop.dataset.repoId = repo.repo_id;
    drop.addEventListener("click", () => removeDraftPath(repo));
    row.appendChild(drop);
    host.appendChild(row);
  }
}

async function addDraftPath() {
  const field = document.getElementById("p-new-path");
  const typed = field.value.trim();
  if (typed === "" || draft.project === null) {
    return;
  }
  const answer = await write(`${API}/${idOf(draft.project)}/repos/add`, {
    root_path: typed,
  });
  if (answer === null) {
    showRefusal("p-refusal", view.status);
    return;
  }
  if (!answer.added) {
    // The refusal is a sentence the tool wrote — a path that does not probe as
    // a repo has no `git_common_dir`, and saying so is the difference between
    // this and a session that later binds to Unassigned for no stated reason.
    showRefusal("p-refusal", answer.refused);
    return;
  }
  showRefusal("p-refusal", null);
  field.value = "";
  await loadDraftPaths();
  await reload();
}

async function removeDraftPath(repo) {
  await write(`${API}/${idOf(draft.project)}/repos/remove`, { repo_id: repo.repo_id });
  await loadDraftPaths();
  await reload();
}

//: Defect 6's create-side half. A second project of the same name is a real
//: intent the store supports on purpose (E1: keyed by id, never by name), so
//: this is a **warning and not a refusal** — the first Create says what is
//: about to happen, the second one does it. `armed` holds the name that was
//: warned about, so changing the field after the warning re-arms it.
const duplicate = { armed: null };

function duplicateWarning(name) {
  return (
    `There is already a project named "${name}". A name is a label and not an ` +
    "identity here, so this makes a second project. Press Create again to do it."
  );
}

//: Defect 2 of the second QA pass — defect 7's failure class, fixed on the
//: delete side and left here. Two POSTs both leave before `loadList()` runs,
//: so `view.projects` never holds the first project when the second is
//: decided and the duplicate-name warning cannot see it either: a double click
//: made two projects on three of three measured attempts.
//:
//: A flag rather than a disabled button, for `inFlight.delete`'s reason and
//: one more: `#p-save` is a `<form>` submit control, and disabling it inside
//: its own handler is a race against the browser's second submit rather than a
//: guard on it. The wrapper covers **both** branches of this handler — create
//: and edit — because they share the submit, and the branch that is about to
//: issue a request is not known until the name is read.
async function onProjectSubmit(event) {
  event.preventDefault();
  if (inFlight.project) {
    return;
  }
  inFlight.project = true;
  try {
    await submitProject();
  } finally {
    inFlight.project = false;
  }
}

async function submitProject() {
  const name = document.getElementById("p-name").value.trim();
  const description = document.getElementById("p-desc").value.trim();
  if (name === "") {
    // Defect 10: `required` is satisfied by a space, so the browser submits and
    // this used to `return` with nothing said at all.
    showRefusal("p-refusal", NEEDS_NAME);
    return;
  }
  const editing = draft.project;
  if (editing === null) {
    const clashes = view.projects.some((row) => row.name === name);
    if (clashes && duplicate.armed !== name) {
      duplicate.armed = name;
      showRefusal("p-refusal", duplicateWarning(name));
      return;
    }
    const answer = await write(API, { name, description });
    if (answer === null || !answer.created) {
      showRefusal("p-refusal", answer === null ? view.status : answer.refused);
      return;
    }
    duplicate.armed = null;
    document.getElementById("dlg-project").close();
    // BC-1. The intent is declared **here**, synchronously, one statement after
    // the create — ahead of both awaits below, so a row clicked while this
    // branch settles supersedes it instead of losing to it. `dataset.level`
    // moves up for the same reason: set after `loadList()` it also undid a Back
    // pressed during the read.
    view.openId = answer.project.project_id;
    root().dataset.level = "detail";
    await loadList();
    // `refreshDetail` and not `loadDetail`: this branch must not re-assert an
    // intent it recorded a round trip ago.
    await refreshDetail(answer.project.project_id);
    // `renderList()` used to follow, to pick up the `aria-current` that
    // `loadDetail` had only just made true. `openId` is now true before
    // `loadList()` paints the list, so the second pass is redundant — and a
    // redundant pass rebuilds every row under whatever click is in flight.
    return;
  }
  if (name !== editing.name) {
    const answer = await write(`${API}/${idOf(editing)}/rename`, { name });
    if (answer === null || !answer.renamed) {
      showRefusal("p-refusal", answer === null ? view.status : answer.refused);
      return;
    }
  }
  if (description !== (editing.description || "")) {
    // Absent **clears** it, exactly as it does at creation — so an emptied box
    // sends no `description` rather than an empty string, and the one spelling
    // of "there is no description" stays the store's.
    const answer = await write(
      `${API}/${idOf(editing)}/description`,
      description === "" ? {} : { description }
    );
    if (answer === null || !answer.described) {
      showRefusal("p-refusal", answer === null ? view.status : answer.refused);
      return;
    }
  }
  document.getElementById("dlg-project").close();
  await reload();
}

// ----- `#dlg-delete`: D61's three-way choice, drawn from the refusal ---------
//
// The flow, and why it is three steps rather than one button.
//
// 1. **Before any request**, the dialog says what the delete would take, and
//    what it says is *every session record in the project* — because
//    `commit_project_delete` runs `DELETE FROM session WHERE workspace_id = ?`
//    and the running rows go too.
//
//    This is defect 1, and it was the worst thing on the page. The dialog used
//    to filter `ended_at !== null` and show the complement, which is the count
//    for the **orphan** branch presented as the unconditional one: QA saw
//    "6 session records" over a delete whose own record said `doomed: [8 ids]`.
//    `store/reads.py:285-291` predicted the drift in a comment written before
//    this page shipped. `DeletePlan.doomed` is now the only thing rendered the
//    moment there is one, and `endedSessions` is gone rather than corrected.
// 2. **The first POST carries no `on_running`.** Not `"refuse"` — nothing.
//    Default-refuse has to be unskippable by omission, and a field that is
//    never in the body cannot be edited out of it.
// 3. **The choices are the server's refusal**, including the session ids it
//    named. A list the page derived itself would offer to kill a session that
//    had already ended between the paint and the click.

async function deleteProject(projectId, onRunning) {
  const payload = onRunning === null ? {} : { on_running: onRunning };
  return write(`${API}/${encodeURIComponent(projectId)}/delete`, payload);
}

function deleteDialog() {
  const dialog = document.createElement("dialog");
  dialog.id = "dlg-delete";
  const panel = element("div", "dlg");

  const title = element("h3", null, "Delete project");
  title.id = "dlg-delete-title";
  panel.appendChild(title);

  const body = element("p", null);
  body.id = "dlg-delete-body";
  panel.appendChild(body);

  // Defect 6. The title said "Delete <name>" and nothing else, and two
  // projects may share a name by design. The id is what the button acts on, so
  // the id is on screen beside the description, which is the field a person
  // actually wrote to tell them apart.
  const identity = element("div", "dlg-identity");
  identity.id = "dlg-delete-identity";
  panel.appendChild(identity);

  const doomed = element("div", "dlg-live");
  doomed.id = "dlg-delete-doomed";
  panel.appendChild(doomed);

  const live = element("div", "dlg-live");
  live.id = "dlg-delete-live";
  panel.appendChild(live);

  const choices = element("div", "dlg-choices");
  choices.id = "dlg-delete-choices";
  panel.appendChild(choices);

  const acts = element("div", "dlg-acts");
  const cancel = button("ghost", "Cancel");
  cancel.id = "dlg-delete-cancel";
  cancel.addEventListener("click", () => dialog.close());
  acts.appendChild(cancel);
  panel.appendChild(acts);

  dialog.appendChild(panel);
  return dialog;
}

function choice(key, text, note, danger, disabled) {
  const node = button("dlg-choice");
  node.dataset.choice = key;
  if (danger) {
    node.dataset.danger = "true";
  }
  // Defect 4. Absent would be wrong here and disabled is right, which is the
  // opposite of D59's rule for the reserved project — and for the opposite
  // reason. A stop *is* a thing you may do to a running session; this
  // particular set of sessions has no pane Shepherd can reach, and a person who
  // is not shown the choice cannot be told why it cannot work.
  if (disabled) {
    node.disabled = true;
  }
  node.appendChild(element("span", null, text));
  node.appendChild(element("small", null, note));
  return node;
}

function idList(host, label, ids) {
  if (ids.length === 0) {
    return;
  }
  host.appendChild(element("div", "dlg-row", label));
  for (const id of ids) {
    host.appendChild(element("div", "dlg-row", id));
  }
}

//: The sessions still going. This one stays a local filter and the count of
//: what dies does not, and the difference is the point: this number is a
//: *warning* that the delete will refuse, and the server corrects it on the
//: very next line by answering `running` itself. The other was the number in
//: front of the destructive button.
function runningSessions(project) {
  return project.sessions.filter((row) => row.ended_at === null);
}

//: `kill_failures`, rendered — the one member of `delete_outcome`'s eleven that
//: had no reader on this page. The server already knew *why* a stop did not
//: take (`tools_projects_delete.py:132`, and `bump_anomaly(STOP_FAILED)` had
//: fired), and the dialog said only "N session(s) … were not stopped". A
//: refusal that cannot say why sends a person to the logs for a fact the
//: response was already carrying.
//:
//: The reason is a `RunnerRefusal` string with a tmux argv inside it, so it is
//: **wrapped, not ellipsised** — `.dlg-reason` in `app.css`. The half of an
//: argv that names the socket is the half that answers the question, and
//: `.dlg-identity`'s truncation would be exactly the wrong borrowing here.
function renderKillFailures(host, failures) {
  if (failures.length === 0) {
    return;
  }
  host.appendChild(element("div", "dlg-row", "Not stopped, and why:"));
  for (const failure of failures) {
    const entry = element("div", "dlg-fail");
    entry.appendChild(element("div", "dlg-row", failure.session_id));
    entry.appendChild(element("div", "dlg-reason", failure.reason));
    host.appendChild(entry);
  }
}

//: `doomed`, rendered — the server's list, never a filter over it.
function renderDoomed(ids) {
  const host = document.getElementById("dlg-delete-doomed");
  host.replaceChildren();
  idList(host, "These session records go with the project:", ids);
}

function destroysLabel(n) {
  return `This deletes the project and ${countLabel(n, "session record", "session records")}`;
}

function renderIdentity(project) {
  const host = document.getElementById("dlg-delete-identity");
  host.replaceChildren();
  host.appendChild(titled("div", "dlg-row mono", project.project_id));
  host.appendChild(
    titled("div", "dlg-row", project.description || NO_DESCRIPTION)
  );
  for (const repo of project.repos) {
    host.appendChild(titled("div", "dlg-row mono", repo.root_path));
  }
}

function openDeleteDialog(project) {
  const dialog = document.getElementById("dlg-delete");
  // **Every** session record, not the ended ones: this is what `doomed` will
  // say, computed the one way that agrees with the DELETE statement.
  const all = project.sessions.map((row) => row.session_id);
  const live = runningSessions(project);
  document.getElementById("dlg-delete-title").textContent = `Delete ${project.name}`;
  renderIdentity(project);
  document.getElementById("dlg-delete-body").textContent =
    destroysLabel(all.length) +
    (live.length === 0
      ? ". Nothing in it is running."
      : `, including ${countLabel(live.length, "session", "sessions")} still ` +
        "running — the delete will refuse until you choose what happens to them.");

  renderDoomed(all);
  document.getElementById("dlg-delete-live").replaceChildren();

  const choices = document.getElementById("dlg-delete-choices");
  choices.replaceChildren();
  const go = choice(
    "delete",
    "Delete the project",
    "Asks the server. A session still running refuses it.",
    true,
    false
  );
  go.addEventListener("click", () => onDeleteAnswer(project, null));
  choices.appendChild(go);
  dialog.showModal();
}

//: The refusal that is about running sessions is the one with a choice to
//: offer. A refusal that names none — the reserved project, a project deleted
//: in another tab — is a sentence and nothing else, because there is no answer
//: the page could give that would change it.
//: Defect 7. Two rapid clicks used to issue two deletes: the first succeeded
//: and the second raced it and lost, so the last sentence a person read was
//: *"there is no project '<ULID>' to delete"* — a failure, naming a raw id,
//: about a delete that had worked. One in two runs. The guard is a flag rather
//: than a disabled button because the choices are rebuilt on every answer and
//: a disabled node is replaced before the second click reaches it.
//: `project` is the create/edit submit, added by the second QA pass. Two keys
//: and not a general "the page is busy" latch: the delete dialog and the
//: project dialog are different modals and a shared flag would make one of
//: them silently swallow the other's first click.
const inFlight = { delete: false, project: false };

//: The note under "Stop them, then delete", written out of the plan's own
//: split. `killable` is `runner_handle IS NOT NULL` — the column the shipped
//: kill path asks — so an empty one means the server has already decided this
//: choice cannot work, and offering it as the primary danger choice made the
//: user discover that by clicking it.
function stopNote(answer) {
  if (answer.killable.length === 0) {
    return (
      "Shepherd does not own any of these sessions — they were started " +
      "outside it and there is no pane to stop. Use Unassigned instead."
    );
  }
  if (answer.unkillable.length === 0) {
    return "Ends the running work, then deletes the project.";
  }
  return (
    `Ends ${countLabel(answer.killable.length, "session", "sessions")}. ` +
    `Shepherd does not own ${answer.unkillable.join(", ")}, so the delete ` +
    "will refuse again over those."
  );
}

async function onDeleteAnswer(project, onRunning) {
  if (inFlight.delete) {
    return;
  }
  inFlight.delete = true;
  let answer;
  try {
    answer = await deleteProject(project.project_id, onRunning);
  } finally {
    inFlight.delete = false;
  }
  const choices = document.getElementById("dlg-delete-choices");
  const live = document.getElementById("dlg-delete-live");
  choices.replaceChildren();
  live.replaceChildren();
  if (answer === null) {
    document.getElementById("dlg-delete-body").textContent = view.status;
    return;
  }
  if (answer.deleted) {
    await renderDeleteOutcome(answer);
    return;
  }

  // Defect 7's other half: the list behind the dialog is one delete out of
  // date the moment a delete refuses for a reason that is about the world —
  // a project another tab removed answers "there is no project '<ULID>'", and
  // the row for it is still on screen. Re-read **before** anything in the
  // dialog is written, because every line below is synchronous from here and
  // an `await` between the sentence and the ids it explains is a frame in
  // which the two disagree.
  await loadList();
  // The refusal's own count, which is the first moment `doomed` exists. The
  // dialog said a number before the button; this is the server agreeing with
  // it, or correcting it, in the same words.
  document.getElementById("dlg-delete-body").textContent =
    `${answer.refused} ${destroysLabel(answer.doomed.length)}.`;
  renderDoomed(answer.doomed);
  // `killed` is shown on a refusal too, and this is the case that is easy to
  // miss: on a mixed project the owned sessions really were stopped before the
  // commit half refused over the ones that could not be.
  idList(live, "Already stopped by this attempt:", answer.killed);
  renderKillFailures(live, answer.kill_failures);
  if (answer.running.length === 0) {
    return;
  }
  idList(live, "Still running:", answer.running);
  const kill = choice(
    ON_RUNNING.kill,
    "Stop them, then delete",
    stopNote(answer),
    true,
    answer.killable.length === 0
  );
  kill.addEventListener("click", () => onDeleteAnswer(project, ON_RUNNING.kill));
  choices.appendChild(kill);
  const orphan = choice(
    ON_RUNNING.orphan,
    "Move them to Unassigned, then delete",
    "The work keeps running; only the project goes.",
    false,
    false
  );
  orphan.addEventListener("click", () => onDeleteAnswer(project, ON_RUNNING.orphan));
  choices.appendChild(orphan);
  const wait = choice(
    "cancel", "Wait — keep the project", "Nothing changes.", false, false
  );
  wait.addEventListener("click", () => document.getElementById("dlg-delete").close());
  choices.appendChild(wait);
}

async function renderDeleteOutcome(answer) {
  const panel = document.getElementById("dlg-delete-doomed");
  panel.replaceChildren();
  const outcome = element("div", "dlg-live");
  outcome.id = "dlg-delete-outcome";
  outcome.appendChild(
    element(
      "div",
      "dlg-row",
      `${countLabel(answer.destroyed.length, "session record", "session records")} destroyed.`
    )
  );
  idList(outcome, "Moved to Unassigned, still running:", answer.orphaned);
  idList(outcome, "Stopped by this delete:", answer.killed);
  // On the success path too, and the case is narrow rather than impossible: a
  // kill that raised leaves `ended_at` NULL and the commit half normally
  // refuses over it — unless the session ended on its own between the raise
  // and the re-derivation, in which case the delete went through *and* a stop
  // Shepherd issued did not land. That is precisely the moment a person is
  // owed the reason, and the moment a refusal-only reader would drop it.
  renderKillFailures(outcome, answer.kill_failures);
  for (const link of answer.severed) {
    outcome.appendChild(
      element("div", "dlg-row", `${link.session_id}: ${link.column} was cleared`)
    );
  }
  panel.appendChild(outcome);
  document.getElementById("dlg-delete-body").textContent = "The project is gone.";
  view.openId = null;
  view.detail = null;
  root().dataset.level = "list";
  await loadList();
}

// ----- the shell this page builds inside `#page-projects` ---------------------
//
// The two panes and the two dialogs are built here rather than declared in
// `index.html`: this module is the only thing that reads them, and a shell that
// ships empty slots for a page it does not otherwise know is a contract in two
// places. `#page-projects` itself, its `data-level`, and the nav entry that
// reveals it are the shell's — see the contract list in the task ledger.

function scaffold(host) {
  host.replaceChildren();

  const listPane = element("div", "herd-col");
  // A `.proj-band` and **not** a `.col-head`: `.col-head` carries
  // `text-transform: uppercase`, and Playwright's `inner_text()` returns the
  // transformed text, so `tools/render_check.py`'s "every page shows its own
  // name" reads `PROJECTS` there and reports the page as unnamed. The same
  // transform caught T7.2 on Settings, which is why that page's title is a
  // band too. Found in a browser, not by reading.
  const band = element("div", "proj-band");
  band.appendChild(titled("h2", "proj-title", "Projects"));
  listPane.appendChild(band);
  const list = element("div", "proj-list");
  list.id = "proj-list";
  listPane.appendChild(list);
  const add = button("new-project", "New project");
  add.id = "proj-new";
  add.addEventListener("click", () => openProjectDialog(null));
  listPane.appendChild(add);
  host.appendChild(listPane);

  const detail = element("div", "proj-detail");
  detail.id = "proj-detail";
  host.appendChild(detail);

  host.appendChild(projectDialog());
  host.appendChild(deleteDialog());
}

export function mountProjects() {
  const host = root();
  if (host === null) {
    return null;
  }
  scaffold(host);
  loadList();
  return { reload };
}
