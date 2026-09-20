"""T10 — the trust pre-flight (`engines/claude_code/trust.py`).

`projects[<cwd>].hasTrustDialogAccepted` comes from
`docs/probes/2026-09-14-schemas/transcripts/captures/claude-json-shape.txt` —
**9 true, 2 false** across 11 entries — and the fixtures below carry exactly that
mix so the `False` half is not a case nobody exercised.

**The real `~/.claude.json` is never read here, and that is now asserted rather
than promised.** Every call names a `tmp_path`, and the one test that exercises
the *default* path points `$HOME` at a `tmp_path` first and then pins the exact
path chosen. The old form asserted `str(Path.home() / ".claude.json") in
state.source` against the live user file: it opened the user's real 97 KB config
on every run, and its assertion was satisfied by *every* return path, so it
proved nothing either way. That combination is what turned T10-R1 from a
contained mutation experiment into a write on a live user file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from shepherd.engines.claude_code.trust import (
    CONFIG_DIR_ENV,
    CONFIG_FILENAME,
    TrustState,
    config_file,
    trust_state,
)

MODULE = (
    Path(__file__).resolve().parents[2]
    / "src" / "shepherd" / "engines" / "claude_code" / "trust.py"
)

#: The captured mix, verbatim: 11 entries, `hasTrustDialogAccepted` true 9 /
#: false 2 (`transcripts/captures/claude-json-shape.txt`).
TRUSTED_CWDS = tuple(f"/tmp/shp-schemas-trusted-{index}" for index in range(9))
UNTRUSTED_CWDS = ("/tmp/shp-schemas-refused-0", "/tmp/shp-schemas-refused-1")


def config_home(tmp_path: Path) -> Path:
    projects: dict[str, object] = {
        cwd: {
            "allowedTools": [],
            "mcpServers": {},
            "hasTrustDialogAccepted": cwd in TRUSTED_CWDS,
            "lastVersionBase": "2.1.270",
        }
        for cwd in TRUSTED_CWDS + UNTRUSTED_CWDS
    }
    projects["/tmp/shp-schemas-nokey"] = {"allowedTools": [], "lastVersionBase": "2.1.270"}
    payload = {"userID": "redacted", "numStartups": 7, "projects": projects}
    (tmp_path / ".claude.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_an_accepted_dialog_reads_true(tmp_path: Path) -> None:
    home = config_home(tmp_path)
    states = [trust_state(cwd, home) for cwd in TRUSTED_CWDS]
    assert [state.trusted for state in states] == [True] * 9
    assert all("hasTrustDialogAccepted" in state.source for state in states)


def test_a_declined_dialog_reads_false_and_is_not_an_unknown(tmp_path: Path) -> None:
    """The captured file has two of these. `False` is a fact, `None` is not."""
    home = config_home(tmp_path)
    states = [trust_state(cwd, home) for cwd in UNTRUSTED_CWDS]
    assert [state.trusted for state in states] == [False, False]


def test_an_absent_entry_is_unknown_never_false(tmp_path: Path) -> None:
    """Principle 5. `-p` sessions create no `projects[]` entry at all, so
    "no entry" cannot mean "untrusted" — it means nobody has been asked."""
    home = config_home(tmp_path)
    for cwd in ("/tmp/shp-schemas-nokey", "/tmp/never-seen"):
        state = trust_state(cwd, home)
        assert state.trusted is None, cwd
        assert state.source != ""


def test_the_key_is_the_raw_cwd_path(tmp_path: Path) -> None:
    """`projects` is keyed by the absolute cwd, "raw path, not slugged"."""
    home = tmp_path
    (home / ".claude.json").write_text(
        json.dumps({"projects": {"/tmp/shp/work": {"hasTrustDialogAccepted": True}}}),
        encoding="utf-8",
    )
    assert trust_state("/tmp/shp/work", home).trusted is True
    assert trust_state("-tmp-shp-work", home).trusted is None
    assert trust_state("/tmp/shp/work/", home).trusted is None


def test_trust_state_writes_nothing(tmp_path: Path) -> None:
    """K3: Shepherd reads the engine's configuration. It never writes it."""
    home = config_home(tmp_path)
    path = home / ".claude.json"
    before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    before_mtime = path.stat().st_mtime_ns
    before_listing = sorted(entry.name for entry in home.iterdir())

    for cwd in (*TRUSTED_CWDS, *UNTRUSTED_CWDS, "/tmp/never-seen"):
        trust_state(cwd, home)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_digest
    assert path.stat().st_mtime_ns == before_mtime
    assert sorted(entry.name for entry in home.iterdir()) == before_listing


# ----- every branch's verdict, pinned ------------------------------------------

#: One row per `return` in `trust_state`: how to build the file, the cwd to ask
#: about, the exact `trusted`, and the `source` — in full where it is
#: deterministic, as a prefix where it embeds an OS or a json message.
#:
#: The hunter's CRITICAL is why this table exists: mutating the `unreadable`
#: branch to `trusted=True` **and** to `trusted=False` both survived 25/25 green,
#: and at 09:57:52 on 2026-09-17 the `True` form was briefly live on disk while
#: the suite ran green (T10-R1). A branch whose *type* is asserted and whose
#: *verdict* is not is an untested branch.
def _absent(home: Path) -> None:
    return None


def _unreadable(home: Path) -> None:
    # The suite runs as **root**, so `chmod 000` does not reach this branch at
    # all. A directory where a file belongs does: `read_text` raises
    # `IsADirectoryError`, which is an `OSError` and not a `FileNotFoundError`.
    (home / CONFIG_FILENAME).mkdir()


def _undecodable(home: Path) -> None:
    # D25's torn tail, landing mid-sequence. The engine writes this file with
    # `JSON.stringify`, which does not escape non-ASCII, so a half-written
    # multibyte character is the realistic damage — and `UnicodeDecodeError` is
    # a `ValueError`, **not** an `OSError`, so it escapes an `except OSError`.
    (home / CONFIG_FILENAME).write_bytes(
        '{"projects": {"/tmp/work": {"note": "café'.encode("utf-8")[:-1]
    )


def _write(home: Path, text: str) -> None:
    (home / CONFIG_FILENAME).write_text(text, encoding="utf-8")


CWD = "/tmp/work"

BRANCHES: tuple[tuple[str, object, bool | None, str], ...] = (
    ("absent", _absent, None, "absent: {path}"),
    ("unreadable", _unreadable, None, "unreadable: {path}: "),
    ("undecodable", _undecodable, None, "undecodable: {path}: "),
    ("malformed", lambda home: _write(home, "{not json"), None, "malformed: {path}: "),
    (
        "document is an array",
        lambda home: _write(home, "[]"),
        None,
        "the document is not an object but an array: {path}",
    ),
    (
        "document is null",
        lambda home: _write(home, "null"),
        None,
        "the document is not an object but null: {path}",
    ),
    (
        "no projects key",
        lambda home: _write(home, '{"userID": "redacted"}'),
        None,
        "no projects key at all: {path}",
    ),
    (
        "projects is an array",
        lambda home: _write(home, '{"projects": []}'),
        None,
        "projects is not an object but an array: {path}",
    ),
    (
        "projects is null",
        lambda home: _write(home, '{"projects": null}'),
        None,
        "projects is not an object but null: {path}",
    ),
    (
        "no entry",
        lambda home: _write(home, '{"projects": {"/elsewhere": {}}}'),
        None,
        f"no entry for {CWD}: {{path}}",
    ),
    (
        "entry is a string",
        lambda home: _write(home, '{"projects": {"/tmp/work": "trusted"}}'),
        None,
        f"the entry for {CWD} is not an object but a string: {{path}}",
    ),
    (
        "no trust key",
        lambda home: _write(home, '{"projects": {"/tmp/work": {"allowedTools": []}}}'),
        None,
        f"no hasTrustDialogAccepted for {CWD}: {{path}}",
    ),
    (
        "trust key is a string",
        lambda home: _write(home, '{"projects": {"/tmp/work": {"hasTrustDialogAccepted": "yes"}}}'),
        None,
        f"hasTrustDialogAccepted for {CWD} is not a boolean but a string: {{path}}",
    ),
    (
        "accepted",
        lambda home: _write(home, '{"projects": {"/tmp/work": {"hasTrustDialogAccepted": true}}}'),
        True,
        f"projects[{CWD}].hasTrustDialogAccepted: {{path}}",
    ),
    (
        "declined",
        lambda home: _write(home, '{"projects": {"/tmp/work": {"hasTrustDialogAccepted": false}}}'),
        False,
        f"projects[{CWD}].hasTrustDialogAccepted: {{path}}",
    ),
)


def test_every_branch_pins_an_exact_verdict(tmp_path: Path) -> None:
    """Every `return` in `trust_state`, with its `trusted` value asserted.

    Goes red on any mutation of a verdict — including the two the hunter proved
    survive today: `unreadable` answering `True`, and `unreadable` answering
    `False`. A wrong `True` reports a workspace as trusted that nobody ever
    accepted a dialog for.
    """
    for index, (name, build, trusted, source) in enumerate(BRANCHES):
        home = tmp_path / f"case-{index}"
        home.mkdir()
        build(home)  # type: ignore[operator]
        expected = source.format(path=home / CONFIG_FILENAME)
        state = trust_state(CWD, home)
        assert state.trusted is trusted, f"{name}: {state}"
        if source.endswith(": "):
            assert state.source.startswith(expected), f"{name}: {state.source!r}"
            assert len(state.source) > len(expected), f"{name}: no detail after the prefix"
        else:
            assert state == TrustState(trusted=trusted, source=expected), name


def test_the_shape_guards_distinguish_what_they_found(tmp_path: Path) -> None:
    """`source` is the whole point of `TrustState`, so no two branches may share
    one. `projects` absent, an array and `null` all said "no projects object"
    before, and a `str` entry said "no entry for <cwd>" — a lie, the entry
    exists. This host runs **2.1.273** and `data-schemas.md` pins **2.1.270**, so
    schema drift is the live case: it has to announce itself, not read as absence.
    """
    sources = []
    for index, (_name, build, _trusted, _source) in enumerate(BRANCHES):
        home = tmp_path / f"case-{index}"
        home.mkdir()
        build(home)  # type: ignore[operator]
        sources.append(trust_state(CWD, home).source.replace(str(home), "<home>"))

    assert len(set(sources)) == len(BRANCHES) - 1, sources  # accepted/declined share one
    assert len(BRANCHES) == 15


# ----- the path it chooses -----------------------------------------------------


def test_the_default_home_is_the_real_home_and_is_never_read_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`$CLAUDE_CONFIG_DIR/.claude.json`, else `~/.claude.json` — with `$HOME`
    pointed at a `tmp_path`, so the assertion is about the path *chosen* and the
    user's real file is never opened."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    assert config_file(None) == tmp_path / CONFIG_FILENAME
    assert trust_state(CWD, None) == TrustState(
        trusted=None, source=f"absent: {tmp_path / CONFIG_FILENAME}"
    )

    monkeypatch.setenv(CONFIG_DIR_ENV, "/tmp/shp-cfg")
    assert config_file(None) == Path("/tmp/shp-cfg") / CONFIG_FILENAME
    assert trust_state(CWD, None).source.endswith("/tmp/shp-cfg/.claude.json")

    # An injected home wins over both, so a caller that has one never consults
    # the environment at all.
    monkeypatch.setenv(CONFIG_DIR_ENV, "/tmp/shp-cfg")
    assert config_file(tmp_path / "injected") == tmp_path / "injected" / CONFIG_FILENAME


def test_an_empty_config_dir_env_names_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set-but-empty is a misconfiguration, not an unset variable.

    Falling back to `~/.claude.json` would read the very file the operator's
    empty setting says not to, and `Path("") / ".claude.json"` is a **relative**
    path that would read whatever `.claude.json` the cwd happens to hold.
    Neither is an answer; "no file can be named" is.
    """
    monkeypatch.setenv(CONFIG_DIR_ENV, "")
    assert config_file(None) is None
    state = trust_state(CWD, None)
    assert state.trusted is None
    assert state.source == f"${CONFIG_DIR_ENV} is set and empty, so no config file can be named"


def test_the_config_home_is_required_at_the_call_site() -> None:
    """T10-R2: the "optional argument a caller may forget" whose default was the
    user's real file. The first caller to forget it was the test written beside
    it, and a mutation planted in that path wrote the user's live 97 KB config
    (T10-R1). "I don't have one" is now a `None` somebody typed.
    """
    with pytest.raises(TypeError):
        trust_state(CWD)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        config_file()  # type: ignore[call-arg]


def test_the_module_stays_small() -> None:
    """The cap that produced the split. Do not raise it — `rows.py`, `stops.py`,
    `signals/fields.py`, `reads.py` and `writes.py` are five prior instances of
    the split being the right answer."""
    assert len(MODULE.read_text(encoding="utf-8").splitlines()) <= 250
