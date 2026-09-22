# T5.2 remediation — a colour contract that reads one notation certifies one notation

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: code-reviewer)
- Base: `8cf0e4d` (`worktree-agent-a707de229afd3fe16`, "U16: the legend key takes
  its bucket colour"). **Deliberately not on `integration`** — T5.2 is held off
  it, because a stylesheet without its markup leaves the shipped page broken.
- Branch: `worktree-agent-a377e9e352405bde7`, commit `4575d83`. Not merged.
- Files touched: `src/shepherd/web/static/app.css`, `tests/web/test_shell.py`,
  `tests/web/fixtures/shell_harness.html` — and this file. Nothing else.
- Python: `/root/Shepherd/.venv/bin/python`
- `tests/web/test_shell.py` was green before a line of this was written. Nothing
  here was red; what is fixed is **unearned green**.

## The shape of the whole thing, once

`test_the_root_palette_aliases_match_core_stops` and
`test_every_bucket_rule_aliases_the_shared_colour_variable` both read hexes.
The stylesheet also spelled two palette colours as `rgb` triples — twelve of
them. Retune `needs_you` in `core.stops.PALETTE` and the two **hex** spellings
go red, get fixed, the suite goes green — and ten amber tints on the nav badge,
the approval card, the decision card, the choice list and the confirm dialog are
still the old colour. The contract reports success while the property it
protects is broken.

Lines 969 and 1720 are the tell: each held `var(--needs-you)` / `var(--finished)`
**and** the hand-written triple, in the same declaration block.

**This is the third recorded instance in this repo of a rule keyed on one exact
spelling passing on the idiomatic spelling of the same violation.** The first
two were boundary scans. This one is a UI contract, which says the shape belongs
to *scans* — to any rule that recognises a value by how it is written — and not
to any one subsystem.

## What is wrong, and what it is now

| # | Defect | Fix |
|---|---|---|
| **H1** | twelve palette colours re-spelled as `rgb` triples the contract cannot see: `--needs-you` `#F59E0B` at `:276, 458, 459, 885, 886, 952, 968, 969, 1386, 1387`, `--finished` `#10B981` at `:294, 1720` | each becomes `color-mix(in srgb, var(--needs-you) N%, transparent)` — `color-mix()` was already load-bearing at `:815`, so no new capability. Applied by one transform over the two triples rather than twelve times by hand, so no site is fixed by hand and none is missed by hand. **And the guard now enumerates the notations** (below) |
| **H2** | contrast: **seven** failures, not the one the review named. Recomputed below | `--b-text`, a `color-mix()` derivation of each bucket's own pinned hex, on the three rules that paint a bucket colour as *words* |
| **M3** | `.bubble` (`:377`) and `.prose` (`:410`) had no `overflow-wrap`, and `.scroll` is `overflow-y: auto` — an `overflow-x: visible` beside an `auto` computes to `auto`, so one unbroken token scrolls the conversation pane sideways | `overflow-wrap: anywhere`, the idiom already in `.path-text`, `.facts dd`, `.detail-why`, `.step-body`, `.approval-tool` and `.decision-body` |
| **M4** | `.topbar h1` / `.topbar-sub` are flex children with no `min-width: 0`, so they keep their `min-content` floor and an over-long title paints past the viewport — *document*-level horizontal scroll | `min-width: 0` plus the nowrap/ellipsis clip `.detail-title` (`:1004`) and `.card-title` (`:842`) already use |
| **M5** | the 12-render result could not be reproduced from the branch: the harness page was never committed | `tests/web/fixtures/shell_harness.html`, committed, **not** under `web/static/` where `server.py`'s content-type table would serve it |
| **L6** | `test_the_stylesheet_ships_no_webfont` did not scan for `image-set(`, which takes a **bare string** URL and slips all five other shapes | one word, and shown red against a planted `image-set("shepherd.woff2" 1x)` |

## H1: the guard now enumerates every notation the value can take

A colour contract that reads one notation certifies one notation. Four are now
covered, each by its own test in `tests/web/test_shell.py`:

| notation | how it is caught |
|---|---|
| `#RRGGBB` | counted — **exactly twice** per bucket, the `:root` alias and the `.bucket-*` block. A third literal anywhere is a failure |
| `#RGB` | expanded and compared |
| `rgb()` / `rgba()` | decomposed, comma **and** space-separated syntax, integer and percentage channels |
| `color()` | refused outright. A notation the guard cannot decompose is a notation it cannot certify. The lookbehind lets `color-mix(` through |

The violet and blue triples at `:30-31, 553, 1381, 1650, 1770` are **not**
palette colours and are untouched, as the review directed.

**Shown to bite**, on `4575d83`, `__pycache__` cleared first:

```
planted: background: rgba(245, 158, 11, 0.16);
E  AssertionError: [('rgba(245, 158, 11, 0.16)', 'needs_you')]
FAILED tests/web/test_shell.py::test_no_rgb_literal_respells_a_palette_colour
EXIT=1
```

Removed, exit 0.

## H2: the recomputed contrast table

Measured against this file's own `--ink-*` values, small text, WCAG 2.1 SC 1.4.3
(4.5:1). **Before** — the review flagged `blocked` on the legend; it is seven
failures across three grounds:

| bucket | `--ink-850` (`.legend`) | `--ink-700` (`.tip-who`) | `--ink-800` (`.sheet-acts`) |
|---|---|---|---|
| running | 5.25 | **4.38 FAIL** | 5.01 |
| needs_you | 8.98 | 7.49 | 8.57 |
| finished | 7.61 | 6.34 | 7.26 |
| unfinished | 4.56 | **3.80 FAIL** | **4.35 FAIL** |
| blocked | **4.05 FAIL** | **3.38 FAIL** | **3.87 FAIL** |
| paused | 7.95 | 6.63 | 7.58 |
| error | 5.13 | **4.28 FAIL** | 4.89 |
| unclassified | 7.60 | 6.34 | 7.25 |

**After**, with `--b-text: color-mix(in srgb, var(--bucket-colour) 78%, var(--text))`:

| bucket | computed `--b-text` | `--ink-850` | `--ink-700` | `--ink-800` |
|---|---|---|---|---|
| running | `#6199F5` | 6.78 | 5.66 | 6.47 |
| needs_you | `#F2AF3D` | 10.08 | 8.41 | 9.62 |
| finished | `#40C499` | 8.80 | 7.34 | 8.39 |
| unfinished | `#9F7BF5` | 6.09 | 5.08 | 5.81 |
| blocked | `#818EA1` | 5.80 | **4.84** | 5.54 |
| paused | `#38C1DA` | 9.01 | 7.52 | 8.60 |
| error | `#ED696A` | 6.27 | 5.23 | 5.99 |
| unclassified | `#ADB3BD` | 9.15 | 7.63 | 8.73 |

Worst case 4.84, and it is the case the review named.

**Three things about the fix, each of which was the alternative:**

1. **Raising the type is in here and is recorded as *not* the fix.**
   `.legend-key` `0.78rem` → `0.82rem`/500, `.tip-who` and `.sheet-acts` →
   `0.72rem`/600. It helps a phone reader and it is worth having. It does not
   move the threshold: WCAG's large-text bar is **18.66px bold**, not 14px
   bold, and none of these three rules is anywhere near it. Option (a) as
   written could not have cleared `blocked` on `--ink-700`, so option (b) was
   always going to carry the compliance.
2. **`--b-text` is a derivation, never a second literal.** A hand-picked
   lighter hex per bucket would be exactly the drift H1's guard exists to
   catch, wearing a new name — and `test_every_bucket_rule_derives_its_text_colour_from_its_own_hex`
   fails if one appears. `test_each_palette_hex_is_spelled_exactly_twice`
   closes the same door from the other side.
3. **It is declared per-bucket, and that is forced, not stylistic.** A custom
   property substitutes `var()` at the element it is *declared* on. Written in
   `:root` it would resolve against `:root`'s `--b` — the unclassified grey —
   freeze there, and inherit down unchanged: every bucket the same grey, and
   the tests above would still have passed because nothing in the CSS would
   look wrong. The `:root` copy that is there is only the unclassified default.

**The glyphs keep `--b`.** `.legend-mark`, `.card-mark`, `.detail-mark`,
`.mini-mark`, `.sheet-glyph` and `.tip-head span:first-child` are non-text
content at the 3:1 threshold, and their job is to be the undiluted swatch the
text beside them is naming.

**Lightening the grounds was available and is refused.** `--ink-850` is the
second operand of the card wash (`:815`), so moving it moves U16.

## M5: the render evidence is regenerable now

```
/root/Shepherd/.venv/bin/python tools/render_check.py \
    --file tests/web/fixtures/shell_harness.html <shots>
```

→ `12 pages checked · 12 screenshots · 0 failures`, exit 0, at **390** and 1280.

Two things about the harness, because the previous one had neither:

- **It is out of the static tree.** `server.py` is byte-pinned to a
  content-type table of `.html` / `.js` / `.css`, so a page dropped in
  `web/static/` would be *served* — a test fixture reachable from the running
  product. `tests/web/fixtures/` is read by name and never globbed.
- **Its strings are hostile enough that the check can fail.** A real absolute
  repo path as the topbar title, in a `.bubble`, in a `.prose`, in a
  `.card-title` and in a `.proj-row`; and a 400-character engine prompt
  carrying one unbroken base64 token. The review's point was that the old
  fixture's strings were short enough that nothing could overflow, so the test
  could not fail.

**Shown to bite.** Reverting `.topbar h1`'s four added declarations against the
committed harness:

```
FAIL [phone] page scrolls sideways by 118px
12 pages checked · 12 screenshots · 1 failures
EXIT=1
```

Desktop did not report it. The 390 viewport is the one that catches it, which
is the viewport the design calls primary.

**`render_check.py` still measures only *document* overflow**, so a pane
scrolling inside itself is invisible to it — that is why M3 is pinned by a
static rule in `test_shell.py` as well, and why the two findings are fixed by
two different kinds of check.

## Not fixed, deliberately

`--b: var(--unclassified)` as the `:root` default means a card with **no**
bucket class renders as a plausible `unknown`. The default is right (the
alternatives are worse on contrast) and **the fix belongs to T5.3**: assert
that every `.card` the shell renders carries one of the eight `.bucket-*`
classes. Untouched here.

## Process note, recorded rather than quiet

Mid-run I proved the topbar guard by planting the regression into the live
`app.css`, then reverted the plant with `git checkout -- src/shepherd/web/static/app.css`
— **before the work was committed**, so it reverted the whole file, not the
plant. Every app.css edit was lost. They were re-applied as a single scripted
pass, the tests and the render check were re-run from scratch on the result
(both green, recorded above), and the commit was made **before** the remaining
two plants.

The rule that generalises: **a mutation proof requires a commit to return to.**
`git checkout -- <path>` reverts to HEAD, not to "before the plant", and an
uncommitted tree makes those the same command with very different blast radii.
This is the same shape as the two rules already in `CLAUDE.md` — isolating the
*name* (one plant) is not isolating the *effect* (one whole-file revert).

## Verification, all on `4575d83`

| Check | Result |
|---|---|
| `pytest tests/web/test_shell.py tests/web/test_palette.py tests/web/test_frontend_no_build_step.py -q` | **24 passed**, exit 0 |
| `render_check.py --file tests/web/fixtures/shell_harness.html` | 12 pages, 0 failures, exit 0, at 390 and 1280 |
| rgb guard, planted `rgba(245, 158, 11, 0.16)` | red, exit 1; removed, exit 0 |
| webfont guard, planted `image-set("shepherd.woff2" 1x)` | red, exit 1; removed, exit 0 |
| contrast guard, against the pre-fix stylesheet | red on all three rules — it was one of the five REDs the cycle opened with |

`__pycache__` cleared before every mutation run. No tmux. Nothing written under
`~/.claude/` or `docs/probes/`. Committed by path.
