"""What an installed wheel is, asserted against the manifest (T17-3, T16-2).

Two M1 deliverables live in `pyproject.toml` and nowhere else, so nothing in the
repo-run path can prove them. Both were found by running the thing rather than
by reading it:

* **T17-3** — `main(argv)` and `run()` exist and 30 tests exercise them, but with
  no `[project.scripts]` table there is no `shepherd` on `PATH` at all.
* **T16-2** — `src/shepherd/web/static/*` is served from the package by path,
  which works from a source tree and in the tests; `[tool.setuptools.packages.find]`
  ships `.py` files only, so an installed wheel answers `/` with a 404.

The manifest is read as data, not grepped: a key in the wrong table is exactly
the failure mode a substring search cannot see.
"""

from __future__ import annotations

import os
import tomllib
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "pyproject.toml"
STATIC_ROOT = REPO_ROOT / "src" / "shepherd" / "web" / "static"


def manifest() -> dict[str, object]:
    with MANIFEST.open("rb") as handle:
        loaded: dict[str, object] = tomllib.load(handle)
    return loaded


def table(root: dict[str, object], *path: str) -> dict[str, object]:
    current: object = root
    for key in path:
        assert isinstance(current, dict), path
        current = current.get(key, {})
    assert isinstance(current, dict), path
    return current


def test_the_shepherd_console_command_is_registered() -> None:
    """T17-3: without this table `shepherd` is importable but not runnable."""
    scripts = table(manifest(), "project", "scripts")
    assert scripts.get("shepherd") == "shepherd.cli.main:run"


def test_the_daemons_have_console_commands_too() -> None:
    """The two processes the composition root is: both are started by a unit
    file or a human, and neither should need `python -m` to exist."""
    scripts = table(manifest(), "project", "scripts")
    assert scripts.get("shepherd-controld") == "shepherd.daemons.controld:run"
    assert scripts.get("shepherd-sessiond") == "shepherd.daemons.sessiond:run"


def test_every_static_asset_ships_in_the_wheel() -> None:
    """T16-2: the fleet page is the milestone's whole point; a 404 on `/` from an
    installed wheel is M1 not shipping, however green the tests are."""
    package_data = table(manifest(), "tool", "setuptools", "package-data")
    patterns = package_data.get("shepherd.web")
    assert isinstance(patterns, list) and patterns != []

    assets = sorted(path.name for path in STATIC_ROOT.iterdir() if path.is_file())
    assert assets != []
    unshipped = [
        name
        for name in assets
        if not any(fnmatch(f"static/{name}", str(pattern)) for pattern in patterns)
    ]
    assert unshipped == [], unshipped


def test_the_live_marker_is_registered() -> None:
    """T18's lane is `@pytest.mark.live` and excluded from the default run; an
    unregistered marker is a warning today and a silent typo tomorrow."""
    options = table(manifest(), "tool", "pytest", "ini_options")
    markers = options.get("markers")
    assert isinstance(markers, list)
    assert any(str(entry).startswith("live") for entry in markers)


def test_every_entry_point_module_runs_as_a_module() -> None:
    """`python -m <module>` must do what the console command does, or say nothing.

    Without `if __name__ == "__main__":`, `python -m shepherd.cli.main doctor`
    imports the module, runs no command, prints nothing and **exits 0** — the
    silent-success failure class, and the one form of "it worked" nobody can
    disprove. `shepherd` is not on `PATH` in a source checkout, so `python -m`
    is also the way this build is actually run.
    """
    import subprocess
    import sys

    for target in table(manifest(), "project", "scripts").values():
        module_name, _, _ = str(target).partition(":")
        completed = subprocess.run(
            [sys.executable, "-m", module_name, "--help-does-not-exist"],
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = completed.stdout + completed.stderr
        assert combined.strip() != "", f"{module_name} ran as a module and said nothing"
        assert completed.returncode != 0, (
            f"{module_name} exited 0 on an argument it does not accept"
        )


def test_every_console_command_resolves_to_a_real_callable() -> None:
    """A manifest string is not an entry point until it imports and calls.

    A typo in `[project.scripts]` is invisible until someone installs the wheel
    and runs the command — this is the cheapest place to find it.
    """
    from importlib import import_module

    for target in table(manifest(), "project", "scripts").values():
        module_name, _, attribute = str(target).partition(":")
        module = import_module(module_name)
        assert callable(getattr(module, attribute)), target


def segment_match(pattern: str, name: str) -> bool:
    """`fnmatch` per path segment — the way a package-data glob actually works.

    Plain `fnmatch` is the wrong model and quietly so: its `*` matches `/`, so
    `fnmatch("static/vendor/xterm.js", "static/*")` is **True** while setuptools
    ships nothing from that directory. A manifest check built on it is a check
    that cannot fail, which is this repo's dominant defect wearing a `*`.
    """
    wanted, given = pattern.split("/"), name.split("/")
    if len(wanted) != len(given):
        return False
    return all(
        fnmatch(piece, part) for part, piece in zip(wanted, given, strict=True)
    )


def test_the_manifest_globs_reach_every_static_asset_one_level_down() -> None:
    """T19/T16-2 again, one directory deeper — where the glob stops matching.

    `test_every_static_asset_ships_in_the_wheel` walks `iterdir()`, which is the
    top level only, so it is satisfied by `static/*` and cannot see that the
    vendored terminal one directory down ships nothing. The defect is the same
    one M1 shipped once; the scan that missed it is the interesting part.
    """
    package_data = table(manifest(), "tool", "setuptools", "package-data")
    patterns = package_data.get("shepherd.web")
    assert isinstance(patterns, list) and patterns != []
    # The matcher is only worth anything if it separates the two: a self-check,
    # because "it agreed with the manifest" is what the broken version did too.
    assert segment_match("static/*", "static/app.js")
    assert not segment_match("static/*", "static/vendor/xterm.js")
    assert fnmatch("static/vendor/xterm.js", "static/*")  # the trap, named

    assets = sorted(
        str(path.relative_to(STATIC_ROOT.parent))
        for path in STATIC_ROOT.rglob("*")
        if path.is_file()
    )
    assert any("vendor/" in name for name in assets), "arrival: no vendored asset"
    unshipped = [
        name
        for name in assets
        if not any(segment_match(str(pattern), name) for pattern in patterns)
    ]
    assert unshipped == [], unshipped


def test_the_vendor_file_ships_in_a_built_wheel(tmp_path: Path) -> None:
    """The manifest is a claim; this builds the wheel and lists what is in it.

    Built through **`pyproject.toml`'s own declared backend**, so the thing under
    test is the manifest this repo ships rather than a second model of it. The
    tree is copied to `tmp_path` first: a backend run in the checkout leaves
    `build/` and `*.egg-info` behind, and a test that dirties the repository it
    is verifying is a test nobody will keep running.

    A single-level `static/*` glob passes every manifest-reading check above and
    fails here, which is the point: M1 shipped that defect once and its symptom
    was a 404 from an installed wheel, three steps away from anything the suite
    could see.
    """
    import shutil
    import subprocess
    import sys
    import zipfile

    tree = tmp_path / "tree"
    tree.mkdir()
    shutil.copy2(MANIFEST, tree / "pyproject.toml")
    shutil.copytree(
        REPO_ROOT / "src",
        tree / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    output = tmp_path / "wheel"
    output.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from setuptools import build_meta;"
            " print(build_meta.build_wheel(sys.argv[1]))",
            str(output),
        ],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-3000:]

    built = sorted(output.glob("*.whl"))
    assert len(built) == 1, built
    with zipfile.ZipFile(built[0]) as wheel:
        shipped = set(wheel.namelist())

    # Arrival first: the wheel is a real wheel holding the package's code.
    assert "shepherd/web/server.py" in shipped
    assert "shepherd/web/static/index.html" in shipped

    expected = {
        f"shepherd/web/{path.relative_to(STATIC_ROOT.parent)}"
        for path in STATIC_ROOT.rglob("*")
        if path.is_file()
    }
    assert len(expected) >= 12, sorted(expected)
    assert "shepherd/web/static/vendor/xterm.js" in expected  # the table is right
    assert sorted(expected - shipped) == [], sorted(expected - shipped)
