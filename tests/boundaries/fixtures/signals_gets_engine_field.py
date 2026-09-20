# EVASION fixture (A1): `.get()` is not a Subscript — and since every neutral key
# is per-payload optional, `.get()` is the idiom the rule table will be in.
def tool_input(signal: object) -> object:
    return signal.fields.get("tool_input")
