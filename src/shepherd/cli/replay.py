"""`shepherd replay`, rendered (T12).

Its own module for the reason `store/stops.py` is: `cli/commands.py` sits at
ADR-1's 600-line cap, and a command added to a file at its cap pushes the
pressure onto the prose that explains the other five. The seam is the same one
every command uses — `Cli.call` → `invoke()` — and nothing here knows what a
stop log is.

**`cli/` is L5.** It imports no `signals/`, opens no store and reads no log
(D19, D35, DP9). In a standalone `shepherd` process the capability is simply
absent from the tool surface, and the honest failure — *no such capability
here* — is the one `status` already gives.
"""

from __future__ import annotations

from collections.abc import Mapping

from shepherd.cli.commands import (
    EXIT_OK,
    UNKNOWN,
    Cli,
    as_mapping,
    as_rows,
    count,
    flag,
    rate,
    text,
)

__all__ = ["REPLAY_DRY_RUN", "REPLAY_NO_CLASSIFIER", "describe_changes", "run_replay"]


#: RD7 in the product: the diff is written on every run, the columns are not.
#: A command that silently overwrote every verdict because a rule was mid-edit
#: is the one way `replay` can do damage, so the write is the flagged path and
#: the read-only path is the default.
REPLAY_DRY_RUN = "this run changed no column. Pass --apply to overwrite them."

#: RD8: §8's example shows `--classifier h-8`; M2 has no rule-set versioning, so
#: the flag does not exist and the line under the counts says why rather than
#: leaving a reader to assume a comparison happened.
REPLAY_NO_CLASSIFIER = (
    "this build records no classifier version, so nothing above says which rules"
    " wrote the 'before' column (--classifier is not implemented)"
)


def describe_changes(changes: list[Mapping[str, object]]) -> list[str]:
    """§8's census — `unknown → stalled_pending_tool (31)` — in first-seen order.

    The pairs are what a tuner acts on; a bare "37 changed" is a number nobody
    can do anything with.
    """
    counted: dict[str, int] = {}
    for change in changes:
        pair = f"{text(change, 'before', 'no verdict')} → {text(change, 'after', UNKNOWN)}"
        counted[pair] = counted.get(pair, 0) + 1
    return [f"    {pair} ({total})" for pair, total in counted.items()]


def run_replay(cli: Cli, since: str | None, apply: bool) -> int:
    """`replay`, through the one registered tool (D19, D35, DP9).

    In a standalone `shepherd` process the capability is simply not there, and
    `cli.explain` says so and fails — never a silent no-op, and never a second
    store opened from a consumer (§7 rule 3, D37, T18-1's named trap). A tool
    that is present and *refused* the arguments is a different answer with a
    different exit code, which is why the result is read rather than only its
    payload.
    """
    args: dict[str, object] = {"apply": apply}
    if since is not None:
        args["since"] = since
    result = cli.call("replay", args)
    if not result.ok:
        # A refused `--since` is a usage error, not a missing capability: the
        # tool is here and it read the value. Exiting 0 on `--since 30d` after
        # printing `read 0 records` is what this replaces.
        return cli.explain("replay", result)
    payload = as_mapping(result.data)
    cli.say(
        f"  read {count(payload, 'read')} records"
        f" ({count(payload, 'skipped_malformed')} malformed,"
        f" {count(payload, 'skipped_version')} unknown version,"
        f" {count(payload, 'orphaned')} orphaned,"
        f" {count(payload, 'unreadable_files')} unreadable files,"
        f" {count(payload, 'skipped_undated')} undated partitions skipped)"
    )
    cli.say(f"  reclassified {count(payload, 'reclassified')} sessions")
    cli.say(f"  changed {count(payload, 'changed')}:")
    for line in describe_changes(as_rows(payload.get("changes"))):
        cli.say(line)
    cli.say(
        f"  unknown rate: {rate(payload, 'unknown_rate_before') * 100:.1f}%"
        f" → {rate(payload, 'unknown_rate_after') * 100:.1f}%"
    )
    # A crashed rule is a bug, not a rule gap: it is counted beside the rate it
    # is kept out of, never folded into the tuning backlog (D34, principle 5).
    cli.say(f"  classifier failures: {count(payload, 'classifier_failures')}")
    cli.say(f"  diff: {text(payload, 'diff_path', UNKNOWN)}")
    cli.say(f"  {REPLAY_NO_CLASSIFIER}")
    if flag(payload, "applied") is not True:
        cli.say(f"  {REPLAY_DRY_RUN}")
    return EXIT_OK
