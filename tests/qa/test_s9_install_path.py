"""S9 — the install path: `pip install -e .`, then run every console command.

**Nothing is installed on this host.** The three entries in
`[project.scripts]` exist only as declarations; `tests/test_packaging.py` reads
the manifest as data and builds a wheel, which proves the *table* is right and
the *files* ship — and never runs a single one of them. Every other suite in
this tree reaches the CLI as `cli.main.main(argv)`, in-process, with `src/` on
`sys.path`.

So the first thing a Mac will do — `pip install -e .` and then type `shepherd` —
has never been exercised anywhere, and it is the step where a console-script
entry point that names a function that does not exist, a package that does not
import from an installed layout, or a dependency that will not resolve, all
show up at once.

**The venv is a throwaway and it is outside the repo tree** (`tmp_path`), for the
reason `[tool.setuptools.packages.find]` makes obvious: a `.venv` inside the
project is a directory the build backend and every scan in this suite would then
have to be told to ignore.

**Every command runs in a scrubbed environment whose directories are all under
`tmp_path`** — `XDG_*` and `CLAUDE_CONFIG_DIR` included. That is not decoration:
`shepherd-controld` with an unscrubbed environment opens the operator's **real**
`~/.local/share/shepherd/shepherd.db` and binds `/run/user/…/shepherd/`, which
is precisely what happened once while this scenario was being built.

*Lying implementations this now catches:* a `[project.scripts]` entry pointing at
a callable that does not exist (the script exists on `PATH` and dies on import —
invisible to a manifest read); a package that imports only from a source tree; a
dependency range that does not resolve; and a console command that reports
success while printing a refusal — every exit code here is asserted against the
shipped constant, never against a literal.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

from shepherd.cli.commands import EXIT_FAILURE, EXIT_OK, EXIT_USAGE
from shepherd.daemons.controld import EXIT_REFUSED
from shepherd.host.base import HostDirs
from shepherd.host.detect import detect_host

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "pyproject.toml"

INSTALL_TIMEOUT_S = 600.0
COMMAND_TIMEOUT_S = 90.0
READY_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 20.0

READY_PREFIX = "controld: http://"


@dataclass(frozen=True)
class Installed:
    """One throwaway venv with this project installed into it."""

    root: Path
    home: Path
    env: dict[str, str]

    def script(self, name: str) -> Path:
        return self.root / "bin" / name

    def run(self, name: str, *argv: str) -> subprocess.CompletedProcess[str]:
        """One console command, by **path into the venv's `bin/`**.

        Never by bare name through `PATH`: a bare `shepherd` could resolve to
        something else on the machine, and then a green result would be about
        that other thing. The point of this scenario is that *this* install
        produced a runnable command.
        """
        return subprocess.run(
            [str(self.script(name)), *argv],
            cwd=str(self.home),
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_S,
        )


def console_scripts() -> tuple[str, ...]:
    """Every name in `[project.scripts]`, read from the manifest at test time.

    Enumerated, never listed: a fourth console script added to `pyproject.toml`
    joins this scenario by itself, and a literal tuple here is how S9 would go
    stale on the first one.
    """
    import tomllib

    with MANIFEST.open("rb") as handle:
        loaded = tomllib.load(handle)
    scripts = loaded.get("project", {}).get("scripts", {})
    assert scripts, "[project.scripts] is empty; there is nothing to install"
    return tuple(sorted(scripts))


def isolated_env(root: Path, home: Path) -> dict[str, str]:
    """A scrubbed environment, every directory of it under `tmp_path`.

    `PYTHONPATH` is **not** set — that is the whole point: the installed package
    has to be importable from the venv's own `site-packages`, not from `src/`.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CLAUDE", "ANTHROPIC", "AI_AGENT", "XDG_", "PYTHON"))
    }
    env["PATH"] = f"{root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["HOME"] = str(home)
    env["CLAUDE_CONFIG_DIR"] = str(home / "engine-config")
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        env[name] = str(home / name.lower())
    env["XDG_RUNTIME_DIR"] = str(home / "run")
    # `HOME` was already redirected above; `TMPDIR` was not, and it is the
    # other half of the same question — `MacHost` puts the runtime directory
    # under it, so until 2026-09-20 this daemon bound its control socket in the
    # operator's real `$TMPDIR/Shepherd/`. See S8's `isolated_env` for the same
    # fix and the same reasoning.
    env["TMPDIR"] = str(home / "run")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def host_dirs_for(env: Mapping[str, str]) -> HostDirs:
    """The three directories **this host's** driver resolves from `env` (D55).

    S8's helper, repeated here for S8's reason — these two scenario files
    duplicate rather than share, so that an edit to one cannot silently change
    what the other asserts. Asked through `HostPlatform` and never by
    re-spelling one platform's variable names: `LinuxHost` reads `XDG_*`,
    `MacHost` reads `HOME` and `TMPDIR`.
    """
    with mock.patch.dict(os.environ, dict(env), clear=True):
        return detect_host().dirs()


def pid_is_gone(pid: int) -> bool:
    """`not alive`, through the seam the product itself uses (D55).

    `Path(f"/proc/{pid}").exists()` was the reader. On macOS that path never
    exists, so the teardown check below was true of every pid and passed
    without checking. `process_liveness` reads a table on both platforms and
    sends nothing — `os.kill(pid, 0)` is the idiom this repo refuses by name
    (CLAUDE.md, 2026-09-17).
    """
    return not detect_host().process_liveness(pid, None).alive


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Installed]:
    """`python -m venv` + `pip install -e .`, module-scoped.

    Module-scoped because an install is one event and every check here reads the
    same one: four installs would be four subjects for one claim, and it is the
    slowest thing in this package by an order of magnitude.

    The install's own exit code is asserted here rather than in a test, because
    a fixture that swallowed it would turn a broken install into a suite of
    errors about missing files.
    """
    base = tmp_path_factory.mktemp("s9")
    root, home = base / "venv", base / "home"
    home.mkdir()
    for name in ("engine-config", "xdg_data_home", "xdg_config_home", "xdg_state_home",
                 "xdg_cache_home", "run"):
        (home / name).mkdir()

    made = subprocess.run(
        [sys.executable, "-m", "venv", str(root)],
        capture_output=True, text=True, check=False, timeout=INSTALL_TIMEOUT_S,
    )
    assert made.returncode == 0, f"venv creation failed:\n{made.stdout}\n{made.stderr}"

    # **An editable install writes metadata into the *source* tree**, not only
    # into the venv: setuptools produces `src/shepherd.egg-info/` beside the
    # package. It is gitignored and no boundary rule reads it, but it is a file
    # this scenario created in the repo, so the teardown owns it — and only if
    # this run is what created it.
    egg_info = REPO_ROOT / "src" / "shepherd.egg-info"
    egg_info_existed = egg_info.exists()

    # The same "and only if this run is what created it" reasoning, applied to
    # the repo's own venv — which the teardown below used to assert was *empty*
    # of a `shepherd` script, absolutely. That is a claim about how the host was
    # provisioned, not about anything this scenario did: a developer whose
    # `.venv` carries an ordinary `pip install -e .` fails it before the module
    # has run a single test. This host is one (`.venv/bin/shepherd` dated 08:55,
    # before the lane ever ran), and it turned the whole module's teardown red.
    #
    # What this scenario must actually promise is that it did not install into
    # the repo's venv, and that is a **delta**, exactly as `egg_info` above is.
    repo_venv_script = REPO_ROOT / ".venv" / "bin" / "shepherd"
    repo_venv_script_existed = repo_venv_script.exists()

    install = subprocess.run(
        [str(root / "bin" / "pip"), "install", "-e", str(REPO_ROOT)],
        capture_output=True, text=True, check=False, timeout=INSTALL_TIMEOUT_S,
    )
    assert install.returncode == 0, (
        f"`pip install -e .` failed (rc={install.returncode}):\n"
        f"{install.stdout[-4000:]}\n{install.stderr[-4000:]}"
    )
    env = isolated_env(root, home)
    try:
        yield Installed(root=root, home=home, env=env)
    finally:
        # Teardown verifies itself. The venv is under `tmp_path_factory`'s own
        # root, which pytest removes; nothing is installed anywhere else and
        # nothing reaches the real `PATH`.
        assert repo_venv_script.exists() == repo_venv_script_existed, (
            "this scenario changed whether the repo's own venv has a `shepherd` "
            f"script (before={repo_venv_script_existed}, "
            f"after={repo_venv_script.exists()}): the install escaped its throwaway"
        )
        if not egg_info_existed and egg_info.exists():
            shutil.rmtree(egg_info)
            assert not egg_info.exists(), f"{egg_info} survived its own teardown"


def a_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# ----- the install produced the commands --------------------------------------


def test_every_declared_console_script_exists_and_is_executable(
    installed: Installed,
) -> None:
    """Arrival for the whole scenario: the three names really are on disk.

    The names come from the manifest, so this is a comparison between what the
    project **declares** and what the install **produced** — which is the one
    thing `tests/test_packaging.py` cannot do, because it reads only the
    declaration.
    """
    declared = console_scripts()
    missing = [name for name in declared if not installed.script(name).exists()]
    assert missing == [], f"declared in [project.scripts] but not installed: {missing}"
    not_executable = [
        name for name in declared if not os.access(installed.script(name), os.X_OK)
    ]
    assert not_executable == []


def test_every_console_script_resolves_its_entry_point(installed: Installed) -> None:
    """A script that names a callable that does not exist dies on import.

    That failure is **invisible** to a manifest read: `shepherd = "a.b:nope"` is
    a perfectly well-formed table entry. So each command is run and its stderr
    is checked for the two import-time shapes — every command here is expected to
    produce *some* legible output and never a traceback.
    """
    problems = []
    for name in console_scripts():
        answer = installed.run(name, "--no-such-flag-at-all")
        combined = answer.stdout + answer.stderr
        if "Traceback (most recent call last)" in combined:
            problems.append(f"{name}: died with a traceback\n{combined[-1500:]}")
        if not combined.strip():
            problems.append(f"{name}: produced no output at all (rc={answer.returncode})")
    assert problems == []


def test_the_package_imports_from_site_packages_and_not_from_src(
    installed: Installed,
) -> None:
    """`PYTHONPATH` is unset in this environment, so an import can only come
    from the install. Arrival: the module really was imported, and it says where
    from."""
    answer = subprocess.run(
        [str(installed.root / "bin" / "python"), "-c",
         "import shepherd, sys; print(shepherd.__file__); print('src' in sys.path)"],
        cwd=str(installed.home), env=installed.env,
        capture_output=True, text=True, check=False, timeout=COMMAND_TIMEOUT_S,
    )
    assert answer.returncode == 0, answer.stderr
    assert answer.stdout.strip(), "the import printed nothing"
    assert "PYTHONPATH" not in installed.env


# ----- what each command does when a person types it --------------------------


def test_shepherd_with_no_arguments_prints_usage_and_exits_usage(
    installed: Installed,
) -> None:
    """The first thing anybody types. `EXIT_USAGE` from the shipped constant."""
    answer = installed.run("shepherd")
    assert answer.returncode == EXIT_USAGE, (answer.returncode, answer.stderr)
    assert "usage: shepherd" in answer.stdout + answer.stderr


def test_shepherd_help_is_not_a_command_this_build_knows(
    installed: Installed,
) -> None:
    """**A finding, recorded as one.** `--help` is refused, not answered.

    `shepherd --help` — the second thing anybody types, and the first thing a
    Mac user types after `shepherd` alone — prints *"unknown command
    '--help'"* and exits `EXIT_USAGE`. The usage block follows it, so nobody is
    stranded; the message is nevertheless wrong about what happened, because
    `--help` is not an unknown *command*, it is the conventional spelling of the
    thing the usage block is.

    Asserted as the behaviour that is there, so that fixing it turns this red
    and the note in `docs/plans/m1-m4-qa/harness.md` gets re-read.
    """
    answer = installed.run("shepherd", "--help")
    combined = answer.stdout + answer.stderr
    assert answer.returncode == EXIT_USAGE, combined
    assert "unknown command" in combined, combined
    # …and the user is not left with nothing: the usage block is printed anyway.
    assert "usage: shepherd" in combined


def test_shepherd_doctor_runs_and_succeeds(installed: Installed) -> None:
    """The one command a standalone process can fully answer (`EXIT_OK`).

    This is what keeps `status`'s failure below a **finding** rather than a
    broken install: the same binary, the same environment, one command that
    works end to end.
    """
    answer = installed.run("shepherd", "doctor")
    assert answer.returncode == EXIT_OK, answer.stdout + answer.stderr
    assert answer.stdout.strip(), "doctor printed nothing"


def test_shepherd_status_fails_the_way_s8_measured(installed: Installed) -> None:
    """T18-1 again, this time from a **real install**.

    S8 showed it beside a running daemon with `src/` on `PYTHONPATH`; this shows
    the same thing from the artefact a user would actually have. Two different
    routes to the same observation is what makes it a property of the product
    rather than of a harness.
    """
    answer = installed.run("shepherd", "status")
    combined = answer.stdout + answer.stderr
    assert answer.returncode == EXIT_FAILURE, combined
    assert "fleet_summary" in combined
    assert "control daemon" in combined


def test_shepherd_sessiond_refuses_without_its_required_argument(
    installed: Installed,
) -> None:
    """**A finding.** The console script cannot be run as a person would run it.

    `shepherd-sessiond` declares `--expected-schema-version` as *required*, so
    typing the command bare is an `argparse` error and exit 2 — the daemon is
    only startable by something that already knows the schema version. That is a
    defensible design for a supervised unit and a surprise for a human reading
    `[project.scripts]`, and neither the manifest test nor any in-process test
    could have said so.
    """
    answer = installed.run("shepherd-sessiond")
    combined = answer.stdout + answer.stderr
    assert answer.returncode == 2, (answer.returncode, combined)
    assert "expected-schema-version" in combined


def test_shepherd_controld_starts_binds_and_stops(installed: Installed) -> None:
    """The installed daemon, started for real and torn down with its own signal.

    Gated on `controld`'s own readiness banner — bounded, on a reader thread,
    for the reason S8's fixture records. Teardown is `SIGTERM` plus a bounded
    wait plus a liveness check through the host seam, and the exit line the
    daemon prints is read back,
    so *"it stopped"* is the daemon's own account rather than an inference from
    a return code.
    """
    port = a_free_port()
    process = subprocess.Popen(
        [str(installed.script("shepherd-controld")), "--port", str(port)],
        cwd=str(installed.home), env=installed.env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        banner = _wait_for_banner(process)
        assert f":{port}" in banner, banner
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=STOP_TIMEOUT_S)
        rest = process.stdout.read() if process.stdout is not None else ""
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    assert pid_is_gone(process.pid), "the daemon's pid is still alive after teardown"
    assert "controld stopped" in rest, f"the daemon printed no exit line: {rest!r}"
    assert "did not exit" not in rest, f"a thread outlived the shutdown: {rest!r}"


def test_the_daemon_wrote_only_into_the_throwaway_home(installed: Installed) -> None:
    """Isolation, checked against the operator's real directories.

    An environment that failed to scrub would silently open the operator's real
    database. That is not hypothetical — it is what a scratch probe did once
    while this scenario was being written, which is why the check exists rather
    than the promise.

    **Which directory that is depends on the platform**, and until 2026-09-20
    this check named one of them: it looked under `home / "xdg_data_home"`, the
    Linux layout, so on macOS — where `shepherd-controld` resolves
    `Library/Application Support/Shepherd` from `HOME` — it searched a directory
    that had never existed and reported the daemon had written elsewhere. The
    daemon had in fact written inside the throwaway all along; the check was
    looking in the wrong place, which is the same failure in the other
    direction. It now asks the seam where to look.
    """
    for name in ("XDG_DATA_HOME", "XDG_RUNTIME_DIR", "CLAUDE_CONFIG_DIR", "HOME", "TMPDIR"):
        assert installed.env[name].startswith(str(installed.home)), (
            name, installed.env[name]
        )

    # Every directory the driver actually resolved, not every variable we set:
    # on a platform that ignores those variables the loop above proves nothing.
    dirs = host_dirs_for(installed.env)
    for directory in (dirs.data_dir, dirs.config_dir, dirs.runtime_dir):
        assert directory.is_relative_to(installed.home), directory

    made = sorted(path.name for path in installed.home.rglob("*.db"))
    assert made, "the throwaway home is empty; the daemon wrote elsewhere"


def _wait_for_banner(process: subprocess.Popen[str]) -> str:
    """S8's bounded reader, for S8's reason: `readline()` has no deadline."""
    assert process.stdout is not None
    found: list[str] = []
    arrived = threading.Event()

    def read() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if line.startswith(READY_PREFIX):
                found.append(line.strip())
                arrived.set()
                return

    reader = threading.Thread(target=read, name="s9-banner-reader", daemon=True)
    reader.start()
    if arrived.wait(READY_TIMEOUT_S):
        return found[0]
    if process.poll() is not None:
        raise AssertionError(
            f"shepherd-controld exited before binding (rc={process.returncode})"
        )
    raise AssertionError(f"no {READY_PREFIX!r} within {READY_TIMEOUT_S}s")


def test_the_refused_port_path_is_reachable_from_the_installed_daemon(
    installed: Installed,
) -> None:
    """`EXIT_REFUSED`, driven: a held port is a refusal, not a crash.

    Uses a socket this test holds open, so the port really is taken. Without it
    the constant is a value no test in the tree ever observes — and `main`'s
    `except OSError` branch is the one a user meets when they start the daemon
    twice.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        port = int(held.getsockname()[1])
        answer = subprocess.run(
            [str(installed.script("shepherd-controld")), "--port", str(port)],
            cwd=str(installed.home), env=installed.env,
            capture_output=True, text=True, check=False, timeout=COMMAND_TIMEOUT_S,
        )
    combined = answer.stdout + answer.stderr
    assert answer.returncode == EXIT_REFUSED, (answer.returncode, combined)
    assert "not available" in combined, combined
