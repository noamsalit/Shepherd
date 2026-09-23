"""QA round 5 harness — wf:wf-20260921T212808Z-9172ed6b.

A **test package**, never product code. Nothing under `src/` is imported for
modification and nothing here is importable by `src/`.

The package is deliberately separate from `tests/qa/`: that package composes
under a `ScriptedHost` with autouse fixtures, and round 5's whole subject is the
real `LinuxHost`, a real tmux socket and a real pane.
"""
