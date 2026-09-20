# EVASION fixture (A1): iteration and `.keys()` are whole-mapping escapes.
def names(signal: object) -> list[str]:
    return [key for key in signal.fields.keys()]
