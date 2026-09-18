"""The tmux driver: twelve `Runner` members as argv, and the one exec site (T8).

**Every member is one or two tmux argvs through one injected `run_argv`**, so the
whole driver is testable with no tmux server anywhere. `subprocess` appears in
exactly one function in this module — `make_run_argv`, the real `RunArgv` — and
`test_local_runner_constructs_no_subprocess_call` asserts `LocalRunner` itself
never names it.

## The exec site, and why the guarantee lives here

`make_run_argv`'s **first statement** is `check_tmux_argv(argv, permitted=...)`
(ADR-M3-8). Not a lint, not a test: the one place in `src/` that starts a
process refuses before it starts it. The three AST rules in
`tests/boundaries/test_tmux_blast_radius.py` are a second net and each of them
falls to one line of indirection — `from .tmux_cmd import TMUX_BIN`,
`f"kill-{verb}"` — while the argv those lines build is still a plain list of
strings by the time it reaches here.

**The check runs twice, and the second call is the one nobody wrote down.**
`ensure_server` prefixes the launch with `DetachedLaunch.prefix` (DP5), so the
argv handed to the exec site can begin `systemd-run …` — and `check_tmux_argv`
deliberately returns early on an argv that is not tmux's ("a guard that polices
`git` gets turned off"). A wrapper is therefore a hole in the guard exactly as
wide as the wrapper: `[*prefix, <binary>, "kill-server"]` would sail through.
`_tmux_tail` re-presents the argv from the binary onward, so the prefix cannot
launder what follows it.

**A third rule says what this site may start at all** (`_names_the_binary`, T8-3
decision 2): both checks above return quietly on an argv naming no binary, which
left `["sh", "-c", "<payload>"]` unrecognised by either. The binary is recognised through `tmux_cmd._is_binary`
— by **basename**, and never spelled here, because `src/` has exactly one module
that spells it (`tmux_cmd.py`) and `test_tmux_is_spelled_in_exactly_one_module`
keeps it that way. Sharing that one predicate with the guard's own early return
is **T8-2**: a scan for the literal name saw `systemd-run --scope tmux …` and
walked past `systemd-run --scope /usr/bin/tmux …`, and C1
(`implementation-constraints.md`) is a standing instruction to write the second
form.

## Degradation: a value, a refusal, or a counted unknown — never a traceback

Every entry point answers with a `ProcState`, a `PaneState`, a `PaneRef` tuple or
a `RunnerRefusal` (`test_the_runner_never_raises`, over 12 entry points enumerated
from the `Runner` Protocol itself). An absent binary counts
`AnomalyKind.TMUX_UNAVAILABLE`; a listing line or a capture we cannot read counts
`AnomalyKind.PANE_UNREADABLE`.

**`record_anomaly` is a required field, and that is T6-2's whole resolution.**
`read_pane`'s sink is an *optional* parameter, and an optional parameter a caller
may forget is precisely the "tested seam that never runs" shape this repo keeps
finding. Here it is a constructor argument with no default: a caller that forgets
it does not compile under `mypy --strict` and does not construct at runtime.

## Deviations from the plan's `Produces`

Three injected fields the plan does not list (`spawn_argv`, `sink_dir`,
`record_anomaly`), `LISTING_FORMAT` in place of a bare `PANE_FORMAT`, `-c <cwd>`
on `new-session`, and `send-keys -H` for every payload. Each is argv the member
cannot build without it, and each is written up — with what it would otherwise
break — as **T8-1** in `docs/plans/2026-09-17-m3-BLOCKERS.md`.

"""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.anomalies import Anomaly, AnomalyKind
from shepherd.core.runner import (
    PaneFields,
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
    SpawnArgv,
    command_size,
)
from shepherd.host.base import DetachedLaunch
from shepherd.runner.base import ByteStream, PaneRef
from shepherd.runner.pane import FIELD_SEPARATOR, PANE_FORMAT, parse_pane_fields, read_pane
from shepherd.runner.tmux_cmd import (
    SESSION_PREFIX,
    WHY,
    _is_binary,
    check_tmux_argv,
    session_name,
    target,
    tmux_argv,
)

#: `RunnerHandle.runner`. The name a stored handle round-trips through.
RUNNER_NAME = "local"

#: `#{session_name}` prepended to T6's seven fields. `PANE_FORMAT` carries no
#: session name, and both `probe` (filter to one target) and `list_owned_panes`
#: (the cap's population) are *selections over sessions* — neither is expressible
#: without it. The name is split off on the **first** separator, and a tmux
#: session name cannot contain one (`tmux_cmd.NAME_RE`), so the free-text
#: `#{pane_title}` still cannot shift a field.
LISTING_FORMAT = f"#{{session_name}}{FIELD_SEPARATOR}{PANE_FORMAT}"

#: An owned pane: `shepherd_` + a Crockford ULID. The bootstrap session
#: (`ensure_server`) deliberately does not match — it holds no session slot.
OWNED_SESSION_RE = re.compile(rf"^{SESSION_PREFIX}[0-9A-HJKMNP-TV-Z]{{26}}$")

#: The session that keeps the server alive when no owned pane does.
BOOTSTRAP_SESSION_ID = "bootstrap"

#: `160x45` is the geometry every captured pane was observed at
#: (`14-list-sessions-after-sigterm.txt`).
DEFAULT_COLS = 160
DEFAULT_ROWS = 45

#: One word per attached client, so the client count is a line count that no
#: client's own fields can shift. The listing's shape is captured with the wider
#: format in `p3-concurrent-20260917T111005Z/04-inner-list-clients.txt`.
CLIENT_FORMAT = "#{client_tty}"

#: `pipe-pane`'s argument is run through `sh -c` by tmux, so the path it names is
#: confined to characters no shell re-reads.
SINK_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")

#: How long a stopped `attach` stream waits before looking for more bytes. Not a
#: clock: it spells no instant and `tests/boundaries/test_one_clock.py` is about
#: who may write a stamp.
STREAM_POLL_S = 0.05


@dataclass(frozen=True)
class CommandResult:
    """One finished process: what it returned and what it wrote."""

    rc: int
    stdout: bytes
    stderr: bytes


RunArgv = Callable[[list[str]], CommandResult]


def _tmux_tail(argv: list[str]) -> list[str]:
    """`argv` from the binary onward, so a wrapper prefix cannot hide it.

    The binary is recognised by **basename** (`_is_binary`, T8-2), the same
    predicate the guard's own early return uses: scanning for the literal name
    found `systemd-run --scope tmux …` and walked straight past
    `systemd-run --scope /usr/bin/tmux …`, which is the same process on the same
    socket.
    """
    for index, word in enumerate(argv):
        if _is_binary(word):
            return list(argv[index:])
    return []


def _names_the_binary(argv: list[str]) -> None:
    """T8-3 decision 2: **this exec site starts the multiplexer and nothing else.**

    T8-3 constrained the shell-executing verbs' *command argument* and left this
    site's own `argv[0]` open: `["sh", "-c", "<payload>"]` names no binary, so
    `check_tmux_argv` returns early (by design — "a guard that polices `git` gets
    turned off") and `_tmux_tail` has nothing to re-present. Neither gate saw it.

    The closing rule is **positive and injects nothing**: an argv that never
    names the binary is not this site's to run. Not a deny-list of shells — the
    shape `COMMAND_ARG_RE` rejected one layer down — and it lives here, so the
    predicate stays argv-in/refusal-out over tmux's own argvs. A
    `DetachedLaunch.prefix` (DP5) may still precede the binary, by basename, so
    C1's absolute path is permitted here exactly as it is in `_tmux_tail`.

    **The residual is named, not left to be discovered**: an argv that both wraps
    a shell and *trails* a real multiplexer argv satisfies this rule. Closing it
    needs the words before the binary compared against an injected launch prefix,
    a required argument at the composition root. Row 7 of `T8_3_TABLE`, OPEN.
    """
    if _tmux_tail(argv):
        return
    raise RunnerRefusal(
        f"this exec site starts the multiplexer binary and nothing else, and no word of "
        f"{argv!r} names it (compared by basename, so an absolute or relative path counts): "
        f"a detached-launch prefix may precede the binary, but an argv that never reaches it "
        f"is not this site's to run — see {WHY}"
    )


def make_run_argv(permitted: frozenset[str], commands: frozenset[str]) -> RunArgv:
    """The one function in `src/` that starts a process (ADR-M3-8).

    Refuses, never repairs. argv only — never `shell=True`, never a path it
    resolved itself, never a `try` around the check: a refusal that becomes an
    `rc` is a refusal a caller can ignore.

    `commands` is T8-3's allow-list for the tmux verbs that run a shell command
    (`permitted_commands(...)`). It is required for the reason `permitted` is:
    both are facts this exec site holds and neither has a safe default —
    `runner/` cannot spell the engine's binary (T8-1) and must not fix a second
    engine's name at import time.
    """

    def run_argv(argv: list[str]) -> CommandResult:
        check_tmux_argv(argv, permitted=permitted, commands=commands)
        check_tmux_argv(_tmux_tail(argv), permitted=permitted, commands=commands)
        _names_the_binary(argv)
        completed = subprocess.run(argv, capture_output=True, check=False)
        return CommandResult(
            rc=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )

    return run_argv


@dataclass
class _PipeStream:
    """The tail of the file `pipe-pane` is appending to, and the way to stop it."""

    path: Path
    stop: Callable[[], None]
    closed: bool = False

    def chunks(self) -> Iterator[bytes]:
        with self.path.open("rb") as handle:
            while True:
                data = handle.read()
                if data:
                    yield data
                    continue
                if self.closed:
                    return
                time.sleep(STREAM_POLL_S)

    def close(self) -> None:
        """Idempotent: closing a closed stream is not an error."""
        if self.closed:
            return
        self.closed = True
        self.stop()


@dataclass(frozen=True)
class LocalRunner:
    """A tmux socket, driven through one injected command seam.

    Satisfies `Runner` structurally; it is not a base class and nothing inherits
    from it (§14.2).
    """

    socket: str
    run_argv: RunArgv
    launch: DetachedLaunch
    now: Callable[[], str]
    spawn_argv: SpawnArgv
    record_anomaly: Callable[[Anomaly], None]
    sink_dir: Path
    cols: int = DEFAULT_COLS
    rows: int = DEFAULT_ROWS

    # ----- the seam ----------------------------------------------------------

    def _run(self, *words: str, prefix: tuple[str, ...] = ()) -> CommandResult:
        """One invocation. An absent binary is a counted unknown, then a refusal."""
        argv = [*prefix, *tmux_argv(self.socket, *words)]
        try:
            return self.run_argv(argv)
        except FileNotFoundError as error:
            self._count(AnomalyKind.TMUX_UNAVAILABLE, f"the tmux binary is not on PATH: {error}")
            raise RunnerRefusal(f"tmux is not available on this host: {argv!r}") from error

    def _checked(self, *words: str, prefix: tuple[str, ...] = ()) -> CommandResult:
        """`_run`, refusing a non-zero rc rather than reading a half answer."""
        result = self._run(*words, prefix=prefix)
        if result.rc != 0:
            raise RunnerRefusal(
                f"tmux exited {result.rc} for {list(words)!r}: "
                f"{result.stderr.decode('utf-8', 'replace').strip()!r}"
            )
        return result

    def _count(self, kind: AnomalyKind, detail: str) -> None:
        self.record_anomaly(Anomaly(kind=kind, detail=detail, engine_session_id=None))

    def _handle(self, name: str) -> RunnerHandle:
        return RunnerHandle(runner=RUNNER_NAME, socket=self.socket, session_name=name)

    # ----- the listing -------------------------------------------------------

    def _listing(self) -> dict[str, PaneFields]:
        """`list-sessions -F` as a map. A line we cannot read is counted, not raised.

        An absent server is an empty map rather than a refusal: `probe` on a
        session tmux has already forgotten is the **normal** path after
        `kill-session`, which removes the row and the exit status with it (E-M3-17).
        """
        result = self._run("list-sessions", "-F", LISTING_FORMAT)
        if result.rc != 0:
            return {}
        found: dict[str, PaneFields] = {}
        for raw in result.stdout.decode("utf-8", "replace").splitlines():
            if not raw.strip():
                continue
            name, separator, rest = raw.partition(FIELD_SEPARATOR)
            try:
                if not separator:
                    raise ValueError(f"no {FIELD_SEPARATOR!r} in {raw!r}")
                found[name] = parse_pane_fields(rest)
            except ValueError as error:
                self._count(AnomalyKind.PANE_UNREADABLE, f"unreadable listing line: {error}")
        return found

    # ----- the members -------------------------------------------------------

    def ensure_server(self) -> None:
        """Probe, and if nothing answers start the server **outside** our cgroup.

        The prefix comes from `host.detached_launch()` (DP5) and is never built
        here: a tmux server first started inside a systemd user unit dies with the
        unit, taking every owned pane with it. `status off` so an attached human
        sees no host name in the status line.
        """
        bootstrap = session_name(BOOTSTRAP_SESSION_ID)
        if self._run("has-session", "-t", target(bootstrap)).rc == 0:
            return
        self._checked(
            "new-session", "-d", "-s", bootstrap, prefix=self.launch.prefix
        )
        self._checked("set-option", "-g", "status", "off")

    def start(self, spec: SessionSpec) -> RunnerHandle:
        """`new-session -d`, then `remain-on-exit` **before anything can exit**.

        E-M3-16: without `remain-on-exit on` a pane that exits is removed and its
        status goes with it. Setting it in a later call loses the exit code of
        every fast failure — a refused trust dialog exits 1 immediately (C15).

        E-M3-10: the **frame** is counted here because only here is it known —
        these words and every `-e K=V` of an unbounded `spec.env` are part of the
        one message tmux measures, and `+ 1` is the separator joining them to the
        engine's first word.
        """
        name = session_name(spec.session_id)
        env: list[str] = []
        for key, value in spec.env.items():
            env += ["-e", f"{key}={value}"]
        prefix = ["new-session", "-d", "-s", name, "-c", spec.cwd,
                  "-x", str(self.cols), "-y", str(self.rows), *env]
        self._checked(*prefix, *self.spawn_argv(spec, frame_bytes=command_size(prefix) + 1))
        self._checked("set-option", "-w", "-t", target(name), "remain-on-exit", "on")
        return self._handle(name)

    def attach(self, handle: RunnerHandle) -> ByteStream:
        """`pipe-pane -o`, and a tail over the file it appends to."""
        sink = self.sink_dir / f"{handle.session_name}.pipe"
        if not SINK_PATH_RE.fullmatch(str(sink)):
            raise RunnerRefusal(
                f"a pipe-pane sink is run through sh -c, so its path is confined to "
                f"{SINK_PATH_RE.pattern}: {str(sink)!r}"
            )
        sink.parent.mkdir(parents=True, exist_ok=True)
        sink.touch()
        spot = target(handle.session_name)
        self._checked("pipe-pane", "-o", "-t", spot, f"cat >> {sink}")

        def stop() -> None:
            self._checked("pipe-pane", "-t", spot)

        return _PipeStream(path=sink, stop=stop)

    def snapshot(self, handle: RunnerHandle, scrollback: int) -> bytes:
        """That much scrollback **plus the visible pane**, ANSI intact (T9-1).

        The argument goes out as the capture's own history depth and nothing
        trims the answer afterwards: the row count of the result is therefore not
        derivable from it (45 rows came back for a depth of 40 on a 45-row pane),
        and acceptance clause 10 pins this argv rather than a length.
        """
        result = self._checked(
            "capture-pane", "-e", "-p", "-S", f"-{scrollback}", "-t", target(handle.session_name)
        )
        return result.stdout

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        """`send-keys -H`, one hex word per byte — byte-exact, and never the tty.

        A2: writing to `#{pane_tty}` delivers **zero** bytes to the program and
        prints the text on the screen instead.
        """
        self._checked(
            "send-keys",
            "-H",
            "-t",
            target(handle.session_name),
            *[f"{byte:02x}" for byte in data],
        )

    def attached_clients(self, handle: RunnerHandle) -> int:
        """`list-clients` for this one session: one line per client, counted.

        The line shape is the captured one —
        `p3-concurrent-20260917T111005Z/04-inner-list-clients.txt` is a single
        client printed through `-F`, and `tmux-attach-keys-…/attach.txt` l.13 is
        the **no client** case, which prints nothing at all. `#{client_tty}` is
        one word per line, so the count cannot be shifted by a client whose other
        fields hold a space.

        Scoped to the target: a client attached to some *other* owned session is
        not a human looking at this pane, and the socket-wide listing would say
        it was.
        """
        result = self._checked(
            "list-clients", "-t", target(handle.session_name), "-F", CLIENT_FORMAT
        )
        return len([line for line in result.stdout.decode("utf-8", "replace").splitlines() if line])

    def clear_input(self, handle: RunnerHandle) -> None:
        """The captured clearing step, verbatim: the key name, never a hex byte.

        `steps.log` l.7 is `send-keys -t =shepherd_kc: C-u` and
        `01b-after-ctrl-u.txt` is the box it left empty. The hex form of the same
        control character through `write()` is **not** captured, which is why
        this is a member of its own rather than a payload (T13-2).
        """
        self._checked("send-keys", "-t", target(handle.session_name), "C-u")

    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None:
        """E-M3-22: this forces `window-size=manual`, so a later human attach is clipped."""
        self._checked(
            "resize-window", "-t", target(handle.session_name), "-x", str(cols), "-y", str(rows)
        )

    def interrupt(self, handle: RunnerHandle) -> None:
        """Escape — never a signal to a pid (D43, N14)."""
        self._checked("send-keys", "-t", target(handle.session_name), "Escape")

    def terminate(self, handle: RunnerHandle) -> None:
        """One session, by its exact target. Never the server (K6, K16)."""
        self._checked("kill-session", "-t", target(handle.session_name))

    def probe(self, handle: RunnerHandle) -> ProcState:
        """One observation. A row tmux no longer has is `alive=False`, not a raise.

        `exit_signal` is always `None`: `#{pane_dead_signal}` was empty even after
        SIGTERM (the engine handled it and exited 143), so it is recorded as an
        unknown rather than inferred from the status.
        """
        observed_at = self.now()
        fields = self._listing().get(handle.session_name)
        if fields is None:
            return ProcState(
                alive=False, pid=None, exit_code=None, exit_signal=None, observed_at=observed_at
            )
        return ProcState(
            alive=not fields.pane_dead,
            pid=fields.pane_pid,
            exit_code=fields.pane_dead_status,
            exit_signal=None,
            observed_at=observed_at,
        )

    def pane(self, handle: RunnerHandle) -> PaneState:
        """`capture-pane -e -p` classified against the listing's format fields.

        The `-e` capture is not optional: plain `-p` cannot separate the TUI's dim
        ghost suggestion from a draft the user typed (E-M3-5).
        """
        capture = self._checked(
            "capture-pane", "-e", "-p", "-t", target(handle.session_name)
        ).stdout
        fields = self._listing().get(handle.session_name)
        if fields is None:
            self._count(
                AnomalyKind.PANE_UNREADABLE,
                f"no listing row for {handle.session_name!r}, so the pane has no format fields",
            )
            raise RunnerRefusal(f"no pane on {self.socket!r} named {handle.session_name!r}")
        anomalies: list[Anomaly] = []
        state = read_pane(capture, fields, anomalies)
        for anomaly in anomalies:
            self.record_anomaly(anomaly)
        return state

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        """The cap's population (N11): panes on the socket, never rows in a store."""
        return tuple(
            PaneRef(
                session_name=name,
                session_id=name[len(SESSION_PREFIX) :],
                pane_pid=fields.pane_pid,
                dead=fields.pane_dead,
            )
            for name, fields in sorted(self._listing().items())
            if OWNED_SESSION_RE.fullmatch(name)
        )
