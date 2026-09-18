"""The engine's event vocabulary — the product's own copy of the 33 names.

**Two independent sources, reconciled by one test (r4, A7).** The list below is
a literal, transcribed from the `claude doctor` capture that enumerates it:
`docs/probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt`
("Valid events: …"), re-confirmed present in 2.1.273 by Task 1's drift check
(G12). `tests/boundaries/` parses that same capture independently, and
`test_hook_event_names_match_the_doctor_capture` asserts the two are equal, in
order, 33 of them.

It is a literal here and **not** a parse, because parsing it at runtime would
make the installed package depend on the probe tree, which is not shipped —
M6's packaging would break, and only after installation (G13, F11).
`hooks/binary/hook-events.json` is not a source either: it is empty on disk
(`{"offset":null,"count":0,"events":null}`) though data-schemas cites a count of
33 from it.

**Order is part of the data.** The capture lists the names in the engine's own
order; the reconciliation test compares sequences, so a reordering fails.
"""

from __future__ import annotations

#: The 33 names, in the capture's order.
ALL_HOOK_EVENT_NAMES: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "Notification",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PreModelSwitch",
    "PostModelSwitch",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
    "DirectoryAdded",
    "MessageDisplay",
)

#: What Shepherd registers a dispatcher for: §8's "Events subscribed" list, minus
#: what it cannot use. **`WorktreeCreate` is deliberately absent** — any command
#: hook on it breaks `--worktree` (data-schemas §WorktreeCreate).
#:
#: **`PostToolBatch` is here as of M3 T22**, which closed M1 blocker T18-2 by
#: executing that entry's four-item checklist verbatim (add the name; re-review
#: the installer's dry-run diff against a **populated throwaway** settings file;
#: re-run the `hookd` latency probe against E34's budget; assert the real
#: `~/.claude/settings.json` sha256 is unchanged). It is the **only** event that
#: records a permission refusal or a hook block, so without it
#: `AnomalyKind.TOOL_BLOCKED_BY_HOOK` and `TOOL_PERMISSION_REFUSED` were
#: structurally dead and `doctor` printed `idle` rather than a count.
#: `tests/engines/test_post_tool_batch_subscription.py` fails the build if it is
#: removed again — 25 names, asserted, not assumed.
SUBSCRIBED_EVENTS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PostToolBatch",
    "MessageDisplay",
    "Notification",
    "PermissionRequest",
    "PermissionDenied",
    "Elicitation",
    "ElicitationResult",
    "Stop",
    "StopFailure",
    "SessionEnd",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "PreCompact",
    "PostCompact",
    "CwdChanged",
    "PreModelSwitch",
    "PostModelSwitch",
    "FileChanged",
)

#: E16/C6: a malformed entry on either of these disables **every** hook in the
#: file, ours included — so their breakage is reported before we merge.
CRITICAL_EVENTS: tuple[str, ...] = ("PreToolUse", "PermissionRequest")
