# self-check fixture for test_storage_boundary (D26).
import sqlite3


def fold_and_save() -> None:
    sqlite3.connect(":memory:")
