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

async function read(path) {
  return envelope(await fetch(path, { headers: { Accept: "application/json" } }));
}

async function write(path, payload) {
  return envelope(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
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

async function loadDetail(projectId) {
  view.openId = projectId;
  const data = await read(`${API}/${encodeURIComponent(projectId)}`);
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
  row.appendChild(element("span", "proj-name", project.name));
  const meta = element("div", "proj-meta");
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
  link.appendChild(element("span", "mini-title", row.title || UNTITLED));
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
  row.appendChild(element("code", "path-text", repo.root_path));
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
  band.appendChild(element("h2", "proj-title", project.name));
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
// takes a name, and the two repo verbs act one path at a time against a
// project that already exists. So the paths section is live only when editing
// — there is no id to add a path to before the project is made — and the
// description is write-once, because no verb changes it (see the ledger).

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
  // No verb changes a description after the create, so the field is inert here
  // rather than a control that silently drops what was typed into it.
  desc.disabled = editing;
  document.getElementById("p-desc-note").textContent = editing
    ? "Set when the project was created; no verb changes it in this build."
    : "";
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

async function onProjectSubmit(event) {
  event.preventDefault();
  const name = document.getElementById("p-name").value.trim();
  if (name === "") {
    return;
  }
  const editing = draft.project;
  if (editing === null) {
    const answer = await write(API, {
      name,
      description: document.getElementById("p-desc").value.trim(),
    });
    if (answer === null || !answer.created) {
      showRefusal("p-refusal", answer === null ? view.status : answer.refused);
      return;
    }
    document.getElementById("dlg-project").close();
    await loadList();
    root().dataset.level = "detail";
    await loadDetail(answer.project.project_id);
    renderList();
    return;
  }
  if (name !== editing.name) {
    const answer = await write(`${API}/${idOf(editing)}/rename`, { name });
    if (answer === null || !answer.renamed) {
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
// 1. **Before any request**, the dialog says what the delete would take. The
//    record cannot tell it: `DeletePlan.doomed` is computed and then discarded
//    by `delete_project`, and the refusal carries `running` only. So the count
//    comes from the detail already on screen — the project's sessions whose
//    `ended_at` is set, which is `running_sessions_for`'s rule read the other
//    way round. It is a copy of a store derivation and it is named as one in
//    `docs/plans/projects-ui-blockers/t9-1.md`.
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

function choice(key, text, note, danger) {
  const node = button("dlg-choice");
  node.dataset.choice = key;
  if (danger) {
    node.dataset.danger = "true";
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

function endedSessions(project) {
  // `running` is `ended_at IS NULL` in `store/reads.py`; this is the
  // complement of that, over the same projected rows.
  return project.sessions.filter((row) => row.ended_at !== null);
}

function runningSessions(project) {
  return project.sessions.filter((row) => row.ended_at === null);
}

function openDeleteDialog(project) {
  const dialog = document.getElementById("dlg-delete");
  const doomed = endedSessions(project);
  const live = runningSessions(project);
  document.getElementById("dlg-delete-title").textContent = `Delete ${project.name}`;
  document.getElementById("dlg-delete-body").textContent =
    `This deletes the project and ${countLabel(doomed.length, "session record", "session records")}` +
    (live.length === 0
      ? ". Nothing in it is running."
      : `, and ${countLabel(live.length, "session", "sessions")} in it ` +
        "are still running — the delete will refuse until you choose what happens to them.");

  const doomedHost = document.getElementById("dlg-delete-doomed");
  doomedHost.replaceChildren();
  idList(
    doomedHost,
    "These session records go with the project:",
    doomed.map((row) => row.session_id)
  );
  document.getElementById("dlg-delete-live").replaceChildren();

  const choices = document.getElementById("dlg-delete-choices");
  choices.replaceChildren();
  const go = choice(
    "delete",
    "Delete the project",
    "Asks the server. A session still running refuses it.",
    true
  );
  go.addEventListener("click", () => onDeleteAnswer(project, null));
  choices.appendChild(go);
  dialog.showModal();
}

//: The refusal that is about running sessions is the one with a choice to
//: offer. A refusal that names none — the reserved project, a project deleted
//: in another tab — is a sentence and nothing else, because there is no answer
//: the page could give that would change it.
async function onDeleteAnswer(project, onRunning) {
  const answer = await deleteProject(project.project_id, onRunning);
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

  document.getElementById("dlg-delete-body").textContent = answer.refused;
  document.getElementById("dlg-delete-doomed").replaceChildren();
  // `killed` is shown on a refusal too, and this is the case that is easy to
  // miss: on a mixed project the owned sessions really were stopped before the
  // commit half refused over the ones that could not be.
  idList(live, "Already stopped by this attempt:", answer.killed);
  if (answer.running.length === 0) {
    return;
  }
  idList(live, "Still running:", answer.running);
  const kill = choice(
    ON_RUNNING.kill,
    "Stop them, then delete",
    "Ends the running work. A session Shepherd does not own has no pane to " +
      "stop, so this can refuse again and say which.",
    true
  );
  kill.addEventListener("click", () => onDeleteAnswer(project, ON_RUNNING.kill));
  choices.appendChild(kill);
  const orphan = choice(
    ON_RUNNING.orphan,
    "Move them to Unassigned, then delete",
    "The work keeps running; only the project goes.",
    false
  );
  orphan.addEventListener("click", () => onDeleteAnswer(project, ON_RUNNING.orphan));
  choices.appendChild(orphan);
  const wait = choice("cancel", "Wait — keep the project", "Nothing changes.", false);
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
  band.appendChild(element("h2", "proj-title", "Projects"));
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
