"""M3's capabilities, registered once so every consumer reaches the same ones.

`web/` and `cli/` reach these through `invoke()` and nothing else (D32, D35), and
M4's gate lands behind that signature without changing a file here (D38) — which
is only true because the `blast_class` values are set correctly **now**.

**L4 composes; it does not reimplement.** Every decision here was made one layer
down and is called, not restated: admission and §11's caps
(`orchestration/spawn.py`), the record-before-terminate order (`lifecycle.py`),
the dialog gate (`dialogs.py`), the 96-key write policy and the mailbox
(`tools_messaging.py` -> `orchestration/`), the pane (`tools_terminal.py` ->
the `Runner` seam). There is no second copy of any of them, and no tmux word
appears in any of the three files.

**Every handler returns a projection, never a row** (§13). A store dataclass is
never returned and never spread: a column added to `session` tomorrow cannot
appear on the wire by accident, and `owner_id`, the pid and the engine's own
session id never leave the process.

**Every failure is a value.** A refusal, a session that is not ours, a policy
that said "not now" — each comes back as a field a page can render, because
`invoke()` flattens a raise into one generic literal and a page told "request
failed" cannot tell a refusal from a crash (principle 5, §13 Errors).

## The split, and Task 18's size cap

Task 18 asks for *one module ≤ 450 lines*. Twelve capabilities, their schemas
and their projections come to ~660, so this is **three modules, each
size-asserted**, rather than one cap raised — the ninth time this repo has taken
that trade. The halves are three jobs a reader can name: start and stop a
session (here), say something to one and read its answer
(`tools_messaging.py`), and drive its terminal (`tools_terminal.py`).

## Recorded deviations from Task 18's `Produces`, reported rather than quiet

1. **`register_m3_tools` takes nine more required injections than the three
   written down.** `(store, runner, now)` cannot build `spawn_session` (which
   needs `sleep`, `publish`, `ensure_server`, `engine_config_home`), `ask_session`
   (`run_fork`, `binary`, `projects_root`, `can_fork`) or `answer_permission`
   (`read_sidecar`). T8-1's situation exactly. They are **required** keyword
   arguments rather than defaulted ones for T6-2's reason: an injection a caller
   can forget is one that will be forgotten.
2. **`read_sidecar` is injected rather than resolved here.** `SidecarState`'s own
   docstring says the caller resolves the engine's field names into one of its
   three members — and `toolsurface/` may not spell engine vocabulary, so the
   resolution could not live in this file even if it wanted to.
3. **`TerminalStream` carries the snapshot** beside the session id and the two
   methods. See its docstring: the screen and the stream that continues it have
   to be taken as one act.

**`rename_session` is registered by T20, not here** (revision 2): T20 produces
the handler and depends on this task, so the tool is registered where the
function is written. Its route stays in `POST_ROUTES` — a route is a
path->name table and the name is resolved through `invoke()` at call time.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.runner import WriteDecision
from shepherd.core.states import Origin
from shepherd.core.stream import StreamEvent
from shepherd.orchestration.admission import SpawnRefused
from shepherd.orchestration.ask import ForkRunner
from shepherd.orchestration.dialog_keys import PERMISSION_KEYS, PermissionChoice, SidecarState
from shepherd.orchestration.dialogs import DialogAnswer, answer_permission
from shepherd.orchestration.lifecycle import interrupt_session, record_and_terminate
from shepherd.orchestration.spawn import SpawnOutcome, spawn_owned_session
from shepherd.runner.base import Runner
from shepherd.store.db import Store
from shepherd.toolsurface.registry import register
from shepherd.toolsurface.spawn_origin import spawn_origin
from shepherd.toolsurface.tools_messaging import build_messaging_tools
from shepherd.toolsurface.tools_terminal import (
    TerminalStream,
    build_terminal_tools,
    handle_for,
    no_pane,
)
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
    arg_bool,
    arg_optional_str,
    arg_str,
)

__all__ = [
    "M3_TOOL_NAMES",
    "TerminalStream",
    "build_m3_tools",
    "register_m3_tools",
]

Clock = Callable[[], str]
#: An engine session id -> what the engine's own live record says about it. The
#: resolution of the engine's field names is the caller's (see deviation 2).
SidecarReader = Callable[[str], SidecarState]

#: The twelve of Task 18's table, in its order. `rename_session` is **not** here.
M3_TOOL_NAMES: tuple[str, ...] = (
    "spawn_session",
    "send_to_session",
    "ask_session",
    "interrupt_session",
    "kill_session",
    "answer_permission",
    "get_session_output",
    "terminal_snapshot",
    "terminal_write",
    "terminal_resize",
    "terminal_stream",
    "list_mailbox",
)

_EVERY_AUDIENCE = frozenset({Audience.MASTER, Audience.SESSION, Audience.HUMAN})
_MASTER_AND_HUMAN = frozenset({Audience.MASTER, Audience.HUMAN})
_HUMAN_ONLY = frozenset({Audience.HUMAN})

# ----- projections (§13: an explicit whitelist at every response sink) --------


def project_spawn(outcome: SpawnOutcome | SpawnRefused) -> dict[str, object]:
    """A spawn that happened, or the refusal — one shape carrying both answers.

    `cap` names which of §11's three refused, because "refused" alone is not
    something a human can act on: a depth cap and a total-panes cap want
    different next moves.
    """
    if isinstance(outcome, SpawnRefused):
        return {
            "spawned": False,
            "session_id": None,
            "state": None,
            "detail": None,
            "refusal": outcome.reason,
            "cap": outcome.cap,
        }
    return {
        "spawned": True,
        "session_id": outcome.session_id,
        "state": str(outcome.state.value),
        "detail": outcome.detail,
        "refusal": None,
        "cap": None,
    }


def project_dialog(answer: DialogAnswer, session_id: str) -> dict[str, object]:
    """`keys_sent` travels outward because it is what makes "no key was sent"
    checkable at this seam rather than in a test's private bookkeeping."""
    return {
        "session_id": session_id,
        "answered": answer.decision is WriteDecision.SEND_NOW,
        "decision": str(answer.decision.value),
        "reason": answer.reason,
        "keys_sent": answer.keys_sent,
    }


# ----- handlers ---------------------------------------------------------------


def spawn(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    sleep: Callable[[float], None],
    publish: Callable[[StreamEvent], None],
    ensure_server: Callable[[], None],
    engine_config_home: Path | None,
    args: ToolArgs,
    ctx: CallerContext,
) -> dict[str, object]:
    """§11's caps and §13's allowlist are enforced **inside** the sequence.

    Nothing is checked twice here: a second copy of a cap is a copy that will
    disagree with the first one, and the refusal it would produce would not be
    the one the sequence's own tests hold.
    """
    return project_spawn(
        spawn_owned_session(
            store=store,
            runner=runner,
            now=now,
            sleep=sleep,
            publish=publish,
            ensure_server=ensure_server,
            engine_config_home=engine_config_home,
            workspace_id=arg_str(args, "workspace_id"),
            cwd=arg_str(args, "cwd"),
            brief=arg_optional_str(args, "brief"),
            title=arg_optional_str(args, "title"),
            model=arg_optional_str(args, "model"),
            effort=arg_optional_str(args, "effort"),
            parent_session_id=arg_optional_str(args, "parent_session_id"),
            origin=spawn_origin(ctx),
            ephemeral=arg_bool(args, "ephemeral"),
        )
    )


def interrupt(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    publish: Callable[[StreamEvent], None],
    session_id: str,
) -> dict[str, object]:
    """`Escape`, never a signal to a pid (D43). Writes no state: an interrupted
    turn emits no turn-ending event, so the pane poll is what decides."""
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    interrupt_session(
        store=store, runner=runner, handle=handle, session_id=session_id, now=now, publish=publish
    )
    return {"session_id": session_id, "ok": True, "interrupted": True}


def kill(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    publish: Callable[[StreamEvent], None],
    session_id: str,
) -> dict[str, object]:
    """Records before killing — and that order is `lifecycle.py`'s, not repeated
    here. A failed kill propagates its refusal rather than answering "killed"."""
    handle = handle_for(store, session_id)
    if handle is None:
        return no_pane(session_id)
    observed = record_and_terminate(
        store=store, runner=runner, handle=handle, session_id=session_id, now=now, publish=publish
    )
    return {
        "session_id": session_id,
        "ok": True,
        "killed": True,
        "exit_code": observed.exit_code,
        "exit_signal": observed.exit_signal,
        "observed_at": observed.observed_at,
    }


def answer(
    *,
    store: Store,
    runner: Runner,
    read_sidecar: SidecarReader,
    session_id: str,
    choice: PermissionChoice,
) -> dict[str, object]:
    """D44. Both sources are composed **inside** `answer_permission`: the pane
    kind, then the sidecar, then the option set, and only then a key."""
    row = store.get_owned_session(session_id)
    handle = None if row is None else row.runner_handle
    if row is None or handle is None or row.engine_session_id is None:
        return no_pane(session_id)
    return project_dialog(
        answer_permission(
            store=store,
            runner=runner,
            handle=handle,
            session_id=session_id,
            choice=choice,
            sidecar=read_sidecar(row.engine_session_id),
        ),
        session_id,
    )


def _choice(args: ToolArgs) -> PermissionChoice:
    """The closed set, checked at the seam.

    JSON Schema's `enum` is not one of the two things a binding is guaranteed to
    carry through unchanged (D53), so the set is enforced here — and a
    positional digit chosen from an *open* set is precisely the failure P4 was
    run to prevent. `ToolArgumentRefused` rather than a raise, so the caller is
    told its own value back instead of "request failed".
    """
    value = arg_str(args, "choice")
    if value not in PERMISSION_KEYS:
        raise ToolArgumentRefused(f"choice {value!r} is not one of {sorted(PERMISSION_KEYS)}")
    return value  # type: ignore[return-value]


# ----- registration -----------------------------------------------------------


def build_m3_tools(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    sleep: Callable[[float], None],
    publish: Callable[[StreamEvent], None],
    ensure_server: Callable[[], None],
    engine_config_home: Path | None,
    run_fork: ForkRunner,
    binary: str,
    projects_root: Path,
    can_fork: bool,
    read_sidecar: SidecarReader,
) -> tuple[ToolDef, ...]:
    """The twelve, with every dependency closed over (D32)."""
    session_arg: dict[str, object] = {
        "type": "object",
        "properties": {"session_id": {"type": "string"}},
        "required": ["session_id"],
    }
    return (
        ToolDef(
            name="spawn_session",
            description="Start one owned session in its own pane (§11's caps apply).",
            input_schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "cwd": {"type": "string"},
                    "brief": {"type": "string"},
                    "title": {"type": "string"},
                    "model": {"type": "string"},
                    "effort": {"type": "string"},
                    "parent_session_id": {"type": "string"},
                    "ephemeral": {"type": "boolean"},
                },
                "required": ["workspace_id", "cwd"],
            },
            blast_class=BlastClass.LOCAL_WRITE,
            handler=lambda args, ctx: spawn(
                store=store,
                runner=runner,
                now=now,
                sleep=sleep,
                publish=publish,
                ensure_server=ensure_server,
                engine_config_home=engine_config_home,
                args=args,
                ctx=ctx,
            ),
            audiences=_EVERY_AUDIENCE,
        ),
        ToolDef(
            name="interrupt_session",
            description="What a user pressing Ctrl-C would do — never a signal (D43).",
            input_schema=session_arg,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: interrupt(
                store=store,
                runner=runner,
                now=now,
                publish=publish,
                session_id=arg_str(args, "session_id"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="kill_session",
            description="End one owned session; the kill is recorded before it is issued.",
            input_schema=session_arg,
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: kill(
                store=store,
                runner=runner,
                now=now,
                publish=publish,
                session_id=arg_str(args, "session_id"),
            ),
            audiences=_MASTER_AND_HUMAN,
        ),
        ToolDef(
            name="answer_permission",
            description="Answer D44's dialog with one captured key, or refuse and say why.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "choice": {"type": "string"},
                },
                "required": ["session_id", "choice"],
            },
            blast_class=BlastClass.LOCAL_DESTRUCTIVE,
            handler=lambda args, ctx: answer(
                store=store,
                runner=runner,
                read_sidecar=read_sidecar,
                session_id=arg_str(args, "session_id"),
                choice=_choice(args),
            ),
            audiences=_HUMAN_ONLY,
        ),
        *build_messaging_tools(
            store=store,
            runner=runner,
            now=now,
            run_fork=run_fork,
            binary=binary,
            projects_root=projects_root,
            can_fork=can_fork,
        ),
        *build_terminal_tools(store, runner, projects_root),
    )


def register_m3_tools(
    *,
    store: Store,
    runner: Runner,
    now: Clock,
    sleep: Callable[[float], None],
    publish: Callable[[StreamEvent], None],
    ensure_server: Callable[[], None],
    engine_config_home: Path | None,
    run_fork: ForkRunner,
    binary: str,
    projects_root: Path,
    can_fork: bool,
    read_sidecar: SidecarReader,
) -> None:
    """Called by the composition root at startup, before `freeze_registry()`."""
    for tool in build_m3_tools(
        store=store,
        runner=runner,
        now=now,
        sleep=sleep,
        publish=publish,
        ensure_server=ensure_server,
        engine_config_home=engine_config_home,
        run_fork=run_fork,
        binary=binary,
        projects_root=projects_root,
        can_fork=can_fork,
        read_sidecar=read_sidecar,
    ):
        register(tool)
