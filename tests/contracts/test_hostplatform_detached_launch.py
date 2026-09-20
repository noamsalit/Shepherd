"""T7 — `detached_launch`, D55's seventh seam member (M3 plan DP5).

The driver-level half of the one contract suite: the shared row that every
implementation answers lives in `test_hostplatform_contract.py`, and what
cannot be expressed as one row — the four (kind × resolution) combinations, the
argv shape, and `MacHost`'s write-and-annotate regime — lives here.

Every case is driven through the **pure** half (`detached_launch_for`) or a
constant, so the whole file runs without a live supervision experiment: the
captures in `docs/probes/2026-09-14-schemas/gap-fill/systemd-tmux-20260914T170532Z/`
already answered the host question, and re-running it would only risk the
sessions §18's incident cost us.
"""

from __future__ import annotations

from pathlib import Path

from shepherd.host.base import SupervisionKind
from shepherd.host.linux import LinuxHost, detached_launch_for
from shepherd.host.mac import MacHost
from shepherd.testkit.scripted_host import SCRIPTED_DETACHED_LAUNCH


def test_detached_launch_leaves_the_argv_unchanged_without_a_supervisor(tmp_path: Path) -> None:
    """A container has no systemd user manager, so nothing may be wrapped.

    `q1-cgstop.txt` is why the wrapper exists; `SupervisionKind`'s third value
    is why it must not be applied everywhere. Identity by **value** is the
    assertion: a prefix that is merely empty-ish would pass a truthiness check
    and still corrupt the argv.
    """
    containerish = LinuxHost(environ={"HOME": str(tmp_path)}, uid=0)
    assert containerish.supervision().kind == "foreground"

    plan = containerish.detached_launch()
    argv = ["a-long-lived-server", "--socket", "shepherd-m3-example"]
    assert plan.prefix == ()
    assert [*plan.prefix, *argv] == argv
    assert plan.verified is True


def test_detached_launch_wraps_under_systemd_and_not_otherwise() -> None:
    """The wrapper is the systemd-user answer and **only** that one (DP5).

    Driven through the pure half so all four combinations are exercised without
    a live supervision experiment: the captures in
    `systemd-tmux-20260914T170532Z/` already answered the host question.
    """
    argv = ["a-long-lived-server", "--socket", "shepherd-m3-example"]

    wrapped = detached_launch_for("systemd_user", "/usr/bin/systemd-run")
    assert wrapped.prefix == ("systemd-run", "--user", "--scope", "--")
    assert wrapped.mechanism == "systemd-run --user --scope"
    assert [*wrapped.prefix, *argv] == ["systemd-run", "--user", "--scope", "--", *argv]
    assert wrapped.verified is True

    # …and every other host shape hands the argv back **unchanged and
    # identical by value** — a container has no systemd user manager at all.
    bare_cases: tuple[tuple[SupervisionKind, str | None], ...] = (
        ("foreground", "/usr/bin/systemd-run"),
        ("launchd", "/usr/bin/systemd-run"),
        ("systemd_user", None),
    )
    for kind, resolved in bare_cases:
        bare = detached_launch_for(kind, resolved)
        assert bare.prefix == (), (kind, resolved)
        assert [*bare.prefix, *argv] == argv, (kind, resolved)
        assert bare.mechanism == "none", (kind, resolved)
        assert bare.detail.strip() != "", (kind, resolved)
        assert bare.verified is True


def test_detached_launch_returns_argv_never_a_string() -> None:
    """K5: the seam hands back an **argv fragment**, never a command line.

    A `str` prefix would splat into characters and a spaced element would be a
    shell command wearing an argv's clothes — both are the `shell=True` shape
    this seam exists to make impossible. All three drivers are checked, with
    the wrapped Linux case among them.
    """
    plans = (
        detached_launch_for("systemd_user", "/usr/bin/systemd-run"),
        detached_launch_for("foreground", None),
        MacHost().detached_launch(),
        SCRIPTED_DETACHED_LAUNCH,
    )
    for plan in plans:
        # `str` is not a `tuple`, so this also refuses a bare command line.
        assert isinstance(plan.prefix, tuple), plan
        for element in plan.prefix:
            assert isinstance(element, str), plan
            assert element == element.strip() != "", plan
            assert not any(character in element for character in " \t;|&<>$`\n"), plan


def test_machost_detached_launch_is_written_and_annotated() -> None:
    """Write-and-annotate, not refuse (T7): every spawn asks this question.

    The record carries `verified`, so the guess is visible at the call site and
    a caller that wants to refuse can read it — which is what makes writing the
    value honest rather than a claim about a Mac nobody has run this on.
    """
    plan = MacHost().detached_launch()
    assert plan.prefix == ()
    assert plan.mechanism == "none"
    assert plan.detail.strip() != ""
    assert plan.verified is False
    assert MacHost().verified() is False
