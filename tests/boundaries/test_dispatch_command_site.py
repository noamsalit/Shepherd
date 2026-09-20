"""P20: the dispatch command has one definition **package**, `shepherd.host`.

A package, not a file (r4 A4): `host/linux.py` and `host/mac.py` must each carry
their own command — the rule forbids a second *authority*, not a second
*driver*. Every other module reaches the command through
`HostPlatform.hook_dispatch()`.

The scan reads the file before it consults the package (B1). It used to return
early on `shepherd.host` *before opening the file*, and its one negative
self-check passed exactly that package — so emptying `host_mac_dispatch.py` to
`X = 1` kept this test green, and so did deleting it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    DISPATCH_LITERALS,
    HOST_ONLY_PACKAGE,
    MISSING_MODULE,
    fixture,
    in_package,
    iter_modules,
    mentions_token,
    string_literals,
)


def dispatch_violations(path: Path, package: str) -> list[str]:
    found = [
        f"{package}: dispatch literal {literal!r} outside host/"
        for literal in sorted(string_literals(path))
        for marker in DISPATCH_LITERALS
        if literal.strip() == marker or mentions_token(literal, marker)
    ]
    return [] if in_package(package, HOST_ONLY_PACKAGE) else found


def test_dispatch_command_has_one_definition_site() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in dispatch_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        dispatch_violations(MISSING_MODULE, HOST_ONLY_PACKAGE)

    # self-check: a second definition site anywhere else fails…
    second_site = fixture("engines_builds_dispatch_command.py")
    assert dispatch_violations(second_site, "shepherd.engines.claude_code") != []
    # …including when the command is spelled in bytes, which is how a socket
    # write is most likely to spell it (C5).
    bytes_site = fixture("engines_builds_dispatch_command_bytes.py")
    assert dispatch_violations(bytes_site, "shepherd.engines.claude_code") != []

    # …while MacHost's own differing command inside host/ is clean
    # (negative fixture 3: two drivers, one authority).
    mac = fixture("host_mac_dispatch.py")
    assert dispatch_violations(mac, HOST_ONLY_PACKAGE) == []
    # …and THAT is proved by the same file firing when it is not host/ (B1):
    # the exemption is what silences it, not an unread file.
    assert dispatch_violations(mac, "shepherd.engines") != []
