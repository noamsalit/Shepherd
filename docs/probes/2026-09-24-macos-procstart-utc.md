# Probe — macOS: the engine's `procStart` is `lstart` read in UTC (2026-09-24)

**Question.** BC-01 (qa6 report §8): on a Mac off UTC, `MacHost.process_liveness` judged every real
Claude Code session dead, because its token differed from the sidecar's `procStart` by the UTC offset.
Which timezone does the engine spell `procStart` in, and does pinning `TZ` on the child `ps` make the
product's token equal it?

**Host.** macOS 26.6.2 (build 25G83), Darwin 25.6.0, arm64. `TZ` unset in the shell; `date +%Z` → `IDT`
(UTC+3). Claude Code 2.1.281 (the sidecar writer).

**Status:** verified live 2026-09-24 on this host. Every line below is pasted verbatim; only read-only
commands were run. The sidecar was read through a copy in the session scratchpad, never in place.

---

## Result 1 — `ps -o lstart=` spells the start in the caller's timezone

This shell's own pid (7052):

```
$ date +%Z
IDT
$ date -u
Thu Sep 24 09:27:57 UTC 2026
$ ps -o lstart= -p 7052
Thu Sep 24 12:27:57 2026
$ TZ=UTC ps -o lstart= -p 7052
Thu Sep 24 09:27:57 2026
```

Same process, same instant, two spellings three hours apart: the default one is local (IDT), the
`TZ=UTC` one agrees with `date -u`.

## Result 2 — the engine writes `procStart` in UTC

One live session's sidecar, `~/.claude/sessions/32604.json`, copied to the scratchpad and read there:

```
$ cp ~/.claude/sessions/32604.json $SCRATCH/sidecar-32604.json
$ python -c "import json; d=json.load(open('$SCRATCH/sidecar-32604.json')); print(repr(d.get('procStart')), d.get('pid'))"
'Wed Sep 23 13:26:05 2026' 32604
$ ps -o lstart= -p 32604
Wed Sep 23 16:26:05 2026
$ TZ=UTC ps -o lstart= -p 32604
Wed Sep 23 13:26:05 2026
```

`procStart` equals the `TZ=UTC` spelling byte for byte, and differs from the default (local) spelling
by exactly the host's offset. That is the 3.0 h `files.procstart_offset_hours` qa6's L5 measured.

## What follows for `mac.py`

`MAC_LIVENESS_TZ = "UTC"`, passed to the one `ps` call as `TZ` in the child's environment
(`mac_liveness_env`). Nothing else changes: the argv, the resolution caveat (a token to the second, so
a pid reused inside one second is not seen — §5 of `2026-09-20-macos-g1-capture.md`), and the
rc/empty-output rules are as measured on 2026-09-20.

## What this does not settle

- The locale. `lstart`'s day and month names follow `LC_TIME`; this host runs the default `C`/`en_US`
  spelling and so does the engine. A host with a non-English `LC_TIME` is not measured here and is
  out of this fix's scope.
- Whether a future engine version changes its spelling. The regression test
  `tests/contracts/test_machost_liveness_utc.py` pins the product side only.
