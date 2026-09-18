# EVASION fixture (A2): the third spelling, via sysconfig.
import sysconfig


def tag() -> str:
    return sysconfig.get_platform()
