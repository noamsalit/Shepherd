# Violating fixture for test_stop_reason_is_never_read_from_a_payload.
#
# Three spellings, because one spelling is how the platform rule was defeated in
# M1 (`import sys as s; s.platform` slipped a scan pinned to `sys.platform`).
# D46's field does not exist on the payload, so every one of these reads `None`
# forever and the rule built on it never fires — silently.
#
# A `#` header rather than a docstring, per the fixtures' convention.


def subscript(payload: dict[str, object]) -> object:
    return payload["stop_reason"]


def dot_get(payload: dict[str, object]) -> object:
    return payload.get("stop_reason")


def through_an_attribute_path(signal: object) -> object:
    # The receiver is an attribute chain, not a bare name — the shape a scan
    # that only inspected `ast.Name` receivers would miss.
    return signal.fields.get("stop_reason")  # type: ignore[attr-defined]


def legal_and_must_not_fire(row: dict[str, object], entry: dict[str, object]) -> object:
    # Our own column and the transcript's own field, in the same file, so the
    # fixture proves the rule discriminates rather than counting occurrences.
    return row["stop_reason"], entry.get("stop_reason")
