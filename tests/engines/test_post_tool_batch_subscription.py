"""T22 — M1's T18-2 checklist, executed verbatim against a throwaway file.

The checklist, preserved in `docs/plans/2026-09-16-m1-BLOCKERS.md` under T18-2
and quoted here so it is not paraphrased into something easier:

  1. add the name to `SUBSCRIBED_EVENTS`;
  2. re-review the installer's dry-run diff against a throwaway settings file;
  3. re-run `test_hookd_latency_under_10ms` against E34's 3.2 ms budget;
  4. assert the real settings file's sha256 is unchanged.

**The diff is taken against a POPULATED copy, not the shipped `{}`.**
`tests/e2e/conftest.py` writes `settings.write_text("{}\\n")` — *"an explicit,
empty settings file"*, its own docstring says. A merge reviewed against `{}`
cannot exhibit the bad-merge-with-a-populated-file risk this task exists to
check: there is nothing to merge into, no pre-existing `hooks` key, no user
entry to preserve, and none of `hooks_config.py`'s three stated properties is
exercised. The fixture below is a throwaway copy carrying **Shepherd's own
installed block, produced by the shipped `install_hooks`** — never hand-written,
because a hand-written block is the test supplying its own input shape — plus
one **foreign** entry on `PreToolUse` that the diff must leave untouched.

**T24's `installed_settings` fixture does not exist in the tree yet**, so this
module builds it. When T24 lands, this is the fixture to move, not to duplicate.

The real `~/.claude/settings.json` is never read and never written here. That is
not a docstring promise: `tests/conftest.py` carries a `sys.addaudithook` over
the whole suite that records every open of that exact path and asserts no write
mode ever appears, with the session guard's own two reads as its proof of life.

Seam: `install_hooks(settings_path, entry)` — the installer's public interface,
the same one `shepherd install-hooks` reaches through `invoke()`.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

import conftest
import pytest

from shepherd.engines.claude_code.events import ALL_HOOK_EVENT_NAMES, SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hookd_command import HookEntry
from shepherd.engines.claude_code import hooks_config
from shepherd.engines.claude_code.hooks_config import (
    MANAGED_MARKER,
    install_hooks,
    inspect_hooks,
)
from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, LinuxHost

#: The one event that carries a refusal, named **here in the test** and nowhere
#: in `src/` outside `engines/`: §5.0's engine-vocabulary rule fails the build on
#: a hook event name in a literal anywhere else, and it is not scanned over
#: `tests/`.
REFUSAL_EVENT = "PostToolBatch"

#: The count M1 asserted (24) plus this task's one name. Written as the sum so
#: the arithmetic is visible rather than a number a later reader must trust.
EXPECTED_SUBSCRIBED = 24 + 1

#: A user's own hook, in the captured shape (data-schemas §"Hooks config
#: schema"). It sits on `PreToolUse` — a `CRITICAL_EVENT`, and the event our own
#: block also writes to — because an entry on an event we never touch would
#: survive any implementation at all.
FOREIGN_COMMAND = "/usr/local/bin/audit.sh"
FOREIGN_GROUP: dict[str, object] = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": FOREIGN_COMMAND, "timeout": 15}],
}


@pytest.fixture()
def entry() -> HookEntry:
    """The real host's dispatch command — the same construction
    `tests/engines/test_hooks_install.py` uses, so the bytes written here are
    the bytes the product writes."""
    plan = SocketPlan(
        path=Path("/run/user/0/shepherd/sessiond.sock"),
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )
    built = build_hook_entry(plan, LinuxHost().hook_dispatch(plan))
    if not built.available:
        pytest.skip(f"no dispatcher on this host: {built.reason}")
    return built


#: `SUBSCRIBED_EVENTS` as it stood **before** this task — M1's 24 names — derived
#: by removing the one name added rather than retyped, so the fixture cannot
#: drift from the constant it is the "before" of.
PRE_CHANGE_EVENTS: tuple[str, ...] = tuple(
    name for name in SUBSCRIBED_EVENTS if name != REFUSAL_EVENT
)


@pytest.fixture()
def installed_settings(
    tmp_path: Path, entry: HookEntry, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A POPULATED throwaway settings file: a foreign hook plus **our own block,
    written by the shipped installer** at the **pre-change** subscription.

    Produced rather than typed. A hand-written "installed" block would only
    prove the fixture agrees with the fixture; this one is whatever
    `install_hooks` really writes. Pinning the constant to the 24 names is what
    makes the later diff *the* diff under review — installing twice at the same
    subscription is idempotent and its diff is empty, which would pass a
    "nothing was removed" assertion while proving nothing at all.
    """
    path = tmp_path / "throwaway-settings.json"
    path.write_text(
        json.dumps(
            {
                "model": "claude-haiku-4-5-20251001",
                "hooks": {"PreToolUse": [FOREIGN_GROUP]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hooks_config, "SUBSCRIBED_EVENTS", PRE_CHANGE_EVENTS)
    result = install_hooks(path, entry)
    assert result.refused_reason is None, result.refused_reason
    assert result.events_installed == len(PRE_CHANGE_EVENTS) == len(SUBSCRIBED_EVENTS) - 1
    assert REFUSAL_EVENT not in path.read_text(encoding="utf-8"), (
        "the fixture must be the file as it stood before this task"
    )
    monkeypatch.undo()
    return path


def test_post_tool_batch_is_subscribed() -> None:
    """Replaces `test_post_tool_batch_is_still_not_subscribed`, and **names the
    task that replaced it** (M3 T22, plan §Task 22, acceptance clause 13).

    Goes red if the name is removed again. Whoever removes it is removing the
    only event that records a permission refusal or a hook block, and with it
    the only thing that lets `TOOL_BLOCKED_BY_HOOK` and
    `TOOL_PERMISSION_REFUSED` ever move — read M1 blocker T18-2 and this
    module's docstring before doing it.
    """
    assert REFUSAL_EVENT in ALL_HOOK_EVENT_NAMES, "the engine no longer has this event"
    assert REFUSAL_EVENT in SUBSCRIBED_EVENTS
    assert len(SUBSCRIBED_EVENTS) == EXPECTED_SUBSCRIBED
    assert len(set(SUBSCRIBED_EVENTS)) == len(SUBSCRIBED_EVENTS), "a name was duplicated"


def test_the_installer_diff_is_reviewed_against_a_populated_throwaway_file(
    installed_settings: Path, entry: HookEntry, tmp_path: Path
) -> None:
    """Checklist item 2, and the check that the file under review is a real one.

    Goes red if any test path resolves to the real settings file, **and** if the
    file the diff is taken against has no pre-existing `hooks` key — a diff
    against `{}` proves only that a merge into nothing works.
    """
    before = installed_settings.read_text(encoding="utf-8")
    loaded: object = json.loads(before)
    assert isinstance(loaded, dict)
    hooks = loaded.get("hooks")
    assert isinstance(hooks, dict) and hooks, "the diff must be taken against a POPULATED file"
    assert FOREIGN_GROUP in hooks["PreToolUse"], "the foreign entry is the point"

    # K3, asserted on the value rather than promised in prose.
    assert tmp_path in installed_settings.parents
    assert ".claude" not in str(installed_settings)

    dry = install_hooks(installed_settings, entry, dry_run=True)
    assert dry.refused_reason is None
    assert installed_settings.read_text(encoding="utf-8") == before, "a dry run wrote bytes"

    applied = install_hooks(installed_settings, entry)
    assert applied.refused_reason is None
    after = installed_settings.read_text(encoding="utf-8")
    added = [
        line
        for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm=""
        )
        if line.startswith("+") and not line.startswith("+++")
    ]
    removed = [
        line
        for line in difflib.unified_diff(
            before.splitlines(), after.splitlines(), lineterm=""
        )
        if line.startswith("-") and not line.startswith("---")
    ]

    # The whole diff is one added event block. Nothing is removed — which is the
    # property `{}` could never test, because `{}` has nothing to remove.
    assert removed == [], removed
    assert any(REFUSAL_EVENT in line for line in added), added
    assert not any(FOREIGN_COMMAND in line for line in added + removed)


def test_a_foreign_hook_entry_survives_the_subscription_change(
    installed_settings: Path, entry: HookEntry
) -> None:
    """`hooks_config.py`'s first stated property — "nothing is overwritten that we
    did not understand" — at the one event where ours and theirs share a key.

    Goes red if the added 25th event disturbs an entry Shepherd does not own.
    """
    install_hooks(installed_settings, entry)

    decoded: object = json.loads(installed_settings.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    hooks = decoded["hooks"]
    assert isinstance(hooks, dict)
    groups = hooks["PreToolUse"]
    assert isinstance(groups, list)
    assert FOREIGN_GROUP in groups, "the user's own hook was changed"
    assert decoded["model"] == "claude-haiku-4-5-20251001", "a sibling key was lost"

    inspected = inspect_hooks(installed_settings, entry)
    assert inspected.foreign_entries == 1
    assert inspected.managed_entries == len(SUBSCRIBED_EVENTS)
    # Arrival before absence: our own block really is on the new event.
    ours = [group for group in groups if group.get(MANAGED_MARKER) is True]
    assert len(ours) == 1
    assert REFUSAL_EVENT in hooks


def test_the_refusal_event_gets_a_managed_entry_of_its_own(
    installed_settings: Path, entry: HookEntry
) -> None:
    """The 25th name reaches the file, marked, with an explicit timeout (E18/C7).

    Goes red if the name is in the tuple but the installer's loop never writes
    it — a constant edited without the write being observed.
    """
    install_hooks(installed_settings, entry)

    decoded: object = json.loads(installed_settings.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    hooks = decoded["hooks"]
    assert isinstance(hooks, dict)
    groups = hooks[REFUSAL_EVENT]
    assert isinstance(groups, list) and len(groups) == 1
    group = groups[0]
    assert isinstance(group, dict)
    assert group[MANAGED_MARKER] is True
    entries = group["hooks"]
    assert isinstance(entries, list) and len(entries) == 1
    written = entries[0]
    assert isinstance(written, dict)
    assert written["timeout"] == entry.timeout_s
    assert written["command"] == entry.command


# ----- checklist item 4: the real settings file, proved rather than promised --


def test_the_audit_hook_is_alive_on_the_real_settings_path() -> None:
    """The negative control for the zero-writes claim, with a real exit code.

    A hook that never fires reports zero writes for every file in the universe.
    The session guard in `tests/conftest.py` opens the real settings file for
    **reading** once before any test runs, so by the time this executes the hook
    must already have recorded it. If this is empty, the zero-writes assertion
    at session end is vacuous and this says so here rather than at teardown.
    """
    assert conftest.SETTINGS_OPENS, "the audit hook recorded nothing — it is dead"
    assert all(
        not conftest.open_is_a_write(mode, flags)
        for mode, flags in conftest.SETTINGS_OPENS
    ), conftest.SETTINGS_OPENS


def test_the_audit_hook_fires_on_a_real_write(tmp_path: Path) -> None:
    """…and it fires on a **write**, which the control above cannot show.

    Planted against a throwaway file, never the real one (T10-R1 rule 3: never
    plant in a path whose default target is a real user file). Both spellings of
    intent are exercised, because `os.open` carries flags and `io.open` a mode
    string, and a classifier tested against one of them is untested against the
    other.
    """
    recorded: list[tuple[str | None, int | None]] = []
    target = tmp_path / "settings.json"

    def probe(event: str, args: tuple[object, ...]) -> None:
        if event != "open" or not args:
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        if os.fspath(path) != str(target):
            return
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else None
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else None
        recorded.append((mode, flags))

    sys.addaudithook(probe)
    target.write_text("{}\n", encoding="utf-8")  # io.open: a mode string
    descriptor = os.open(target, os.O_WRONLY | os.O_APPEND)  # os.open: flags
    os.close(descriptor)

    assert len(recorded) == 2, recorded
    assert all(conftest.open_is_a_write(mode, flags) for mode, flags in recorded), recorded
    # …and it stays quiet on a read, or "is this a write?" is not a question.
    target.read_text(encoding="utf-8")
    assert len(recorded) == 3, recorded
    assert not conftest.open_is_a_write(*recorded[2]), recorded[2]


def test_the_real_settings_file_is_byte_identical(
    real_user_settings: conftest.SettingsObservation,
) -> None:
    """Checklist item 4, stated as the clause states it.

    The digest is the session's **pre-image**, taken before any test ran, and is
    compared against the file as it stands now — inside the very module that
    subscribes a new hook event, which is the change T18-2 refused to make
    without this assertion.
    """
    now = conftest.observe_settings(conftest.real_config_dir())

    assert now.digest == real_user_settings.digest
    assert now.siblings == real_user_settings.siblings
