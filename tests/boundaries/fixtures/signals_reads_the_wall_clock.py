# Violating fixture for test_one_clock.
#
# This is not a hypothetical spelling. It is the exact one the M1 closure check
# dropped into signals/ to prove the hand-maintained writer list could not see a
# NEW writer: the full suite passed (exit 0) and mypy --strict passed (exit 0).
#
# A `#` header rather than a docstring is deliberate — the repo's fixtures avoid
# docstrings so a string-literal scan cannot be accused of reading prose. This
# rule is AST-only and would not care, but the convention is worth keeping.

from datetime import UTC, datetime


def stamped_now() -> str:
    # Defect 1's own spelling: a second writer, therefore a second format.
    return datetime.now(UTC).isoformat()


def also_a_violation() -> str:
    # A different speller of the same instant. `.strftime` is how the five
    # original writers disagreed with each other.
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
