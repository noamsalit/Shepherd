# EVASION fixture (A1): handing the whole mapping to a callee leaks every key.
def render(signal: object) -> str:
    return format_fields(signal.fields)
