"""What each `shepherd` command does, with `invoke()` as the only way in.

Two rules shape everything here:

* **Principle 5.** An unknown is printed as an unknown. A missing title, a
  discovery status no scan has published, a host driver that has never been
  verified — each is a value this module renders, never a blank it hides and
  never a reassuring default it invents.
* **§13's response rule.** The tools hand back a projected mapping of plain
  values; this module reads named keys out of it and formats them. It never
  reconstructs a row type, because it cannot import one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TextIO

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.states import FLEET_STATE_ORDER
from shepherd.host.base import HostPlatform, SocketPathTooLong
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.types import CallerContext, Failure, ToolResult

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 64

#: What `status` prints where the title carrier has not landed yet (principle 5).
NO_TITLE = "(no title yet)"

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Cli:
    """One command's world: where to write, who is asking, what host this is."""

    host: HostPlatform
    out: TextIO
    err: TextIO
    ctx: CallerContext
    socket_name: str

    def say(self, line: str) -> None:
        print(line, file=self.out)

    def complain(self, line: str) -> None:
        print(f"shepherd: {line}", file=self.err)

    def call(self, name: str, args: Mapping[str, object]) -> ToolResult:
        return invoke(name, args, self.ctx)

    def read(self, name: str, args: Mapping[str, object]) -> Mapping[str, object] | None:
        """A tool's payload, or `None` after saying what to do about it."""
        result = self.call(name, args)
        if not result.ok:
            self.explain(name, result)
            return None
        return as_mapping(result.data)

    def explain(self, name: str, result: ToolResult) -> int:
        """Say what went wrong and hand back the exit code that fits it.

        Three different pieces of advice, because they are three different
        situations and one of them used to be told as another: a handler that
        raised half way through a destructive write was reported with the
        *capability is absent here* sentence, so a user whose database had just
        been rewritten was told to start a daemon.
        """
        if result.failure is Failure.REFUSED:
            self.complain(f"{name}: {result.error}")
            return EXIT_USAGE
        if result.failure is Failure.FAILED:
            self.complain(
                f"{name} failed while running: {result.error}. The capability is"
                " present here and it raised — whatever it had started may be"
                " half done, so check before re-running it."
            )
            return EXIT_FAILURE
        self.complain(
            f"{name} did not answer: {result.error}. The tool surface this process"
            " sees has no such capability registered — start the shepherd control"
            " daemon, or run this command against a host where it is running."
        )
        return EXIT_FAILURE


# --- reading a projected payload without ever widening to `Any` ---------------


def as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def as_rows(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [as_mapping(item) for item in value]
    return []


def text(payload: Mapping[str, object], key: str, default: str = "") -> str:
    value = payload.get(key)
    return value if isinstance(value, str) and value != "" else default


def rate(payload: Mapping[str, object], key: str) -> float:
    """A projected rate. A key nobody sent is `0.0` over an empty population —
    the same reading `replay` itself gives, never a silent `None` in a `%`."""
    value = payload.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def count(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def flag(payload: Mapping[str, object], key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


# --- status -------------------------------------------------------------------


def state_rank(row: Mapping[str, object]) -> tuple[int, str]:
    """§16's order, derived from state — never alphabetical, never by mtime.

    An unrecognised state sorts after every known one rather than being dropped:
    a state we cannot rank is still a session someone is running.
    """
    state = text(row, "state")
    order = [str(member.value) for member in FLEET_STATE_ORDER]
    rank = order.index(state) if state in order else len(order)
    return rank, text(row, "session_id")


def describe_session(row: Mapping[str, object]) -> str:
    session_id = text(row, "session_id", UNKNOWN)
    title = text(row, "title", NO_TITLE)
    where = text(row, "cwd", UNKNOWN)
    line = f"  {text(row, 'state', UNKNOWN):<10} {title}  ·  {where}  ·  {session_id}"
    reason = text(row, "needs_you_reason")
    return f"{line}\n{'':<13}{reason}" if reason else line


def run_status(cli: Cli) -> int:
    """The fleet, through `fleet_summary` and `list_sessions` (D38)."""
    summary = cli.read("fleet_summary", {})
    if summary is None:
        return EXIT_FAILURE
    listed = cli.read("list_sessions", {})
    if listed is None:
        return EXIT_FAILURE
    counts = as_mapping(summary.get("counts"))
    tally = " · ".join(
        f"{member.value} {count(counts, str(member.value))}" for member in FLEET_STATE_ORDER
    )
    cli.say(f"fleet: {count(summary, 'session_count')} sessions · {tally}")
    rows = sorted(as_rows(listed.get("sessions")), key=state_rank)
    if not rows:
        cli.say("  no sessions are known to this database yet")
    for row in rows:
        cli.say(describe_session(row))
    return EXIT_OK


# --- doctor -------------------------------------------------------------------

#: Principle 5 again, in the one place it is most load-bearing: `doctor` is what
#: a user runs when something is wrong, so a fact we do not have is printed as a
#: fact we do not have — with the reason we do not have it.
NOT_INSPECTED = (
    "hooks: not inspected — pass --settings PATH to name the file to read."
    " There is no default: nothing here points at a file you did not choose."
)

#: Principle 5 at the two lines T17 was blocked on. With the capability absent
#: from the tool surface this consumer still may not go around it (D19, D35), so
#: the answer stays *unknown* — with the reason, never a blank and never a guess.
ENGINE_UNKNOWN = (
    "engine: unknown — no registered tool reports the engine version or the"
    " schema drift-check date, and this consumer may not go around the tool"
    " surface to find out (D19, D35)"
)

SCHEMA_UNKNOWN = (
    "schema version unknown (no registered tool reports it — start the control"
    " daemon, which registers one)"
)

#: An unrun gate must never read as a passed one (G12).
NEVER_CHECKED = "drift check: never run on this host"

DRIFT_VERDICT_DRIFT = "drift"
DRIFT_VERDICT_UNCHECKED = "unchecked"


def describe_host(cli: Cli) -> str:
    """G1/D55: a driver nobody has ever run says so, in capitals."""
    verdict = (
        "verified on this kind of host"
        if cli.host.verified()
        else "UNVERIFIED — this driver has never been run on a real host of this kind,"
        " so every line below it is a best reading rather than an observation"
    )
    return f"host: {type(cli.host).__name__} · {verdict}"


def describe_dirs(cli: Cli) -> str:
    dirs = cli.host.dirs()
    return (
        f"directories: data {dirs.data_dir} · config {dirs.config_dir}"
        f" · runtime {dirs.runtime_dir}"
    )


def describe_supervision(cli: Cli) -> str:
    supervision = cli.host.supervision()
    manageable = "manageable" if supervision.manageable else "not manageable from here"
    return (
        f"supervision: {supervision.kind} · {supervision.detail} · {manageable}"
        f" · {supervision.start_limit_note}"
    )


def describe_login(cli: Cli) -> str:
    login = cli.host.login_persistence()
    enabled = UNKNOWN if login.enabled is None else ("yes" if login.enabled else "no")
    return (
        f"login persistence: survives logout: {enabled} · {login.mechanism}"
        f" · {login.detail}"
    )


def describe_database(cli: Cli, problems: list[str]) -> str:
    """F16: the first-run case is the first thing anyone hits — and §7's
    migration rules 1-2, which now have a line of their own (BLOCKER T17-1)."""
    data_dir = cli.host.dirs().data_dir
    if not data_dir.exists():
        return (
            f"database: not created yet — nothing at {data_dir}, so the control"
            " daemon has never run on this host. Start it and this line changes."
        )
    status = cli.call("schema_status", {})
    if not status.ok:
        return f"database: a data directory exists at {data_dir} · {SCHEMA_UNKNOWN}"
    payload = as_mapping(status.data)
    applied = count(payload, "schema_version")
    expected = count(payload, "expected_version")
    if flag(payload, "database_exists") is not True:
        return (
            f"database: a data directory exists at {data_dir}, but no database file"
            f" is in it yet · this build expects schema version {expected}"
        )
    if applied != expected:
        problems.append(
            f"the database at {data_dir} is at schema version {applied} and this"
            f" build expects {expected}; §7 is forward-only, so run the version"
            " of shepherd that wrote it, or migrate forward"
        )
    return f"database: {data_dir} · schema version {applied} · this build expects {expected}"


def describe_engine(cli: Cli, problems: list[str]) -> str:
    """G12 (BLOCKER T17-2): what is running, what the captures are pinned to, and
    when the drift gate last ran here — stated on every run, not buried."""
    result = cli.call("engine_version", {})
    if not result.ok:
        return ENGINE_UNKNOWN
    payload = as_mapping(result.data)
    version = text(payload, "version", UNKNOWN)
    pinned = text(payload, "pinned_version", UNKNOWN)
    verdict = text(payload, "drift_verdict", DRIFT_VERDICT_UNCHECKED)
    checked_at = text(payload, "drift_checked_at")
    if verdict == DRIFT_VERDICT_UNCHECKED or not checked_at:
        drift = NEVER_CHECKED
    else:
        drift = f"drift check {checked_at}: {verdict}"
    if verdict == DRIFT_VERDICT_DRIFT:
        problems.append(
            "the last engine schema drift check found drift: the captured shapes"
            " can no longer be trusted on this engine. Re-run"
            " docs/probes/drift_check.py and re-probe what moved (D41)"
        )
    return f"engine: {version} · schemas pinned {pinned} · {drift}"


def describe_dispatch(cli: Cli, problems: list[str]) -> str:
    """G2: a hook command that cannot run is refused at install time, not written."""
    try:
        plan = cli.host.control_socket(cli.socket_name)
    except SocketPathTooLong as refusal:
        problems.append(str(refusal))
        return (
            f"control socket: refused — {refusal}. Point the runtime directory"
            " somewhere shorter and re-run."
        )
    socket_line = (
        f"control socket: {plan.path} · budget {plan.socket_path_budget} bytes"
        f" · directory mode {plan.dir_mode:o} · socket mode {plan.sock_mode:o}"
    )
    dispatch = cli.host.hook_dispatch(plan)
    if dispatch.available:
        requires = ", ".join(dispatch.requires) or "nothing"
        dispatch_line = f"hook dispatch: available · requires {requires} · {dispatch.reason}"
    else:
        problems.append(f"the hook dispatcher is unavailable: {dispatch.reason}")
        dispatch_line = (
            f"hook dispatch: unavailable — {dispatch.reason}. install-hooks will"
            " refuse rather than write a hook that cannot run."
        )
    return f"{socket_line}\n{dispatch_line}"


def describe_hooks(cli: Cli, settings_path: str | None, problems: list[str]) -> str:
    """C6: a pre-existing broken entry disables every hook in the file, ours included."""
    if settings_path is None:
        return NOT_INSPECTED
    inspection = cli.read("inspect_hooks", {"settings_path": settings_path})
    if inspection is None:
        problems.append(f"the settings file at {settings_path} could not be read")
        return f"hooks: could not be read at {settings_path}"
    installed = flag(inspection, "installed") is True
    matches = flag(inspection, "command_matches_current_host") is True
    managed = count(inspection, "managed_entries")
    foreign = count(inspection, "foreign_entries")
    if not installed:
        line = (
            f"hooks: not installed in {settings_path} · {foreign} entries there are"
            " not ours and are left alone"
        )
    elif matches:
        line = (
            f"hooks: installed in {settings_path} · {managed} of our entries"
            f" · {foreign} not ours · the installed command matches this host"
        )
    else:
        problems.append(
            f"the hook command installed in {settings_path} is not the one this host"
            " would write; re-run install-hooks --settings PATH --yes"
        )
        line = (
            f"hooks: installed but stale in {settings_path} · {managed} of our entries"
            " · the installed command is NOT the one this host would write"
        )
    breakage = inspection.get("pre_existing_breakage")
    for problem in as_strings(breakage):
        problems.append(f"{settings_path}: {problem}")
        line += f"\n    pre-existing breakage: {problem}"
    return line


def as_strings(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def describe_discovery(summary: Mapping[str, object] | None) -> str:
    """Decision pressure 5 and RD9: which source saw what, and what was skipped."""
    if summary is None:
        return (
            "discovery: unknown — no fleet_summary answered, so nothing here has"
            " observed a session yet"
        )
    discovery = as_mapping(summary.get("discovery"))
    parts: Sequence[str] = (
        f"hooks {text(discovery, 'hooks', UNKNOWN)}",
        f"registry {count(discovery, 'registry_sessions')} sessions",
        f"{count(discovery, 'sdk_cli_skipped')} skipped as non-interactive",
        # T19-1/DP2. The three are rendered **together**, always: a `-p` run
        # shorter than one sweep is never reconciled at all, so `reconciled`
        # on its own would claim a completeness this lane cannot have.
        f"{count(discovery, 'sdk_cli_reconciled')} of those reconciled to ephemeral",
        f"{count(discovery, 'sdk_cli_missed')} missed — rows no sweep ever saw",
        f"{count(discovery, 'skipped_other')} skipped for other reasons",
        f"{count(discovery, 'unknown_status')} unknown status",
        f"last scan {text(discovery, 'last_scan_at', 'never')}",
    )
    return "discovery: " + " · ".join(parts)


#: T18-2 is CLOSED by M3 Task 22. These two counters — the ones that record a
#: permission refusal and a hook block — were rendered as `idle` with a reason
#: for two milestones, because the only engine event that carries a refusal was
#: not in this build's hook subscription and they were **structurally unable to
#: move**. A `0` would have read as "we looked and found none", and this build
#: had never looked.
#:
#: It looks now. The event is subscribed, the installer writes an entry for it,
#: and `tests/cli/test_doctor_idle_counters.py::test_the_two_refusal_counters_can_now_move`
#: drives a real captured refusal through the lane and watches one increment. So
#: the `idle` rendering is gone — an `idle` on a counter that *can* move is the
#: same unexplained value the `idle` was introduced to prevent, pointing the
#: other way — and every anomaly reads as the count it is. There is deliberately
#: no idle-list left in this module to add the next one to.


def describe_anomaly(anomalies: Mapping[str, object], name: str) -> str:
    return f"{name} {count(anomalies, name)}"


def describe_anomalies(summary: Mapping[str, object] | None) -> str:
    if summary is None:
        return "anomalies: unknown — no fleet_summary answered"
    anomalies = as_mapping(summary.get("anomalies"))
    if not anomalies:
        return "anomalies: none are counted by this build"
    counted = " · ".join(describe_anomaly(anomalies, name) for name in sorted(anomalies))
    return f"anomalies: {counted}"


def describe_fleet(summary: Mapping[str, object] | None) -> str:
    if summary is None:
        return (
            "fleet: unknown — fleet_summary is not registered in this process."
            " Run this against a host where the control daemon is running."
        )
    counts = as_mapping(summary.get("counts"))
    tally = " · ".join(
        f"{member.value} {count(counts, str(member.value))}" for member in FLEET_STATE_ORDER
    )
    return f"fleet: {count(summary, 'session_count')} sessions · {tally}"


def run_doctor(cli: Cli, settings_path: str | None) -> int:
    """Twelve lines, and a non-zero exit when one of them needs a human."""
    problems: list[str] = []
    summary_result = cli.call("fleet_summary", {})
    summary = as_mapping(summary_result.data) if summary_result.ok else None
    lines = (
        describe_host(cli),
        describe_dirs(cli),
        describe_dispatch(cli, problems),
        describe_supervision(cli),
        describe_login(cli),
        describe_database(cli, problems),
        describe_hooks(cli, settings_path, problems),
        describe_discovery(summary),
        describe_engine(cli, problems),
        describe_anomalies(summary),
        describe_fleet(summary),
    )
    for line in lines:
        cli.say(line)
    for problem in problems:
        cli.complain(problem)
    return EXIT_FAILURE if problems else EXIT_OK


# --- install-hooks / uninstall-hooks ------------------------------------------

#: Principle 4 made operational: anything that writes the user's configuration
#: asks first. `--yes` is the only spelling of consent, and its absence is a
#: dry run rather than a prompt, so the command is safe under automation too.
CONFIRM = "this run changed nothing. Pass --yes to apply it."

NEEDS_SETTINGS = (
    "{command} needs --settings PATH. There is no default, and that is deliberate:"
    " no run of this command can reach a file you did not name."
)


def dispatch_command(cli: Cli) -> tuple[str, str | None]:
    """`(command, refusal)` — the command this host would write, or why it cannot.

    G2/E19: an unavailable dispatcher and an over-budget socket path are both
    refusals *before* any write. A hook that exits 0 having delivered nothing is
    exactly the failure principle 5 forbids hiding.
    """
    try:
        plan = cli.host.control_socket(cli.socket_name)
    except SocketPathTooLong as refusal:
        return "", str(refusal)
    dispatch = cli.host.hook_dispatch(plan)
    if not dispatch.available:
        return "", f"the hook dispatcher is unavailable: {dispatch.reason}"
    return dispatch.command, None


def report_warnings(cli: Cli, payload: Mapping[str, object]) -> None:
    for warning in as_strings(payload.get("warnings")):
        cli.say(f"    warning: {warning}")


def report_backup(cli: Cli, payload: Mapping[str, object]) -> None:
    backup = text(payload, "backup_path")
    settings = text(payload, "settings_path")
    if backup and backup != settings:
        cli.say(f"    backup: {backup}")
    else:
        cli.say("    no backup was needed: that file did not exist before this run")


def run_install_hooks(
    cli: Cli, settings_path: str | None, *, dry_run: bool, assume_yes: bool
) -> int:
    """Refuse a dead hook, back up, write, validate, restore on failure (C6, G2)."""
    if settings_path is None:
        cli.complain(NEEDS_SETTINGS.format(command="install-hooks"))
        return EXIT_USAGE
    command, refusal = dispatch_command(cli)
    if refusal is not None:
        cli.complain(
            f"{refusal}. install-hooks refuses rather than writing a hook command"
            " that cannot run — a hook that fails silently is worse than no hook."
        )
        return EXIT_FAILURE
    apply_now = assume_yes and not dry_run
    payload = cli.read(
        "install_hooks", {"settings_path": settings_path, "dry_run": not apply_now}
    )
    if payload is None:
        return EXIT_FAILURE
    refused = text(payload, "refused_reason")
    if refused:
        cli.complain(f"install-hooks refused and changed nothing: {refused}")
        return EXIT_FAILURE
    events = count(payload, "events_installed")
    if apply_now:
        cli.say(f"installed our dispatcher entry on {events} events in {settings_path}")
        report_backup(cli, payload)
    else:
        cli.say(f"would install our dispatcher entry on {events} events in {settings_path}")
        cli.say(f"    would write the command: {command}")
        cli.say(f"    {CONFIRM}")
    report_warnings(cli, payload)
    return EXIT_OK


def run_uninstall_hooks(cli: Cli, settings_path: str | None, *, assume_yes: bool) -> int:
    """Remove exactly our marked entries — and, without --yes, only say what it would."""
    if settings_path is None:
        cli.complain(NEEDS_SETTINGS.format(command="uninstall-hooks"))
        return EXIT_USAGE
    if not assume_yes:
        inspection = cli.read("inspect_hooks", {"settings_path": settings_path})
        if inspection is None:
            return EXIT_FAILURE
        managed = count(inspection, "managed_entries")
        foreign = count(inspection, "foreign_entries")
        cli.say(
            f"would remove {managed} of our entries from {settings_path}"
            f" · {foreign} entries there are not ours and would be left alone"
        )
        cli.say(f"    {CONFIRM}")
        return EXIT_OK
    payload = cli.read("uninstall_hooks", {"settings_path": settings_path})
    if payload is None:
        return EXIT_FAILURE
    refused = text(payload, "refused_reason")
    if refused:
        cli.complain(f"uninstall-hooks refused and changed nothing: {refused}")
        return EXIT_FAILURE
    cli.say(f"removed {count(payload, 'events_installed')} of our entries from {settings_path}")
    report_backup(cli, payload)
    report_warnings(cli, payload)
    return EXIT_OK
