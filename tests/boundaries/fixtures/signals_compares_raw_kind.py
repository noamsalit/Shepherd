# self-check fixture for test_signals_never_compares_raw_kind.
def is_stop(signal: object) -> bool:
    return signal.raw_kind == "the engine's own name"
