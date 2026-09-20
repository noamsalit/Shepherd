# NEGATIVE fixture: pass-through into a dataclass field is the whole reason
# raw_kind exists — anomaly detail and doctor, never control flow.
def record(signal: object) -> object:
    return Anomaly(kind="unmapped", detail=signal.raw_kind)
