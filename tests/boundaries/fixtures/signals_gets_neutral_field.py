# NEGATIVE fixture (BLOCKING 2): `.get("ask")` is a neutral key and is clean.
# The rule is about WHICH key, never about which syntax reads it.
def ask(signal: object) -> object:
    return signal.fields.get("ask")
