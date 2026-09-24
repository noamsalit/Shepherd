# REMFIX-1 — code-reviewer and failure-hunter findings on `fix/qa6-bugfix` @ `3c83037`

Worktree `.claude/worktrees/qa6-P16`, branch `fix/qa6-bugfix` @ `3c83037`. Not committed (the router
commits). Every command was run from the worktree as
`PYTHONPATH=$PWD/src /Users/noamsalit/Git/Shepherd/.venv/bin/pytest -p no:randomly …`.
The router chose the scope: seven fixes. Each one had a failing test first, then the fix, then a green run.

## Files

- `src/shepherd/web/static/session.js`: `paintActions(row, force)` plus the `actionsDrawn` WeakMap (#1)
- `src/shepherd/orchestration/master_turn.py`: `send_turn`'s open-failure path does close, then `finally` release (#2)
- `src/shepherd/web/static/settings.js`: `sendIntent` keeps every confirmed reply; `choose` repaints on failure; new `clearFailureNote` (#3)
- `src/shepherd/engines/claude_code/ingest_socket.py`: `_is_live` narrowed; new `owned_inode`, `unlink_owned_socket` (#4)
- `src/shepherd/daemons/control_ingest.py`: shutdown unlink goes through `unlink_owned_socket` (#4)
- `src/shepherd/runner/local.py`: `TMUX_CALL_TIMEOUT_S`, the `timeout=` at the exec site, and `_run` maps `TimeoutExpired` to a `RunnerRefusal` (#5)
- `src/shepherd/web/static/terminal.js`: comments only (#6 reword, #7 move)
- tests: `tests/web/test_session_pane_qa6_live.py`, `tests/orchestration/test_master_turn_failures.py`,
  `tests/web/test_projects_settings_qa6_live.py`, `tests/engines/test_socket_live_owner.py`,
  `tests/runner/test_local.py`, `tests/web/test_session_page.py`. All changes are additive; no assertion was weakened.
- `tests/boundaries/consumer_manifest.json`: `files` digests for `session.js`, `settings.js` and `terminal.js`;
  each path's existing `post_milestone.edits` `why` gets a REMFIX-1 sentence. `baseline` and `rebase` are untouched.

## #1 [HIGH, reviewer #1] BC-13 regression: a header refresh closed `why?` and dropped focus

- **Finding.** `refreshSessionHeader` ran `slot("session-actions").replaceChildren(actionList(row), whyNote(row))`
  on every envelope, for any session.
- **RED.** `test_session_pane_qa6_live.py::test_a_header_refresh_keeps_an_open_why_and_the_focus` opens `why?`, focuses
  the external action link, changes the open session's title in the store (the positive signal that the pass ran),
  and publishes an event for **another** session. Result: exit 1,
  `AssertionError: {'open': False, 'focused': False, 'inside': False}`.
- **GREEN.** `paintActions(row, force)` computes a signature: `JSON.stringify([session_id, next_actions, decided_by,
  confidence])`, which is everything `actionList` and `whyNote` read (`MODEL_LANE_NOTE` is a constant). The signature
  is stored in a WeakMap keyed by the slot, following the pattern of `projects.js`'s `drawn`. The refresh skips the
  redraw when the signature has not changed. `renderSession` passes `force` and always draws. No new single-line
  assignment was added, so `REQUIRED_ASSIGNMENTS` is unchanged. Result: the test passes, along with
  `test_session_wiring.py` and `test_session_page.py`.

## #2 [HIGH, hunter H2] a raising `close()` on a failed open wedged the master

- **Finding.** `send_turn`'s `except Exception:` called `turn.runtime.close()` and then `self._release(turn)`. When
  `close()` raised, the release never ran.
- **RED.** `test_master_turn_failures.py::test_a_close_that_raises_on_a_failed_open_still_releases_the_slot` makes the
  drain's `set_app_state` fail once and uses a runtime whose `close()` raises. Result: exit 1,
  `AssertionError: a raising close kept the slot`.
- **GREEN.** The path now uses `_run_turn`'s shape: `try: close / finally: self._release(turn)`. Decision: the close's
  own error still propagates out of that `send_turn` call, as it does in `_run_turn`. It is not converted to a
  `TurnRefused`. The next `send_turn` returns `TurnStarted`.

## #3 [HIGH, hunter H4 + MEDIUM M4] settings could show a level the daemon did not hold

- **Finding.** When a reply arrived for a superseded click, `sendIntent` recursed without recording the reply. On a
  failure, `choose` returned without repainting. So the sequence "level 2, click 3 (lands), click 2 (refused)" left 2
  pressed while the daemon held 3. Separately, a success cleared only the NOT_MADE note and left UNREACHABLE on screen.
- **RED.** Result: exit 1, two tests failed.
  - `test_projects_settings_qa6_live.py::test_a_landed_level_is_shown_when_the_superseding_write_fails`:
    `assert ('false', 'true') == ('true', 'false')`.
  - `::test_a_later_success_clears_the_unreachable_note`: `assert 'The request … last read.' == ''`.
- **GREEN.** `sendIntent` writes `state.level = data.level` for every non-null reply before it recurses. `choose`
  calls `renderPanel()` on success and on failure. A success calls `clearFailureNote()`, which clears the note when it
  starts with NOT_MADE or equals UNREACHABLE. The single `state.level = data.level` assignment moved into `sendIntent`;
  it is still the one site that writes a confirmed reply, so `REQUIRED_SETTINGS_ASSIGNMENTS` is unchanged. Result: the
  two tests pass, along with `test_settings_page.py` and `test_settings_live.py`.

## #4 [MEDIUM, reviewer #3 / hunter H1 partial] stale-socket probe and shutdown unlink

- **Finding.** `_is_live` read any `OSError` (a timeout, a would-block) as "stale", and the path was then unlinked.
  Each owner's shutdown also unlinked whatever file sat at the path, which could be a newer owner's socket.
- **RED.** Result: exit 1, 5 failed.
  - `test_a_probe_that_cannot_prove_the_path_stale_is_a_refusal[timeout|would-block|other-oserror]`:
    `AssertionError: None`, meaning no `SocketInUse` was raised.
  - `test_an_ingest_owner_whose_path_was_replaced_leaves_it` and `test_a_control_owner_whose_path_was_replaced_leaves_it`:
    `AssertionError: the old owner unlinked the newer owner's socket`.

  The controls `test_a_refused_or_absent_probe_is_stale[refused|absent]` and `test_an_owner_still_unlinks_its_own_socket`
  passed both before and after the fix.
- **GREEN.** `_is_live` returns False only for `ConnectionRefusedError` and `FileNotFoundError`. Any other `OSError`
  means the socket is held. There is one shared helper pair in `ingest_socket.py`: `owned_inode(path)` is read right
  after `bind_listener`, and `unlink_owned_socket(path, inode)` unlinks only when the path still has that inode. Both
  `serve_ingest` and `serve_control_ingest` use the pair in their `finally`.
- **Limits, recorded here and not built.**
  - On macOS, a listener with a full backlog also answers `ECONNREFUSED`, so it cannot be told apart from a stale file.
    A lock-file design would close that gap. That is an OWNER item.
  - There is a window between `bind` and `owned_inode`.
  - On macOS, connecting to a **non-socket** file at the path raises `ENOTSOCK` (errno 38, measured here). Under the
    router's rule ("only refused/absent are stale") that is now a `SocketInUse` refusal, not an unlink. No test plants
    a regular file there, and the refusal message ("held by a running process") is inaccurate for that case.

## #5 [MEDIUM, reviewer #2] the exec site had no timeout while `DELIVERY_LOCK` is held

- **Finding.** `make_run_argv`'s `subprocess.run` had no timeout, so one hung tmux call held every delivery.
- **RED.** `test_local.py::test_a_hung_tmux_call_is_a_refusal_not_a_held_lock` puts a stand-in named `tmux` first on
  `PATH`. It runs `exec sleep 5` and is not tmux, so no tmux socket is touched. The test drives
  `LocalRunner.interrupt` through the real `make_run_argv`. Result: exit 1, `Failed: DID NOT RAISE RunnerRefusal`.
  That run patched the constant with `raising=False` so the observed failure was behavioural. The committed test
  patches it with the default `raising=True`.
- **GREEN.** A new constant `TMUX_CALL_TIMEOUT_S = 10.0`, annotated with `#:` like the file's other constants, is passed
  as `timeout=` at the exec site. `LocalRunner._run` maps `TimeoutExpired` to
  `RunnerRefusal("tmux timed out after {TMUX_CALL_TIMEOUT_S}s: …")`, next to the existing `FileNotFoundError` mapping.
- **Why the mapping is in `_run` and not at the exec site.** `test_the_exec_callable_checks_before_it_execs` forbids
  any `Try` or `ExceptHandler` inside `run_argv`. `test_local_runner_constructs_no_subprocess_call` requires that only
  `make_run_argv` and `run_argv` reference `subprocess.`. So `TimeoutExpired` is imported by name
  (`from subprocess import TimeoutExpired`), and `LocalRunner` is still the only consumer of `make_run_argv` in `src/`
  (`compose.py:293`). No test changed.
- **Line band.** `local.py` is at 500 lines, the maximum `test_the_module_is_within_its_line_budget` allows. The band
  was not edited. Lines were reclaimed from code only, and no prose was removed:
  - `ensure_server`'s `new-session` call was joined onto one line.
  - `write()` and `resize()` each bind `spot = target(...)` and make a one-line `_checked` call; the argv is unchanged.

## #6 [MEDIUM, reviewer #4] P15's scan blind spot on `snapshotForEmulator`

- **Finding.** The pty scan does not read `snapshotForEmulator`'s body, because its parameter is `capture` and the scan
  keys on other tokens. A DOM sink added there later would not be caught.
- **RED.** This is a coverage gap on correct code, so the RED is the old scan's blindness. It was shown on an
  **in-memory, inert** mutant: terminal.js text with `document.body.append(String(capture));` inserted before the
  return, read as text only and never executed. The old checks, `pty_path_findings` and `html_sink_findings`, both
  return `[]`. The new `snapshot_findings` returns `['document', '.append']`. The new test also carries its own
  negative fixture, an inline violating body, and asserts that every planted shape is reported.
- **GREEN.**
  - `test_session_page.py::test_the_snapshot_transform_has_no_sink_and_returns_bytes` uses
    `block_after(text, "function snapshotForEmulator")`. It asserts that the body contains none of `document`,
    `window`, `.append`, `textContent`, `HTML`, `DOMParser`, `createContextualFragment` or `Element`, and that every
    `return` is `new Uint8Array(` or `Uint8Array.from(`.
  - `test_pty_bytes_never_reach_innerHTML` gains the arrival assertion `snapshotForEmulator(`.
  - The parameter is still named `capture`. The terminal.js comment now names the covering test.

## #7 [LOW, reviewer #5] orphaned comment in terminal.js

The comment "The degrade's own three outcomes (review finding 5)…" sat above the BC-10 block. It is back above
`SCREEN_READING`, where it was at `6c70cd3`. The change is comments only and has no behavioural test. The evidence is
`js_syntax_check` plus the whole `tests/web` run.

## Checks (tree `3c83037` + this change set)

- New tests: RED as recorded above; all GREEN.
- `pytest tests/web`: 370 passed, 1 deselected, exit 0.
- `pytest tests/orchestration tests/master tests/engines tests/daemons tests/runner`: 722 passed, 6 skipped,
  3 deselected, exit 0.
- `pytest tests/boundaries`: only the 3 baseline `test_collected_node_ids.py` ERRORs. Before the manifest edit,
  `test_completing_l4_changed_no_consumer_byte` listed exactly `session.js`, `settings.js` and `terminal.js`.
- `mypy --strict src`: 2 errors, the baseline pair (`linux.py:104`, `detect.py:29`).
- `tools/js_syntax_check.py` on `session.js`, `settings.js` and `terminal.js`: 3 files, 0 failures.
- Default lane `--ignore=tests/qa5`: see README § REMFIX-1.
