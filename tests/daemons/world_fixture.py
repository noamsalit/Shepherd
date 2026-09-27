"""The daemon suite's shared throwaway host: the `world` fixture and its type.

Moved here verbatim from `tests/daemons/test_controld.py` (qa6 rulings P8), so
`tests/daemons/test_controld_start_order.py` can use the same fixture instead of
a second copy. Nothing in it changed on the way.

**Not a `conftest.py`**, for the reason `scripted_hosts.py` gives: `tests/daemons`
has no `__init__.py`, so a `conftest` here is imported under the bare name
`conftest` and shadows `tests/conftest.py`. Tried in P8: collection of
`tests/e2e/test_live_stop_classification.py` (`from conftest import
SettingsObservation`) then fails. A uniquely named module cannot collide, and a
test module imports the fixture by name (`from world_fixture import World, world`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.host.detect import detect_host


@dataclass(frozen=True)
class World:
    """A throwaway host: XDG dirs, an engine config dir with no sessions in it."""

    data_dir: Path
    runtime_dir: Path
    engine_config_dir: Path
    cwd: Path


#: Every environment variable any `HostPlatform` driver reads to place its
#: directories. All of them are redirected, not just the ones the platform this
#: was written on happens to read: `LinuxHost` takes `XDG_*`, `MacHost` takes
#: `HOME` and `TMPDIR`, and a fixture that sets only one family silently hands
#: the *other* platform the developer's real home. That is not hypothetical —
#: it is what this fixture did, and `~/Library/Application Support/Shepherd`
#: had a real `shepherd.db` in it to prove the point.
HOST_DIR_ENV: tuple[str, ...] = (
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "HOME",
    "TMPDIR",
)


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """A throwaway host — for **whichever** driver `detect_host()` returns.

    `data_dir` and `runtime_dir` are read back from the seam rather than spelled
    here, because the two drivers place them differently
    (`.local/share/shepherd` vs `Library/Application Support/Shepherd`) and a
    test that spells one platform's layout is asserting about the wrong machine
    on the other.
    """
    targets = {
        "XDG_DATA_HOME": tmp_path / "xdg_data_home",
        "XDG_CONFIG_HOME": tmp_path / "xdg_config_home",
        "XDG_STATE_HOME": tmp_path / "xdg_state_home",
        "XDG_CACHE_HOME": tmp_path / "xdg_cache_home",
        "XDG_RUNTIME_DIR": tmp_path / "run",
        "HOME": tmp_path / "home",
        "TMPDIR": tmp_path / "run",
    }
    # The list and the redirect cannot drift apart: adding a variable to
    # HOST_DIR_ENV without redirecting it fails here rather than in whichever
    # test first reads the developer's real home.
    assert tuple(targets) == HOST_DIR_ENV
    for name, target in targets.items():
        monkeypatch.setenv(name, str(target))

    engine_config_dir = tmp_path / "engine-config"
    (engine_config_dir / "sessions").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()

    dirs = detect_host().dirs()
    # Arrival, not trust: the driver really did follow the redirect. Without
    # this the fixture is happy to hand back the real user's directories.
    for directory in (dirs.data_dir, dirs.runtime_dir):
        assert tmp_path in directory.parents, f"{directory} escaped the throwaway host"

    return World(
        data_dir=dirs.data_dir,
        runtime_dir=dirs.runtime_dir,
        engine_config_dir=engine_config_dir,
        cwd=work,
    )
