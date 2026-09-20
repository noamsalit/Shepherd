# EVASION fixture (C5): the same event name, one `b` prefix away from invisible.
def matches(payload: bytes) -> bool:
    return payload == b"SubagentStop"
