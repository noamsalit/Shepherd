# self-check fixture for test_consumer_boundary: analysed as `shepherd.cli`.
import sqlite3


def status() -> None:
    sqlite3.connect("shepherd.db")
