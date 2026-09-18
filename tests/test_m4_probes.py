"""Task 1's three Required Checks over the M4 Agent SDK probe captures.

`test_m4_probe_captures_exist` goes red if one of the four capture folders is missing, or if a
folder has no `versions.txt`, or if a `versions.txt` does not name all three versions the probes
were measured at (`claude-agent-sdk` 0.2.153, bundled CLI 2.1.273, PATH CLI 2.1.274).

`test_findings_cite_real_capture_paths` goes red if a `docs/probes/...` path named in `FINDINGS.md`
does not exist on disk. It is the check that stops a finding from being written from memory: a
probe answer whose evidence path is invented cannot pass it.

`test_p1_capture_shows_the_isolation_lock` parses P1's `raw-stream.jsonl` and asserts
`system/init.tools` is **exactly** the probe's own five tools as a set, and that the only mounted
MCP server is the probe's own. It goes red if any built-in or account-connector tool is present.
That is the safety precondition P2-P4 were scheduled after: a probe master that still holds `Bash`,
`Read`, `Write`, `Edit` or `WebFetch` is a probe master that can act on the host, and a probe
master that still holds the account connectors is one that can act off it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO / "docs" / "probes" / "2026-09-17-m4-sdk"

#: One folder per probe. The value is the `<name>` half of `<name>-<UTC>`.
PROBES = ("p1-versions", "p2-interrupt", "p3-shadow", "p4-plugins")

#: The three versions every capture must name. P1 re-pinned `data-schemas.md`'s Agent SDK section
#: at exactly these; a capture that does not say which versions it was taken at is not evidence.
VERSIONS = ("0.2.153", "2.1.273", "2.1.274")

#: The inert tools `probe_m4.py` mounts. Nothing else may appear in `system/init.tools`.
PROBE_TOOLS = frozenset({
    "mcp__shepherd__fleet_summary",
    "mcp__shepherd__spawn_session",
    "mcp__shepherd__shadow_tool",
    "mcp__shepherd__fail_tool",
    "mcp__shepherd__raise_tool",
})

#: Every capture path FINDINGS.md may cite starts here.
_PATH_RE = re.compile(r"docs/probes/[A-Za-z0-9_./-]*[A-Za-z0-9_/-]")


def _folder(name: str) -> Path:
    matches = sorted(PROBE_DIR.glob(f"{name}-*"))
    assert matches, f"no capture folder {PROBE_DIR}/{name}-<UTC>/ — probe {name} did not run"
    return matches[-1]


def _init_messages(stream: Path) -> list[dict[str, object]]:
    inits: list[dict[str, object]] = []
    for raw in stream.read_text().splitlines():
        line = json.loads(raw).get("line")
        if isinstance(line, dict) and line.get("type") == "system" and line.get("subtype") == "init":
            inits.append(line)
    return inits


def test_m4_probe_captures_exist() -> None:
    for name in PROBES:
        run = _folder(name)
        versions = run / "versions.txt"
        assert versions.is_file(), f"{versions} missing"
        text = versions.read_text()
        missing = [v for v in VERSIONS if v not in text]
        assert not missing, f"{versions} does not name {missing}: {text!r}"


def test_findings_cite_real_capture_paths() -> None:
    findings = PROBE_DIR / "FINDINGS.md"
    assert findings.is_file(), f"{findings} missing"
    cited = sorted({m.group(0) for m in _PATH_RE.finditer(findings.read_text())})
    assert cited, "FINDINGS.md cites no capture path at all"
    missing = [p for p in cited if not (REPO / p).exists()]
    assert not missing, f"FINDINGS.md cites paths that do not exist: {missing}"


def test_p1_capture_shows_the_isolation_lock() -> None:
    run = _folder("p1-versions")
    # the `locked` run sits at the folder root; `locked-syscli` is the same configuration driven
    # against the PATH CLI, and the lock has to hold on both binaries
    for stream in (run / "raw-stream.jsonl", run / "locked-syscli" / "raw-stream.jsonl"):
        assert stream.is_file(), f"{stream} missing"
        inits = _init_messages(stream)
        assert inits, f"{stream} contains no system/init message"
        for init in inits:
            tools = set(init.get("tools") or [])  # type: ignore[arg-type]
            assert tools == set(PROBE_TOOLS), (
                f"{stream}: system/init.tools is not exactly the probe's own tools. "
                f"unexpected={sorted(tools - PROBE_TOOLS)} missing={sorted(PROBE_TOOLS - tools)}"
            )
            servers = [s.get("name") for s in (init.get("mcp_servers") or [])]  # type: ignore[union-attr]
            assert servers == ["shepherd"], f"{stream}: mcp_servers is {servers}, not just the probe's own"
