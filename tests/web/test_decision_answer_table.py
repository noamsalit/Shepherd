"""D77 (SD-06): the card's number → answer table is the server's key order.

**Seam: the shipped module's text, cross-checked against `dialog_keys`.** The
page maps the engine's own numbers to `approve` / `approve_always` / `deny` from
one table, and the server turns those words back into keys from another
(`orchestration/dialog_keys.py::PERMISSION_KEYS`). Two tables are two places to
disagree, so the JS one is parsed and compared **whole** against the Python
one's order — a swap of 2 and 3 in either file sends the scope-carrying "always
allow" as a refusal, or a refusal as a standing grant, and fails here.

The expected value is also stated as a literal: the order is a fact the P4 probe
recorded (Enter, then `2`, then `3`), not something to re-derive by reading the
same table twice.
"""

from __future__ import annotations

import re

from web.test_session_page import code_only, source

from shepherd.orchestration.dialog_keys import PERMISSION_KEYS

_TABLE = r"const {name}\s*=\s*\{{([^}}]*)\}};"
_NUMBERED = re.compile(r'(\d+)\s*:\s*"([a-z_]+)"')
_WORDED = re.compile(r'([a-z_]+)\s*:\s*"([a-z_]+)"')


def js_table(name: str, pair: re.Pattern[str]) -> dict[str, str]:
    """One `const NAME = { … };` object literal from `session.js`, as pairs."""
    match = re.search(_TABLE.format(name=name), code_only(source("session.js")))
    assert match is not None, f"{name} is not a single object-literal constant"
    found = dict(pair.findall(match.group(1)))
    assert found != {}, f"arrival: {name} parsed to nothing"
    return found


def test_the_numbered_answers_follow_the_servers_key_order() -> None:
    table = {int(number): answer for number, answer in js_table("PERMISSION_ANSWERS", _NUMBERED).items()}
    assert table == {n: k for n, k in zip((1, 2, 3), PERMISSION_KEYS, strict=True)}
    assert table == {1: "approve", 2: "approve_always", 3: "deny"}


def test_the_universal_answers_name_only_keys_the_server_sends() -> None:
    """The unreadable screen's two unnumbered options, by word — never by digit."""
    table = js_table("UNIVERSAL_ANSWERS", _WORDED)
    assert table == {"approve": "approve", "reject": "deny"}
    assert set(table.values()) <= set(PERMISSION_KEYS)
