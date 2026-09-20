# self-check fixture for test_signals_reads_only_neutral_field_keys (r4 BLOCKING 2).
def changed(signal: object) -> object:
    return signal.fields["tool_input"]
