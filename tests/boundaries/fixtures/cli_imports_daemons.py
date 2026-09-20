# self-check fixture for test_nothing_imports_daemons (ADR-1).
from shepherd.daemons import controld


def status() -> None:
    controld.serve()
