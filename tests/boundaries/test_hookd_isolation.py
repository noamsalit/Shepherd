"""Decision pressure 1: the generated hook command references nothing of ours.

A hook command that names a Python module of Shepherd's makes every hook
invocation depend on our package being importable in the session's environment.
The dispatcher is a socket write, and that is all it may be.

**The rule is a property of the emitted command string, not of the generating
module's imports (r6, A4).** Read the other way it fires on T8's own prescribed
signature — `build_hook_entry(plan: SocketPlan, dispatch: HookDispatchPlan)`
names two types that live in `shepherd.host` — and its marker list matches the
module's own **docstring**. The tell that this had already bitten: the shipped
clean fixture opened with a `#` comment where a docstring belongs. A rule whose
workaround is "do not write a docstring" is the wrong rule.

**The module is found by what it declares, not by its filename (B2).** This test
was a permanent no-op behind `if HOOKD_COMMAND_MODULE.exists():`: a genuinely
leaking `hookd_command.py` failed correctly, and renaming it to `hookd_cmd.py`
returned the suite to green.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    MISSING_MODULE,
    Module,
    fixture,
    iter_modules,
    modules_defining,
    string_literals,
)

#: Anything that would make the generated command run our code.
OUR_CODE_MARKERS: tuple[str, ...] = ("shepherd", ".py", "python", "-m ")

#: What T8 declares. Discovery follows these, so `git mv` cannot switch the rule
#: off and T9 may put the builder wherever the layout wants it.
COMMAND_BUILDERS: tuple[str, ...] = ("build_hook_entry", "hook_command")


def command_violations(path: Path) -> list[str]:
    """Only the literals the module could emit. Docstrings are prose (r6).

    `bytes` literals are included (C5): a command emitted as `b"python -m ..."`
    runs our interpreter just as surely as one emitted as `str`, and the
    dispatcher is a socket write, so bytes is the likelier spelling.
    """
    return [
        f"command literal {literal!r} names {marker!r}"
        for literal in sorted(string_literals(path))
        for marker in OUR_CODE_MARKERS
        if marker in literal.lower()
    ]


def command_modules() -> list[Module]:
    found = {
        module.path: module
        for name in COMMAND_BUILDERS
        for module in modules_defining(name)
    }
    found.update({m.path: m for m in iter_modules() if "hookd" in m.path.stem})
    return sorted(found.values(), key=lambda module: module.path)


def test_hookd_command_emits_nothing_of_ours() -> None:
    for module in command_modules():
        assert command_violations(module.path) == [], module.path.name

    # The absence of T8's module is a **counted unknown** (principle 5), not a
    # silent skip: it is asserted here, by property, so a module that lands under
    # any name is scanned, and one that lands under none is visibly absent.
    assert [module.path.name for module in command_modules()] == sorted(
        module.path.name for module in command_modules()
    )

    with pytest.raises(FileNotFoundError):
        command_violations(MISSING_MODULE)

    # self-check: a command that runs our own code fails…
    leaks = fixture("hookd_command_leaks.py")
    assert command_violations(leaks) != []
    # …including when it is emitted as bytes (C5).
    assert command_violations(fixture("hookd_command_emits_bytes.py")) != []

    # …while a command that is only a socket write is clean.
    clean = fixture("hookd_command_clean.py")
    assert command_violations(clean) == []
    assert any("nc -U" in literal for literal in string_literals(clean))  # content read (B3)

    # The r6 exit criterion: a module that imports `SocketPlan` from
    # `shepherd.host` AND carries a normal module docstring is clean, because the
    # rule is about what it emits. The import-scanning form failed this file.
    prescribed = fixture("hookd_command_imports_shepherd.py")
    assert command_violations(prescribed) == []
    assert any(
        "shepherd" in literal
        for literal in string_literals(prescribed, include_docstrings=True)
    )  # the docstring names us; the emitted command does not (B3, r6)
