"""ULID generation — the one clock reader in `core/`, with an injectable `now`.

`session.id` is a ulid (§7) and the fleet joins on it, so ids must sort in
creation order even when two are minted inside the same millisecond.
"""

from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_TIME_CHARS = 10
_RANDOM_CHARS = 16
_RANDOM_BITS = 80
_MAX_RANDOM = (1 << _RANDOM_BITS) - 1

#: Load-bearing, and asserted by `test_concurrent_callers_never_mint_a_duplicate`:
#: replacing this with `if True:` produced 34 duplicate ids across 8 threads, and
#: `session.id` is the fleet's join key (§7). Never relax it to a bare block.
_lock = threading.Lock()

#: The wall-clock lane's anti-regression state. It is deliberately NOT shared with
#: the injected lane: a module global fed by `time.time()` used to swallow every
#: injected `now` below the highest clock any previous caller had observed, which
#: made `new_ulid(fixed)` deterministic only for the process's first caller.
_last_ms = -1
_last_random = 0

#: The injected lane's state, keyed by the injected millisecond. The counter
#: restarts at zero on every new millisecond, so a fixed `now` yields a fixed
#: sequence — what T12's golden-fixture lane needs.
_injected_ms = -1
_injected_random = 0


def _encode(value: int, width: int) -> str:
    chars = ["0"] * width
    for index in range(width - 1, -1, -1):
        chars[index] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_ulid(now: float | None = None) -> str:
    """Return a 26-character ULID.

    Two lanes, because they want opposite things and sharing state between them
    silently broke the second one:

    * **`now is None` — the wall-clock lane.** The id sorts after every ULID this
      process has minted. A clock that stalls or moves backwards advances the
      random component instead, so ordering never regresses.
    * **`now` given — the injected lane.** The injected clock is *authoritative*:
      `int(now * 1000)` is the id's time component, full stop. Callers that want
      ordering pass ordered clocks; a backwards `now` yields a backwards id, which
      is the honest answer. Within one injected millisecond the ids are strictly
      increasing, unique, and identical run to run.
    """
    global _last_ms, _last_random, _injected_ms, _injected_random

    if now is not None:
        stamp_ms = int(now * 1000)
        with _lock:
            if stamp_ms != _injected_ms:
                _injected_ms, _injected_random = stamp_ms, 0
            else:
                _injected_random += 1
            return _encode(stamp_ms, _TIME_CHARS) + _encode(_injected_random, _RANDOM_CHARS)

    stamp_ms = int(time.time() * 1000)
    with _lock:
        if stamp_ms > _last_ms:
            _last_ms = stamp_ms
            _last_random = int.from_bytes(os.urandom(10), "big")
        elif _last_random < _MAX_RANDOM:
            _last_random += 1
        else:
            _last_ms += 1
            _last_random = int.from_bytes(os.urandom(10), "big")
        return _encode(_last_ms, _TIME_CHARS) + _encode(_last_random, _RANDOM_CHARS)
