"""T22 — the **live half** of acceptance clause 9, over what the engine reports.

**This file asserts no option value, and that is the whole design.**
`data-schemas.md` records a master whose option block looked correct — `tools`,
`strict_mcp_config`, `setting_sources`, all as written — while the engine listed
`Bash`, `Read` and `Write` and ran `echo hi` with no callback ever firing. An
option block is what we asked for; `system/init` is what we got. §18 says of the
lock *"verify in M4 and assert it in a test — do not trust it"*, and *"do not
trust it"* is said **of the options**.

**Clause 9 has two halves and neither is filed under the other.**

* **Deterministic half — T21's**
  `tests/master/test_sdk_master.py::test_the_option_block_locks_the_master`,
  over `build_options(...)`. It is not repeated here; repeating it here under a
  "Live" heading is precisely M3's clause-10 defect, where a scripted test sat
  under a live banner and the milestone counted it as live proof.
* **Live half — this file**, over `AgentSDKMaster.system_init()` from a real
  `claude`. Nothing in it can be satisfied by an option value.

**The residue is asserted PRESENT, not absent** (DP10, K20). `setting_sources=[]`
does **not** remove Claude Code's own bundled skills, its slash commands, or the
account's `userEmail` attachment. A test that claimed they were gone would be a
test that could be made to pass by deleting it; a test that asserts they are
there goes red the day the claim changes, in either direction.

**What T21 could not assert, and why this file exists.** T21's live
`system/init` reported `"tools": []` — but that run mounted no tools, so an empty
list is also exactly what a broken mount produces. The strong form needs a
**non-empty** mounted set and a set equality in both directions, and that is
`test_live_master_init_lists_exactly_our_tools`.

**The mounted set is a throwaway MASTER-audience set, and that is deliberate
twice over.** `client.master_tools()` is empty until T23 registers the master's
real capabilities, so the real set today would reproduce T21's `[]` weakness
exactly; and mounting a real `kill_session` into a master driven by a live model
is what the probe harness's own safety sequence forbids (*"every probe mounts
literal-returning fakes only … so no probe master could act on the fleet"*).
What is under test is the **pipeline** — registry → audience projection →
`prefixed_names` → the SDK MCP mount → what the engine lists — which is the part
that can silently disagree.
"""

from __future__ import annotations

import pytest

from .conftest import (
    P4_CAPTURE,
    SHEPHERD_SERVER,
    LiveMaster,
    probe_system_init,
    session_context_keys,
    transcript_attachments,
)

#: What P4 measured on this host on 2026-09-17, with cc10x enabled at user scope
#: and `setting_sources=[]`: `system/init.plugins` is empty. Written out here and
#: also read back off the capture, so *both* a change in cc10x's behaviour and a
#: change in the evidence base are failing tests rather than surprises.
P4_PLUGINS: list[object] = []

#: Claude Code's own bundled skills, three of the eighteen P4 counted. A subset,
#: not the whole list: the count moves when Anthropic ships a skill, and a check
#: that went red on that would be asserting the vendor's release notes. These
#: three are the residue's *arrival*.
KNOWN_BUNDLED_SKILLS: frozenset[str] = frozenset(
    {"deep-research", "design", "code-review"}
)

#: How a plugin's skills are spelled when a plugin is loaded: `<plugin>:<skill>`.
#: Under `setting_sources=[]` no skill carries a namespace at all, which is the
#: same fact as `plugins == []` read from the other field.
PLUGIN_SKILL_SEPARATOR = ":"

#: The attachment `data-schemas.md` and DP10 name by name. The account reaches
#: the master through it whatever `setting_sources` says.
USER_EMAIL_KEY = "userEmail"


def test_the_recorded_p4_finding_is_what_this_module_asserts_against() -> None:
    """Deterministic, and it runs in the **default** lane on purpose.

    The live checks below compare against P4's measurement. A constant typed into
    this file would be a claim about a probe rather than a reading of one, so the
    values are read back off the frozen capture — and this check is what proves
    the reader still finds them. `docs/probes/` is read-only evidence; if it
    moves, this goes red here rather than three minutes into a live run.

    It is also the residue's shape, proved without a live engine: P4's own
    transcript carries a `session_context` attachment whose only key is
    `userEmail`, which is what `test_live_the_known_residue_is_still_present`
    then asserts of a transcript this build produced.
    """
    init = probe_system_init(P4_CAPTURE / "setting-sources-empty" / "raw-stream.jsonl")
    assert init["plugins"] == P4_PLUGINS, init["plugins"]

    skills = init["skills"]
    assert isinstance(skills, list)
    assert KNOWN_BUNDLED_SKILLS <= set(skills), sorted(set(skills))

    # …and the other side of P4's measurement, which is what makes the `[]` above
    # mean something: same binary, same `{}` flag settings, same throwaway cwd,
    # `setting_sources=None` — and cc10x is loaded.
    with_host = probe_system_init(
        P4_CAPTURE / "setting-sources-none" / "raw-stream.jsonl"
    )
    loaded = with_host["plugins"]
    assert isinstance(loaded, list) and loaded, loaded
    assert [entry["name"] for entry in loaded] == ["cc10x"], loaded

    # The same fact read off a second field, which is what makes it a fact and
    # not a field: under `None` the plugin's skills are listed under its
    # namespace; under `[]` **no** skill carries a namespace at all.
    host_skills = with_host["skills"]
    assert isinstance(host_skills, list)
    assert [name for name in host_skills if PLUGIN_SKILL_SEPARATOR in name], host_skills
    assert [name for name in skills if PLUGIN_SKILL_SEPARATOR in name] == [], skills

    transcripts = sorted(
        (P4_CAPTURE / "setting-sources-empty").glob("transcript-*.jsonl")
    )
    assert transcripts, "P4's transcript capture is gone"
    keys = session_context_keys(transcripts[0])
    assert USER_EMAIL_KEY in keys, sorted(keys)


@pytest.mark.live
def test_live_master_init_lists_exactly_our_tools(live_master: LiveMaster) -> None:
    """P-M4-9, live. The engine's own answer, compared **as a set, both ways**.

    Red if any built-in, connector or `Task*` tool appears; red if our tool set
    and the engine's disagree in either direction; and red if nothing was mounted
    at all, because the expected set is asserted non-empty first. That last line
    is the difference between this and T21's `"tools": []`, which a broken mount
    produces just as faithfully as a locked one.

    `mcp_servers` is asserted whole rather than by membership: *"only `shepherd`,
    with status `connected`"* is a claim about the list, and a membership test
    would pass with the account's connectors beside it.
    """
    assert live_master.mounted, "nothing was mounted, so the equality is vacuous"

    reported = live_master.init["tools"]
    assert isinstance(reported, list), reported
    assert set(reported) == set(live_master.mounted), {
        "engine": sorted(set(reported) - set(live_master.mounted)),
        "ours": sorted(set(live_master.mounted) - set(reported)),
    }
    # Stated as its own line because it is the property the check is named for:
    # nothing the engine brought with it survives.
    assert [name for name in reported if not name.startswith("mcp__shepherd__")] == []

    assert live_master.init["mcp_servers"] == [SHEPHERD_SERVER], live_master.init[
        "mcp_servers"
    ]

    # G-M4-4 / P4, from the engine rather than from the option block — and it is
    # **not vacuous**: the host really does have cc10x enabled at user scope
    # (asserted in `live_master`, off the user's own settings file, read-only),
    # and the master still sees no plugin at all.
    assert live_master.init["plugins"] == P4_PLUGINS, live_master.init["plugins"]
    assert live_master.init["plugins"] == probe_system_init(
        P4_CAPTURE / "setting-sources-empty" / "raw-stream.jsonl"
    )["plugins"]


@pytest.mark.live
def test_live_the_known_residue_is_still_present(live_master: LiveMaster) -> None:
    """DP10. **Asserted present**, and the docstring is where the reason lives.

    `setting_sources=[]` does not exclude Claude Code's own bundled skills, its
    slash commands, or the `userEmail` the account injects into the transcript.
    We cannot make them absent and the plan says so. So this check asserts they
    are **there**:

    * an absence claim about a known-present thing is a claim that can be made
      true by deleting the test, which is the one failure mode a proof must not
      have (K20);
    * asserted present, the check goes red **in either direction** — the day
      Anthropic starts excluding skills under `setting_sources=[]`, M4's written
      record of what leaks is wrong and a red test is how anyone finds out.

    What is *not* claimed anywhere in this milestone: that the master is isolated
    from the account. It is not. `tools=[]` is what makes the skills unreachable
    (P4), and that is a different sentence from "they are gone".
    """
    skills = live_master.init["skills"]
    assert isinstance(skills, list), skills
    assert KNOWN_BUNDLED_SKILLS <= set(skills), sorted(set(skills))

    commands = live_master.init["slash_commands"]
    assert isinstance(commands, list) and commands, commands

    assert live_master.transcript is not None, (
        "the engine wrote no transcript for this session, so the attachment "
        "half of the residue was not read"
    )
    subtypes = transcript_attachments(live_master.transcript)
    assert "session_context" in subtypes, sorted(subtypes)
    keys = session_context_keys(live_master.transcript)
    assert USER_EMAIL_KEY in keys, sorted(keys)


@pytest.mark.live
def test_the_live_master_left_no_engine_process(live_master: LiveMaster) -> None:
    """The pid ledger, read after the fixture tore the engine down.

    **Arrival first, and it is an assertion:** a pid was found and asserted alive
    while the turn ran, so the absence below is the absence of something that was
    there. A runtime that never spawned anything would satisfy an emptiness check
    perfectly.

    Liveness is read from `/proc` and never from a signal — CLAUDE.md's
    2026-09-17 rule, whose cost was a rebooted host.
    """
    assert live_master.pids, (
        "no engine process was ever found — the arrival never happened"
    )
    assert live_master.survivors == (), live_master.survivors
