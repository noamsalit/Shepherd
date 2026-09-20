# EVASION fixture (A3): a string method on an engine event name is branching.
def is_pre(signal: object) -> bool:
    return signal.raw_kind.startswith("Pre")
