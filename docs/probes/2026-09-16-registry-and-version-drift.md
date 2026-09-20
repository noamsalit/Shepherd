# Probe — live-session registry under `-p`, and engine version drift (2026-09-16)

Two findings, both live on this host today. The first closes a gap `data-schemas.md` names
explicitly. The second is the D41 re-probe trigger firing for the first time.

---

## Finding 1 — `-p` sessions DO appear in `~/.claude/sessions/<pid>.json`

**The open gap.** `data-schemas.md` §"Live-session registry `~/.claude/sessions/<pid>.json`" says:

> **`-p` sessions: not verified.** … The process may already have exited when the registry was
> read. Absence during a live `-p` turn still needs a probe that confirms the pid is alive at
> check time.

**The probe.** Launch `claude -p` with a prompt that keeps it alive ~20 s
(`sleep 18 && echo PROBEDONE`), then list the registry while `kill -0 <pid>` confirms the process
is alive. Throwaway cwd under `/tmp`; the user's real config dir, because an isolated
`CLAUDE_CONFIG_DIR` has no credentials (see Finding 3 below).

**Result: it registers.** pid 4110260, then 4110361 on a repeat — the sidecar `<pid>.json` and its
`<pid>.<64hex>.key` sibling both appeared during the run and were **deleted on exit**.

Captured shape for a `-p` session (secrets elided, otherwise verbatim):

```json
{
  "bridgeSessionId": null,
  "cwd": "/tmp/shp-reg-p-rw1jU0",
  "entrypoint": "sdk-cli",
  "kind": "interactive",
  "messagingSocketPath": "<path>",
  "name": "shp-reg-p-rw1ju0-fe",
  "nameSince": 1789590167990,
  "nameSource": "derived",
  "peerFeatures": ["notify_idle", "reply_across_default_dirs", "artifact_yield"],
  "peerProtocol": 1,
  "pid": 4110361,
  "pidDomain": "linux:64835ff781b0486f95b67b152a8cf404:pid:[4026531836]",
  "procStart": "562742328",
  "sessionId": "2a9b2090-6fe9-4b7b-8e2d-3bc180c11a74",
  "startedAt": 1789590167990,
  "status": "busy",
  "statusUpdatedAt": 1789590168392,
  "tmux": "spike:@1.%1",
  "updatedAt": 1789590168392,
  "version": "2.1.273"
}
```

**The correction that matters.** `kind` is **`"interactive"` even for a `-p` run**. It does not
separate print mode from a TUI. **`entrypoint` is the field that does** — `sdk-cli` for `-p`,
`cli` for interactive (the same split the transcript envelope uses, per data-schemas §"Transcript
entry: common envelope"). Any discovery code that branches on `kind` to decide "is this headless"
is wrong; branch on `entrypoint`.

Two more notes for whoever builds discovery:

- `tmux` is **inherited from the launching environment**, not discovered. This `-p` process was
  launched from inside a tmux pane and faithfully recorded that pane, though nothing about the
  process is "in" tmux in the sense the field implies. Trust it for sessions Shepherd spawns;
  treat it as a hint for sessions it did not.
- `nameSource: "derived"` with a name built from the cwd (`shp-reg-p-rw1ju0-fe`). Under D29 that
  is an `engine`-sourced title, and it is available with no hooks and no transcript read.

**Status:** verified live 2026-09-16 against Claude Code 2.1.273. The earlier "not verified" note
in data-schemas was written against 2.1.270 and its probe raced the exit; this one did not.

---

## Finding 2 — the engine has moved to 2.1.273; every schema was captured against 2.1.270

```text
$ claude --version
2.1.273 (Claude Code)

$ ls /root/.local/share/claude/versions/
2.1.269  2.1.270  2.1.271  2.1.273
```

`data-schemas.md` opens with: *"Captures were made on Linux 6.8 with `claude --version` =
`2.1.270 (Claude Code)`"*, and **all 127 schemas** rest on that. D41 anticipated exactly this:

> A shape copied from a capture can be re-probed when the engine upgrades; a shape typed from
> memory cannot.

This is that moment, three patch versions on. **Nothing here says a shape has changed** — no
mismatch has been observed, and the registry shape above matches the 2.1.270 capture field for
field. But the reference is no longer pinned to the running binary, and that is a standing risk
rather than a resolved one.

**What M1 should do about it, and what it should not.** Not a re-run of the whole probe suite —
that is days of work for a patch bump. The cheap, proportionate move is a **schema-drift check**:
re-extract the binary's own enums and hook-event list (the existing
`docs/probes/2026-09-14-schemas/hooks/extract_binary.py` already does this, and it is the one
probe that needs no live session) and diff against
`docs/probes/2026-09-14-schemas/hooks/binary/`. If the 33 event names and the four enums are
unchanged, the fold rules are safe and the risk is closed cheaply. If they moved, M1 learns it at
planning time instead of in production.

That check is also the thing to run on every future engine upgrade, which makes it worth owning
as a small script rather than a one-off.

### The drift check, run — result: no drift on the surface M1 and M2 depend on

Two notes on method first, because both are small traps:

- `docs/probes/2026-09-14-schemas/hooks/extract_binary.py` **no longer runs** against 2.1.273. It
  byte-searches for minified anchors (`var we=f(()=>u({session_id:o(),…`) and dies with
  `ValueError: subsection not found`. That is a minifier artifact, not evidence of schema change —
  anchors move on every build. The extractor needs anchor repair before it is useful again.
- `docs/probes/2026-09-14-schemas/hooks/binary/hook-events.json` on disk is **empty**
  (`{"offset": null, "count": 0, "events": null}`) even though data-schemas cites `"count": 33`
  from it. The stored artifact does not match its own citation — presumably a later failed re-run
  overwrote it. The 33 names quoted in the data-schemas prose are still good (they come from
  `claude doctor` output captured in `R03_config_unknown_event_name/doctor.txt`); the JSON beside
  them is not. Worth repairing so a future reader does not trust the empty file.

  **Repaired 2026-09-16.** The file now carries the 33 names, regenerated from that `claude doctor`
  capture — the authoritative record of the same list, and the one data-schemas' own quoted example
  shows — with a `_provenance` block stating where they came from, why the file was empty, and that
  it was **not** re-extracted from the binary (the extractor's anchors no longer match 2.1.273). The
  citation at `data-schemas.md:242` is now true of the file on disk as well as of the probe run.

So the check was run directly against the two binaries instead:

```text
2.1.273: 228,663,608 bytes | 2.1.270: 223,981,040 bytes

33 documented event names -> absent from 2.1.273: NONE (all 33 present)

SessionEnd.reason          -> UNCHANGED (exact ordered list found)
SessionStart.source        -> UNCHANGED (exact ordered list found)
StopFailure.error          -> UNCHANGED (exact ordered list found)
Notification.type          -> UNCHANGED (exact ordered list found)
```

Each enum was searched as its **exact ordered comma-separated literal**, so this is stronger than
"the values exist somewhere": the lists are byte-identical to the ones data-schemas records for
2.1.270.

**Conclusion.** The hook-event surface and the four enums that M1's fold and M2's stop-reason
table rest on are unchanged from 2.1.270 to 2.1.273. The version drift is real but benign for this
work, and the risk is closed rather than merely noted. What this does **not** cover: per-event
*field* shapes (the zod schemas), which the broken extractor would have given. Those remain
verified at 2.1.270 only. Since the fold is written to be field-tolerant anyway (C8 — only four
fields are on every event), that residual is small, but it is not zero.

Re-run: `/tmp/…/scratchpad/drift_check.py`, reproduced in this repo's probe folder if it is ever
needed again — it is ~30 lines and needs no live session.

---

## Finding 3 — an isolated `CLAUDE_CONFIG_DIR` has no credentials

An attempt to run the probe under `CLAUDE_CONFIG_DIR=<throwaway>` failed with:

```text
Not logged in · Please run /login     [rc=1]
```

Credentials live in the real config dir, so **isolation and authentication are mutually
exclusive** for live probes. Any live run that needs a model must use the user's real config dir
and isolate through the **working directory** and `--settings` instead — which is what the
2026-09-14 suite did, recording that `~/.claude/settings.json`'s sha256 was identical before and
after every run.

This is a constraint on M1's own test strategy, and on anything later that wants a hermetic
end-to-end run: there is no hermetic authenticated `claude` on this host.
