# EVASION fixture (C5): a command emitted as bytes runs our interpreter just as
# surely as one emitted as str.
def hook_command(socket_path: bytes) -> bytes:
    return b"python3 -m shepherd.daemons.hookd " + socket_path
