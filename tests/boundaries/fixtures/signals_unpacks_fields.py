# EVASION fixture (A1): `**` leaks every key at once, including the engine's.
def snapshot(signal: object) -> dict[str, object]:
    return {**signal.fields}
