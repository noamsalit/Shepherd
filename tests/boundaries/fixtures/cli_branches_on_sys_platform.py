# self-check fixture: a platform identifier outside host/.
import sys


def is_mac() -> bool:
    return sys.platform == "darwin"
