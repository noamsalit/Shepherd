# EVASION fixture (A1): a computed key cannot be checked, so it fails closed.
def value(signal: object, key: str) -> object:
    return signal.fields.get(key)
