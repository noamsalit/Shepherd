"""The decorators that turn a test function into a planned scenario.

`@scenario("W1")` applies `pytest.mark.qa6` and `pytest.mark.qa6_scenario("W1")`;
`@live_scenario("S0")` applies `qa6live` instead. The id must be a test-plan id
(`catalog.BY_ID`); `test_harness_guards` asserts every id is implemented at most
once across the package.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec

import pytest

from .catalog import BY_ID

P = ParamSpec("P")


class _Apply:
    """A decorator that keeps the test function's signature intact."""

    def __init__(self, sid: str, lane_mark: pytest.MarkDecorator) -> None:
        if sid not in BY_ID:
            raise ValueError(f"{sid!r} is not a test-plan scenario id")
        self.sid = sid
        self.lane_mark = lane_mark

    def __call__(self, func: Callable[P, None]) -> Callable[P, None]:
        marked: Callable[P, None] = self.lane_mark(pytest.mark.qa6_scenario(self.sid)(func))
        return marked


def scenario(sid: str) -> _Apply:
    return _Apply(sid, pytest.mark.qa6)


def live_scenario(sid: str) -> _Apply:
    return _Apply(sid, pytest.mark.qa6live)
