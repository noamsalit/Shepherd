# EVASION fixture (C5): a bytes literal was invisible to every literal rule, and
# `Frame.payload` is bytes — the transport layer is where these appear.
def stat_path() -> bytes:
    return b"/proc/self/stat"
