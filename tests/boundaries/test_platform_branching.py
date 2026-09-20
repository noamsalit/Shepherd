"""D55 made mechanical: nothing outside `host/` may branch on the platform.

Path literals and identifiers are matched against **different AST node classes**
and never against each other, so a field name can never trip a path-literal rule
(that is what killed the revision-2 `sun_path` scan — F4).

Two r6 widenings, each because the r5 form was proven defeatable by a one-liner:

* identifiers are resolved to their **origin** before matching, exactly as
  `module_imports` has always resolved imports. `import sys as s; s.platform`,
  `from sys import platform`, `import platform as pf; pf.system()` and
  `from os import uname` all used to be clean, and the `from x import y` forms
  are the important half — they leave no dotted chain to enumerate;
* path literals match at **word boundaries** and skip docstrings, so `/proc`
  does not fire on `/procedure` and a `doctor` help string may describe what it
  does. A boundary test that cries wolf gets an exemption added to it, which is
  the same death ADR-1 describes, reached from the other side.

`test_kind_is_never_branched_on` lives here for the same reason: it is a
"do not branch on this" rule (E35, F3 — `entrypoint` is the discriminator).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _imports import (
    HOST_ONLY_PACKAGE,
    MISSING_MODULE,
    PLATFORM_IDENTIFIERS,
    PLATFORM_PATH_LITERALS,
    fixture,
    identifiers,
    in_package,
    iter_modules,
    mentions_token,
    parsed,
    resolved_identifiers,
    string_literals,
)

#: The brief requires these four asserted explicitly and by name; the rule is
#: enforced package-wide so no future package can quietly become the exception.
NAMED_PACKAGES: tuple[str, ...] = (
    "shepherd.signals",
    "shepherd.store",
    "shepherd.web",
    "shepherd.cli",
)


def platform_violations(path: Path, package: str) -> list[str]:
    """Every scan reads the file BEFORE it consults the package (B1).

    The exemption used to be an early return above the open, and the self-check
    handed it the exempt package — so it returned `[]` for a nonexistent path and
    emptying `host_mac_dispatch.py` to `X = 1` kept its test green.
    """
    found = [
        f"{package}: platform path literal {marker!r} in {literal!r}"
        for literal in sorted(string_literals(path))
        for marker in PLATFORM_PATH_LITERALS
        if mentions_token(literal, marker)
    ]
    names = resolved_identifiers(path)
    found += [
        f"{package}: platform identifier {marker!r}"
        for marker in PLATFORM_IDENTIFIERS
        if marker in names
    ]
    return [] if in_package(package, HOST_ONLY_PACKAGE) else found


def kind_branch_violations(path: Path, package: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            touches_kind = any(isinstance(o, ast.Attribute) and o.attr == "kind" for o in operands)
            against_literal = any(
                isinstance(o, ast.Constant) and isinstance(o.value, str) for o in operands
            )
            if touches_kind and against_literal:
                found.append(f"{package}: .kind compared against a string literal")
        elif isinstance(node, ast.Match):
            subject = node.subject
            if isinstance(subject, ast.Attribute) and subject.attr == "kind":
                for case in node.cases:
                    pattern = case.pattern
                    if isinstance(pattern, ast.MatchValue) and isinstance(
                        pattern.value, ast.Constant
                    ):
                        found.append(f"{package}: .kind matched against a literal")
    return found


def test_no_platform_branching_outside_host() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in platform_violations(module.path, module.package)
    ]
    assert violations == []

    # Asserted explicitly and by name, per the brief.
    scanned = {module.package for module in iter_modules()}
    for named in NAMED_PACKAGES:
        assert named in scanned, f"{named} is not on the analysis path"
        assert [
            message
            for module in iter_modules()
            if in_package(module.package, named)
            for message in platform_violations(module.path, module.package)
        ] == []

    # B1: even for the exempt package, a missing file must raise, not return [].
    with pytest.raises(FileNotFoundError):
        platform_violations(MISSING_MODULE, HOST_ONLY_PACKAGE)

    # self-check: a path literal and an identifier are caught independently…
    assert platform_violations(fixture("signals_reads_proc.py"), "shepherd.signals") != []
    assert platform_violations(fixture("cli_branches_on_sys_platform.py"), "shepherd.cli") != []
    # …including a path literal spelled as bytes (C5: the transport layer).
    assert platform_violations(fixture("signals_reads_proc_bytes.py"), "shepherd.signals") != []
    # …and every alias spelling of every origin symbol (A2). The `from x import y`
    # forms leave no dotted chain at all, so no enumeration of spellings sees them.
    for name in (
        "cli_platform_alias_import.py",  # import sys as s; s.platform
        "cli_platform_from_import.py",  # from sys import platform
        "cli_platform_module_alias.py",  # import platform as pf; pf.system()
        "cli_uname_from_import.py",  # from os import uname
        "cli_branches_on_os_name.py",  # os.name — the other common way
        "cli_reads_platform_machine.py",  # platform.machine()
        "cli_reads_sysconfig_platform.py",  # sysconfig.get_platform()
    ):
        assert platform_violations(fixture(name), "shepherd.cli") != [], name

    # …the same code inside host/ is the one place it belongs…
    proc = fixture("signals_reads_proc.py")
    assert platform_violations(proc, HOST_ONLY_PACKAGE) == []
    # …and that exemption is proved by the same file firing outside host/ (B3),
    # which is asserted above, so an emptied fixture cannot pass both halves.

    # Negative fixtures, each with its content asserted rather than assumed.
    budget = fixture("engines_reads_socket_budget.py")
    assert platform_violations(budget, "shepherd.engines") == []
    assert "socket_path_budget" in identifiers(budget)  # the content IS read (B3)

    procedure = fixture("signals_says_procedure.py")
    assert platform_violations(procedure, "shepherd.signals") == []
    assert any("/procedure" in literal for literal in string_literals(procedure))

    prose = fixture("cli_docstring_mentions_launchctl.py")
    assert platform_violations(prose, "shepherd.cli") == []
    # …and the docstring exemption is what silences it, not an unopened file:
    assert any(
        mentions_token(literal, marker)
        for literal in string_literals(prose, include_docstrings=True)
        for marker in PLATFORM_PATH_LITERALS
    )


def test_kind_is_never_branched_on() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in kind_branch_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        kind_branch_violations(MISSING_MODULE, "shepherd.signals")

    # self-check: branching on `.kind` fails; comparing against the enum member
    # a layer below defines is how it is meant to be written.
    assert kind_branch_violations(fixture("registry_branches_on_kind.py"), "shepherd.signals") != []
    entrypoint = fixture("registry_uses_entrypoint.py")
    assert kind_branch_violations(entrypoint, "shepherd.signals") == []
    # …with the negative fixture's content asserted (B3): it really does compare
    # a kind — against the enum member, which is the whole point.
    assert "SignalKind.SESSION_STOPPED" in identifiers(entrypoint)
    assert "entrypoint" in identifiers(entrypoint)
