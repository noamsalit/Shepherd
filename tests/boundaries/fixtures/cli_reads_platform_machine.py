# EVASION fixture (A2): the architecture half of the same module.
import platform


def arch() -> str:
    return platform.machine()
