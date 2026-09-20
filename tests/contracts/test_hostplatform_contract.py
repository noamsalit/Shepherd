"""The one contract suite every `HostPlatform` implementation passes (T3, T4).

D55 draws the seam; §14.2 says a `Protocol` earns a `Scripted*` double and one
suite every implementation passes. Three implementations run here —
`LinuxHost` (verified on this host), `MacHost` (written, **unverified**, no
capture exists for any of its values — G1) and `ScriptedHost` (a concrete peer
that answers from a fixture, never a base class).

Real-host assertions are **skipped, never faked**, for a driver whose platform
is not the one running the suite. The platform-independent half — record
shapes, budget arithmetic, path composition, the dispatch command's shape — runs
everywhere, which is what keeps `MacHost` honest rather than merely absent.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import shutil
import socket
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

import pytest

from shepherd.core.clock import parse_stamp
from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.host.base import (
    DetachedLaunch,
    HookDispatchPlan,
    HostDirs,
    HostPlatform,
    Liveness,
    LoginPersistence,
    SocketPathTooLong,
    SocketPlan,
    Supervision,
)
from shepherd.host.detect import detect_host
from shepherd.host.linux import (
    LINUX_SOCKET_PATH_BUDGET,
    LinuxHost,
    login_persistence_argv,
    supervision_probe_argv,
)
from shepherd.host.mac import MAC_SOCKET_PATH_BUDGET, MacHost, UnverifiedHostCapability
from shepherd.testkit.scripted_host import ScriptedHost

ON_LINUX = sys.platform.startswith("linux")
ON_DARWIN = sys.platform == "darwin"

#: Verbs that would *change* the host. `login_persistence()` and
#: `supervision()` are observations; T3's scope forbids them from mutating
#: anything. An argv element is always a standalone literal, so the rule is
#: "no literal in `host/` **is** one of these words" — prose that happens to
#: contain the word "start" is not an argv and is not an offender.
MUTATING_ARGV_WORDS: frozenset[str] = frozenset(
    {
        "enable",
        "disable",
        "start",
        "stop",
        "restart",
        "kill",
        "bootstrap",
        "bootout",
        "kickstart",
        "load",
        "unload",
    }
)

#: The two provenance markers a `mac.py` literal may carry (see
#: `test_machost_constants_are_annotated`). `VERIFIED` is a **substring** of
#: `UNVERIFIED`, which is exactly the spelling collision that would let one
#: marker silently satisfy the other's rule — so the verified marker is matched
#: with a negative lookbehind and must carry its capture inside parentheses.
UNVERIFIED_MARKER = "UNVERIFIED"
VERIFIED_CAPTURE = re.compile(r"(?<!UN)VERIFIED \((?P<capture>[^)]*)\)")

#: Where a capture may live. A `VERIFIED` annotation that points anywhere else
#: is not a citation.
CAPTURE_ROOT = "docs/probes/"

#: D55's seam owns exactly **seven** things, plus `verified()` — which reports
#: on the driver, not on the host, and so is not one of the seven.
SEAM_MEMBERS: frozenset[str] = frozenset(
    {
        "dirs",
        "control_socket",
        "hook_dispatch",
        "supervision",
        "process_liveness",
        "login_persistence",
        "detached_launch",
        "verified",
    }
)

#: …and these appear only ever as commands, so they are forbidden anywhere in
#: a literal, prose included.
MUTATING_COMMAND_FRAGMENTS: tuple[str, ...] = (
    "enable-linger",
    "disable-linger",
    "set-property",
    "daemon-reload",
)


# --------------------------------------------------------------------------
# The three implementations under one suite
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Implementation:
    """One driver plus whether *this* machine can answer its real-host cases."""

    name: str
    host: HostPlatform
    real_host: bool


def scripted_fixture() -> ScriptedHost:
    """`ScriptedHost` built from the seven frozen records (T4)."""
    runtime_dir = Path("/scripted/run/shepherd")
    dirs = HostDirs(
        data_dir=Path("/scripted/data/shepherd"),
        config_dir=Path("/scripted/config/shepherd"),
        runtime_dir=runtime_dir,
    )
    socket_plan = SocketPlan(
        path=runtime_dir / "sessiond.sock",
        dir_mode=0o700,
        sock_mode=0o600,
        socket_path_budget=107,
    )
    dispatch = HookDispatchPlan(
        command=f"scripted-send {socket_plan.path}",
        requires=("scripted-send",),
        available=True,
        reason="scripted fixture",
    )
    supervision = Supervision(
        kind="foreground",
        detail="scripted fixture: no supervisor",
        manageable=False,
        start_limit_note="scripted fixture: no start limit applies",
    )
    login = LoginPersistence(
        enabled=True,
        mechanism="scripted fixture",
        detail="scripted fixture: persistence is whatever the fixture says",
    )
    return ScriptedHost(
        host_dirs=dirs,
        socket_plan=socket_plan,
        dispatch=dispatch,
        supervision_plan=supervision,
        login=login,
        liveness_by_pid={
            4049158: Liveness(
                alive=True,
                start_token="544014506",
                observed_at="2026-09-16T00:00:00+00:00",
            )
        },
        observed_at="2026-09-16T00:00:00+00:00",
        is_verified=False,
    )


IMPLEMENTATIONS: tuple[Implementation, ...] = (
    Implementation("LinuxHost", LinuxHost(), ON_LINUX),
    Implementation("MacHost", MacHost(), ON_DARWIN),
    # A fixture answers every question, so every case is a "real host" case.
    Implementation("ScriptedHost", scripted_fixture(), True),
)

IMPLEMENTATION_IDS: tuple[str, ...] = tuple(impl.name for impl in IMPLEMENTATIONS)


@pytest.fixture(params=IMPLEMENTATIONS, ids=IMPLEMENTATION_IDS)
def implementation(request: pytest.FixtureRequest) -> Iterator[Implementation]:
    impl = request.param
    assert isinstance(impl, Implementation)
    yield impl


# --- the seven members, one assertion block each ----------------------------


def assert_dirs_case(host: HostPlatform) -> None:
    dirs = host.dirs()
    assert isinstance(dirs, HostDirs)
    for directory in (dirs.data_dir, dirs.config_dir, dirs.runtime_dir):
        assert directory.is_absolute(), directory
    assert len({dirs.data_dir, dirs.config_dir, dirs.runtime_dir}) == 3


def assert_control_socket_case(host: HostPlatform) -> None:
    plan = host.control_socket("sessiond")
    assert isinstance(plan, SocketPlan)
    assert plan.path.name == "sessiond.sock"
    assert plan.path.parent == host.dirs().runtime_dir
    assert plan.dir_mode == 0o700  # §15 l.2219
    assert plan.sock_mode == 0o600  # §13 l.2044, E20
    assert plan.socket_path_budget > 0

    # The budget is enforced by the seam, not by whoever binds (E19).
    headroom = plan.socket_path_budget - len(str(plan.path.parent).encode("utf-8")) - len(".sock")
    at_budget = host.control_socket("x" * (headroom - 1))
    assert len(str(at_budget.path).encode("utf-8")) == plan.socket_path_budget
    with pytest.raises(SocketPathTooLong):
        host.control_socket("x" * headroom)


def assert_hook_dispatch_case(host: HostPlatform) -> None:
    plan = host.control_socket("sessiond")
    dispatch = host.hook_dispatch(plan)
    assert isinstance(dispatch, HookDispatchPlan)
    # The contract case is that a driver *has* a command naming its
    # requirements — never that two drivers' commands are equal.
    assert dispatch.command.strip() != ""
    assert dispatch.requires != ()
    assert all(requirement.strip() != "" for requirement in dispatch.requires)
    assert dispatch.reason.strip() != ""


def assert_supervision_case(host: HostPlatform) -> None:
    supervision = host.supervision()
    assert isinstance(supervision, Supervision)
    assert supervision.kind in ("systemd_user", "launchd", "foreground")
    assert supervision.detail.strip() != ""
    assert supervision.start_limit_note.strip() != ""


def assert_process_liveness_case(host: HostPlatform) -> None:
    # A pid that cannot exist is observed as gone, never guessed as alive.
    gone = host.process_liveness(0x7FFFFFFF, None)
    assert isinstance(gone, Liveness)
    assert gone.alive is False
    assert gone.observed_at.strip() != ""


def assert_login_persistence_case(host: HostPlatform) -> None:
    persistence = host.login_persistence()
    assert isinstance(persistence, LoginPersistence)
    assert persistence.enabled in (True, False, None)
    assert persistence.mechanism.strip() != ""
    assert persistence.detail.strip() != ""


def assert_detached_launch_case(host: HostPlatform) -> None:
    plan = host.detached_launch()
    assert isinstance(plan, DetachedLaunch)
    assert isinstance(plan.prefix, tuple)
    assert plan.mechanism.strip() != ""
    assert plan.detail.strip() != ""
    assert isinstance(plan.verified, bool)
    # Whatever the wrapper, the wrapped argv survives it unchanged and in order.
    argv = ["a-long-lived-server", "--socket", "shepherd-m3-example"]
    assert [*plan.prefix, *argv][len(plan.prefix) :] == argv


def test_contract_suite(implementation: Implementation) -> None:
    """Seven members plus `verified()`, against every implementation."""
    host = implementation.host

    # Platform-independent half — runs everywhere, for every driver.
    assert_dirs_case(host)
    assert_control_socket_case(host)
    assert_hook_dispatch_case(host)
    assert isinstance(host.verified(), bool)

    if not implementation.real_host:
        pytest.skip(
            f"{implementation.name}: real-host cases skipped on {sys.platform} "
            "(skipped, never faked — G1)"
        )

    assert_supervision_case(host)
    assert_process_liveness_case(host)
    assert_login_persistence_case(host)
    assert_detached_launch_case(host)


def test_detect_host_returns_the_driver_for_this_platform() -> None:
    host = detect_host()
    assert host.verified() is ON_LINUX
    assert isinstance(host, LinuxHost if ON_LINUX else MacHost)


# --------------------------------------------------------------------------
# T3 — LinuxHost, against the captures
# --------------------------------------------------------------------------


def test_dirs_apply_xdg_defaults(tmp_path: Path) -> None:
    """E22/C3: neither `XDG_DATA_HOME` nor `XDG_CONFIG_HOME` is ever set here."""
    home = tmp_path / "home"
    host = LinuxHost(environ={"HOME": str(home), "XDG_RUNTIME_DIR": str(tmp_path / "run")}, uid=7)
    dirs = host.dirs()
    assert dirs.data_dir == home / ".local" / "share" / "shepherd"
    assert dirs.config_dir == home / ".config" / "shepherd"

    # …and an explicitly set variable wins over the default.
    overridden = LinuxHost(
        environ={
            "HOME": str(home),
            "XDG_DATA_HOME": str(tmp_path / "d"),
            "XDG_CONFIG_HOME": str(tmp_path / "c"),
            "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        },
        uid=7,
    )
    assert overridden.dirs().data_dir == tmp_path / "d" / "shepherd"
    assert overridden.dirs().config_dir == tmp_path / "c" / "shepherd"

    # On this host both variables really are unset (the capture's claim).
    assert "XDG_DATA_HOME" not in os.environ
    assert "XDG_CONFIG_HOME" not in os.environ


def test_runtime_dir_falls_back_to_run_user_uid(tmp_path: Path) -> None:
    """C3/G7: `XDG_RUNTIME_DIR` has no default — derive it from `os.getuid()`."""
    host = LinuxHost(environ={"HOME": str(tmp_path)}, uid=1234)
    assert host.dirs().runtime_dir == Path("/run/user/1234/shepherd")

    # The derivation, not the literal `0` every probe happened to record.
    live = LinuxHost(environ={"HOME": str(tmp_path)})
    assert live.dirs().runtime_dir == Path(f"/run/user/{os.getuid()}/shepherd")

    # When it *is* set (it is, on this host: /run/user/0), it is used verbatim.
    used = LinuxHost(environ={"HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(tmp_path / "r")}, uid=9)
    assert used.dirs().runtime_dir == tmp_path / "r" / "shepherd"


def test_socket_path_budget_enforced(tmp_path: Path) -> None:
    """E19: the seam refuses one byte past the budget, and this kernel agrees.

    Two halves, tangled until 2026-09-20. The first is **arithmetic**:
    `plan_socket()` refuses one byte past whatever budget the driver carries.
    That is pure, so it runs against `LinuxHost` on any host and says nothing
    about the machine it runs on.

    The second asks **this kernel** whether the budget is folklore, and it can
    only ever be about the platform running the suite. 107 bytes bind on Linux;
    on macOS `sun_path` is 104 bytes including the NUL, so 103 bind and 104
    raise `OSError: AF_UNIX path too long`
    (`docs/probes/2026-09-20-macos-g1-capture.md` §1). This half used to assert
    the *Linux* constant against whatever kernel was present, which is why a
    macOS budget that was right the whole time produced a red suite here.
    """
    assert LINUX_SOCKET_PATH_BUDGET == 107

    runtime = tmp_path / "run"
    host = LinuxHost(environ={"HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(runtime)}, uid=0)
    prefix = len(str(host.dirs().runtime_dir).encode("utf-8")) + len("/.sock")
    ok = host.control_socket("s" * (LINUX_SOCKET_PATH_BUDGET - prefix))
    assert len(str(ok.path).encode("utf-8")) == LINUX_SOCKET_PATH_BUDGET
    with pytest.raises(SocketPathTooLong) as refused:
        host.control_socket("s" * (LINUX_SOCKET_PATH_BUDGET - prefix + 1))
    assert refused.value.budget == LINUX_SOCKET_PATH_BUDGET

    # The budget is not folklore: this kernel agrees at exactly this boundary,
    # at whichever number the driver for this platform carries.
    budget = detect_host().control_socket("sessiond").socket_path_budget
    assert budget == (MAC_SOCKET_PATH_BUDGET if ON_DARWIN else LINUX_SOCKET_PATH_BUDGET)

    directory = tmp_path / "b"
    directory.mkdir()
    base = str(directory) + "/"
    binds = base + "a" * (budget - len(base.encode("utf-8")))
    assert len(binds.encode("utf-8")) == budget
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as good:
        good.bind(binds)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as bad:
        with pytest.raises(OSError):
            bad.bind(binds + "a")


def test_socket_plan_dispatch_command_names_its_requirements() -> None:
    host = LinuxHost()
    dispatch = host.hook_dispatch(host.control_socket("sessiond"))
    assert dispatch.requires == ("timeout", "nc")
    for requirement in dispatch.requires:
        assert requirement in dispatch.command
    assert str(host.control_socket("sessiond").path) in dispatch.command
    assert dispatch.reason.strip() != ""


def test_linux_dispatch_command_carries_q0() -> None:
    """E34: without `-q0` the same command costs 253.6 ms instead of 3.2 ms."""
    host = LinuxHost()
    dispatch = host.hook_dispatch(host.control_socket("sessiond"))
    assert "-q0" in dispatch.command.split()


def test_dispatch_command_is_the_only_platform_difference_asserted_here() -> None:
    """The contract case is shape, not equality (G2, E34)."""
    linux_host = LinuxHost()
    mac_host = MacHost()
    linux_dispatch = linux_host.hook_dispatch(linux_host.control_socket("sessiond"))
    mac_dispatch = mac_host.hook_dispatch(mac_host.control_socket("sessiond"))

    for dispatch in (linux_dispatch, mac_dispatch):
        assert dispatch.command.strip() != ""
        assert dispatch.requires != ()

    assert linux_dispatch.command != mac_dispatch.command
    assert "-q0" in linux_dispatch.command.split()
    assert "-q0" not in mac_dispatch.command.split()


def test_supervision_is_foreground_without_runtime_dir(tmp_path: Path) -> None:
    """E23/C3: `No medium found` is a deployment shape, not an error."""
    containerish = LinuxHost(environ={"HOME": str(tmp_path)}, uid=0)
    supervision = containerish.supervision()
    assert supervision.kind == "foreground"
    assert supervision.manageable is False
    assert supervision.detail.strip() != ""

    assert supervision_probe_argv() == ("systemctl", "--user", "is-system-running")


@pytest.mark.skipif(not ON_LINUX, reason="reads /proc")
def test_process_liveness_matches_proc_stat_field_22() -> None:
    """E31/C13: field 22 is the start token the registry calls `procStart`."""
    pid = os.getpid()
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    after_comm = raw[raw.rindex(")") + 1 :].split()
    assert len(after_comm) + 2 == 52  # the capture's field count
    expected = after_comm[19]  # field 22 == index 19 after (pid, comm)

    liveness = LinuxHost().process_liveness(pid, None)
    assert liveness.alive is True
    assert liveness.start_token == expected
    # The stamp is UTC and in the one format `core.clock` writes and reads —
    # a host stamp becomes `observed_at`/`ended_at` on a real session row.
    assert liveness.observed_at.endswith("Z")
    parsed = parse_stamp(liveness.observed_at)
    assert parsed is not None and parsed.tzinfo is UTC

    # Given the token, the same process is still the same process.
    assert LinuxHost().process_liveness(pid, expected).alive is True


@pytest.mark.skipif(not ON_LINUX, reason="reads /proc")
def test_process_liveness_rejects_mismatched_start_token() -> None:
    """E31: a pid whose start token differs is a **different** process."""
    liveness = LinuxHost().process_liveness(os.getpid(), "1")
    assert liveness.alive is False
    assert liveness.start_token is not None
    assert liveness.start_token != "1"

    gone = LinuxHost().process_liveness(0x7FFFFFFF, None)
    assert gone.alive is False
    assert gone.start_token is None


def host_string_literals() -> Iterator[tuple[str, str]]:
    host_package = Path(inspect.getfile(LinuxHost)).parent
    for module in sorted(host_package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield module.name, node.value


def test_login_persistence_is_read_only() -> None:
    """T3 scope: observe lingering; never flip it."""
    argv = login_persistence_argv(1234)
    assert argv[0] == "loginctl"
    assert argv[1] == "show-user"
    assert "1234" in argv
    assert not MUTATING_ARGV_WORDS & set(argv)
    assert not MUTATING_ARGV_WORDS & set(supervision_probe_argv())

    # No mutating verb is constructible anywhere in host/, in any driver.
    offenders = [
        f"{module}: {literal!r}"
        for module, literal in host_string_literals()
        if literal.strip() in MUTATING_ARGV_WORDS
        or any(fragment in literal for fragment in MUTATING_COMMAND_FRAGMENTS)
    ]
    assert offenders == []

    persistence = LinuxHost().login_persistence()
    assert persistence.enabled in (True, False, None)


def test_host_subprocess_calls_are_argv_lists() -> None:
    """K5: no `shell=True`, ever."""
    host_package = Path(inspect.getfile(LinuxHost)).parent
    for module in sorted(host_package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    assert keyword.arg != "shell", f"{module.name} passes shell="


# --------------------------------------------------------------------------
# T4 — MacHost is unverified and says so; ScriptedHost is a peer
# --------------------------------------------------------------------------


def test_machost_reports_unverified() -> None:
    assert MacHost().verified() is False
    assert LinuxHost().verified() is True
    assert MAC_SOCKET_PATH_BUDGET == 103  # D55, no capture
    assert MAC_SOCKET_PATH_BUDGET != LINUX_SOCKET_PATH_BUDGET


def test_machost_dispatch_is_unavailable_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G2/E34: a dispatcher that does not resolve refuses, by name.

    This test is the same rule it always was, applied one layer down. It used
    to assert that `MacHost` refuses **unconditionally**, because the flag set
    was a guess (G2). The flag set was measured on 2026-09-20
    (`docs/probes/2026-09-20-macos-g1-capture.md` §2), so refusing regardless of
    the host would now be the dishonest answer — it would report "no capture"
    on a host where the capture exists.

    What must not weaken is the half that protects the user: a host where the
    requirements do not resolve gets **no hook and a reason naming what is
    missing**, never a hook that exits 0 having delivered nothing. So the
    refusal is provoked here rather than assumed, by giving the process a PATH
    with nothing on it.
    """
    host = MacHost()
    plan = host.control_socket("sessiond")

    monkeypatch.setenv("PATH", str(tmp_path))
    refused = host.hook_dispatch(plan)
    assert refused.available is False
    assert refused.reason.startswith("missing on this host: ")
    for requirement in host.hook_dispatch(plan).requires:
        assert requirement in refused.reason
    assert build_hook_entry(plan, refused).command == ""


@pytest.mark.skipif(
    not ON_DARWIN,
    reason="the dispatcher is probed against this host's PATH; only a Mac has the Mac's",
)
def test_machost_dispatch_resolves_on_a_stock_mac() -> None:
    """G1's netcat item, closed: stock `/usr/bin/perl` and `/usr/bin/nc`.

    `tests/engines/test_hook_dispatch_delivery.py` is the half that proves the
    command *works*; this is the half that proves it is reachable with nothing
    installed. Neither `timeout` nor `gtimeout` may appear in it — they are
    `coreutils`, and requiring a `brew install` to see any signal at all would
    make the engine's whole hook lane opt-in on this platform.
    """
    host = MacHost()
    dispatch = host.hook_dispatch(host.control_socket("sessiond"))
    assert dispatch.available is True, dispatch.reason
    assert dispatch.requires == ("perl", "nc")
    # Two different facts, asserted separately. Until 2026-09-20 this was one
    # assertion — `shutil.which(requirement).startswith("/usr/bin/")` — which
    # is a claim about **PATH order**, not about what ships with the OS. Both
    # `perl` and `netcat` are common Homebrew formulae, and a host that has
    # either puts `/opt/homebrew/bin` first: the test would go red on a machine
    # where `hook_dispatch()` is correct and the product works. A false red on
    # someone else's Mac is not a stricter test, it is a broken one.
    for requirement in dispatch.requires:
        stock = Path("/usr/bin") / requirement
        assert stock.is_file(), (
            f"{requirement} is not at {stock}: the claim this test makes is that "
            "the dispatcher needs nothing installed, and that claim is about the "
            "stock location, not about PATH"
        )
        assert shutil.which(requirement) is not None, (
            f"{requirement} is present at {stock} but not reachable on PATH"
        )
    assert "timeout" not in dispatch.command.split()
    assert "gtimeout" not in dispatch.command.split()
    # The measured trap, kept out (§2): -w 0 truncates a 40 KB frame. Matched
    # by prefix, not by set membership: Apple's `nc` takes `-w0` as a single
    # token, which is how the regression would idiomatically be written, and a
    # rule keyed on one exact spelling passes on the other spelling of the same
    # violation. `tests/engines/test_hook_dispatch_delivery.py` catches the
    # truncation itself byte-for-byte; this names the cause.
    offending = [token for token in dispatch.command.split() if token.startswith("-w")]
    assert offending == [], (
        f"the dispatch command carries a netcat idle timeout: {offending}. "
        "§2 measured -w 0 truncating a 40 KB frame; the bound is the perl alarm."
    )


@pytest.mark.skipif(ON_DARWIN, reason="on macOS the probes run for real")
def test_machost_refuses_host_probes_off_platform() -> None:
    host = MacHost()
    for probe in (host.supervision, host.login_persistence):
        with pytest.raises(UnverifiedHostCapability):
            probe()
    with pytest.raises(UnverifiedHostCapability):
        host.process_liveness(1, None)


def test_machost_constants_are_annotated() -> None:
    """Every value literal in `mac.py` sits on a line that says where it came from.

    "Value literal" is every `str`, `int` and `float` constant that is not a
    docstring. `bool` and `Ellipsis` are excluded: `frozen=True`,
    `check=False` and `tuple[str, ...]` are control flow and typing, not
    claims about macOS. Every literal that *is* a claim — a path, a budget, a
    mode, a flag set, a reason — must carry one of **two** markers.

    Until 2026-09-20 there was one marker and it said `UNVERIFIED (no capture)`.
    Three of G1's five items closed that day on a real Mac, and leaving those
    three annotated "no capture" would have made the marker a lie — the precise
    failure the marker exists to prevent. So a second marker was added rather
    than the first being widened: `VERIFIED (docs/probes/…)`, which must **name
    the capture**, and the named file must exist. A literal with neither marker
    still fails.

    **What the elided form costs, stated exactly, because the first version of
    this docstring overstated it.** `VERIFIED (docs/probes/…§2)` is a
    continuation shorthand: it names no file, so the file-exists check cannot
    reach it. Until the third block below existed, the only rule on the elided
    form was "starts with `docs/probes/`", and a new unmeasured constant written
    as `MAC_NEW_GUESS = "launchctl"  # VERIFIED (docs/probes/…§2)` passed — the
    module-level "some literal names a real file" check is satisfied
    permanently by three other constants, so it could not object. That is the
    rubber stamp this file is written against, reappearing inside the rule
    meant to prevent it.

    So the elision is now allowed **only where it is genuinely a continuation**:
    a literal sitting on the first line of an assignment must cite a capture in
    full. A new constant is a new statement and its value is on its head line,
    so it cannot be stamped; the fabricated line above now goes red. What
    remains convention — and is *not* claimed here — is that a full citation
    names a capture which actually measured *that* value. No text rule can see
    that.
    """
    source = Path(inspect.getfile(MacHost))
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text, filename=str(source))

    def annotated(line: str) -> bool:
        """Either marker, and `VERIFIED` only when it carries a capture."""
        return UNVERIFIED_MARKER in line or VERIFIED_CAPTURE.search(line) is not None

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))

    unannotated = [
        f"{source.name}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (str, int, float))
        and not isinstance(node.value, bool)
        and id(node) not in docstrings
        and not annotated(lines[node.lineno - 1])
    ]
    assert unannotated == []
    assert "D55" in text

    # Both markers are in use, so neither branch of the rule is dead code.
    assert UNVERIFIED_MARKER in text, "no literal in mac.py is marked unverified"
    assert VERIFIED_CAPTURE.search(text), "no literal in mac.py is marked verified"

    # A `VERIFIED` annotation must name a capture that **exists**. Without this
    # the marker is a word anyone can type over a value nobody measured — the
    # rubber stamp this file's whole discipline is written against.
    repo_root = Path(inspect.getfile(MacHost)).parents[3]
    cited = {
        match.group("capture").split("§")[0].strip()
        for match in VERIFIED_CAPTURE.finditer(text)
    }
    named_files = sorted(reference for reference in cited if reference.endswith(".md"))
    assert named_files, "every VERIFIED annotation elided its capture; none names a file"
    for reference in named_files:
        assert (repo_root / reference).is_file(), (
            f"mac.py cites a capture that is not in the tree: {reference}"
        )
    # …and an elided citation (a continuation line) must still point into the
    # probe tree, so `VERIFIED (…)` cannot become a citation-free stamp.
    for reference in sorted(cited - set(named_files)):
        assert reference.startswith(CAPTURE_ROOT), (
            f"mac.py carries a VERIFIED annotation citing nothing: {reference!r}"
        )

    # The elision is a *continuation* shorthand, so it is allowed only where it
    # continues something. A literal on the head line of an assignment is the
    # whole value of a new constant: nothing above it names a capture, so an
    # elided marker there cites nothing at all. Those must be cited in full.
    heads = {
        statement.lineno
        for statement in ast.walk(tree)
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign))
    }

    def elided_stamp(lineno: int) -> bool:
        """A `VERIFIED` on this line that names no `.md` capture."""
        match = VERIFIED_CAPTURE.search(lines[lineno - 1])
        if match is None:
            return False
        return not match.group("capture").split("§")[0].strip().endswith(".md")

    stamped = [
        f"{source.name}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (str, int, float))
        and not isinstance(node.value, bool)
        and id(node) not in docstrings
        and node.lineno in heads
        and elided_stamp(node.lineno)
    ]
    assert stamped == [], (
        "a literal is stamped VERIFIED with an elided citation on the first "
        f"line of its own assignment, which cites nothing: {stamped}. An "
        "elision may only continue a statement whose head names the capture "
        f"in full ({CAPTURE_ROOT}<file>.md)."
    )


def test_scripted_host_answers_every_protocol_member() -> None:
    """§14.2: the double grows the moment the Protocol does, or this goes red.

    The expected names are D55's seven things written out, plus `verified()` —
    read from the decision, never from `HostPlatform` itself, so a member that
    is renamed or quietly dropped disagrees with the spec here.
    """
    declared = {
        name
        for name, value in vars(HostPlatform).items()
        if inspect.isfunction(value) and not name.startswith("_")
    }
    assert declared == SEAM_MEMBERS

    for impl in IMPLEMENTATIONS:
        for name in sorted(declared):
            member = getattr(type(impl.host), name, None)
            assert inspect.isfunction(member), f"{impl.name} does not answer {name}()"
            assert inspect.signature(member) == inspect.signature(
                getattr(HostPlatform, name)
            ), f"{impl.name}.{name}() does not match the Protocol"


def test_scripted_host_is_not_a_base_class() -> None:
    """§14.2: `Scripted*` is a concrete peer — nothing inherits from it."""
    assert ScriptedHost.__subclasses__() == []

    src_root = Path(inspect.getfile(ScriptedHost)).parents[1]
    inheritors: list[str] = []
    for module in sorted(src_root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                    if name == "ScriptedHost":
                        inheritors.append(f"{module.name}:{node.name}")
    assert inheritors == []

    # It is a peer of the real drivers: the same suite, the same interface.
    peer: HostPlatform = scripted_fixture()
    assert peer.dirs().data_dir == Path("/scripted/data/shepherd")
