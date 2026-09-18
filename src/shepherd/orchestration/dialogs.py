"""T16 — answering a dialog, and only a dialog whose text we have captured (D44).

Two verbs, two key maps, nothing shared: mixing them is how a bare Enter reaches
the trust screen and selects `No, exit`, which exits with status 1 (C15, A11).

**A digit is positional, so the text is matched before any key is sent.** P4
pressed `Tab` and the dialog **stayed up** with option 1 re-labelled `1. Yes, and
tell Claude what to do next` (`02a-tab-dialog.txt` -> `02b-tab-after.txt`). The
pane classifier calls both screens the same kind, so a gate keyed on the kind
alone would send `3` where position 3 has no captured outcome, and Enter where it
approves *with a follow-up instruction nobody wrote*. That is BLOCKER-T1-4:
**Shepherd cannot see an amendment it did not make**, so an option set that is
not the captured one is refused, never guessed at.

**The observable is the pane, never a hook.** Neither refusal P4 measured fired a
permission-denied event and neither fired a turn-ending one, so a caller waiting
on an event to confirm its deny waits for ever.

**Clause 4's second half, which T13 could not close (T13-1).** The write policy
takes pane values and has no sidecar field, so this gate composes both sources,
and an **absent** sidecar is counted (`AnomalyKind.SIDECAR_ABSENT`) and refused
rather than read as clear — it is the normal state during the trust dialog
(DP8), which is exactly why inferring from it would be wrong.

**Still `unknown`, deliberately unimplemented:** a non-Bash tool's option set,
what Enter does after `Tab`, whether a text reply follows `3`. No capture shows
them, so nothing here answers them.

**The captured half lives in `dialog_keys.py`** — the keys, the evidence and the
two pure matchers — and is re-exported here under the names Task 16 publishes,
with an identity test pinning each to one object (M1's F9).

Deviations from Task 16's `Produces`: a `DialogAnswer` rather than a bare
`WriteDecision` (four refusals collapsing into one member is a value a reader
cannot act on — T14's accepted precedent), a required keyword-only `sidecar`, and
no clock, because this writes no row and an unread clock is a promise the
signature cannot keep.
"""

from __future__ import annotations

from dataclasses import dataclass

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.runner import PaneKind, RunnerHandle, WriteDecision
from shepherd.orchestration.dialog_keys import (
    ALLOW_OPTION_PREFIX,
    DIALOG_EVIDENCE,
    PERMISSION_KEYS,
    TRUST_KEYS,
    TRUST_OPTIONS,
    PermissionChoice,
    SidecarState,
    is_the_captured_permission_dialog,
    is_the_captured_trust_dialog,
)
from shepherd.runner.base import Runner
from shepherd.store.db import Store

__all__ = [
    "ALLOW_OPTION_PREFIX",
    "DIALOG_EVIDENCE",
    "PERMISSION_KEYS",
    "TRUST_KEYS",
    "TRUST_OPTIONS",
    "DialogAnswer",
    "PermissionChoice",
    "SidecarState",
    "answer_permission",
    "answer_trust",
]


@dataclass(frozen=True)
class DialogAnswer:
    """What one attempt did, and why. `keys_sent` is countable at the seam."""

    decision: WriteDecision
    reason: str | None
    keys_sent: int


def _send(runner: Runner, handle: RunnerHandle, keys: tuple[str, ...]) -> DialogAnswer:
    for key in keys:
        runner.write(handle, key.encode("ascii"))
    return DialogAnswer(decision=WriteDecision.SEND_NOW, reason=None, keys_sent=len(keys))


def _refuse(reason: str) -> DialogAnswer:
    """No key is sent, and the reason says which gate stopped it."""
    return DialogAnswer(decision=WriteDecision.REFUSE_DIALOG, reason=reason, keys_sent=0)


def answer_permission(
    *,
    store: Store,
    runner: Runner,
    handle: RunnerHandle,
    session_id: str,
    choice: PermissionChoice,
    sidecar: SidecarState,
) -> DialogAnswer:
    """Answer D44's dialog with one captured key, or refuse and say why.

    The order is the safety property: the pane kind, then the sidecar, then the
    option set, and only then a key. Each refusal names itself, so a caller can
    tell "there is no dialog" from "there is one I must not key into".
    """
    pane = runner.pane(handle)
    if pane.kind is not PaneKind.PERMISSION_DIALOG:
        return _refuse(f"{session_id}: the pane is {pane.kind.value}, not a permission dialog")
    if sidecar is SidecarState.ABSENT:
        store.bump_anomaly(AnomalyKind.SIDECAR_ABSENT.value)
        return _refuse(f"{session_id}: the sidecar is absent — counted, never read as clear")
    if sidecar is not SidecarState.WAITING:
        return _refuse(f"{session_id}: the sidecar does not say this session is waiting on you")
    if not is_the_captured_permission_dialog(pane.dialog_text):
        # T16-1: counted, not only returned. A refusal a caller reads out of a
        # `reason` reaches no surface `doctor` renders, and this is the one
        # standing between a positional digit and a tool no human approved
        # (principle 5).
        store.bump_anomaly(AnomalyKind.DIALOG_TEXT_UNRECOGNISED.value)
        return _refuse(
            f"{session_id}: this screen is not the option set we captured — Tab may have amended"
            " it, or it is another tool's dialog. A digit is positional, so nothing is sent"
        )
    return _send(runner, handle, PERMISSION_KEYS[choice])


def answer_trust(
    *, runner: Runner, handle: RunnerHandle, session_id: str, trust: bool
) -> DialogAnswer:
    """Answer the workspace-trust screen. A different screen, a different map.

    No sidecar is asked for: the engine writes none until trust is accepted
    (`01-trust-dialog-sidecar.json` is literally `<absent: …>`), so requiring one
    here would refuse every trust dialog there has ever been.
    """
    pane = runner.pane(handle)
    if pane.kind is not PaneKind.TRUST_DIALOG:
        return _refuse(f"{session_id}: the pane is {pane.kind.value}, not a trust dialog")
    if not is_the_captured_trust_dialog(pane.dialog_text):
        return _refuse(f"{session_id}: the trust options are not the two we captured, in order")
    return _send(runner, handle, TRUST_KEYS[trust])
