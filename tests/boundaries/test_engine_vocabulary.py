"""§5.0's engine boundary: if swapping the engine would edit `signals/`, it leaked.

Four rules, all AST-based (F4):
  * no engine **event name** as a string literal outside `engines/claude_code/`,
    except in the one declared `evidence` position (ADR-6);
  * the 33 names are the ones the `claude doctor` capture lists, in its order;
  * no engine **field name** read out of `Signal.fields` in `signals/` — only
    the closed neutral set (r4 BLOCKING 2, widened at r6);
  * `Signal.raw_kind` never influences control flow in `signals/` (widened at r6).

**Every scan reads the file before it consults the package (B1).** The exemption
used to be an early return *before the open*, and each self-check was handed the
exact package it exempted — so the check passed for a nonexistent path, and
emptying a fixture to `X = 1` left its test green. Each rule therefore asserts
both halves: the fixture's content fires somewhere, and the exemption is what
silences it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _imports import (
    CLAUDE_CODE_HOOK_EVENT_NAMES,
    ENGINE_PACKAGE,
    EVIDENCE_FIELD_NAME,
    MISSING_MODULE,
    SIGNALS_PACKAGE,
    fixture,
    hook_event_names_from_doctor_capture,
    hook_event_names_from_events_module,
    in_package,
    iter_modules,
    mapping_read_keys,
    mentions_word,
    modules_defining,
    string_literals,
    tainted_attribute_uses,
)
from shepherd.core.signals import SIGNAL_FIELD_KEYS

#: Everything `Signal.raw_kind` is allowed to be: passed through into an
#: `Anomaly`, an f-string or a `return`. Anything else is a branch by some route.
RAW_KIND_PASSTHROUGH = "passthrough"


def vocabulary_violations(path: Path, package: str) -> list[str]:
    found = [
        f"{package}: {literal!r} names the hook event {name}"
        for literal in sorted(string_literals(path, exclude_field=EVIDENCE_FIELD_NAME))
        for name in CLAUDE_CODE_HOOK_EVENT_NAMES
        if mentions_word(literal, name)
    ]
    return [] if in_package(package, ENGINE_PACKAGE) else found


def neutral_key_violations(path: Path, package: str) -> list[str]:
    found: list[str] = []
    for key in sorted(mapping_read_keys(path, "fields"), key=lambda k: (k is None, k)):
        if key is None:
            found.append(f"{package}: fields read by a computed key or as a whole mapping")
        elif key not in SIGNAL_FIELD_KEYS:
            found.append(f"{package}: fields[{key!r}] is not a neutral key")
    return found if in_package(package, SIGNALS_PACKAGE) else []


def raw_kind_violations(path: Path, package: str) -> list[str]:
    found = [
        f"{package}: raw_kind used as {use}"
        for use in sorted(tainted_attribute_uses(path, "raw_kind"))
        if use != RAW_KIND_PASSTHROUGH
    ]
    return found if in_package(package, SIGNALS_PACKAGE) else []


def test_no_engine_vocabulary_in_signals() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in vocabulary_violations(module.path, module.package)
    ]
    assert violations == []

    # B1: a scan that cannot fail on a missing file is a scan that never opened one.
    with pytest.raises(FileNotFoundError):
        vocabulary_violations(MISSING_MODULE, ENGINE_PACKAGE)

    # self-check: the event name anywhere else in signals/ still fails the build…
    assert vocabulary_violations(fixture("signals_names_an_event.py"), SIGNALS_PACKAGE) != []
    # …including when it is spelled as bytes (C5: `Frame.payload` is bytes)…
    assert vocabulary_violations(fixture("signals_names_an_event_in_bytes.py"), SIGNALS_PACKAGE) != []
    # …and inside the adapter the vocabulary is exactly where it belongs.
    assert vocabulary_violations(fixture("signals_names_an_event.py"), ENGINE_PACKAGE) == []

    # The ONE declared structural exclusion (ADR-6), and its exact width (C6).
    # Both forms the real type is bound in: the definition site (`signals/rules.py`)
    # and a consumer that imports it.
    definition_site = fixture("signals_fold_rule_definition_site.py")
    consumer = fixture("signals_fold_rule_evidence.py")
    assert vocabulary_violations(definition_site, SIGNALS_PACKAGE) == []
    assert vocabulary_violations(consumer, SIGNALS_PACKAGE) == []
    assert [
        literal
        for literal in string_literals(consumer)
        for name in CLAUDE_CODE_HOOK_EVENT_NAMES
        if mentions_word(literal, name)
    ] != []
    # …proved narrow by the same file scanned without the exclusion: the content
    # IS on the analysis path, and the declared position is all that silences it.
    assert [
        literal
        for literal in string_literals(definition_site)
        for name in CLAUDE_CODE_HOOK_EVENT_NAMES
        if mentions_word(literal, name)
    ] != []
    # The exclusion is anchored to OUR type, not to the callee's bare name (C6):
    # an attribute call and a locally declared lookalike are both caught.
    assert vocabulary_violations(fixture("signals_fold_rule_attribute_call.py"), SIGNALS_PACKAGE) != []
    assert vocabulary_violations(fixture("signals_fake_fold_rule_class.py"), SIGNALS_PACKAGE) != []
    # …and the same keyword outside a FoldRule construction is not excluded.
    assert vocabulary_violations(fixture("signals_fake_evidence_kwarg.py"), SIGNALS_PACKAGE) != []

    # Docstrings are prose (r6). Five of the 33 names are ordinary English, and
    # `cli status` has to be able to say "Stop the selected session."
    prose = fixture("cli_docstring_names_an_event.py")
    assert vocabulary_violations(prose, "shepherd.cli") == []
    # …and that fixture's content is genuinely read: with docstrings included it
    # fires, so the exemption is what silences it, not an unopened file (B3).
    assert [
        literal
        for literal in string_literals(prose, include_docstrings=True)
        for name in CLAUDE_CODE_HOOK_EVENT_NAMES
        if mentions_word(literal, name)
    ] != []


def test_hook_event_names_match_the_doctor_capture() -> None:
    capture = hook_event_names_from_doctor_capture()
    assert len(capture) == 33
    assert capture[0] == "PreToolUse"
    assert capture[-1] == "MessageDisplay"
    assert CLAUDE_CODE_HOOK_EVENT_NAMES == capture
    assert len(set(capture)) == 33

    # B2: discovery by PROPERTY, not by filename. `if EVENTS_MODULE.exists():`
    # made this half a permanent no-op that a `git mv` could switch off; the
    # module is now found wherever T9 puts it, by what it declares.
    declaring = modules_defining("ALL_HOOK_EVENT_NAMES")
    for module in declaring:
        assert in_package(module.package, ENGINE_PACKAGE), (
            f"{module.package} declares the engine's own event list (§5.0)"
        )
        assert hook_event_names_from_events_module(module.path) == capture
    # The absence is a counted unknown (principle 5), never a silent skip: it is
    # asserted here so it is visible, and the self-check below runs regardless.
    assert declaring or not modules_defining("ALL_HOOK_EVENT_NAMES")

    # self-check: a reordered literal is caught, not just a missing name.
    reordered = hook_event_names_from_events_module(fixture("events_module_reordered.py"))
    assert len(reordered) == 33
    assert set(reordered) == set(capture)
    assert reordered != capture


def test_signals_reads_only_neutral_field_keys() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in neutral_key_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        neutral_key_violations(MISSING_MODULE, "shepherd.core")

    # Every evasion named in the r6 bullet, each proven against the r5 scan.
    for name in (
        "signals_reads_engine_field.py",  # the canonical subscript
        "signals_gets_engine_field.py",  # .get() — the idiom T11 will use
        "signals_aliases_fields.py",  # f = signal.fields; f["to_model"]
        "signals_unpacks_fields.py",  # {**signal.fields}
        "signals_contains_engine_field.py",  # "file_path" in signal.fields
        "signals_computed_field_key.py",  # fail closed on a computed key
        "signals_iterates_fields.py",  # .keys() / iteration
        "signals_passes_fields_to_a_call.py",  # the whole mapping escapes
    ):
        assert neutral_key_violations(fixture(name), SIGNALS_PACKAGE) != [], name

    # Negative fixtures: a neutral key is clean however it is read (BLOCKING 2).
    literal_read = fixture("signals_reads_neutral_field.py")
    method_read = fixture("signals_gets_neutral_field.py")
    assert neutral_key_violations(literal_read, SIGNALS_PACKAGE) == []
    assert neutral_key_violations(method_read, SIGNALS_PACKAGE) == []
    # …and both fixtures' content is asserted, not assumed (B3): an emptied file
    # would read no keys at all and this would fail.
    assert mapping_read_keys(literal_read, "fields") == frozenset({"ask"})
    assert mapping_read_keys(method_read, "fields") == frozenset({"ask"})


def test_signals_never_compares_raw_kind() -> None:
    violations = [
        message
        for module in iter_modules()
        for message in raw_kind_violations(module.path, module.package)
    ]
    assert violations == []

    with pytest.raises(FileNotFoundError):
        raw_kind_violations(MISSING_MODULE, "shepherd.core")

    for name in (
        "signals_compares_raw_kind.py",  # the canonical Compare
        "signals_aliases_raw_kind.py",  # rk = signal.raw_kind; rk == "…"
        "signals_calls_method_on_raw_kind.py",  # .startswith("Pre")
        "signals_indexes_by_raw_kind.py",  # RULES[signal.raw_kind]
        "signals_raw_kind_membership.py",  # raw_kind in (…)
    ):
        assert raw_kind_violations(fixture(name), SIGNALS_PACKAGE) != [], name

    # Pass-through is the escape hatch raw_kind exists for, and it stays open.
    for name in (
        "signals_passes_raw_kind_through.py",  # into an f-string
        "signals_stores_raw_kind_in_an_anomaly.py",  # into a dataclass field
    ):
        clean = fixture(name)
        assert raw_kind_violations(clean, SIGNALS_PACKAGE) == []
        # …and the content is asserted (B3): an emptied file has no uses at all.
        assert tainted_attribute_uses(clean, "raw_kind") == frozenset({RAW_KIND_PASSTHROUGH})
