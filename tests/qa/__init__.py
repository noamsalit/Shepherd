"""The M1–M4 QA pass: tests of the *composed* product, not of one milestone.

`docs/plans/2026-09-18-m1-m4-qa-plan.md` is the plan; every module here is one
of its nine scenarios, named `test_s<N>_…`, and every module's docstring says
what a **lying implementation** would look like that the scenario now catches.

Two rules this package holds itself to, beyond the repo's:

* **Never a literal population.** The registry, the enums and the audiences are
  enumerated at test time and compared as sets, with the enumeration rule
  written into the check. A hard-coded tool list is how a cross-milestone
  scenario goes stale without anybody noticing.
* **Arrival before absence.** Every emptiness assertion is preceded by a
  positive control on the same reader, so *"nothing was found"* is distinguished
  from *"nothing can be found"*.
"""
