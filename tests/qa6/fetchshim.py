"""The parked-fetch shim for the C-26 race scenarios (R1-R7), env-plan §6.

A copy of `tests/web/conftest.py`'s proven `HOLD_MATCHING_FETCH` (it holds the
*request* and sends it on release — test-plan Difference 8), extended with:

* `__release_first()` — release only the oldest held request, so a scenario
  can order two replies deliberately (the losing interleaving, every time);
* `__hold(on)` — turn holding on or off without reinstalling;
* `__delivered` — the positive control: the count of released requests whose
  response (or error) has reached the page. A scenario waits on this number,
  never on a duration. Wave 7's stop-if: if a held fetch is not released or
  `__delivered` does not increment, R1-R7 are BLOCKED.

**This JS changes network timing only** (test-plan §0 row "fetch shim"). It is
installed with `page.add_init_script` or `page.evaluate`, and every scenario
using it is labelled so; no user action is ever fired from JS.
"""

from __future__ import annotations

from typing import Protocol

HOLD_MATCHING_FETCH = """(pattern) => {
  const real = window.fetch;
  const held = [];
  const expression = new RegExp(pattern);
  window.__held = held;
  window.__delivered = 0;
  window.__holding = true;
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!window.__holding || !expression.test(url)) {
      return real.call(window, input, init);
    }
    return new Promise((resolve, reject) => {
      held.push(() =>
        real.call(window, input, init).then(
          (response) => { window.__delivered += 1; resolve(response); },
          (error) => { window.__delivered += 1; reject(error); }
        )
      );
    });
  };
  window.__release = () => {
    const queued = held.splice(0, held.length);
    for (const send of queued) { send(); }
    return queued.length;
  };
  window.__release_first = () => {
    const first = held.shift();
    if (first) { first(); return 1; }
    return 0;
  };
  window.__hold = (on) => { window.__holding = Boolean(on); return window.__holding; };
}"""


class _Evaluates(Protocol):
    def evaluate(self, expression: str, arg: object = None) -> object: ...


def install(page: _Evaluates, pattern: str) -> None:
    """Install into a loaded page (labelled: network timing only)."""
    page.evaluate(HOLD_MATCHING_FETCH, pattern)


def held_count(page: _Evaluates) -> int:
    value = page.evaluate("() => (window.__held || []).length")
    return int(value) if isinstance(value, (int, float)) else -1


def delivered(page: _Evaluates) -> int:
    value = page.evaluate("() => window.__delivered ?? -1")
    return int(value) if isinstance(value, (int, float)) else -1


def release_all(page: _Evaluates) -> int:
    value = page.evaluate("() => window.__release()")
    return int(value) if isinstance(value, (int, float)) else 0


def release_first(page: _Evaluates) -> int:
    value = page.evaluate("() => window.__release_first()")
    return int(value) if isinstance(value, (int, float)) else 0


def set_holding(page: _Evaluates, on: bool) -> bool:
    return bool(page.evaluate("(on) => window.__hold(on)", on))
