"""QA round 6 — the macOS harness for Shepherd as built (M1-M4 + Projects + dark UI).

Nothing in this package does anything at import time: no Playwright, no
environment reads, no subprocess, no filesystem writes. The default pytest lane
collects this directory (it deselects the `qa6`/`qa6live` markers), so an
import-time side effect here would run on every plain `pytest`.

Entry point: `.venv/bin/python tests/qa6/run.py`. See `BUILDING.md`.
"""
