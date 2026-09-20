# self-check fixture for test_no_platform_branching_outside_host (D55):
# a platform path literal outside host/.
def start_ticks(pid: int) -> str:
    return f"/proc/{pid}/stat"
