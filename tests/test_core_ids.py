"""T1: `core/ids.py` — the only clock reader in `core/`, with an injectable `now`.

Two of these tests exist because the first version of this file asserted only the
*shape* of a ULID, and both defects it missed were load-bearing:

* the injected `now` was silently discarded whenever any earlier caller had read
  a later wall clock, so `new_ulid(FIXED_NOW)` was deterministic only when this
  test happened to be the process's first ULID caller (C1);
* the `with _lock:` was unasserted — replacing it with `if True:` left the whole
  suite green while 8 threads produced 34 duplicate ids for `session.id`, the
  fleet's join key (§7, C2).

So: the injected clock is decoded out of the id, and the lock is killed by a
concurrency test rather than trusted.
"""

from __future__ import annotations

import threading

from shepherd.core.ids import new_ulid

FIXED_NOW = 1_700_000_000.0
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def decode_ms(ulid: str) -> int:
    """The ULID spec's time component: the leading 10 Crockford base32 chars.

    Decoded independently of `ids.py` (which encodes) — this is the inverse of
    the published spec, not a re-run of the module's own arithmetic.
    """
    value = 0
    for char in ulid[:10]:
        value = value * 32 + _ALPHABET.index(char)
    return value


def test_ulid_is_monotonic_and_sortable() -> None:
    # Known-good literal shape: a ULID is 26 Crockford base32 characters,
    # 10 of time + 16 of randomness (the ULID spec, not a recomputation).
    ids = [new_ulid(FIXED_NOW) for _ in range(1000)]

    assert all(len(value) == 26 for value in ids)
    assert all(set(value) <= set(_ALPHABET) for value in ids)

    # Monotonic within a single millisecond: identical `now`, still strictly increasing.
    assert len(set(ids)) == 1000
    assert ids == sorted(ids)

    # Sortable across time: a later clock sorts after every earlier id.
    later = new_ulid(FIXED_NOW + 1.0)
    assert later > ids[-1]

    # The time component is the leading 10 characters and is stable for one `now`.
    assert len({value[:10] for value in ids}) == 1


def test_injected_clock_reaches_the_id_even_after_a_wall_clock_call() -> None:
    """C1: the injected `now` is authoritative, not merely a lower bound.

    The wall clock is read FIRST on purpose: the defect was invisible while this
    module happened to be the process's first ULID caller.
    """
    new_ulid()  # a 2026 wall-clock reading, which used to poison every later id

    stamped = new_ulid(FIXED_NOW)

    assert decode_ms(stamped) == 1_700_000_000_000
    # …and it is still authoritative when the injected clock moves backwards.
    assert decode_ms(new_ulid(FIXED_NOW - 60.0)) == 1_699_999_940_000
    # A backwards injected clock therefore sorts backwards. That is the point:
    # the caller's clock decides, and callers that want order pass order.
    assert new_ulid(FIXED_NOW - 60.0) < stamped


def test_injected_clock_is_deterministic_from_a_fixed_now() -> None:
    """T12's golden-fixture lane: same injected millisecond, same id sequence."""
    first = [new_ulid(FIXED_NOW + 10.0) for _ in range(3)]
    # A different millisecond restarts the sequence, so returning to it repeats it.
    new_ulid(FIXED_NOW + 11.0)
    second = [new_ulid(FIXED_NOW + 10.0) for _ in range(3)]

    assert first == second
    assert first == sorted(set(first))


def test_concurrent_callers_never_mint_a_duplicate() -> None:
    """C2: kills the `with _lock:` → `if True:` mutant (8×20k produced 34 dupes)."""
    threads_count, per_thread = 8, 20_000
    minted: list[list[str]] = [[] for _ in range(threads_count)]

    def mint(slot: int) -> None:
        minted[slot] = [new_ulid() for _ in range(per_thread)]

    threads = [threading.Thread(target=mint, args=(slot,)) for slot in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    everything = [value for batch in minted for value in batch]
    assert len(everything) == threads_count * per_thread
    assert len(set(everything)) == len(everything)


def test_concurrent_callers_on_one_injected_clock_never_mint_a_duplicate() -> None:
    """The same guarantee on the deterministic lane, which has its own counter."""
    threads_count, per_thread = 8, 20_000
    minted: list[list[str]] = [[] for _ in range(threads_count)]

    def mint(slot: int) -> None:
        minted[slot] = [new_ulid(FIXED_NOW + 5.0) for _ in range(per_thread)]

    threads = [threading.Thread(target=mint, args=(slot,)) for slot in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    everything = [value for batch in minted for value in batch]
    assert len(set(everything)) == threads_count * per_thread
    assert {decode_ms(value) for value in everything} == {1_700_000_005_000}
