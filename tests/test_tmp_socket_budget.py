"""The suite's own `tmp_path` must leave room for a Unix socket (E19, G1).

Dozens of tests here bind a real `AF_UNIX` socket under `tmp_path`, so the base
pytest hands out is load-bearing and, until this file, unchecked. On macOS
`tempfile.gettempdir()` is `$TMPDIR` — `/var/folders/…/T/`, 47 bytes before
pytest adds a `pytest-of-<user>/pytest-<n>/<test-name>0/` of its own — and the
103-byte budget (`docs/probes/2026-09-20-macos-g1-capture.md` Result 1) is gone
before a test writes a single character.

`tests/conftest.py` picks a short base when the caller has not. This asserts
that the choice actually worked, on whatever platform is running, *and* that the
kernel agrees by binding a socket there. A budget nobody checks is how
`--basetemp=` became something a human had to remember.
"""

from __future__ import annotations

import socket
from pathlib import Path

from shepherd.host.detect import detect_host

#: What a test needs room for beyond its own `tmp_path`: the deepest socket any
#: test in this suite composes is `<tmp_path>/run/shepherd/controld.sock`, and
#: the fixtures that nest one directory deeper are still inside this.
DEEPEST_SUFFIX = "/run/shepherd/controld.sock"

#: Headroom beyond that, so this fails while there is still room to fix it
#: rather than on the day a test name grows by one character.
MINIMUM_SLACK_BYTES = 8


def test_tmp_path_leaves_room_for_a_control_socket(tmp_path: Path) -> None:
    """Arithmetic first: the base plus the deepest suffix fits this platform."""
    budget = detect_host().control_socket("sessiond").socket_path_budget
    assert budget > 0

    composed = f"{tmp_path}{DEEPEST_SUFFIX}"
    size = len(composed.encode("utf-8"))
    assert size + MINIMUM_SLACK_BYTES <= budget, (
        f"pytest's tmp_path is too long for a Unix socket on this platform: "
        f"{size} bytes of {budget} used by {composed!r}. Either the base "
        f"tests/conftest.py picks has grown, or --basetemp was passed something "
        f"long. Nothing in tests/ can bind a socket from here."
    )


def test_a_socket_really_binds_under_tmp_path(tmp_path: Path) -> None:
    """…and the kernel agrees, because arithmetic is not a bind (B1)."""
    directory = tmp_path / "run" / "shepherd"
    directory.mkdir(parents=True)
    path = directory / "controld.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as bound:
        bound.bind(str(path))
        assert path.exists()
