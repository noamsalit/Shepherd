"""T20's live proof — **this test is §18's `can_set_title` probe** (D29, DP1).

`.venv/bin/python -m pytest tests/e2e/test_live_rename.py -m live -q`. Excluded
from the default run by `addopts = "-q -m 'not live'"`.

It starts a **throwaway owned session** on a throwaway tmux socket, types
`/rename <title>` into it through the shipped `Runner` seam, and reads back what
the engine wrote. Its recorded output is what a human reads before considering
whether to flip `can_set_title` — and nothing here flips it: the ceiling is a
value this module builds, `engines/claude_code/spawn.py` still ships `False`, and
`tests/engines/test_spawn_argv.py::test_can_set_title_ships_false` fails the
build if that changes without a recorded approval.

**P5 is NOT this test.** `/rename` against a session live in **another** process
is **G-M3-5**; the 2026-09-14 prober declined it because it *"risks two writers
on one transcript"*, and DP1's recommendation keeps `can_set_title = False` for
attached sessions on exactly that evidence. The target here is always a session
Shepherd started, on a socket Shepherd owns.

**The socket.** `shepherd-m3-rename` — a throwaway matching `THROWAWAY_SOCKET_RE`,
never the user's `shepherd` socket, and `-L` is on every invocation because the
exec site refuses an argv without it (`check_tmux_argv`, ADR-M3-8). Teardown is
`kill-session` through the seam: the tmux server exits with its last session, and
`list_owned_panes()` is asserted empty afterwards rather than assumed.

**Isolation** is this lane's (F10/A16): the user's **real** `CLAUDE_CONFIG_DIR`,
because an isolated one has no credentials; a `mktemp` working directory; an
explicit throwaway `--settings`. The engine's own bookkeeping — a trust entry for
the throwaway directory, and a transcript under `~/.claude/projects/-tmp-…` — is
this lane's documented, accepted residue.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from e2e.conftest import LIVE_MODEL, Throwaway, real_config_dir

from shepherd.core.anomalies import Anomaly
from shepherd.core.runner import (
    EngineCapabilities,
    PaneKind,
    RunnerHandle,
    SessionSpec,
    command_size,
)
from shepherd.core.states import Origin, Ownership
from shepherd.engines.claude_code.spawn import (
    BINARY_NAME,
    capabilities,
    resolve_binary,
    spawn_argv,
)
from shepherd.engines.claude_code.transcript import locate_transcript
from shepherd.host.base import DetachedLaunch
from shepherd.orchestration.rename import confirm_engine_title, rename_session
from shepherd.runner.local import LocalRunner, make_run_argv
from shepherd.runner.tmux_cmd import permitted_commands, permitted_sockets
from shepherd.store.db import Store, open_store
from shepherd.toolsurface.compose import SINK_PROGRAM

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A throwaway socket, matching `THROWAWAY_SOCKET_RE`. Never `shepherd`.
SOCKET = "shepherd-m3-rename"

#: The title typed at the engine. Distinctive, so finding it in a transcript is
#: a real search and not a coincidence.
TITLE = "shp-t20-live-title"

#: The TUI's own prefix on `#{pane_title}` once a title exists (data-schemas
#: §"Session title": `pane_title=✳ shp-probe-title-1`).
PANE_TITLE_PREFIX = "✳ "

SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFH"
NOW = "2026-09-17T10:00:00.000000+00:00"

#: How long the engine is given to come up, answer trust, and write a title.
TRUST_CEILING_S = 90.0
READY_CEILING_S = 120.0
TITLE_CEILING_S = 60.0
POLL_S = 0.5

#: Bytes, not key names: the seam's write channel is opaque, and `send-keys -H`
#: delivers them byte-exact. `\x1b[B` is Down, `\r` is Enter — the two keys the
#: 2026-09-14 probe pressed to accept the trust dialog
#: (`probe_tui.py` step 1: `Down`, then `Enter`, capture `01c-trust-yes-selected.txt`).
DOWN = b"\x1b[B"
ENTER = b"\r"

#: The trust dialog's second option, verbatim from the screen this host renders.
#: `❯` marks the selected row (`01-trust-dialog.ansi` has it on `No, exit`).
TRUST_YES = "Yes, I trust this folder"
SELECTED = "❯"


def _press_down_until_yes(runner: LocalRunner, handle: RunnerHandle) -> str | None:
    """One press, then a re-read. Returns the selected row once it is `Yes`."""
    pane = runner.pane(handle)
    for line in (pane.dialog_text or "").splitlines():
        if line.strip().startswith(SELECTED) and TRUST_YES in line:
            return line.strip()
    runner.write(handle, DOWN)
    return None


def await_value[T](
    probe: Callable[[], T | None], message: str, ceiling_s: float
) -> T:
    """Poll until the probe answers, or fail naming what never arrived."""
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        found = probe()
        if found is not None:
            return found
        time.sleep(POLL_S)
    raise AssertionError(f"{message} (waited {ceiling_s}s)")


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def live_runner(tmp_path: Path, settings: Path) -> LocalRunner:
    """`LocalRunner` over a real tmux on the throwaway socket.

    `spawn_argv` is the shipped one with this lane's `--settings` appended — the
    engine module deliberately passes none ("the live lane adds its own").
    """
    binary = resolve_binary()
    anomalies: list[Anomaly] = []

    def argv(spec: SessionSpec, *, frame_bytes: int) -> list[str]:
        extra = ["--settings", str(settings)]
        built = spawn_argv(spec, binary, frame_bytes=frame_bytes + command_size(extra))
        return [*built, *extra]

    return LocalRunner(
        socket=SOCKET,
        # T8-3 landed after this module was written and made `commands`
        # required: the exec site's allow-list for the tmux verbs that run a
        # shell command. `cat` is `runner/local.py`'s own `pipe-pane` sink
        # program and `BINARY_NAME` is the engine's, exactly as
        # `toolsurface/compose.py::build_runner` passes them.
        run_argv=make_run_argv(
            permitted_sockets(SOCKET), permitted_commands(SINK_PROGRAM, BINARY_NAME)
        ),
        launch=DetachedLaunch(
            prefix=(),
            mechanism="none",
            detail="the live lane runs outside a supervision unit",
            verified=True,
        ),
        now=lambda: NOW,
        spawn_argv=argv,
        record_anomaly=anomalies.append,
        sink_dir=tmp_path / "sink",
    )


def test_typing_rename_makes_the_engine_write_custom_title(
    store: Store, throwaway: Throwaway, tmp_path: Path
) -> None:
    """§18's probe. Type `/rename <title>` at an owned pane; read back what the
    engine wrote into its **own** files.

    Four assertions, each of them the thing DP1 turns on:

    * the transcript gains **`custom-title` and `agent-name`** — the engine wrote
      them, Shepherd wrote nothing (principle 4, K3);
    * the registry sidecar reports **`nameSource:"user"`** with this name, which
      is the only thing `title_synced_at` may be stamped from;
    * `#{pane_title}` becomes **`✳ <title>`**;
    * and `rename_session`, run a second time once that read-back is available,
      stamps `title_synced_at` — the write-back working end to end, **with the
      ceiling supplied as a value by this test and `False` in the shipped record**.
    """
    engine_session_id = str(uuid.uuid4())
    runner = live_runner(tmp_path, throwaway.settings)
    spec = SessionSpec(
        session_id=SESSION_ID,
        engine_session_id=engine_session_id,
        cwd=str(throwaway.workdir),
        brief=None,
        title=None,
        model=LIVE_MODEL,
        effort=None,
        engine="claude_code",
        runner="local",
        env={},
    )

    handle = runner.start(spec)
    try:
        workspace = store.upsert_workspace("shepherd-live", str(throwaway.workdir)).id
        store.create_owned_session(
            session_id=SESSION_ID,
            engine_session_id=engine_session_id,
            workspace_id=workspace,
            repo_id=None,
            cwd=str(throwaway.workdir),
            started_at=NOW,
            origin=Origin.ORCHESTRATOR,
            parent_session_id=None,
            depth=0,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=handle,
            model=LIVE_MODEL,
            effort=None,
        )

        # ----- 1. the trust dialog: move the selection, **re-read**, then Enter.
        #
        # C15/A11: a bare `Enter` here selects `No, exit` and the process is
        # gone. The re-read is not politeness — pressed at the first frame that
        # classifies as the dialog, `Down` is dropped and the `Enter` that
        # follows exits (observed twice on this host, at 0.5 s). So the press is
        # repeated until the pane itself shows `Yes` selected, exactly as the
        # mailbox's clearing step re-reads before any text follows (DP10).
        await_value(
            lambda: True if runner.pane(handle).kind is PaneKind.TRUST_DIALOG else None,
            "the trust dialog never appeared",
            TRUST_CEILING_S,
        )
        selection = await_value(
            lambda: _press_down_until_yes(runner, handle),
            "the trust dialog never showed `Yes, I trust this folder` selected",
            TRUST_CEILING_S,
        )
        assert TRUST_YES in selection, selection
        runner.write(handle, ENTER)

        # ----- 2. a prompt-ready pane, which is the only pane a rename may reach
        await_value(
            lambda: True if runner.pane(handle).kind is PaneKind.PROMPT_READY else None,
            f"the engine never reached a prompt-ready pane; last screen was "
            f"{runner.pane(handle).kind} / {runner.pane(handle).dialog_text!r}",
            READY_CEILING_S,
        )
        pid = runner.probe(handle).pid
        assert pid is not None, "the pane has no pid, so no sidecar can be named"

        # ----- 3. the rename, through the shipped verb, under a ceiling this
        #         test supplies. The shipped record still says False.
        assert capabilities(pane_driver_available=True).can_set_title is False
        ceiling = EngineCapabilities(
            can_spawn=True,
            can_steer=True,
            can_fork=True,
            can_set_title=True,
            has_hooks=True,
            effort_ladder=("low", "medium", "high", "xhigh", "max"),
            transcript_format="jsonl",
        )
        first = rename_session(
            store=store,
            runner=runner,
            handle=handle,
            session_id=SESSION_ID,
            title=TITLE,
            now=lambda: NOW,
            capabilities=ceiling,
            ownership=Ownership.OWNED,
            config_dir=real_config_dir(),
        )
        assert first.title == TITLE
        assert first.source == "user"

        # ----- 4. the read-backs: three independent readers of one fact
        confirmed = await_value(
            lambda: True
            if confirm_engine_title(config_dir=real_config_dir(), pid=pid, title=TITLE)
            else None,
            "the sidecar never reported nameSource:'user' with this title",
            TITLE_CEILING_S,
        )
        assert confirmed is True

        pane_title = await_value(
            lambda: runner.pane(handle).fields.pane_title
            if runner.pane(handle).fields.pane_title == f"{PANE_TITLE_PREFIX}{TITLE}"
            else None,
            "#{pane_title} never became the user title",
            TITLE_CEILING_S,
        )
        assert pane_title == f"{PANE_TITLE_PREFIX}{TITLE}"

        transcript = await_value(
            lambda: locate_transcript(real_config_dir() / "projects", engine_session_id),
            "no transcript was written for this session id",
            TITLE_CEILING_S,
        )
        kinds = await_value(
            lambda: _title_entry_kinds(transcript) or None,
            "the transcript never gained a custom-title entry",
            TITLE_CEILING_S,
        )
        assert {"custom-title", "agent-name"} <= kinds, sorted(kinds)

        # ----- 5. and now the stamp, which only a read-back may write
        second = rename_session(
            store=store,
            runner=runner,
            handle=handle,
            session_id=SESSION_ID,
            title=TITLE,
            now=lambda: NOW,
            capabilities=ceiling,
            ownership=Ownership.OWNED,
            config_dir=real_config_dir(),
        )
        assert second.synced_at == NOW
        assert second.local_only is False
        row = store.get_session(SESSION_ID)
        assert row is not None
        assert row.title_synced_at == NOW
        assert row.title == TITLE
        assert row.title_source == "user"
    finally:
        runner.terminate(handle)

    # The server exits with its last session; nothing is left on the socket.
    assert runner.list_owned_panes() == ()


def _title_entry_kinds(transcript: Path) -> set[str]:
    """Every `type` the transcript carries whose payload names this title.

    Malformed trailing lines are skipped, never raised (D25): the engine appends
    while this reads.
    """
    found: set[str] = set()
    try:
        raw = transcript.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return found
    for line in raw.splitlines():
        try:
            entry: object = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        fields = {str(key): value for key, value in entry.items()}
        if TITLE in (fields.get("customTitle"), fields.get("agentName")):
            kind = fields.get("type")
            if isinstance(kind, str):
                found.add(kind)
    return found
