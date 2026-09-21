# Credentials and authentication — open questions

**Status: OPEN. Nothing here is decided.** Recorded on 2026-09-21 so the
discussion is not had twice. The owner reviewed the options below and
**explicitly did not agree to them** — they are candidates, not choices.

Trigger for reopening: **the remote, multi-user deployment.** While Shepherd is
one person on one machine driving Claude Code, none of this is needed (see §1).

---

## 1. Why nothing is needed today

`Credentials` is a seam in the spec (§6) with **zero implementations in
`src/`**. Nothing in the tree stores, reads or forwards a credential.

It works anyway, because of what Shepherd actually is: it spawns a real
`claude` process, and that process uses **whatever account the CLI on the
machine is already logged into**. The master does the same — `AgentSDKMaster`
runs on the subscription through the harness. Shepherd never sees a secret
because it never needs one.

§6's own table says exactly this: the v1 credential is the *"local Claude
subscription"*, with *"per-user API key / OAuth / BYOK"* in the **later**
column.

So for a single user, on a laptop, driving Claude Code: **this is finished
work, not missing work.** It stops being true the moment any of these is true:

* Shepherd runs somewhere the user is not sitting (remote server);
* more than one person uses the instance;
* an **API-based** runtime is used instead of a CLI harness (`ApiLoopMaster`,
  or a bring-your-own harness — see `harness-contract.md`);
* a connector needs a third-party credential (D20, M4.5).

## 2. The open questions

There is not one authentication question here. There are four, and conflating
them is the mistake this file exists to prevent.

### Q1 — Shepherd → a model provider

Needed only for API-based runtimes. A CLI harness never raises it.

*Candidate:* a token (BYOK), because the major providers do not offer consumer
OAuth for API access. **Not agreed.**

### Q2 — Shepherd → third-party tools (connectors)

*Candidate:* OAuth. M4.5 already says *"OAuth/token capture into the credential
store"*, and these are delegated grants that need refresh and revocation.
**Closest to settled of the four, but still not confirmed.**

### Q3 — A human → Shepherd (the remote, multi-user case)

This is the one the owner named as the real trigger. It is the auth seam §13
defers and the `Users & access` placeholder in the settings design.

*Candidate:* OIDC/SSO. **Not agreed, and not explored.** Session cookies,
device pairing and a single shared passphrase are all plausible and none was
discussed.

### Q4 — Who owns the credential when the harness is a CLI?

Today, by accident rather than decision, the harness does: Shepherd holds
nothing and the CLI's own login applies.

*Candidate:* make that the rule — a CLI harness authenticates itself, and
Shepherd never brokers a seat credential. D30's argument supports it (a
subscription seat is reachable only through the harness; there is no API
endpoint for it), and it would make BYO-harness authentication the harness
author's problem rather than ours. **Not agreed.** The counter-argument was
never put: it means Shepherd cannot tell whether a harness is logged in until
a session fails, and cannot manage credentials centrally for a fleet.

## 3. Two rules that look cheap and are not controversial

Written down here because they constrain whatever is decided above, and
because both are easy to get wrong late.

1. **`credential_ref` is an opaque handle, never a secret.** §7 already says
   so. The database stores references; the secret lives behind `Credentials`,
   in the OS keychain or secret service. There is precedent in the tree: D50
   strips embedded tokens out of `git remote` URLs before storage, for exactly
   this reason.
2. **Never put a credential in argv.** `orchestration/spawn.py` builds an argv
   for every owned session, and `/proc/<pid>/cmdline` is world-readable on
   Linux. The environment is better; a file descriptor or a keychain lookup
   inside the child is better still.

## 4. Related

* `harness-contract.md` §4 — a bring-your-own harness raises Q1 and Q4 together.
* §13 — the auth seam, deferred; the network posture (127.0.0.1 only) is what
  makes the absence safe today.
* §17 — *Real session sandboxing*, which is a different problem with the same
  trigger: both become urgent when Shepherd stops being one person on one
  machine.
