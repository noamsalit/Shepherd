# EVASION fixture (A2): the platform module itself, under an alias.
import platform as pf


def system() -> str:
    return pf.system()
