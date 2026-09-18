# EVASION fixture (A2): `from os import uname`, a bare Name at the call site.
from os import uname


def release() -> str:
    return uname().release
