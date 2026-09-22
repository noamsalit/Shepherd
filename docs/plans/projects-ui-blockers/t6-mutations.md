# T6 — the mutation ledger

**Driver:** `scratchpad/` (gitignored), re-runnable; every row is a **file edit
and nothing else**. No signal, no subprocess against the host, no socket, no
teardown verb — nothing escapes the process, which is the rule
`CLAUDE.md` states and the reason it states it.

**Procedure, per row.** The tree is committed before the first plant, and the
driver **refuses to run on a dirty tree**. `__pycache__` is cleared before every
run: a size-preserving mutation landing in the same second as the last compile
re-imports the unmutated bytecode and is recorded as a false survivor — a hole
written down as a proof there isn't one. Each row reverts with
`git checkout -- <path>`, which is safe here *because* the tree was committed
first: on an uncommitted tree that command goes to HEAD, not to before the
plant.

Tree verified clean after each pass (`git status --porcelain` empty).

| # | mutation | file | gate | verdict |
| --- | --- | --- | --- | --- |
| M1 | the card loses its `bucket-*` class | `flock.js` | `test_every_card_carries_one_of_the_eight_bucket_classes` | **RED** |
| M2 | a session never seen claims `just now` | `flock.js` | `test_a_session_with_no_timestamp_reads_never_seen` | **RED** |
| M3 | the page mints a seventh `page-` root | `flock.js` | `test_the_page_never_mints_a_seventh_page_root` | **RED** |
| M4 | the card grows a fifth item (`card-model`) | `flock.js` | `test_the_card_carries_four_things_and_no_more` | **RED** |
| M5 | an SVG attribute gains a concatenation | `flock.js` | `test_the_two_icons_are_built_as_nodes_not_as_markup` | *survived — bad mutation, see below* |
| M5b | the back chevron goes back through `innerHTML` | `flock.js` | same gate | **RED** |
| M5c | the legend icon goes back through `innerHTML` | `flock.js` | `test_no_unescaped_interpolation_in_frontend` | **RED** |
| M6 | the projects pane reads `workspace.workspace_id` | `flock.js` | `test_the_flock_page_reads_the_keys_the_tree_emits` | **RED** |
| M7 | `who_acts` drifts one word from `PALETTE` | `flock.js` | `test_the_legend_acts_line_comes_from_palette_who_acts` | **RED** |
| M8 | the pane renders only the first action | `session.js` | `test_expanded_row_lists_every_action_with_its_source` | **SURVIVED — real gap** |
| M8b | the same, after the fix | `session.js` | same gate | **RED** |
| M8c | the same, against the named successor | `session.js` | `test_the_session_pane_renders_why_and_every_action` | **RED** |
| M9 | RD6 loses the `retry: "M3"` row | `session.js` | `test_the_pane_labels_unreachable_action_kinds_rather_than_dropping_them` | **RED** |
| M10 | the honest `why?` becomes a `<button>` | `session.js` | `test_why_is_a_note_not_a_button_without_the_lane` | **RED** |
| M11 | `stranded` reverts to `unfinished` in `PALETTE` | `stops.py` | `test_palette_matches_core_stops` | **RED** |
| M12 | the empty list stops saying `nothing to do` | `session.js` | `test_row_with_zero_actions_is_only_a_confident_completed` | **RED** |
| M13 | the strip drops the unknown rate | `flock.js` | `test_the_stop_summary_strip_is_filled_by_the_flock_page` | **RED** |
| M14 | the page sorts client-side | `flock.js` | `test_the_flock_page_does_not_re_derive_the_order` | **RED** |
| M15 | the pane forgets it is a pane (`showLevel` gone) | `session.js` | `test_the_pane_is_mounted_in_the_flocks_third_pane` | **RED** |
| M16 | the debt is paid — `app.js` rewired to `flock.js` | `app.js` | `test_the_pending_shell_wiring_is_exactly_what_is_owed` | **RED** |
| M17 | an **undeclared** module goes missing (`./nowhere.js`) | `app.js` | `test_every_shipped_module_is_reachable_from_the_page` | **RED** |
| M18 | the reachability walk stops biting on an orphan | `test_session_wiring.py` | `test_the_reachability_walk_bites` | **RED** |

22 rows · 21 red · 1 real survivor, closed.

M16 is the important one and it runs the gate **backwards**: it plants the
*fix*, not a defect, and asserts the pin falls. A debt list whose test still
passes after the debt is paid is a permanent exemption wearing a temporary name.
M17 is its companion control: `STALE_SPECIFIERS` lets the walk skip exactly one
declared dead edge, and a module that goes missing without being declared is
still a hard failure — otherwise the skip would have become "the walk tolerates
absence".

## M8 — the one that was a hole

`actions.slice(0, 1).forEach(...)` keeps the ordinal, keeps `action.source`,
keeps the `action-source` class. Every assertion in the successor and in its
`test_fleet_page.py` counterpart stayed green while the pane rendered exactly
the one action the **retired** card test settled for. The word "every" in
`test_the_session_pane_renders_why_and_every_action`'s own name was not being
checked, which would have made D67's claim — *strictly stronger than the test it
retires* — untrue in the one dimension it was about.

Closed by naming the truncating shapes rather than describing the property:
`.slice(`, `actions[0]`, `.at(0)`, `actions.shift(` are banned from
`actionList`, and `actions.forEach(` is required. Re-planted as M8b and M8c;
both red.

## M5 — the one that was a bad mutation

`"9" + ""` inside an SVG attribute value changes nothing the gate is about: the
gate counts `createElementNS(SVG_NS` calls and forbids `innerHTML`, and an
attribute is neither. The mutation was wrong, not the test. Re-planted as **M5b**
(the chevron rebuilt through `innerHTML` with concatenation) and **M5c** (the
legend icon likewise, against the repo-wide escaping scan); both red. Recorded
rather than silently replaced, because "the mutation was bad" is the most
comfortable explanation for a survivor and has to be shown rather than asserted.
