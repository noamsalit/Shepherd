#!/usr/bin/env python3
"""Engine schema-drift check — does the running Claude Code still emit the shapes we captured?

`docs/specs/data-schemas.md` pins all 127 schemas to the engine version named in its header.
When the engine upgrades, a shape copied from a capture can be re-probed; a shape typed from
memory cannot (D41). This is that re-probe, reduced to the part that needs no live session:
the 33 hook-event names and the four enums the fold and the stop-reason table rest on.

Exit status is a gate, not decoration:
  0  no drift on the checked surface
  1  drift found - a name or an enum moved; do not trust the captures until re-probed
  2  could not check (binary not found, capture missing)

It does NOT cover per-event *field* shapes, which the binary extractor would give and which
remain verified only at the captured version. Say so rather than implying full coverage.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE = (
    REPO_ROOT
    / "probes/2026-09-14-schemas/hooks/live/R03_config_unknown_event_name/doctor.txt"
)
VERSIONS_DIR = Path.home() / ".local/share/claude/versions"

#: The version every capture in data-schemas.md is pinned to (its header).
PINNED_VERSION = "2.1.270"

# The four enums, verbatim from data-schemas.md, each as an exact ordered list.
ENUMS: dict[str, list[str]] = {
    "SessionEnd.reason": ["clear", "resume", "logout", "prompt_input_exit", "other"],
    "SessionStart.source": ["startup", "resume", "clear", "compact", "fork"],
    "StopFailure.error": [
        "authentication_failed", "oauth_org_not_allowed", "account_on_hold",
        "verification_required", "billing_error", "rate_limit", "overloaded",
        "invalid_request", "model_not_found", "server_error", "unknown",
        "max_output_tokens", "cloud_credential_error",
    ],
    "Notification.notification_type": [
        "permission_prompt", "idle_prompt", "auth_success", "elicitation_dialog",
        "agent_needs_input", "agent_completed", "elicitation_url_dialog",
        "worker_permission_prompt", "push_notification", "computer_use_enter",
        "computer_use_exit", "quota_auto_resume_fired", "quota_auto_resume_stale",
        "quota_auto_resume_disabled",
    ],
}


def running_version() -> str:
    """The engine version actually installed, discovered — never hard-coded."""
    out = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, check=False
    )
    match = re.search(r"(\d+\.\d+\.\d+)", out.stdout)
    if not match:
        raise SystemExit(f"[2] could not determine the running engine version: {out.stdout!r}")
    return match.group(1)


def binary_for(version: str) -> Path:
    path = VERSIONS_DIR / version
    if not path.exists():
        raise SystemExit(f"[2] engine binary not found for {version} at {path}")
    return path


def captured_event_names() -> list[str]:
    if not CAPTURE.exists():
        raise SystemExit(f"[2] capture missing: {CAPTURE}")
    match = re.search(r"Valid events:\s*(.+)", CAPTURE.read_text())
    if not match:
        raise SystemExit(f"[2] no 'Valid events:' line in {CAPTURE}")
    return [name.strip() for name in match.group(1).split(",")]


def record_verdict(path: Path, version: str, verdict: str, detail: str) -> None:
    """Write the verdict where `doctor`'s `engine:` line can read it.

    `shepherd.engines.claude_code.version.read_drift_record` is the reader; a
    record it cannot parse reads as *unchecked*, never as clean, so a half-written
    file degrades to "nobody has checked here" rather than to a false pass.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "engine_version": version,
                "pinned_version": PINNED_VERSION,
                "verdict": verdict,
                "detail": detail,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"recorded: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="write the verdict to this path for `shepherd doctor` to read",
    )
    args = parser.parse_args()
    version = running_version()
    binary = binary_for(version)
    data = binary.read_bytes()
    names = captured_event_names()

    print(f"engine (discovered): {version}   binary: {binary} ({len(data):,} bytes)")
    print(f"captured event names: {len(names)} (from {CAPTURE.name})")

    drift: list[str] = []

    missing = [n for n in names if f'"{n}"'.encode() not in data]
    if missing:
        drift.append(f"event names absent from the running binary: {missing}")
    print(f"  event names present: {len(names) - len(missing)}/{len(names)}")

    for label, values in ENUMS.items():
        exact = ",".join(f'"{v}"' for v in values).encode()
        if exact in data:
            print(f"  {label:32} UNCHANGED (exact ordered list found)")
            continue
        absent = [v for v in values if f'"{v}"'.encode() not in data]
        if absent:
            drift.append(f"{label}: values absent: {absent}")
            print(f"  {label:32} CHANGED - missing {absent}")
        else:
            drift.append(f"{label}: all values present but the ordered list no longer matches")
            print(f"  {label:32} REORDERED/REGROUPED (all values present)")

    print()
    if drift:
        if args.record is not None:
            record_verdict(args.record, version, "drift", "; ".join(drift))
        print("DRIFT FOUND - the captures can no longer be trusted for this surface:")
        for line in drift:
            print(f"  - {line}")
        print("\nRe-probe before building on any affected shape (D41).")
        return 1

    if args.record is not None:
        record_verdict(
            args.record,
            version,
            "clean",
            f"{len(names)} event names + {len(ENUMS)} enums unchanged at {version}",
        )
    print("No drift on the checked surface (33 event names + 4 enums).")
    print(
        "NOT covered: per-event field shapes, which remain verified only at the version\n"
        "named in data-schemas.md's header. This check is necessary, not sufficient."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
