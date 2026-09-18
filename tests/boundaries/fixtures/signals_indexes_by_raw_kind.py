# EVASION fixture (A3): dispatch by table lookup is still dispatch.
RULES: dict[str, int] = {}


def rule(signal: object) -> int:
    return RULES[signal.raw_kind]
