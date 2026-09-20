"""L4's vocabulary (§11.0, D32, D38, ADR-3).

Nothing here names a transport or a vendor. An exporter translates the registry
outward; it arrives at M4 and it changes no file in `web/` or `cli/`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

#: The validated arguments of one call. `invoke()` checks them against the
#: tool's schema before the handler ever sees them (D53), so a handler reads
#: what it declared and nothing else.
ToolArgs = Mapping[str, object]



class ToolArgumentRefused(Exception):
    """A handler read an argument the schema cannot describe and refused it.

    JSON Schema can say `{"type": "string"}`; it cannot say *a date spelled
    `YYYY-MM-DD`*. So the handler is the only place that can refuse
    `--since 30d`, and a refusal a consumer cannot tell from a crash is a
    refusal it cannot render as usage advice — it told a user whose value was a
    typo to start a daemon. The message is the caller's own value described
    back to them, so it carries nothing about the surface (§13).
    """


class Failure(StrEnum):
    """Why a call did not succeed — the fact a consumer branches on.

    Deliberately **not** the error *text*, which stays one literal for every
    mode so that a caller cannot probe which tools exist or who may call them
    (§13 Errors). What was wrong before was that the one text was the only
    channel: a handler that raised half way through a destructive write and a
    capability that is simply not registered here were indistinguishable, so
    `cli/` told a user whose database had just been rewritten that no such
    capability existed and to start the control daemon.
    """

    UNAVAILABLE = "unavailable"
    """No such tool here, not for this audience, or arguments that do not fit
    the schema. One value for all three, exactly as §13 requires — a caller
    that could tell them apart could enumerate the surface."""

    REFUSED = "refused"
    """The handler read the arguments and refused one. A usage error."""

    FAILED = "failed"
    """The handler raised. The call reached the capability; whatever it had
    started may be half done, and no consumer may advise otherwise."""


class Audience(StrEnum):
    """Who may call a tool. `HUMAN` covers `web/` and `cli/` (ADR-3, RD2)."""

    MASTER = "master"
    SESSION = "session"
    HUMAN = "human"


class ActorKind(StrEnum):
    """Who the audit record says acted (ADR-M4-1, DP2).

    Wider than `Audience` on purpose. `Audience` answers *may this caller reach
    this tool*, and it has three members because that is how many kinds of
    caller the registry distinguishes. `ActorKind` answers *what was on the
    other end*, and M5's queue worker is a fourth: it is not a human, so the
    blast table gives it the card, and a record that called it `human` because
    it arrived on the `MASTER` audience would be the same overclaim K23 is
    about.
    """

    MASTER = "master"
    SESSION = "session"
    HUMAN = "human"
    WORKER = "worker"


#: §13: *"Redaction pass on `action_log.args` … for known secret-shaped keys."*
#: Argument keys whose **value** never reaches a card or a log.
#:
#: **One declaration, here** (RD-T4-3, closed in the QA-prep pass). It was
#: declared in `audit.py` and copied into `approvals.py`, and the copy was
#: forced: `audit.py` imports `shepherd.logs.jsonl`, the gate sits behind
#: `invoke()`, and `cli/` imports `registry` — so the clean import would have
#: dragged `shepherd.logs` into `shepherd status`. That is the transitive hole
#: this module's own docstring below refuses, and **the shipped boundary rule
#: checks only direct importers, so it would have passed while being defeated**.
#: This module imports nothing but stdlib, so it is the only honest home, and
#: both former holders now import from here. `tests/boundaries/
#: test_one_definition_site.py::test_the_redaction_rule_has_one_definition_site`
#: goes red if a second definition reappears — the guard the drift comparison
#: used to be, now asserting the property instead of papering over its absence.
#:
#: Substrings of the lower-cased key, because the shape of the *key* is the
#: signal: `api_token`, `GITHUB_TOKEN` and `token` are one rule.
#:
#: **`credential` is deliberately not a marker.** §13 says the DB, the audit log,
#: the agent's context and the UI see `credential_ref`, so redacting it would
#: delete the one field the rule leaves in.
#:
#: **`key` is one marker and not four** (`api_key`, `apikey`, `private_key`,
#: `access_key`). Four spellings of one family is four things to keep in step,
#: and the one that is forgotten is the one that leaks. It over-matches a key
#: literally named `keyword`, and that is the **safe** direction for a redactor.
#: (It also keeps this module clear of `tests/signals/test_verdict.py`'s
#: credential-word ban, which is stricter than the §13 control it guards —
#: RD-T5-6, owner: router; this list is narrower on its merits, not to get past
#: it.)
SECRET_KEY_MARKERS: frozenset[str] = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "key",
        "cookie",
        "authorization",
    }
)

#: What a redacted value reads as. One spelling, for `SECRET_KEY_MARKERS`' reason.
REDACTED = "<redacted>"


class BlastClass(StrEnum):
    """What a call can damage. A **required** `ToolDef` field, so a tool without
    one does not typecheck — stronger than a lookup table that can miss."""

    LOCAL_READ = "local_read"
    LOCAL_WRITE = "local_write"
    LOCAL_DESTRUCTIVE = "local_destructive"
    EXTERNAL = "external"


@dataclass(frozen=True)
class CallerContext:
    """Who is calling, and the id every error carries back (§13 Errors)."""

    audience: Audience
    caller_id: str
    correlation_id: str
    actor_kind: ActorKind | None = None
    """What was on the other end, when the caller knows something the audience
    cannot express — M5's queue worker arrives on an agent audience and is not a
    human (DP2). **Defaulted, and that is load-bearing:** `web/server.py:230,299`
    and `cli/main.py:164` construct this with three arguments, and a required
    field would edit all three, which takes D38's *no consumer byte changes*
    acceptance test red with it. `actor_kind_of(ctx)` reads the field when it is
    set and derives from the audience otherwise."""


#: A handler takes the argument mapping **and the caller** — not `**kwargs`:
#: `Callable[..., object]` is an explicit `Any` under `disallow_any_explicit`,
#: which K4 forbids, and a keyword-star signature would put the unpacking on the
#: untyped side of the seam.
#:
#: **The second parameter is D1's repair** (M1-M4 QA). `invoke()` checked
#: `ctx.audience` and then discarded the caller before the handler ran, so a
#: handler serving two audiences through one registration could not tell them
#: apart: `spawn_session` wrote one origin for a person clicking the fleet page
#: and for the master alike, and D31's wake set — which selects on that origin —
#: was structurally empty in production.
#:
#: The alternative was letting a caller pass its own origin as an argument, and
#: it was rejected: that puts a security-relevant field in the hands of the
#: caller, which is the thing the audience check exists to prevent. `ctx` is
#: built by the consumer's entry point and never by the call.
#:
#: **`invoke()`'s own signature is unchanged**, so no file in `web/` or `cli/`
#: moves and Gate A (DP1, D38) survives — neither defines a handler.
Handler = Callable[[ToolArgs, "CallerContext"], object]


@dataclass(frozen=True)
class ToolDef:
    """One capability. A capability absent from the registry has no surface that
    can reach it — that is what makes principle 1 structural (D32)."""

    name: str
    description: str
    input_schema: Mapping[str, object]
    blast_class: BlastClass
    handler: Handler
    audiences: frozenset[Audience]


#: The audience a caller declared → what the record calls it, when the caller
#: said nothing more specific. Written out rather than derived from the value, so
#: a fourth `Audience` is a **failing** lookup here rather than a record that
#: invents a kind; `tests/toolsurface/test_audit.py::
#: test_a_worker_context_is_recorded_as_a_worker` enumerates `Audience` at test
#: time and proves the map is total over it.
_KIND_BY_AUDIENCE: Mapping[Audience, ActorKind] = {
    Audience.MASTER: ActorKind.MASTER,
    Audience.SESSION: ActorKind.SESSION,
    Audience.HUMAN: ActorKind.HUMAN,
}


def actor_kind_of(ctx: CallerContext) -> ActorKind:
    """What the record says was on the other end (DP2).

    The **field when it is set**, and the audience only otherwise. Deriving
    unconditionally is what made `ActorKind.WORKER` unreachable at revision 1:
    M5's queue worker arrives on the `MASTER` audience and is not a master, and a
    record that said so would be the same overclaim K23 is about, one row down.

    **One declaration, here** (§T6-4, closed in the QA-prep pass). `audit.py`
    declared it and `registry.py` said it a second time, because importing
    `audit` would drag `shepherd.logs` into `shepherd status` through `cli/`'s
    import of `registry` — and the shipped DP3 rule only checks *direct*
    importers, so it would have passed while defeating the rule. This module is
    stdlib-only, so both now import from here, and
    `tests/boundaries/test_one_definition_site.py::
    test_the_actor_kind_derivation_has_one_definition_site` is what keeps it at
    one.
    """
    if ctx.actor_kind is not None:
        return ctx.actor_kind
    return _KIND_BY_AUDIENCE[ctx.audience]


@dataclass(frozen=True)
class ToolResult:
    """The one shape every consumer receives, success or failure."""

    ok: bool
    data: object
    error: str | None
    failure: Failure | None = None
    """Why, as a value. `None` on success. The text in `error` stays generic;
    this is what a consumer branches on."""


@dataclass(frozen=True)
class AuthzOutcome:
    """What the gate decided about one call, as the injected `Authorizer`
    returns it. `approval_id` is `None` when no card was raised (DP2)."""

    allowed: bool
    approved_by: str | None
    approval_id: str | None
    reason: str | None


@dataclass(frozen=True)
class AuditRecord:
    """One decided call (ADR-M4-1, D25). Never an undecided one: an unknown tool
    name and a wrong audience are refused before there is anything to authorise,
    and auditing them would turn the log into a request log an agent can fill by
    guessing names."""

    at: str
    correlation_id: str
    actor_kind: ActorKind
    actor_id: str
    tool: str
    blast_class: BlastClass
    args: Mapping[str, object]
    autonomy_level: int
    decision: str
    approved_by: str | None
    approval_id: str | None
    result: str
    failure: Failure | None
    duration_ms: int


#: The two injection points, declared **here** rather than beside their
#: implementations. `registry.py` must be able to hold a gate and a sink without
#: importing the modules that build them — otherwise importing `registry`, which
#: `web/` and `cli/` both do, drags `shepherd.logs` in transitively and DP3's
#: rule is true in the letter it checks and false in the spirit it protects.
#: This module imports nothing but stdlib, so it is the only honest home.
Authorizer = Callable[[ToolDef, ToolArgs, CallerContext], AuthzOutcome]

AuditSink = Callable[[AuditRecord], None]


def arg_str(args: ToolArgs, key: str) -> str:
    """A required string argument. `invoke()` has already proved it is there."""
    value = args[key]
    if not isinstance(value, str):
        raise TypeError(f"argument {key!r} is not a string")
    return value


def arg_optional_str(args: ToolArgs, key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"argument {key!r} is not a string")
    return value


def arg_bool(args: ToolArgs, key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"argument {key!r} is not a boolean")
    return value
