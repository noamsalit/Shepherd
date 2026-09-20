# EVASION fixture (A2): `import sys as s` leaves the chain spelled "s.platform".
import sys as s


def is_mac() -> bool:
    return s.platform == "darwin"
