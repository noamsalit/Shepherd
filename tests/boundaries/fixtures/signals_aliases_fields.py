# EVASION fixture (A1): once the mapping is bound to a local, the subscript
# target is a Name and the attribute-shaped rule never sees it.
def to_model(signal: object) -> object:
    f = signal.fields
    return f["to_model"]
