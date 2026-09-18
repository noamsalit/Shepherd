# NEGATIVE self-check: the generated command is a socket write and nothing else.
def hook_command(socket_path: str) -> str:
    return f"cat | nc -U -q0 {socket_path}"
