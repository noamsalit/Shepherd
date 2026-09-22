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
    """D51/K8: loopback-only, offline, and `server.py` serves no font type."""
    source = css()
    for shape in ("@import", "@font-face", "fonts.googleapis", "fonts.gstatic", "url("):
        assert shape not in source, shape
    root = re.search(r":root\s*\{(.*?)\n\}", css_without_comments(), re.DOTALL)
    assert root is not None
    stack = re.search(r"--font:\s*([^;]+);", root.group(1))
    assert stack is not None
    assert stack.group(1).strip().startswith("ui-sans-serif"), stack.group(1)
