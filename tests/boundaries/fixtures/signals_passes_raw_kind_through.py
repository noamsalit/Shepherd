# self-check fixture: passing raw_kind into an anomaly detail is allowed —
# it exists for doctor and anomalies, never for control flow.
def anomaly_detail(signal: object) -> str:
    return f"unmapped: {signal.raw_kind}"
