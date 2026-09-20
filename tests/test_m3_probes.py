"""Task 1's two Required Checks: the M3 probe captures exist, and FINDINGS.md cites real paths.

`test_m3_probe_captures_exist` goes red if one of the four capture folders is missing, or if a
folder has no `versions.txt`, or if its `teardown.txt` does not say `no server running`.

`test_findings_cite_real_capture_paths` goes red if a `docs/probes/...` path named in
`FINDINGS.md` does not exist on disk. It is the check that stops a finding from being written
from memory: a probe answer whose evidence path is invented cannot pass it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO / "docs" / "probes" / "2026-09-17-m3-tmux"

#: One folder per probe. The value is the `<name>` half of `<name>-<UTC>`.
PROBES = ("p1-keys", "p2-fork", "p3-concurrent", "p4-permission")

#: Every capture path FINDINGS.md may cite starts here.
_PATH_RE = re.compile(r"docs/probes/[A-Za-z0-9_./-]*[A-Za-z0-9_/-]")


def _folder(name: str) -> Path:
    matches = sorted(PROBE_DIR.glob(f"{name}-*"))
    assert matches, f"no capture folder {PROBE_DIR}/{name}-<UTC>/ — probe {name} did not run"
    return matches[-1]


def test_m3_probe_captures_exist() -> None:
    for name in PROBES:
        run = _folder(name)
        versions = run / "versions.txt"
        teardown = run / "teardown.txt"
        assert versions.is_file(), f"{versions} missing"
        assert teardown.is_file(), f"{teardown} missing"
        text = teardown.read_text()
        assert "no server running" in text, f"{teardown} does not report 'no server running': {text!r}"


def test_findings_cite_real_capture_paths() -> None:
    findings = PROBE_DIR / "FINDINGS.md"
    assert findings.is_file(), f"{findings} missing"
    cited = sorted({m.group(0) for m in _PATH_RE.finditer(findings.read_text())})
    assert cited, "FINDINGS.md cites no capture path at all"
    missing = [p for p in cited if not (REPO / p).exists()]
    assert not missing, f"FINDINGS.md cites paths that do not exist: {missing}"
