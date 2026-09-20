# NEGATIVE self-check: `entrypoint` is the discriminator, and comparing a kind
# against the enum member a layer below defines is not a literal branch.
from shepherd.core.signals import SignalKind


def is_cli(entry: object) -> bool:
    return entry.entrypoint == "cli"


def is_stop(signal: object) -> bool:
    return signal.kind == SignalKind.SESSION_STOPPED
