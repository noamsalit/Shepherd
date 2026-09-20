# self-check fixture: the exclusion is structural, not textual. The same keyword
# outside a FoldRule construction is not excluded.
def record(evidence: str) -> None:
    return None


record(evidence="§SubagentStop")
