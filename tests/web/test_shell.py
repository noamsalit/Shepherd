"""The shell's stylesheet, read as bytes — the port of the dark prototype.

There is no browser on this host (D51, K8), so what a static scan can prove and
what it cannot is stated rather than implied. It proves the four properties a
reading pass kept getting wrong:

* **E15 / U18** — `[hidden] { display: none !important }` is present and is not
  a comment. Every page root sets `display` from a class (`.scroll`, `.herd`,
  `.panes2`), and an author class rule beats the browser's own `[hidden]`, so
  without this line every "hidden" page renders on top of the visible one. The
  prototype only looked right because its wrapper injected the same rule.
* **U16** — the chosen card treatment is the wash, unconditionally, not one of
  the six treatments the prototype kept side by side behind `data-style`.
* the eight `.bucket-*` rules are the *only* place a palette hex is spelled,
  and the prototype's `:root` names read back the same eight colours.
* no webfont: this server binds loopback, must work offline, and `web/server.py`
  serves `.html` / `.js` / `.css` and nothing else, so a font file could not be
  hosted even locally.

It proves no pixel. The live render is `tools/render_check.py`'s job, and
whether `index.html` uses these classes correctly is T5.3's.
"""

from __future__ import annotations

import re
from pathlib import Path

from shepherd.core.stops import PALETTE, Bucket

STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

#: The prototype's `:root` spelling for each bucket. These are aliases — the
#: hex lives in the `.bucket-*` rule `tests/web/test_palette.py` parses — and
#: this map is what keeps the two spellings from drifting apart silently.
ROOT_ALIASES = {
    Bucket.RUNNING: "--running",
    Bucket.NEEDS_YOU: "--needs-you",
    Bucket.FINISHED: "--finished",
    Bucket.UNFINISHED: "--unfinished",
    Bucket.BLOCKED: "--blocked",
    Bucket.PAUSED: "--paused",
    Bucket.ERROR: "--error",
    Bucket.UNCLASSIFIED: "--unclassified",
}


def css() -> str:
    return (STATIC_ROOT / "app.css").read_text(encoding="utf-8")


def css_without_comments() -> str:
    """A rule inside `/* … */` is documentation, not a rule."""
    return _COMMENT.sub("", css())


def test_app_css_carries_the_hidden_reset() -> None:
    """E15 / U18 — the one line whose absence puts every page on screen."""
    rule = re.search(r"\[hidden\]\s*\{([^}]*)\}", css_without_comments())
    assert rule is not None, "[hidden] reset missing from app.css"
    body = rule.group(1)
    assert re.search(r"display:\s*none\s*!important", body), body


def test_the_card_takes_a_wash_of_its_bucket_colour() -> None:
    """U16 — chosen by building six treatments, not by describing them.

    The prototype kept all six alive behind `.cards[data-style="…"]`. Only the
    winner ports, and it ports unconditionally: a card that needs an attribute
    set on its container to be coloured is a treatment still being compared.
    """
    source = css_without_comments()
    assert "data-style=" not in source, "the treatment comparison scaffold ported"

    rule = re.search(r"\n\.card\s*\{([^}]*)\}", source)
    assert rule is not None, ".card rule missing"
    background = re.search(
        r"background:\s*color-mix\(in srgb,\s*var\(--b\)\s*16%,\s*var\(--ink-850\)\)",
        rule.group(1),
    )
    assert background is not None, rule.group(1)


def test_every_bucket_rule_aliases_the_shared_colour_variable() -> None:
    """`--bucket-colour` is the contract; `--b` is what the design's rules read.

    One hex per bucket, in the block `test_palette.py` parses, aliased rather
    than spelled twice — a second literal is how a palette drifts (T14).
    """
    source = css_without_comments()
    for bucket in Bucket:
        rule = re.search(rf"\.bucket-{bucket.value}\s*\{{([^}}]*)\}}", source)
        assert rule is not None, bucket.value
        body = rule.group(1)
        assert PALETTE[bucket].colour.upper() in body.upper(), bucket.value
        assert "--b: var(--bucket-colour)" in body, bucket.value


def test_the_root_palette_aliases_match_core_stops() -> None:
    """The prototype's `:root` names carry the same eight colours."""
    root = re.search(r":root\s*\{(.*?)\n\}", css_without_comments(), re.DOTALL)
    assert root is not None, ":root token block missing"
    body = root.group(1)
    for bucket, name in ROOT_ALIASES.items():
        found = re.search(rf"{name}:\s*(#[0-9A-Fa-f]{{6}})", body)
        assert found is not None, name
        assert found.group(1).upper() == PALETTE[bucket].colour.upper(), name


def test_the_stylesheet_ships_no_webfont() -> None:
    """D51/K8: loopback-only, offline, and `server.py` serves no font type.

    `image-set()` is in the list because it is the sixth shape and the one the
    other five miss: it takes a **bare string** URL (`image-set("f.woff2" 1x)`)
    with no `url()` token at all, so every other entry here reads clean while
    the page still reaches off-host for bytes.
    """
    source = css()
    for shape in (
        "@import",
        "@font-face",
        "fonts.googleapis",
        "fonts.gstatic",
        "url(",
        "image-set(",
    ):
        assert shape not in source, shape
    root = re.search(r":root\s*\{(.*?)\n\}", css_without_comments(), re.DOTALL)
    assert root is not None
    stack = re.search(r"--font:\s*([^;]+);", root.group(1))
    assert stack is not None
    assert stack.group(1).strip().startswith("ui-sans-serif"), stack.group(1)


def rule_body(selector: str) -> str:
    """The declaration block of the rule whose selector is exactly `selector`.

    Anchored on a line start, so `.prose` does not match `.prose + .prose` and
    `.legend-key` does not match `.legend-key:hover`.
    """
    match = re.search(
        rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}",
        css_without_comments(),
        re.MULTILINE,
    )
    assert match is not None, selector
    return match.group(1)


# --------------------------------------------------------------------------
# The palette contract, over every notation the value can take
# --------------------------------------------------------------------------
#
# T5.2's review found twelve palette colours re-spelled as `rgba()` triples:
# `--needs-you` #F59E0B ten times, `--finished` #10B981 twice. The rules above
# read hexes, so retuning `core.stops.PALETTE` would have reddened the two
# *hex* spellings, those would have been fixed, the suite would have gone
# green -- and ten amber tints on the nav badge, the approval card, the
# decision card, the choice list and the confirm dialog would still have been
# the old colour. A contract reporting success while the property it protects
# is broken.
#
# This is the third recorded instance in this repo of a rule keyed on one exact
# spelling passing on the idiomatic spelling of the same violation. The first
# two were boundary scans; this one is a UI contract, which says the shape
# belongs to *scans*, not to any one subsystem.
#
# So the guard enumerates the notations rather than one of them:
#
#   `#RRGGBB`  -- counted, exactly twice each (the `:root` alias and the
#                 `.bucket-*` block), so a third literal anywhere is a failure
#   `#RGB`     -- expanded and compared
#   `rgb()` / `rgba()` -- decomposed, comma **and** space-separated forms,
#                 integer and percentage channels
#   `color()`  -- refused outright: nothing here needs one, and a notation this
#                 guard cannot decompose is a notation it cannot certify
#
# The violet and blue triples (`--violet-soft`, `--blue-soft`, the focus
# borders) are **not** palette colours and are deliberately left alone.

_SHORT_HEX = re.compile(r"#([0-9A-Fa-f])([0-9A-Fa-f])([0-9A-Fa-f])\b")
_RGB_CALL = re.compile(r"\brgba?\(([^)]*)\)", re.IGNORECASE)
_COLOR_CALL = re.compile(r"(?<![-\w])color\(", re.IGNORECASE)

PALETTE_RGB = {
    tuple(int(entry.colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)): bucket.value
    for bucket, entry in PALETTE.items()
}


def _channel(token: str) -> int | None:
    """One `rgb()` channel as 0-255, or `None` when it is not a plain number."""
    token = token.strip()
    try:
        if token.endswith("%"):
            return round(float(token[:-1]) * 255 / 100)
        return round(float(token))
    except ValueError:
        return None


def rgb_literals(source: str) -> list[tuple[str, tuple[int, int, int]]]:
    """Every `rgb()`/`rgba()` call, decomposed to a 0-255 triple.

    Both CSS syntaxes: `rgb(245, 158, 11)` and `rgb(245 158 11 / 16%)`. A call
    whose channels are not plain numbers (a `var()`, a nested function) is
    skipped -- it carries no literal to compare.
    """
    found: list[tuple[str, tuple[int, int, int]]] = []
    for match in _RGB_CALL.finditer(source):
        args = match.group(1).replace("/", " ").replace(",", " ").split()
        channels = [_channel(token) for token in args[:3]]
        if len(channels) == 3 and all(value is not None for value in channels):
            first, second, third = channels
            assert first is not None and second is not None and third is not None
            found.append((match.group(0), (first, second, third)))
    return found


def test_no_rgb_literal_respells_a_palette_colour() -> None:
    """`rgba(245, 158, 11, .16)` is `--needs-you`, and the hex rules are blind to it."""
    offenders = [
        (text, PALETTE_RGB[triple])
        for text, triple in rgb_literals(css_without_comments())
        if triple in PALETTE_RGB
    ]
    assert not offenders, offenders


def test_no_short_hex_respells_a_palette_colour() -> None:
    """A three-digit hex is a third spelling of the same colour, and expands to one."""
    offenders = [
        match.group(0)
        for match in _SHORT_HEX.finditer(css_without_comments())
        if tuple(int(channel * 2, 16) for channel in match.groups()) in PALETTE_RGB
    ]
    assert not offenders, offenders


def test_the_stylesheet_uses_no_colour_function_this_guard_cannot_read() -> None:
    """`color(srgb 0.96 0.62 0.04)` is the same amber in a fourth notation.

    `color-mix()` is not matched: the lookbehind rejects a preceding `-`.
    """
    assert not _COLOR_CALL.search(css_without_comments()), "color() literal found"


def test_each_palette_hex_is_spelled_exactly_twice() -> None:
    """The `:root` alias and the `.bucket-*` block. A third site is the drift."""
    source = css_without_comments().upper()
    for bucket in Bucket:
        hexadecimal = PALETTE[bucket].colour.upper()
        assert source.count(hexadecimal) == 2, (bucket.value, source.count(hexadecimal))


# --------------------------------------------------------------------------
# Contrast: the three rules that paint a bucket colour as *text*
# --------------------------------------------------------------------------
#
# Measured against this file's own `--ink-*` values, the raw palette fails AA
# for small text in seven places: `blocked` on all three grounds, `unfinished`
# on two, and `running` and `error` on the tooltip. All three rules below set
# `text-transform: uppercase` at well under 18.66px, so the 4.5:1 small-text
# threshold is the one that applies -- raising the type to 0.72-0.82rem helps a
# phone reader but does **not** move the threshold, because WCAG's "large" is
# 18.66px bold, not 14px bold.
#
# So the colour moves, in one derivation rather than eight literals: each
# `.bucket-*` block mixes its own pinned hex toward `--text`. The mix
# percentage is read back out of the stylesheet here rather than assumed, and
# the ratio is computed from the WCAG formula against the palette in
# `core.stops` -- neither number is recomputed the way the CSS computes it.
#
# Lightening the **grounds** instead was available and is refused: `--ink-850`
# is the second operand of the card wash, so moving it moves U16.

#: rule -> the `:root` ground it is painted on. Each is the `background` of the
#: element's own container: `.legend`, `.tip`, and `dialog` respectively.
BUCKET_TEXT_ON = {
    ".legend-key": "--ink-850",
    ".tip-who": "--ink-700",
    ".sheet-acts": "--ink-800",
}

#: WCAG 2.1 SC 1.4.3, small text.
AA_SMALL = 4.5


def root_hex(name: str) -> str:
    root = re.search(r":root\s*\{(.*?)\n\}", css_without_comments(), re.DOTALL)
    assert root is not None
    found = re.search(rf"{name}:\s*(#[0-9A-Fa-f]{{6}})", root.group(1))
    assert found is not None, name
    return found.group(1)


def _srgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _relative_luminance(colour: tuple[int, int, int]) -> float:
    channels = []
    for raw in colour:
        component = raw / 255.0
        channels.append(
            component / 12.92
            if component <= 0.03928
            else ((component + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def mix_srgb(
    first: tuple[int, int, int], second: tuple[int, int, int], weight: float
) -> tuple[int, int, int]:
    """`color-mix(in srgb, first weight%, second)` -- a gamma-encoded lerp.

    CSS Color 4's `srgb` space is the gamma-encoded one (`srgb-linear` is the
    other), so the channels interpolate as written.
    """
    return (
        round(first[0] * weight + second[0] * (1 - weight)),
        round(first[1] * weight + second[1] * (1 - weight)),
        round(first[2] * weight + second[2] * (1 - weight)),
    )


def bucket_text_colour(bucket: Bucket) -> tuple[int, int, int]:
    """What `--b-text` computes to inside `.bucket-<name>`, read from the CSS."""
    rule = re.search(
        rf"\.bucket-{bucket.value}\s*\{{([^}}]*)\}}", css_without_comments()
    )
    assert rule is not None, bucket.value
    declared = re.search(
        r"--b-text:\s*color-mix\(in srgb,\s*var\(--bucket-colour\)\s*(\d+)%,"
        r"\s*var\(--text\)\)",
        rule.group(1),
    )
    assert declared is not None, rule.group(1)
    return mix_srgb(
        _srgb(PALETTE[bucket].colour), _srgb(root_hex("--text")), int(declared.group(1)) / 100
    )


def test_every_bucket_rule_derives_its_text_colour_from_its_own_hex() -> None:
    """One derivation per bucket, off the pinned literal -- not a second literal.

    The review's own warning: a per-bucket text colour spelled as its own hex
    would be exactly the drift the notation guard above exists to catch, in a
    new place. So `--b-text` may only be a `color-mix()` of `--bucket-colour`.
    """
    source = css_without_comments()
    for bucket in Bucket:
        rule = re.search(rf"\.bucket-{bucket.value}\s*\{{([^}}]*)\}}", source)
        assert rule is not None, bucket.value
        assert "--b-text: color-mix(in srgb, var(--bucket-colour)" in rule.group(1), (
            bucket.value,
            rule.group(1),
        )


def test_bucket_coloured_text_clears_aa_on_the_ground_it_is_painted_on() -> None:
    """Seven failures measured before this; the threshold is WCAG's, not ours."""
    failures = []
    for selector, ground in BUCKET_TEXT_ON.items():
        assert "var(--b-text)" in rule_body(selector), selector
        background = _srgb(root_hex(ground))
        for bucket in Bucket:
            ratio = contrast(bucket_text_colour(bucket), background)
            if ratio < AA_SMALL:
                failures.append((selector, ground, bucket.value, round(ratio, 2)))
    assert not failures, failures


# --------------------------------------------------------------------------
# Overflow: two places long real data escapes a 390px viewport
# --------------------------------------------------------------------------
#
# The live render check asserts no **document** overflow, so a pane scrolling
# inside itself is invisible to it, and the harness's strings were short enough
# that nothing overflowed anyway. Both holes are closed -- the harness carries
# a real repo path and a 400-character prompt with an unbroken token -- and
# these two static rules pin the idiom the author applied in six other places
# and missed in these.

def test_verbatim_prose_wraps_an_unbroken_token() -> None:
    """`.scroll` is `overflow-y: auto`, which computes `overflow-x` to `auto`.

    So one unbroken token in an engine prompt -- a URL, a long path, a base64
    blob -- makes the conversation pane scroll sideways. `.decision-body` next
    door already has `word-break: break-word`; these two had nothing.
    """
    for selector in (".bubble", ".prose"):
        assert "overflow-wrap: anywhere" in rule_body(selector), selector


def test_the_topbar_title_cannot_push_the_document_sideways() -> None:
    """A flex child without `min-width: 0` keeps its intrinsic floor.

    `.detail-title` and `.card-title` do this correctly; the topbar's two text
    children did not, and theirs is *document*-level horizontal scroll.
    """
    for selector in (".topbar h1", ".topbar-sub"):
        body = rule_body(selector)
        assert "min-width: 0" in body, selector
        assert "text-overflow: ellipsis" in body, selector
