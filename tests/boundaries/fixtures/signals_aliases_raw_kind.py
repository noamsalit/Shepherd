# EVASION fixture (A3): the Compare operand is a Name, not the Attribute.
def is_stop(signal: object) -> bool:
    rk = signal.raw_kind
    return rk == "the engine's own name"
