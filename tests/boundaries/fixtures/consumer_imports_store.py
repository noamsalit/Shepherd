# self-check fixture for test_consumer_boundary: analysed as `shepherd.web`.
from shepherd.store import open_store


def fleet_page() -> None:
    open_store()
