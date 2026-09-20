# EVASION fixture (A2): `from sys import platform` leaves no dotted chain at all.
from sys import platform


def is_mac() -> bool:
    return platform == "darwin"
