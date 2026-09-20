"""The hook installer, behind `invoke()` (D38.1).

D38's premise "nothing in M1–M3 writes" is false: the hook installer writes. So
`install_hooks`, `uninstall_hooks` and `inspect_hooks` are registered tools from
M1, `blast_class=LOCAL_DESTRUCTIVE`, `audiences={HUMAN}`. In M1 `invoke()` runs
them with no gate; M4 gates them by changing one policy table rather than by
going and finding them. `cli/` (T17) reaches them here, which is also the only
route the consumer boundary leaves open — `cli/` may not import `engines/`.

**The settings path is always an argument** (K3). Nothing in this module points
at `~/.claude`, and the schema marks it required, so a call that omits it fails
at `invoke()` before a handler sees it.
"""

from __future__ import annotations

from pathlib import Path

from shepherd.engines.claude_code.hookd_command import HookEntry
from shepherd.engines.claude_code.hooks_config import (
    HookInspection,
    InstallResult,
    inspect_hooks,
    install_hooks,
    uninstall_hooks,
)
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    ToolDef,
    arg_bool,
    arg_str,
)

_HUMAN_ONLY = frozenset({Audience.HUMAN})

_SETTINGS_PATH_SCHEMA = {
    "type": "object",
    "properties": {"settings_path": {"type": "string"}},
    "required": ["settings_path"],
}

_INSTALL_SCHEMA = {
    "type": "object",
    "properties": {"settings_path": {"type": "string"}, "dry_run": {"type": "boolean"}},
    "required": ["settings_path"],
}


def project_install_result(result: InstallResult) -> dict[str, object]:
    """§13: an explicit whitelist, and the paths as strings — the wire has no `Path`."""
    return {
        "settings_path": str(result.settings_path),
        "backup_path": str(result.backup_path),
        "events_installed": result.events_installed,
        "warnings": list(result.warnings),
        "refused_reason": result.refused_reason,
    }


def project_inspection(inspection: HookInspection) -> dict[str, object]:
    return {
        "installed": inspection.installed,
        "managed_entries": inspection.managed_entries,
        "foreign_entries": inspection.foreign_entries,
        "pre_existing_breakage": list(inspection.pre_existing_breakage),
        "command_matches_current_host": inspection.command_matches_current_host,
    }


def build_hook_tools(entry: HookEntry) -> tuple[ToolDef, ...]:
    """The three, with the host's dispatch entry closed over (P20: one author)."""
    return (
        ToolDef(
            name="install_hooks",
            description="Merge the marked dispatcher entry into a named settings file.",
            input_schema=_INSTALL_SCHEMA,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: project_install_result(
                install_hooks(
                    Path(arg_str(args, "settings_path")),
                    entry,
                    dry_run=arg_bool(args, "dry_run"),
                )
            ),
            audiences=_HUMAN_ONLY,
        ),
        ToolDef(
            name="uninstall_hooks",
            description="Remove exactly our marked entries from a named settings file.",
            input_schema=_SETTINGS_PATH_SCHEMA,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: project_install_result(
                uninstall_hooks(Path(arg_str(args, "settings_path")))
            ),
            audiences=_HUMAN_ONLY,
        ),
        ToolDef(
            name="inspect_hooks",
            description="Report what a named settings file contains, without running the engine.",
            input_schema=_SETTINGS_PATH_SCHEMA,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: project_inspection(
                inspect_hooks(Path(arg_str(args, "settings_path")), entry)
            ),
            audiences=_HUMAN_ONLY,
        ),
    )


def register_hook_tools(entry: HookEntry) -> None:
    """Called by the composition root at startup, before `freeze_registry()`."""
    for tool in build_hook_tools(entry):
        register(tool)
