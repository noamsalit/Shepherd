"""Explains how the launchctl job is installed, and mentions /proc in passing.

NEGATIVE fixture (r6): a docstring is prose, not code. It cannot branch on a
platform, and `doctor`'s help text has to be able to say what it does.
"""


def explain() -> int:
    """Return the number of words in the paragraph about systemctl and XDG_ dirs."""
    return 7
