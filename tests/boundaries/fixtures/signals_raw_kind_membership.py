# EVASION fixture (A3): membership against a tuple of engine names.
def is_terminal(signal: object) -> bool:
    return signal.raw_kind in ("the first name", "the second name")
