# EVASION fixture (A2): `os.name` is one of the two most common ways to branch
# on platform in Python, and D55 says nothing else may branch on platform.
import os


def is_posix() -> bool:
    return os.name == "posix"
