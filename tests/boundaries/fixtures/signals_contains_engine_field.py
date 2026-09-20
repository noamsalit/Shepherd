# EVASION fixture (A1): containment is a read, and it is a branch.
def has_path(signal: object) -> bool:
    return "file_path" in signal.fields
