# NEGATIVE fixture 2 (F4): identifiers are never matched against path literals,
# so a field consumed outside host/ is clean. This is the field whose revision-2
# spelling collided with a raw-text scan.
def fits(plan: object, candidate: str) -> bool:
    return len(candidate.encode()) <= plan.socket_path_budget
