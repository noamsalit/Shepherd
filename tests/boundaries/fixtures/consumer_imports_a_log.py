# self-check fixture for test_consumer_boundary: analysed as `shepherd.web`.
# P-M2-10 (D25's guardrail): nothing the UI renders may come to read a log.
from shepherd.logs.stops import read_stop_records


def fleet_page() -> None:
    read_stop_records()
