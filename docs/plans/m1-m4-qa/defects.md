# M1–M4 QA — defects, with the router's disposition

Five defects, found by the first pass that tested the four milestones **composed** rather than each
one's own seams. D1 is the reason this pass existed.

---

## D1 · CRITICAL · D31's wake set is structurally empty in production · **router-verified**

`store/reads.py:231` — `WAKE_ORIGIN = Origin.ORCHESTRATOR.value`, and the wake query filters on it.
**Nothing in `src/` ever writes that origin.** I grepped it myself: `Origin.ORCHESTRATOR` occurs
**twice** in the whole tree — that `WHERE` clause, and `admission.MASTER_ORIGIN` for the retry cap.
Neither is a write. `tools_m3.SPAWN_ORIGIN = Origin.USER_UI` is what **every** spawn writes, the
master's included; the hook lane and discovery write `EXTERNAL`; `ask.py` writes `ASK_FORK`.

**So the orchestrator can never be told what stopped while the human was away** — the feature D31
exists for. Every wake test passes because **each one writes its own `origin=ORCHESTRATOR` row
directly**: the fixture creates a condition the production path never creates. That is this repo's
signature defect in its purest form, and it survived 1791 tests, four milestones and a milestone
verification because no test before this one drove a *master* spawn rather than a fixture.

**The fix is not one line, and the reason matters.** `spawn_session` is called by a human clicking
the fleet page *and* by the master, through the same handler — so the origin must depend on **who
asked**. And `invoke()` checks `ctx.audience` and then **discards the caller** before the handler
runs (`registry.py`), so the handler *cannot know*. This is the same root constraint that caused
Track C to be cut.

Two honest repairs, and the choice is a design decision:
1. **Bind `ctx` into the handler call** — `tool.handler(args, ctx)` or a per-call closure. Neither
   changes `invoke()`'s signature, so Gate A survives. This also unblocks Track C's reversal
   condition, which needs exactly the same thing.
2. **Let the master pass its own origin explicitly** as an argument. Cheaper, and it puts a
   security-relevant field in the hands of the caller — which is what the audience check exists to
   avoid.

**My reading is (1)**, because it is the repair two open findings already wanted. Either way, the
proof must be a **master-initiated spawn reaching the wake set**, never a fixture row.

## D2 · HIGH · §12's Needs-You rail never shows an approval

`rail.js` renders `fleet_summary.needs_you` and composes nothing; `fleet_summary` builds that list
only from `state == NEEDS_YOU` session rows. **No reader of `ApprovalStore.pending()` exists in
`tools_m1.py`.** §12's own mock shows three row kinds and the third — a pending approval — is
invisible on every page. The rail is the one surface fed by three milestones at once, which is why
no milestone's tests could have caught it.

## D3 · HIGH · `shepherd status` tells you to start a daemon that is already running

Measured beside a real `controld`: exit 1 and *"start the shepherd control daemon"* — **byte-identical
to the no-daemon case**. `shepherd doctor` succeeds in the same environment, which is what makes this
a defect rather than a broken install. Recorded at M1 as T18-1 and routed to M4, where it was not
built. **Now measured against a running daemon** rather than reasoned about.

## D4 · MEDIUM · §T25-8 is not a race — it is deterministic

**20/20 runs**, the foreign worker released by shutdown comes back with `RuntimeError("store is
closed")`, never D54's refusal. The shipped check asserts `is_error is True`, which is true in **both**
branches — so it could not distinguish them, and the ledger's "can race" was generous. Clause 20's
promise still holds: released, before `deadline_at`, every run.

## D5 · LOW · install-path roughness

`shepherd --help` → `unknown command '--help'`, exit 64. `shepherd-sessiond` with no arguments →
argparse error, exit 2. All three console scripts install and run, and `shepherd-controld` binds,
serves and stops from the installed artefact. **This is the path a Mac takes first**, so it is on the
handoff list.

---

## Corrections to my own records, from this pass

- **`MasterRuntime.resume()` has a caller.** My "no caller" register said otherwise; T25 wired it in
  `daemons/plane.py::build_master`, and the register was never updated. **The register was stale, and
  I am the one who kept it.** The harness rewrote its scenario to assert the chain end to end instead.
- **§11 does not state the gate's attribution at level 3.** The harness's independent reading of §11's
  table disagreed with the shipped `TABLE` on two rows; the build claims **less** than the reading, so
  it is right — but the rule lives only in `policy.py`'s comments, not in the spec.
- **§11's "~40 lines" is over at *one* session**, by 2× — 85 lines. Worse than the 5-session figure
  already recorded.

## And one the harness reported against itself

A scratch probe, working out how to drive `shepherd-controld`, ran unisolated and **opened the
operator's real data dir** — it migrated the database and ran a discovery scan. Nothing was deleted.
It is reported here because the harness reported it rather than quietly cleaning up, and because the
response was structural: both live modules now scrub `XDG_*` and `CLAUDE_CONFIG_DIR` before starting
anything, and `test_the_daemon_wrote_only_into_the_throwaway_home` exists **as a check rather than a
promise**.
