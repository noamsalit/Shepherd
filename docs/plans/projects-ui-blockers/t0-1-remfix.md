# T0.1 remediation — the Phase 0 gate reported success without checking

- Workflow: `wf-20260921T212808Z-9172ed6b` (`kind: remfix`, origin: failure-hunter)
- Base: `88bfdc3` on `integration`
- Files touched: `tools/render_check.py`, `tools/js_syntax_check.py`,
  `tests/tools/test_render_check_args.py` — and this file. **No `src/`.**
- Python: `/root/Shepherd/.venv/bin/python`

## The shape of the whole thing, once

Phase 0's negative control removed a `must_see` string from one page. That
proves the DOM assertion bites, and it was read as proving the checker bites.
**A control that exercises one of two gates certifies one of two gates.** The
console gate, the banner gate, the routing assertion and the report's own
counters had never been driven by anything, and four of them were open.

Every fix below has a fixture, and every fixture is accompanied by **variant A,
a clean page that must still pass**. A change that makes everything fail is not
a gate either.

## What was wrong, and what it is now

| # | Defect | Fix | Fixture |
|---|---|---|---|
| **C1** | the console / `pageerror` list was read **once**, at `:158`, above the navigation loop — every error raised while the six pages were actually opened was collected and discarded at `page.close()` | a `sweep()` that runs at arrival, after every page opens, and once before the page closes, and **drains** what it has reported so nothing is counted twice | **C** — a structurally perfect page that throws at t=1500 ms |
| **C2** | `.boom` was checked at `:164`, also above the loop — but the banner is painted by a page's own render, which only happens three lines later | `sweep()` re-checks `.boom` after every open, reporting only banners not yet reported | **E** — a page that paints `.boom` on a nav click |
| **C3** (review) | the loop asserted the clicked root **is visible** and never that the other five are **not** — i.e. it could not catch U18, *the defect this tool was written for* | exclusivity: at arrival, more than one visible root fails; after every click, exactly one must be visible | **F** (all roots visible) and a second fixture that reveals an extra root **only on click**, which only the per-click branch can see |
| **H3** | `js_syntax_check.py` exited **0** having parsed nothing | `if not paths: print("no files given"); return 1` | zero-argv via subprocess |
| **H4** (review) | a missing `#drawer-open` raised `TimeoutError` after 30 s, losing every failure already collected *and* the summary line | same shape as the missing nav entry three lines above: report and `continue` | **G** — a shell with the drawer removed |
| **M4** | `0 failures` was byte-identical whether twelve assertions ran or none | `12 pages checked · 12 screenshots · 0 failures`, and a run that opened no page **fails** | a nav-less page → `0 pages checked` |
| **M5** | `named = ns.url or ns.file` read an empty string as absent, so `--url "$VAR"` with `VAR` unset silently retargeted to the prototype | test `is not None`, reject an empty value | `parse_args(["--url", ""])` → `SystemExit` |
| **L6** | extra positionals were dropped | rejected by name | `["page.html", "out", "extra"]` → `SystemExit` |
| **L7** | `shots.mkdir()` ran before `goto`, leaving an empty `shots/` behind on a run that never reached a page | created lazily, before the first screenshot | a run that shoots nothing leaves no directory |
| **M6** (review) | the one-definition-site assertion was keyed on one exact spelling and **survived** both `page.locator('#drawer-open')` (single quotes — this module's own house style) and `f'[data-page="{target}"].nav-item'` | strip the two definition lines, then require the **tokens** `drawer-open` and `data-page=` to be absent from the remainder | mutation table below |
| **M7** (review) | the by-path loader left a half-initialised module in `sys.modules` when `exec_module` raised | `except BaseException: del sys.modules[name]; raise` | an inert module that raises `ValueError` at import |

## The esprima decision, carried out

`esprima` 4.0.1 is an **ES2017** parser. It reports FAIL on optional chaining,
`??`, `||=`, class fields, private fields, optional catch binding, numeric
separators and `import.meta` — all of which chromium has accepted for years.
`js_syntax_check.py` now parses **with chromium**, the engine the code actually
runs in: each file is served to a headless page from disk under a route-only
origin and `import()`ed; only a `SyntaxError` is reported.

Consequences, stated rather than implied:

1. **A6 is retired.** There is no undeclared third-party parser left, so the
   rule that no file under `tests/` may import or name it is moot. The grep is
   still empty: `grep -rn "esprima" tests/` → no output. The only two
   occurrences in the repo's code are in this tool's docstring, explaining why
   it is gone.
2. **Line numbers are lost.** Chromium exposes no line for a module compile
   error — neither `e.stack` nor the console carries one when the failing
   `import()` is caught (both checked). The report names the file and the
   message (`Unexpected token ';'`) where esprima also named the line. That is
   the price of parsing the real language instead of a proxy for it, and it is
   written into the module docstring so the next reader is not surprised.
3. **A syntax error and a missing file stay distinct.** An unreadable file is
   reported by name before chromium is started; a module that parses and then
   *throws* on a blank page — which every page module does, since they all wire
   the DOM at import time — is **not** reported. Proven by two fixtures.
4. The tool now needs playwright, which it already needed nowhere else; the
   suite reaches it only through a subprocess, and the module-level
   `pytest.importorskip("playwright")` still guards the whole test file (F13).

## Evidence, verbatim

```
$ .venv/bin/python -m pytest tests/tools -q
...............................                                          [100%]
exit 0        (31 tests)

$ .venv/bin/python -m pytest -q
exit 0        1897 passed, 2 skipped

$ .venv/bin/python tools/js_syntax_check.py
no files given
exit 1

$ .venv/bin/python tools/js_syntax_check.py src/shepherd/web/static/*.js
8 file(s) · 0 failure(s)
exit 0

$ grep -rn "esprima" tests/
(no output, exit 1)

$ .venv/bin/mypy --strict tools/render_check.py      → Success (advisory)
$ .venv/bin/mypy --strict tools/js_syntax_check.py   → Success (advisory)
```

The six variants, driven through the **real command line** against a throwaway
loopback server:

```
===== A clean =====
12 pages checked · 12 screenshots · 0 failures
>>> A clean: exit 0
===== C throws at t=1500ms =====
FAIL [phone] after opening flock: pageerror: DEMO boom late
FAIL [desktop] after opening flock: pageerror: DEMO boom late
>>> exit 1
===== D throws on nav click =====
FAIL [phone] after opening settings: pageerror: DEMO boom on settings
FAIL [desktop] after opening settings: pageerror: DEMO boom on settings
>>> exit 1
===== E paints .boom on nav =====
FAIL [phone] after opening settings: error banner: DEMO render failed
FAIL [desktop] after opening settings: error banner: DEMO render failed
>>> exit 1
===== F all roots visible (U18) =====
FAIL [phone] on arrival: 6 page roots visible at once
FAIL [desktop] on arrival: 6 page roots visible at once
>>> exit 1
===== G no drawer control =====
FAIL [phone] no drawer control for shepherd   (×6)
6 pages checked · 6 screenshots · 6 failures
>>> exit 1
```

**Two reports per error, not seven.** C, D and E each produce exactly two
failures — one per viewport — which is the drain working. A list re-read and
never drained reports one error once per remaining page, which is noise dressed
as thoroughness; the fixture for D asserts the count, not merely the presence.

## Mutation probes

The selector rule, applied to the **text** of `render_check.py` with the
mutation held in memory — nothing was written into the repo and nothing was
executed:

| planted second definition | old rule | new rule |
|---|---|---|
| `page.locator('#drawer-open')` — single quotes | **SURVIVES** | caught |
| `f'[data-page="{target}"].nav-item'` — attribute-first | **SURVIVES** | caught |
| `page.locator("#drawer-open")` — double quotes (control) | caught | caught |
| unmutated source | passes | passes |

The per-click exclusivity branch, deleted in a **scratch copy** and re-run
against the fixture that targets it (a text edit only; the copy contains no
signal, no teardown verb, nothing that leaves the process):

```
=== repo version (branch present) ===  10 failures  → exit 1
=== mutant (per-click branch deleted) ===  0 failures → exit 0
```

The loader cleanup, with the old loader body run in scratch on an inert module
that raises `ValueError`:

```
OLD loader leaves it registered: True
  and what the next importer gets: <module 'broken_probe' from '…/broken_probe.py'>
```

## Housekeeping

No `shots/` at the repo root. No stray chromium, no stray `http.server`
(`pgrep` clean). No tmux was used. `docs/probes/`, `src/` and `~/.claude/`
untouched.

## What this does not settle — for the plan owner

1. **The plan still names A6 and its exit criterion** (`grep -rn "esprima" tests/`
   in T0.1's Exit Criteria, and the risk row "esprima becomes an undeclared
   suite dependency"). Both are now vacuous rather than wrong. Editing the plan
   was outside this remediation's scope; the grep still passes, so nothing is
   red.
2. **`js_syntax_check.py` now depends on playwright**, as `render_check.py`
   already did. Neither is declared in `pyproject.toml` — unchanged from before
   for the render checker, new for the JS gate. The suite touches the JS gate
   only through a subprocess and the whole test file skips without playwright,
   so a machine without it still collects and passes.
3. **The gate reports no line number for a JS syntax error.** If that matters
   more than the language ceiling, the decision is reversible and the reasoning
   for both sides is written above.
