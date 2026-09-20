# self-check fixture for test_kind_is_never_branched_on (E35, F3).
def is_cli(entry: object) -> bool:
    return entry.kind == "cli"
