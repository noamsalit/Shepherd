# self-check fixture for test_hookd_imports_nothing_from_shepherd
# (Decision pressure 1): a generated command that runs our own code.
def hook_command(socket_path: str) -> str:
    return f"python3 -m shepherd.daemons.hookd {socket_path}"
