"""Verdicts, the two wait helpers, and the per-scenario clause recorder.

**This module is the repair of qa5's `await_true`.** qa5 raised `HarnessBlocked`
on every blown bound, so every product failure written as "wait until X" was
reported as an environment problem and never as FAIL (existing-harness audit
finding 4). Here there are two helpers with two different contracts:

* `await_env` is for environment liveness (an instance up, a helper alive, a
  browser started). A blown bound raises `Blocked`, always.
* `await_product` is for a product observation. A blown bound raises
  `ProductFail` (verdict `FAIL(bound)`) **only** under test-plan Difference 1:
  a positive control on the same channel, in the same run, observed the thing,
  and the bound is at least 10x that control's latency — or the bound is a
  sourced product constant passed as `Sourced(...)`. Otherwise `Blocked`.

A verdict is `PASS | FAIL | BLOCKED` (Difference 9: qa5's `PARTIAL` is
retired). The recorder lets a scenario measure every clause before deciding,
so a scenario with a predicted-FAIL clause still reports its other clauses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypeVar

T = TypeVar("T")

Verdict = Literal["PASS", "FAIL", "BLOCKED"]
#: `harness_error`: the scenario body raised something that is neither a product
#: assertion nor `Blocked` (a harness KeyError, a refused env, a Playwright
#: timeout) with no failed clause before it. It is recorded as FAIL so it is
#: never lost, but the publish gate reads it as INCOMPLETE, never RED: a harness
#: crash has proven nothing about the product (review finding 7, hunter M9).
FailKind = Literal["assert", "bound", "harness_error"]

#: How often a wait re-reads its predicate. Not a readiness signal: the
#: predicate is.
POLL_S = 0.05

#: Difference 1(c): the bound must be at least this multiple of the positive
#: control's measured latency for a blown bound to be a FAIL.
CONTROL_MULTIPLE = 10.0


class Blocked(Exception):
    """The scenario could not run, or a clause could not be observed.

    Never a verdict about the product. `BLOCKED` never rounds up to PASS.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ProductFail(AssertionError):
    """`FAIL(bound)`: the product never did X within a bound that qualifies."""

    def __init__(
        self, what: str, bound_s: float, control_latency_s: float | None, source: str, message: str | None = None
    ) -> None:
        super().__init__(
            message
            or f"FAIL(bound): {what} did not happen within {bound_s:.3f}s "
            f"(control latency {control_latency_s!r}, bound source: {source})"
        )
        self.what = what
        self.bound_s = bound_s
        self.control_latency_s = control_latency_s
        self.source = source


class ProductUnreachable(Exception):
    """A product socket failure seen by `httpclient.Client.request` (hunter N2).

    Mixed into a subclass of the original socket error (`TimeoutError`,
    `ConnectionRefusedError`, `ConnectionResetError`/`RemoteDisconnected`, any
    other `ConnectionError`, `http.client.HTTPException`), so every caller that
    catches the socket type on purpose still catches it. Classified by WHERE it
    came from (the product's loopback socket), never by its type alone:

    * `after_answer`: this same client got a complete answer earlier in this
      scenario (`scenario_epoch`), so the channel was proven, and the product
      stopped answering: FAIL (`kind`: `assert`, or `bound` for a timeout that
      is at least 10x the earlier answer's latency — Difference 1);
    * otherwise no control proves the channel: BLOCKED.

    `harness_error` stays for exceptions raised by harness code.
    """

    what: str = ""
    after_answer: bool = False
    kind: str = "assert"
    detail: str = ""


#: One number per scenario test, bumped by conftest before its setup: "earlier in the scenario".
_SCENARIO_EPOCH: list[int] = [0]


def begin_scenario() -> int:
    _SCENARIO_EPOCH[0] += 1
    return _SCENARIO_EPOCH[0]


def scenario_epoch() -> int:
    return _SCENARIO_EPOCH[0]


@dataclass(frozen=True)
class Sourced:
    """A bound that is a product constant with a citation (e.g. the 2.0 s scan)."""

    seconds: float
    source: str


def _wait(predicate: Callable[[], T | None], bound_s: float) -> tuple[T | None, float]:
    """Poll until the predicate returns a truthy value or the bound expires.

    Returns the value (or `None`) and the elapsed seconds. Exceptions from the
    predicate propagate: a predicate that cannot evaluate is not "false".
    """
    started = time.monotonic()
    deadline = started + bound_s
    while True:
        value = predicate()
        if value:
            return value, time.monotonic() - started
        if time.monotonic() >= deadline:
            return None, time.monotonic() - started
        time.sleep(POLL_S)


def await_env(predicate: Callable[[], T | None], bound_s: float, what: str) -> T:
    """Environment liveness. A blown bound is `Blocked`, never a FAIL."""
    value, elapsed = _wait(predicate, bound_s)
    if not value:
        raise Blocked(f"environment: {what} not observed within {bound_s}s (waited {elapsed:.2f}s)")
    return value


def await_product(
    predicate: Callable[[], T | None],
    bound: float | Sourced,
    what: str,
    control_latency_s: float | None,
) -> T:
    """A product observation under Difference 1. See the module docstring."""
    bound_s = bound.seconds if isinstance(bound, Sourced) else bound
    value, _elapsed = _wait(predicate, bound_s)
    if value:
        return value
    raise classify_blown_bound(what, bound, control_latency_s)


def classify_blown_bound(
    what: str, bound: float | Sourced, control_latency_s: float | None
) -> Exception:
    """The exception a blown product bound becomes: `ProductFail` or `Blocked`.

    Split out so the guard tests can prove both outcomes without waiting.
    """
    if isinstance(bound, Sourced):
        return ProductFail(what, bound.seconds, control_latency_s, bound.source)
    if control_latency_s is not None and bound >= CONTROL_MULTIPLE * max(control_latency_s, 1e-3):
        return ProductFail(what, bound, control_latency_s, "10x same-channel control")
    return Blocked(
        f"unqualified bound: {what} not observed within {bound}s, and no same-channel "
        f"control qualifies it (control latency {control_latency_s!r}); Difference 1 "
        "makes this BLOCKED, not FAIL"
    )


def observe(predicate: Callable[[], T | None], bound_s: float) -> tuple[T | None, float]:
    """Poll without deciding: the value (or `None`) and the elapsed seconds.

    For a clause whose blown bound is decided by the caller — typically
    FAIL(bound) if a same-channel control qualifies it, else BLOCKED.
    """
    return _wait(predicate, bound_s)


def timed(action: Callable[[], T]) -> tuple[T, float]:
    """Run `action` and return its result and wall-clock latency (a control's)."""
    started = time.monotonic()
    result = action()
    return result, time.monotonic() - started


# ----- the per-scenario clause recorder --------------------------------------


ClauseResult = Literal["pass", "fail", "blocked", "recorded"]


@dataclass
class Clause:
    name: str
    result: ClauseResult
    expected: str
    actual: str
    bound: bool = False


@dataclass
class Recorder:
    """Soft clauses for one scenario, decided once at the end.

    `check` records a clause and continues; `finish` raises the scenario's
    verdict: any failed clause → `AssertionError` (FAIL(assert)); else any
    blocked clause → `Blocked`; else PASS. A failed clause outranks a blocked
    one: a proven failure is information, an unreachable clause is not.
    """

    scenario: str
    clauses: list[Clause] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    finished: bool = False

    def check(self, name: str, ok: bool, expected: object, actual: object) -> bool:
        self.clauses.append(
            Clause(name, "pass" if ok else "fail", _short(expected), _short(actual))
        )
        return ok

    def equal(self, name: str, expected: object, actual: object) -> bool:
        return self.check(name, expected == actual, expected, actual)

    def fail_bound(self, name: str, what: str, bound_s: float, control: str, actual: object = None) -> None:
        """A FAIL(bound) clause (Difference 1): the caller established the control.

        `actual` is what WAS observed instead (hunter M2): a stream that closed
        promptly with the wrong code and one that never closed are different
        failures, and the record must say which.
        """
        observed = "" if actual is None else f"; observed instead: {_short(actual, 400)}"
        self.clauses.append(
            Clause(name, "fail", f"{what} within {bound_s}s", f"not observed; control: {control}{observed}", bound=True)
        )

    def block(self, name: str, reason: str) -> None:
        self.clauses.append(Clause(name, "blocked", "observable", _short(reason)))

    def record(self, name: str, value: object) -> None:
        """A measurement the plan says to record, with no pass/fail oracle."""
        self.clauses.append(Clause(name, "recorded", "recorded", _short(value)))

    def note(self, text: object) -> None:
        self.evidence.append(_short(text, 4000))

    def run_clause(self, name: str, body: Callable[[], None]) -> None:
        """Run `body`; its AssertionError fails this clause, its Blocked blocks it.

        `ProductFail` is an AssertionError subclass and is recorded as a failed
        clause carrying its bound text.
        """
        try:
            body()
        except Blocked as blocked:
            self.block(name, blocked.reason)
        except ProductFail as failed:
            self.clauses.append(Clause(name, "fail", "clause holds", _short(str(failed)), bound=True))
        except AssertionError as failed:
            self.clauses.append(Clause(name, "fail", "clause holds", _short(str(failed))))
        else:
            self.clauses.append(Clause(name, "pass", "clause holds", "held"))

    @property
    def failed(self) -> list[Clause]:
        return [clause for clause in self.clauses if clause.result == "fail"]

    @property
    def blocked(self) -> list[Clause]:
        return [clause for clause in self.clauses if clause.result == "blocked"]

    def finish(self) -> None:
        self.finished = True
        if self.failed:
            names = ", ".join(f"{c.name} (expected {c.expected}; actual {c.actual})" for c in self.failed)
            message = f"{self.scenario}: {len(self.failed)} clause(s) failed: {names}"
            if all(clause.bound for clause in self.failed):
                raise ProductFail(message, 0.0, None, "clause-level", message=f"FAIL(bound): {message}")
            raise AssertionError(message)
        if self.blocked:
            names = ", ".join(f"{c.name}: {c.actual}" for c in self.blocked)
            raise Blocked(f"{self.scenario}: clause(s) not observable: {names}")
        if not self.clauses:
            raise Blocked(f"{self.scenario}: no clause was evaluated; a scenario that checks nothing is not a PASS")

    def as_json(self) -> list[dict[str, str]]:
        return [
            {"name": c.name, "result": c.result, "expected": c.expected, "actual": c.actual,
             "kind": "bound" if c.bound else ""}
            for c in self.clauses
        ]


def _short(value: object, limit: int = 600) -> str:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ----- one scenario's outcome, from its phase, its exception and its recorder --------------


Outcome = tuple[str, str | None, str]


def _failed_kind(recorder: Recorder) -> str:
    return "bound" if recorder.failed and all(clause.bound for clause in recorder.failed) else "assert"


def _failed_names(recorder: Recorder) -> str:
    return ", ".join(f"{c.name} (expected {c.expected}; actual {c.actual})" for c in recorder.failed)[:1500]


def classify_outcome(error: BaseException | None, when: str, recorder: Recorder | None, *,
                     is_scenario: bool, skipped: bool = False) -> Outcome:
    """`(verdict, fail_kind, reason)` for one phase of one test. Pure (the guards drive it).

    * setup: an error is always BLOCKED (a harness that could not set up proved nothing);
    * a failed clause **outranks** whatever interrupted the body afterwards — a
      helper's `Blocked`, a skip, a harness exception, or a return without
      `finish()` — so a proven FAIL is never published as BLOCKED (hunter H1);
    * a scenario that never requested `rec` is BLOCKED, never PASS (review 6);
    * a product socket failure (`ProductUnreachable`, from `Client.request`) with
      no failed clause is FAIL when this client answered earlier in the
      scenario, else BLOCKED (hunter N2);
    * an unexpected exception with no failed clause is FAIL(harness_error)
      (review 7 / hunter M9), which the gate reads as INCOMPLETE.
    """
    if when == "setup":
        if error is None:
            return "PASS", None, ""
        if isinstance(error, Blocked):
            return "BLOCKED", None, error.reason[:2000]
        if skipped:
            return "BLOCKED", None, f"skipped: {str(error)[:2000]}"
        return "BLOCKED", None, f"setup failed ({type(error).__name__}): {str(error)[:2000]}"
    failed = recorder is not None and bool(recorder.failed)
    if error is None:
        if is_scenario and recorder is None:
            return "BLOCKED", None, "harness: the scenario never requested `rec`, so nothing it checked was recorded"
        if recorder is not None and not recorder.finished and is_scenario:
            if failed and recorder is not None:
                return "FAIL", _failed_kind(recorder), (f"{len(recorder.failed)} clause(s) failed, then the scenario "
                                                        f"returned without rec.finish(): {_failed_names(recorder)}")
            return "BLOCKED", None, "harness: the scenario returned without calling rec.finish()"
        return "PASS", None, ""
    text = str(error)[:2000]
    if isinstance(error, ProductFail):
        return "FAIL", "bound", text
    if isinstance(error, AssertionError):
        return "FAIL", "assert", text
    if failed and recorder is not None:
        interrupt = (f"Blocked: {error.reason}" if isinstance(error, Blocked)
                     else f"{'skip' if skipped else type(error).__name__}: {text}")[:600]
        return "FAIL", _failed_kind(recorder), (f"{len(recorder.failed)} clause(s) failed before the body was "
                                                f"interrupted ({interrupt}): {_failed_names(recorder)}")
    if isinstance(error, ProductUnreachable):
        if error.after_answer:
            return "FAIL", "bound" if error.kind == "bound" else "assert", (
                f"product socket failure after this client had answered in this scenario: {text}")
        return "BLOCKED", None, (f"product socket failure with no earlier answer from this client in this "
                                 f"scenario (no control proves the channel): {text}")
    if isinstance(error, Blocked):
        return "BLOCKED", None, error.reason[:2000]
    if skipped:
        return "BLOCKED", None, f"skipped: {text}"
    return "FAIL", "harness_error", f"harness error: unexpected {type(error).__name__} in the scenario body: {text}"
