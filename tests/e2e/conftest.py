"""T18's live lane: isolation fixtures, and the guards that replace construction.

**Isolation rule 1 (F10, K3), stated because it is not obvious.** This lane uses
the user's **real** `CLAUDE_CONFIG_DIR`. It cannot use a throwaway one: an
isolated config dir has no credentials and every `claude` run dies with
`Not logged in · Please run /login`, rc=1
(`docs/probes/2026-09-16-registry-and-version-drift.md` Finding 3). Isolation and
authentication are mutually exclusive on this host (A16, E36).

So K3 is no longer upheld *by construction* here — it is upheld by guards, and
the guards are therefore load-bearing:

* the sha256 of `~/.claude/settings.json` is asserted **before and after every
  test in this package**, not once per session, so a violation names the test
  that caused it (the session-wide guard in `tests/conftest.py` still runs too);
* every `claude` invocation carries an explicit `--settings <throwaway>`;
* every `claude` invocation runs in a `mktemp`-style throwaway working directory;
* no test asserts a session **count** — the real config dir means the user's own
  sessions are visible, and an assertion on how many there are would fail
  whenever the user is working (F10).

**No tmux.** This lane starts no terminal multiplexer at all, so CLAUDE.md's
rules 1-4 and §18's 2026-09-12 incident are satisfied by absence rather than by
a socket name. `tests/boundaries/test_tmux_blast_radius.py` asserts that
mechanically, over the whole tree rather than over this package.

**What a run leaves behind.** Claude Code's own bookkeeping: a trust/`~/.claude.json`
entry for the throwaway directory and a transcript under `~/.claude/projects/-tmp-…`.
Those are the same durable side effects the 2026-09-14 probe suite accepted, and
they are named here so a reader knows.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from shepherd.core.runner import RunnerRefusal, SessionSpec, command_size
from shepherd.daemons.sessiond import INGEST_SOCKET_NAME
from shepherd.engines.claude_code.events import SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.engines.claude_code.hooks_config import install_hooks
from shepherd.engines.claude_code.spawn import BINARY_NAME, resolve_binary, spawn_argv
from shepherd.host.detect import detect_host
from shepherd.runner.local import CommandResult, RunArgv, make_run_argv
from shepherd.runner.tmux_cmd import (
    permitted_commands,
    permitted_sockets,
    target,
    tmux_argv,
)
from shepherd.toolsurface.compose import SINK_PROGRAM

#: The model every live run uses: cheapest, and `effort` is absent for haiku,
#: which is itself a captured fact (data-schemas §Common input fields).
LIVE_MODEL = "claude-haiku-4-5"

CLAUDE_TIMEOUT_S = 180.0


def real_config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def settings_digest() -> str:
    path = real_config_dir() / "settings.json"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return "absent"


@pytest.fixture(autouse=True)
def settings_guard() -> Iterator[str]:
    """P13, asserted **per test** — the boundary, not a backstop (F10)."""
    before = settings_digest()
    yield before
    assert settings_digest() == before, (
        "a test in the live lane changed the real ~/.claude/settings.json"
    )


@dataclass(frozen=True)
class Throwaway:
    """One isolated run: a working directory and a settings file, both disposable."""

    workdir: Path
    settings: Path

    def argv(self, prompt: str) -> list[str]:
        """The one spelling of a live invocation. Never `shell=True`."""
        return [
            "claude",
            "-p",
            prompt,
            "--model",
            LIVE_MODEL,
            "--settings",
            str(self.settings),
        ]

    def tui_argv(
        self,
        brief: str | None,
        *,
        spec: SessionSpec | None = None,
        frame_bytes: int = 0,
    ) -> list[str]:
        """The TUI sibling of `argv`: **no `-p`**, and this lane's settings file.

        Built by the shipped `spawn_argv`, never hand-written — the words an
        owned session is started with are the engine adapter's, and a second
        spelling here would be a copy that drifts. The only thing added is
        `--settings <throwaway>`, which `engines/claude_code/spawn.py`
        deliberately omits ("the live lane adds its own"), and its size is
        counted into the frame tmux measures rather than ignored (E-M3-10).

        `spec` defaults to a throwaway spec so the method is callable as the
        plan spells it, `tui_argv(brief)`; the live runner passes the real one.
        """
        base = spec if spec is not None else self.lane_spec()
        extra = ["--settings", str(self.settings)]
        built = spawn_argv(
            replace(base, brief=brief),
            resolve_binary(),
            frame_bytes=frame_bytes + command_size(extra),
        )
        return [*built, *extra]

    def lane_spec(self) -> SessionSpec:
        """A throwaway `SessionSpec` in this throwaway directory, on haiku."""
        return SessionSpec(
            session_id="01JBQ8Z9XKME5RT3VWNY6P0DFH",
            engine_session_id=str(uuid.uuid4()),
            cwd=str(self.workdir),
            brief=None,
            title=None,
            model=LIVE_MODEL,
            effort=None,
            engine="claude_code",
            runner="local",
            env={},
        )

    def run(self, prompt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.argv(prompt),
            cwd=self.workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=CLAUDE_TIMEOUT_S,
        )


@pytest.fixture()
def throwaway(tmp_path: Path) -> Throwaway:
    """A throwaway working directory plus an explicit, empty settings file."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    return Throwaway(workdir=workdir, settings=settings)


@pytest.fixture()
def shepherd_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Shepherd's *own* dirs, thrown away — never the engine's (ADR-2).

    **`TMPDIR` is part of that and was missing until 2026-09-20.** This fixture
    redirected the `XDG_*` family only, which is `LinuxHost`'s half of the
    question; `MacHost` reads `HOME` and `TMPDIR` and correctly ignores every
    `XDG_` name. With `TMPDIR` left alone, every `controld` this lane started
    bound its control socket in the operator's **real** `$TMPDIR/Shepherd/` —
    which is why `test_sessiond_relays_and_the_buffer_drains_in_order_across_a_restart`
    failed with `ConnectionRefusedError` and nothing about a restart: two
    daemons that were meant to hold separate throwaway runtime directories were
    sharing one global socket path.

    **`HOME` is deliberately *not* redirected, and the reason is a real
    tension.** On macOS `MacHost` derives `data_dir` from `HOME`, so redirecting
    it is what would isolate Shepherd's *database* here. But this lane needs the
    engine's own config to be the real one — `spawn()` passes
    `engine_config_home=None` so a spawn meets a real workspace-trust dialog,
    and `test_hookless_discovery_sees_this_hosts_real_sessions` reads this
    host's actual registry. The engine resolves its account record from
    `$CLAUDE_CONFIG_DIR/.claude.json` (measured: with a throwaway `HOME` it
    reports `Not logged in · Please run /login`), so no combination of
    environment variables gives "throwaway home for Shepherd, real login for the
    engine" — the two want the same variable to point in opposite directions.

    **Consequence, recorded rather than hidden:** on macOS the `controld` this
    lane starts still opens the operator's real
    `~/Library/Application Support/Shepherd/shepherd.db`. That is the residue
    behind the fixture workspace `shepherd-m3-live` visible in the user's own
    UI. `tests/qa/test_s8_*` and `test_s9_*` do not share it — they drive
    `shepherd-controld` as a subprocess with an environment they fully own, and
    both redirect `HOME`.

    Closing it properly means injecting a `HostPlatform` into this lane rather
    than mutating the process environment — `controld.start(host=...)` already
    takes one, which is exactly what the seam is for — so that Shepherd's
    directories and the engine's are chosen independently. That is a change
    across ~8 call sites in live tests that cannot be executed here, so it is
    named as open work rather than applied blind.
    """
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "run"))

    # Arrival, not trust: the driver really did follow the redirect for the one
    # directory this fixture can currently isolate on both platforms.
    assert tmp_path in detect_host().control_socket("probe").path.parents, (
        "the control socket escaped the throwaway runtime directory"
    )
    return tmp_path


# ============================================================================
# T24 — the live lane's tmux half, and the hook block a registration test needs
# ============================================================================
#
# **The socket, and why it is spelled once.** `shepherd-m3-live` matches
# `THROWAWAY_SOCKET_RE`, so `check_tmux_argv` permits a server-wide teardown on
# it (K6-a) and refuses one anywhere else. It is never `shepherd` — that is the
# user's own socket, where `aivisor`, `main` and `spike` live — and never
# `shepherd-runner`, which is the product's and which a test must not share.
# CLAUDE.md rule 3 is satisfied structurally rather than by care: every argv in
# this lane is built by `tmux_argv(...)`, which puts `-L <socket>` at argv[1:3],
# and is then re-checked at the exec site on the real list.
#
# **The ledger.** `TMUX_CALLS` records every argv this lane hands to the exec
# site, *before* the guard runs, so a refused argv is recorded too.
# `test_every_tmux_call_in_the_live_lane_names_a_throwaway_socket` reads it.
# Recording after the guard would make the check report only the calls that
# already passed the check — a scan of its own output.

#: The one socket this lane may name. Never `shepherd`, never `shepherd-runner`.
LIVE_TMUX_SOCKET = "shepherd-m3-live"

#: Every tmux argv the lane has issued this session, in order. Read by the live
#: second check, which asserts it is non-empty first: a scan of nothing finds
#: nothing, which is the vacuous pass this task exists to avoid.
TMUX_CALLS: list[tuple[str, ...]] = []

#: What tmux 3.4 says on this host when a socket has no server. Measured, not
#: recalled: `tmux -L shepherd-m3-live ls` → rc=1,
#: `no server running on /tmp/tmux-0/shepherd-m3-live`.
NO_SERVER = "no server running on"

#: `#{session_name}`, one word per line — the listing the teardown walks.
NAME_FORMAT = "#{session_name}"

#: A foreign hook the installer must leave alone. `installed_settings` plants it
#: **before** `install_hooks` runs, so T22's diff and `inspect_hooks` both have a
#: non-Shepherd entry to be wrong about.
FOREIGN_MATCHER = "Bash"
FOREIGN_COMMAND = "true"


def lane_run_argv(socket: str = LIVE_TMUX_SOCKET) -> RunArgv:
    """The lane's one exec site: the shipped `make_run_argv`, with a ledger.

    `permitted_commands` carries exactly what the product's own composition root
    carries (`toolsurface/compose.py::build_runner`): `SINK_PROGRAM` because
    `runner/local.py` composes `pipe-pane -o -t <target> 'cat >> <sink>'`, and
    `BINARY_NAME` because the engine's binary is the other program a tmux
    shell-executing verb sees here. Both are imported rather than spelled: a
    literal here would be a second, drifting copy of a safety fact whose one
    owner is the exec site's constructor (T8-1, T8-3).
    """
    exec_site = make_run_argv(
        permitted_sockets(socket), permitted_commands(SINK_PROGRAM, BINARY_NAME)
    )

    def recorded(argv: list[str]) -> CommandResult:
        TMUX_CALLS.append(tuple(argv))
        return exec_site(argv)

    return recorded


def live_socket_listing(socket: str = LIVE_TMUX_SOCKET) -> CommandResult:
    """`list-sessions` on the throwaway socket, through the lane's exec site."""
    return lane_run_argv(socket)(tmux_argv(socket, "list-sessions", "-F", NAME_FORMAT))


def live_socket_has_no_server(socket: str = LIVE_TMUX_SOCKET) -> bool:
    """tmux's own words, not merely a non-zero rc.

    An rc of 1 alone is ambiguous — a bad format string returns 1 too — so the
    answer is read off the message tmux prints, which is what a human running
    `tmux -L shepherd-m3-live ls` sees.
    """
    result = live_socket_listing(socket)
    return result.rc != 0 and NO_SERVER in result.stderr.decode("utf-8", "replace")


def teardown_live_socket(socket: str = LIVE_TMUX_SOCKET) -> None:
    """`kill-session` per session, then **one** `kill-server` on the throwaway.

    The order is CLAUDE.md rule 2's, and the `kill-server` is the idiom every
    shipped probe used: bounded here by `check_tmux_argv`, which permits the verb
    only on a socket matching `^shepherd-m3-`. `-L` is on every one of these
    argvs because `tmux_argv` puts it there and the exec site refuses an argv
    without it — which is the whole of §18's 2026-09-12 lesson.
    """
    run = lane_run_argv(socket)
    listing = run(tmux_argv(socket, "list-sessions", "-F", NAME_FORMAT))
    if listing.rc == 0:
        for raw in listing.stdout.decode("utf-8", "replace").splitlines():
            name = raw.strip()
            if not name:
                continue
            try:
                spot = target(name)
            except RunnerRefusal:
                continue  # the server-wide teardown below reaches it anyway
            run(tmux_argv(socket, "kill-session", "-t", spot))
    run(tmux_argv(socket, "kill-server"))


@pytest.fixture(scope="session")
def tmux_live() -> Iterator[str]:
    """The lane's socket, and the backstop that asserts it is empty afterwards.

    Session-scoped so the teardown runs once, after every live module that used
    it. `test_the_live_socket_has_no_server_at_teardown` does the same sequence
    *inside* a test, where a leak names the test that leaked; this is the second
    net, and it is the one that cannot be skipped by `-k`.
    """
    yield LIVE_TMUX_SOCKET
    teardown_live_socket(LIVE_TMUX_SOCKET)
    assert live_socket_has_no_server(LIVE_TMUX_SOCKET), (
        f"the live lane left a tmux server on {LIVE_TMUX_SOCKET!r}"
    )


@pytest.fixture()
def installed_settings(shepherd_home: Path, throwaway: Throwaway) -> Path:
    """Shepherd's **real** installed hook block, in the throwaway settings file.

    The shipped `throwaway` fixture writes `{}`, and a session spawned with an
    empty settings file emits **no hooks to Shepherd at all** — so a test that
    asserts a registration against it cannot fail. This fixture writes the M1
    installer's own output instead: `install_hooks(...)` with a `HookEntry` built
    from `host.hook_dispatch(...)`, validated after the write by
    `hooks_config.py`'s own post-write check. Never a hand-written imitation —
    the probe's block in `docs/probes/2026-09-14-schemas/tmux-tui/make_settings.py`
    is the *probe's*, and what this lane must exercise is Shepherd's.

    Depends on `shepherd_home` so the ingest socket the entry names is the
    throwaway one `sessiond` will bind, not a path under the user's real dirs.
    """
    host = detect_host()
    ingest = host.control_socket(INGEST_SOCKET_NAME)
    entry = build_hook_entry(ingest, host.hook_dispatch(ingest))
    assert entry.available, f"this host cannot dispatch a hook: {entry.reason}"

    # The foreign entry goes in first, so the installer has something of somebody
    # else's to leave alone.
    throwaway.settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": FOREIGN_MATCHER,
                            "hooks": [{"type": "command", "command": FOREIGN_COMMAND}],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = install_hooks(throwaway.settings, entry)
    assert result.refused_reason is None, result.refused_reason
    assert result.events_installed == len(SUBSCRIBED_EVENTS), result
    assert result.warnings == (), result.warnings
    return throwaway.settings


# ============================================================================
# T22 — the live master, the pid ledger, and the readers of P4's frozen capture
# ============================================================================
#
# **T22 owns this block; T26 consumes it.** One writer, and the earlier task is
# the writer — revision 1 of the plan gave the file to T26 while T22 shipped the
# first live test that needs the fixture.
#
# **What a live master run is, stated plainly, because it starts a real
# `claude`.** Explicit `--settings` into a throwaway directory; a working
# directory that is **not** the repo; every inherited `CLAUDE*` / `ANTHROPIC*` /
# `AI_AGENT` variable scrubbed before the subprocess exists; the turn bounded by
# `asyncio.timeout`; the engine's pid recorded, asserted alive while the turn
# runs and asserted gone afterwards on a bounded wait read through the host
# seam — never from a signal (CLAUDE.md, 2026-09-17). `~/.claude/` is read and never written;
# the per-test `settings_guard` above asserts that, per test, by digest.
#
# **The mounted tools are inert fakes**, for the reason the probe harness gives
# in its own safety sequence: *"every probe mounts literal-returning fakes only
# … so no probe master could act on the fleet."* A live model holding a real
# `kill_session` is not a test, it is an incident waiting for a bad sample.

import asyncio
import time
from collections.abc import Mapping
from typing import cast

from shepherd.core.master import MasterEvent
from shepherd.master import sdk_master
from shepherd.master.sdk_tools import prefixed_names
from shepherd.toolsurface import client as master_client
from shepherd.toolsurface.registry import register, reset_registry
from shepherd.toolsurface.types import (
    Audience,
    BlastClass,
    CallerContext,
    ToolArgs,
    ToolDef,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: P4's frozen capture directory (`docs/probes/` is read-only evidence).
P4_CAPTURE = REPO_ROOT / "docs" / "probes" / "2026-09-17-m4-sdk" / "p4-plugins-20260917T214517Z"

#: The one MCP server a locked master may report, whole. A membership test would
#: pass with the account's connectors listed beside it.
SHEPHERD_SERVER: dict[str, str] = {"name": "shepherd", "status": "connected"}

#: The user's own settings file, read to prove the cc10x assertion is not
#: vacuous. Read-only, and the same bytes `settings_guard` digests.
ENABLED_PLUGINS_KEY = "enabledPlugins"
CC10X_PLUGIN = "cc10x@cc10x"

MASTER_TURN_TIMEOUT_S = 180.0
MASTER_PID_GONE_TIMEOUT_S = 20.0

#: Everything that could tell a spawned engine it is inside *this* session. A
#: live check that skipped the scrub would be measuring the session it runs in.
INHERITED_PREFIXES = ("CLAUDE", "ANTHROPIC", "AI_AGENT")

#: The master's throwaway capability set: three literal-returning fakes on the
#: MASTER audience. **Three and not one**, so the set equality in
#: `test_live_master_init_lists_exactly_our_tools` cannot be satisfied by a mount
#: that carried only the first.
FAKE_MASTER_TOOLS: tuple[str, ...] = (
    "t22_isolation_alpha",
    "t22_isolation_beta",
    "t22_isolation_gamma",
)

#: What a fake returns. A literal, and nothing this process could act on.
FAKE_TOOL_ANSWER = "t22 fixture tool; it does nothing"


def pid_is_alive(pid: int) -> bool:
    """The host seam, never a signal (D55, CLAUDE.md 2026-09-17).

    The rule is unchanged and it is the important half: a probe that signals is
    a probe that can end something, and on 2026-09-17 one did, to pid 1. So
    `os.kill(pid, 0)` — the short portable idiom — stays refused.

    What changed is where the answer comes from. `Path(f"/proc/{pid}").exists()`
    is Linux's spelling of it, and on macOS that path never exists: this
    returned `False` for every pid, alive or dead. That is not a crash, which is
    what makes it dangerous — `assert not pid_is_alive(pid)` after a teardown
    passed for a daemon that was still running, and the arrival assertions that
    would have caught it (`assert pid_is_alive(pid)`) failed instead, so the
    lane reported the *opposite* of the truth at both ends.

    `HostPlatform.process_liveness` is the seam the product already uses for
    exactly this question: `/proc/<pid>/stat` on Linux, `ps -o lstart=` on
    macOS, read-only on both, measured on this host in
    `docs/probes/2026-09-20-macos-g1-capture.md` §5.
    """
    return detect_host().process_liveness(pid, None).alive


def probe_system_init(capture: Path) -> Mapping[str, object]:
    """The `system/init` message out of a probe's `raw-stream.jsonl`.

    The capture wraps each frame as `{"_dir": …, "line": {…}}`; this reads the
    `line` and never the wrapper. Raises rather than answering `None` if the
    capture holds no init: a reader that cannot fail on a moved evidence file is
    a reader that reports the absence of evidence as agreement (B1).
    """
    for raw in capture.read_text(encoding="utf-8").splitlines():
        line = json.loads(raw).get("line", {})
        if line.get("type") == "system" and line.get("subtype") == "init":
            return cast("Mapping[str, object]", line)
    raise AssertionError(f"{capture} carries no system/init frame")


def transcript_attachments(transcript: Path) -> frozenset[str]:
    """Every attachment subtype the engine injected into one transcript."""
    found: set[str] = set()
    for raw in transcript.read_text(encoding="utf-8").splitlines():
        entry = json.loads(raw)
        if entry.get("type") == "attachment":
            subtype = entry.get("attachment", {}).get("type")
            if isinstance(subtype, str):
                found.add(subtype)
    return frozenset(found)


def session_context_keys(transcript: Path) -> frozenset[str]:
    """The keys of the `session_context` attachment — DP10's named residue.

    On this account that is exactly `{"userEmail"}`, in P4's capture and in every
    run since. Returned as a set so the check reads *"userEmail is present"* and
    never *"there is exactly one key"*, which is the account's shape and not ours.
    """
    found: set[str] = set()
    for raw in transcript.read_text(encoding="utf-8").splitlines():
        entry = json.loads(raw)
        attachment = entry.get("attachment", {}) if entry.get("type") == "attachment" else {}
        if attachment.get("type") == "session_context":
            found |= set(attachment.get("context", {}))
    return frozenset(found)


def _fake_tool(name: str) -> ToolDef:
    def handler(args: ToolArgs, ctx: CallerContext) -> object:
        return FAKE_TOOL_ANSWER

    return ToolDef(
        name=name,
        description="A T22 fixture capability. It returns a literal and reaches nothing.",
        input_schema={"type": "object", "properties": {}},
        blast_class=BlastClass.LOCAL_READ,
        handler=handler,
        audiences=frozenset({Audience.MASTER}),
    )


@dataclass(frozen=True)
class LiveMaster:
    """One live master turn, and everything a check needs to read off it."""

    init: Mapping[str, object]
    """`system/init`, exactly as the engine reported it."""
    mounted: tuple[str, ...]
    """The prefixed names we mounted, through the shipped projection."""
    events: tuple[MasterEvent, ...]
    pids: tuple[int, ...]
    """Every engine pid seen during the turn, each asserted alive when found."""
    survivors: tuple[int, ...]
    """Any of them the host still reports alive after the wait. Must be empty."""
    workdir: Path
    transcript: Path | None
    """The engine's own transcript for this session, under `~/.claude/projects/`."""


@pytest.fixture(scope="module")
def live_master(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LiveMaster]:
    """One real `claude`, driven through `AgentSDKMaster`, torn down here.

    Module-scoped so the three live checks in `test_live_master_isolation.py`
    read **one** engine's answer rather than three: `system/init` is a property
    of a run, and three runs would be three subjects for one claim.

    The registry is reset, loaded with the fakes and reset again on the way out.
    It is a process global; leaving it loaded would be a fixture that decides the
    next test (`reset_registry`'s own docstring is about exactly this).
    """
    with pytest.MonkeyPatch.context() as patch:
        base = tmp_path_factory.mktemp("t22-live-master")
        settings = base / "flag-settings.json"
        settings.write_text("{}", encoding="utf-8")
        workdir = base / "work"
        workdir.mkdir()

        # **Read before the scrub**, because the scrub removes `CLAUDE_CONFIG_DIR`
        # with everything else beginning `CLAUDE`, and `real_config_dir()` would
        # then answer about a different file than the guard digests.
        #
        # This is what stops `plugins == []` from being a vacuous assertion: P4's
        # finding is *"cc10x is enabled at user scope on this host and the master
        # does not see it"*, and the first half of that sentence is a fact about
        # the operator's settings, not about our options. Disable cc10x and this
        # run should stop claiming to prove anything.
        enabled = json.loads(
            (real_config_dir() / "settings.json").read_text(encoding="utf-8")
        ).get(ENABLED_PLUGINS_KEY, {})
        assert enabled.get(CC10X_PLUGIN) is True, (
            "this host does not have the cc10x user plugin enabled, so an empty"
            " system/init.plugins proves nothing about setting_sources — P4's"
            " measurement is not reproducible here"
        )

        for name in list(os.environ):
            if name.startswith(INHERITED_PREFIXES):
                patch.delenv(name, raising=False)
        patch.chdir(workdir)

        reset_registry()
        try:
            for name in FAKE_MASTER_TOOLS:
                register(_fake_tool(name))
            tools = master_client.master_tools()
            mounted = prefixed_names(tools)

            master = sdk_master.AgentSDKMaster(
                caller_id="t22-isolation",
                turn_id=lambda: "01JBQ8Z9XKME5RT3VWNY6P0DFH",
                bump=lambda kind: None,
                withdraw_turn_approvals=lambda turn_id: 0,
                model=LIVE_MODEL,
                settings=str(settings),
            )
            master.configure(
                tools,
                "Answer with the single word OK and stop there. Call no tools.",
            )

            seen: list[MasterEvent] = []
            pids: list[int] = []

            async def one_turn() -> None:
                async with asyncio.timeout(MASTER_TURN_TIMEOUT_S):
                    async for event in master.send("Say OK."):
                        seen.append(event)
                        pid = _engine_pid(master)
                        if pid is not None and pid not in pids:
                            assert pid_is_alive(pid), pid  # the arrival
                            pids.append(pid)

            asyncio.run(one_turn())
            master.close()

            init = master.system_init()
            assert init is not None, "the engine reported no system/init"

            # Recorded verbatim for T22's **human_verify** checkpoint: §18 says
            # *"do not trust it"*, and a human reads this file before the
            # milestone claims isolation. Written under this task's own scratch
            # path (RD-T17-11), never a shared one.
            record = REPO_ROOT / "scratchpad" / "m4-t22"
            record.mkdir(parents=True, exist_ok=True)
            (record / "system-init.json").write_text(
                json.dumps(dict(init), indent=2, sort_keys=True), encoding="utf-8"
            )
            (record / "live-turn.json").write_text(
                json.dumps(
                    {
                        "mounted": list(mounted),
                        "pids": pids,
                        "event_kinds": [event.kind for event in seen],
                        "text": [
                            event.text for event in seen if event.text is not None
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            deadline = time.monotonic() + MASTER_PID_GONE_TIMEOUT_S
            while any(pid_is_alive(pid) for pid in pids) and time.monotonic() < deadline:
                time.sleep(0.1)

            yield LiveMaster(
                init=init,
                mounted=mounted,
                events=tuple(seen),
                pids=tuple(pids),
                survivors=tuple(pid for pid in pids if pid_is_alive(pid)),
                workdir=workdir,
                transcript=_engine_transcript(init),
            )
        finally:
            reset_registry()


def _engine_pid(master: sdk_master.AgentSDKMaster) -> int | None:
    """The engine's own pid, read off the vendor's transport.

    Private on both sides and named as such (T21 §T21-10): the seam has no pid
    reader, and one added for a live check would be a member with no production
    caller.
    """
    client = getattr(master, "_client", None)
    transport = getattr(client, "_transport", None)
    process = getattr(transport, "_process", None)
    pid = getattr(process, "pid", None)
    return int(pid) if isinstance(pid, int) else None


def _engine_transcript(init: Mapping[str, object]) -> Path | None:
    """Claude Code's own transcript for this session, found by its session id.

    Globbed rather than reconstructed: the project directory name is the cwd with
    every separator rewritten, and a re-derivation of the engine's slugging rule
    is a second spelling of somebody else's fact. **Read-only** — this is under
    `~/.claude/`, which nothing in this repo writes.
    """
    session = init.get("session_id")
    if not isinstance(session, str):
        return None
    for candidate in sorted(real_config_dir().glob(f"projects/*/{session}.jsonl")):
        return candidate
    return None
