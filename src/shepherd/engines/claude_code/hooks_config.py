"""T9: merge a marked, idempotent hook block into a settings file — or refuse.

**The settings path is always a parameter.** There is no default, and no value
in this module points at `~/.claude` (K3). The caller chooses the file; the
tests choose throwaway ones.

Three properties, each bought by a measured failure mode in
data-schemas §"Hooks config schema":

  * **Everything we write is marked** with `_shepherd_managed` — on the matcher
    group *and* on the entry — so uninstall removes exactly our entries and a
    user's own hooks are untouched. The extra key is accepted silently by the
    validator (R03 extra_keys) and the hooks still fire.
  * **Back up, write, validate, restore on failure** (C6/E16). One malformed
    entry on `PreToolUse` or `PermissionRequest` disables *every* hook in the
    file — including ours — and invalid JSON voids the file entirely. Neither is
    reported by `-p`; only `claude doctor` says anything. So the check is ours to
    make, after the write, against the bytes that actually landed.
  * **Nothing is overwritten that we did not understand.** Invalid JSON, a
    `hooks` key that is not an object, or an event whose value is not an array
    are all *refusals or warnings*, never a silent rewrite of the user's file.

The command text is never spelled here: it arrives in a `HookEntry` built from
`HostPlatform.hook_dispatch()` (P20), and its per-entry `timeout` is explicit
because the default is 600 s of blocking (E18, C7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shepherd.engines.claude_code.events import CRITICAL_EVENTS, SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hookd_command import HookEntry

#: The key that makes our entries removable. Accepted silently by the validator
#: on both the group and the entry (data-schemas §"User-scope hooks…").
MANAGED_MARKER = "_shepherd_managed"

#: A `matcher` of `"*"` is accepted on events that have no matchers at all
#: (R03 no_matcher_key / §"Hooks config schema").
MATCH_ALL = "*"

HOOKS_KEY = "hooks"
COMMAND_TYPE = "command"
BACKUP_SUFFIX = ".shepherd-backup"


@dataclass(frozen=True)
class InstallResult:
    """What happened, in enough detail to undo it.

    `backup_path` equals `settings_path` when **nothing was written** — a
    refusal or a dry run — so "no backup exists" is a value rather than a lie.
    For `uninstall_hooks`, `events_installed` counts the events our entries were
    removed from.
    """

    settings_path: Path
    backup_path: Path
    events_installed: int
    warnings: tuple[str, ...]
    refused_reason: str | None


@dataclass(frozen=True)
class HookInspection:
    """`doctor`-grade reading of a settings file, without running `claude`."""

    installed: bool
    managed_entries: int
    foreign_entries: int
    pre_existing_breakage: tuple[str, ...]
    command_matches_current_host: bool


def write_bytes(path: Path, payload: bytes) -> None:
    """The one write seam for the merged file, so a write failure is injectable."""
    path.write_bytes(payload)


def _as_mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return None


def _as_list(value: object) -> list[object] | None:
    return list(value) if isinstance(value, list) else None


def _is_managed(value: object) -> bool:
    mapping = _as_mapping(value)
    return mapping is not None and mapping.get(MANAGED_MARKER) is True


def _load(path: Path) -> tuple[dict[str, object] | None, str | None]:
    """`(settings, refusal)`. A missing or empty file is an empty settings object."""
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return {}, None
    if raw.strip() == b"":
        return {}, None
    try:
        decoded: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f"settings file is not valid JSON, so it is left untouched: {error}"
    mapping = _as_mapping(decoded)
    if mapping is None:
        return None, "settings file is not a JSON object, so it is left untouched"
    return mapping, None


def _entry_problems(entry: object) -> list[str]:
    mapping = _as_mapping(entry)
    if mapping is None:
        return ["entry is not an object"]
    problems: list[str] = []
    kind = mapping.get("type")
    if kind != COMMAND_TYPE and not isinstance(kind, str):
        problems.append("entry has no type")
    if kind == COMMAND_TYPE:
        command = mapping.get("command")
        if not isinstance(command, str) or command == "":
            problems.append("command entry has no command string")
    timeout = mapping.get("timeout")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        problems.append(f"timeout is not a positive number: {timeout!r}")
    return problems


def _breakage(settings: dict[str, object]) -> tuple[str, ...]:
    """Every reason Claude Code would drop something in this file (E16)."""
    raw_hooks = settings.get(HOOKS_KEY)
    if raw_hooks is None:
        return ()
    hooks = _as_mapping(raw_hooks)
    if hooks is None:
        return (f"{HOOKS_KEY} is not an object: every hook in this file is ignored",)
    found: list[str] = []
    for event, raw_groups in hooks.items():
        groups = _as_list(raw_groups)
        if groups is None:
            found.append(f"{event}: not an array of matchers, so this event is ignored")
            continue
        for index, raw_group in enumerate(groups):
            group = _as_mapping(raw_group)
            if group is None:
                found.append(f"{event}.{index}: matcher group is not an object")
                continue
            entries = _as_list(group.get(HOOKS_KEY))
            if entries is None:
                found.append(f"{event}.{index}: group has no hooks array")
                continue
            for position, entry in enumerate(entries):
                for problem in _entry_problems(entry):
                    message = f"{event}.{index}.hooks.{position}: {problem}"
                    if event in CRITICAL_EVENTS:
                        message += " — this disables every hook in the file"
                    found.append(message)
    return tuple(found)


def _managed_group(entry: HookEntry) -> dict[str, object]:
    """The captured shape: a matcher group holding one command entry."""
    return {
        "matcher": MATCH_ALL,
        MANAGED_MARKER: True,
        HOOKS_KEY: [
            {
                "type": COMMAND_TYPE,
                "command": entry.command,
                "timeout": entry.timeout_s,
                MANAGED_MARKER: True,
            }
        ],
    }


def _strip_managed(hooks: dict[str, object]) -> tuple[dict[str, object], int]:
    """Remove exactly our groups and entries. Foreign ones are copied through."""
    kept: dict[str, object] = {}
    removed = 0
    for event, raw_groups in hooks.items():
        groups = _as_list(raw_groups)
        if groups is None:
            kept[event] = raw_groups
            continue
        surviving: list[object] = []
        for raw_group in groups:
            if _is_managed(raw_group):
                removed += 1
                continue
            group = _as_mapping(raw_group)
            entries = None if group is None else _as_list(group.get(HOOKS_KEY))
            if group is None or entries is None:
                surviving.append(raw_group)
                continue
            remaining = [entry for entry in entries if not _is_managed(entry)]
            if len(remaining) == len(entries):
                surviving.append(raw_group)
                continue
            removed += 1
            if remaining:
                group[HOOKS_KEY] = remaining
                surviving.append(group)
        if surviving or not groups:
            kept[event] = surviving
    return kept, removed


def _merge(settings: dict[str, object], entry: HookEntry) -> tuple[dict[str, object], int, list[str]]:
    merged = dict(settings)
    hooks = _as_mapping(merged.get(HOOKS_KEY, {})) or {}
    stripped, _ = _strip_managed(hooks)
    warnings: list[str] = []
    installed = 0
    for event in SUBSCRIBED_EVENTS:
        existing = stripped.get(event, [])
        groups = _as_list(existing)
        if groups is None:
            warnings.append(f"{event}: not an array of matchers — left untouched, not registered")
            continue
        stripped[event] = [*groups, _managed_group(entry)]
        installed += 1
    merged[HOOKS_KEY] = stripped
    return merged, installed, warnings


def _serialise(settings: dict[str, object]) -> bytes:
    """Byte-stable for equal inputs (E17), so a second install is a no-op."""
    return (json.dumps(settings, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _written_problems(path: Path, entry: HookEntry, expected_events: int) -> tuple[str, ...]:
    """Re-read what landed and check it, because `-p` never will (E16)."""
    settings, refusal = _load(path)
    if settings is None:
        return (refusal or "unreadable after write",)
    hooks = _as_mapping(settings.get(HOOKS_KEY))
    if hooks is None:
        return (f"{HOOKS_KEY} is missing or not an object after the write",)
    found = 0
    for event in SUBSCRIBED_EVENTS:
        for group in _as_list(hooks.get(event)) or []:
            mapping = _as_mapping(group)
            if mapping is None or not _is_managed(mapping):
                continue
            for item in _as_list(mapping.get(HOOKS_KEY)) or []:
                candidate = _as_mapping(item)
                if candidate is None:
                    continue
                if candidate.get("command") != entry.command:
                    return (f"{event}: the command that landed is not the host's",)
                found += 1
    if found != expected_events:
        return (f"{found} managed entries landed, expected {expected_events}",)
    return ()


def _restore(path: Path, pre_image: bytes | None) -> None:
    """Rollback never goes through the write seam — that is what just failed."""
    if pre_image is None:
        path.unlink(missing_ok=True)
        return
    path.write_bytes(pre_image)


def _pre_image(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _refusal(settings_path: Path, reason: str, warnings: tuple[str, ...] = ()) -> InstallResult:
    return InstallResult(
        settings_path=settings_path,
        backup_path=settings_path,
        events_installed=0,
        warnings=warnings,
        refused_reason=reason,
    )


def _commit(
    settings_path: Path,
    merged: dict[str, object],
    entry: HookEntry,
    installed: int,
    warnings: tuple[str, ...],
) -> InstallResult:
    """Back up, write, validate, restore on failure (C6)."""
    pre_image = _pre_image(settings_path)
    backup_path = settings_path.with_name(settings_path.name + BACKUP_SUFFIX)
    if pre_image is not None:
        backup_path.write_bytes(pre_image)
    try:
        write_bytes(settings_path, _serialise(merged))
        problems = _written_problems(settings_path, entry, installed)
    except OSError as error:
        problems = (str(error),)
    if problems:
        _restore(settings_path, pre_image)
        return _refusal(
            settings_path,
            "the merged settings file did not validate and was rolled back: "
            + "; ".join(problems),
            warnings,
        )
    return InstallResult(
        settings_path=settings_path,
        backup_path=backup_path if pre_image is not None else settings_path,
        events_installed=installed,
        warnings=warnings,
        refused_reason=None,
    )


def install_hooks(settings_path: Path, entry: HookEntry, dry_run: bool = False) -> InstallResult:
    """Merge one marked dispatcher entry per subscribed event, or refuse."""
    if not entry.available:
        return _refusal(settings_path, entry.reason)
    settings, refusal = _load(settings_path)
    if settings is None:
        return _refusal(settings_path, refusal or "settings file is unreadable")
    raw_hooks = settings.get(HOOKS_KEY)
    if raw_hooks is not None and _as_mapping(raw_hooks) is None:
        return _refusal(
            settings_path,
            f"{HOOKS_KEY} is not an object: every hook in this file is already ignored",
        )
    breakage = _breakage(settings)
    merged, installed, merge_warnings = _merge(settings, entry)
    warnings = (*breakage, *merge_warnings)
    if dry_run:
        return InstallResult(
            settings_path=settings_path,
            backup_path=settings_path,
            events_installed=installed,
            warnings=warnings,
            refused_reason=None,
        )
    return _commit(settings_path, merged, entry, installed, warnings)


def uninstall_hooks(settings_path: Path) -> InstallResult:
    """Remove exactly our entries. A file with none of ours is left byte-identical."""
    settings, refusal = _load(settings_path)
    if settings is None:
        return _refusal(settings_path, refusal or "settings file is unreadable")
    hooks = _as_mapping(settings.get(HOOKS_KEY))
    if hooks is None:
        return InstallResult(settings_path, settings_path, 0, _breakage(settings), None)
    stripped, removed = _strip_managed(hooks)
    if removed == 0:
        return InstallResult(settings_path, settings_path, 0, _breakage(settings), None)
    remaining = {event: groups for event, groups in stripped.items() if groups != []}
    merged = dict(settings)
    if remaining:
        merged[HOOKS_KEY] = remaining
    else:
        merged.pop(HOOKS_KEY, None)
    pre_image = _pre_image(settings_path)
    backup_path = settings_path.with_name(settings_path.name + BACKUP_SUFFIX)
    if pre_image is not None:
        backup_path.write_bytes(pre_image)
    try:
        write_bytes(settings_path, _serialise(merged))
        settings_after, refusal_after = _load(settings_path)
    except OSError as error:
        settings_after, refusal_after = None, str(error)
    if settings_after is None:
        _restore(settings_path, pre_image)
        return _refusal(
            settings_path,
            f"the settings file did not validate after removal and was rolled back: {refusal_after}",
        )
    return InstallResult(
        settings_path=settings_path,
        backup_path=backup_path if pre_image is not None else settings_path,
        events_installed=removed,
        warnings=_breakage(settings_after),
        refused_reason=None,
    )


def inspect_hooks(settings_path: Path, entry: HookEntry | None = None) -> HookInspection:
    """Count what is there. `entry` is the command to compare against.

    Without an `entry` there is nothing to compare the installed command to, so
    `command_matches_current_host` is **False** — unknown is not "matches"
    (principle 5).
    """
    settings, refusal = _load(settings_path)
    if settings is None:
        return HookInspection(
            installed=False,
            managed_entries=0,
            foreign_entries=0,
            pre_existing_breakage=(refusal or "unreadable",),
            command_matches_current_host=False,
        )
    breakage = _breakage(settings)
    hooks = _as_mapping(settings.get(HOOKS_KEY)) or {}
    managed = 0
    foreign = 0
    commands: list[str] = []
    for raw_groups in hooks.values():
        for raw_group in _as_list(raw_groups) or []:
            group = _as_mapping(raw_group)
            if group is None:
                continue
            for item in _as_list(group.get(HOOKS_KEY)) or []:
                candidate = _as_mapping(item)
                if candidate is None:
                    continue
                if _is_managed(group) or _is_managed(candidate):
                    managed += 1
                    command = candidate.get("command")
                    commands.append(command if isinstance(command, str) else "")
                else:
                    foreign += 1
    matches = (
        entry is not None
        and commands != []
        and all(command == entry.command for command in commands)
    )
    return HookInspection(
        installed=managed > 0,
        managed_entries=managed,
        foreign_entries=foreign,
        pre_existing_breakage=breakage,
        command_matches_current_host=matches,
    )
