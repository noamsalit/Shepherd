"""D51/K8: the page runs from the package, with no node and no bundler.

There is no `node`, `npm` or `tsc` on this host. A build artifact appearing in
`web/static/` would mean the page can no longer be served by the thing that
serves it, so the absence is asserted rather than assumed — and so is §12's
"no polling anywhere in the UI", which is a property of the shipped JS.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web"
STATIC_ROOT = WEB_ROOT / "static"

BUILD_ARTIFACTS = (
    "package.json",
    "package-lock.json",
    "node_modules",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.js",
    "rollup.config.js",
)

BUILD_SUFFIXES = (".ts", ".tsx", ".jsx", ".map", ".scss", ".lock")

_SCRIPT_SRC = re.compile(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']")
_LINK_HREF = re.compile(r"<link[^>]*\bhref=[\"']([^\"']+)[\"']")
_BARE_IMPORT = re.compile(r"""(?:^|\s)(?:import|export)[^;\n]*?from\s+[\"']([^\"']+)[\"']""")

REMOTE_PREFIXES = ("http://", "https://", "//")

#: §12: the stream is the liveness path. A timer that re-asks is a poll.
POLLING_SHAPES = ("setInterval", "requestAnimationFrame")


def js_files() -> list[Path]:
    return sorted(STATIC_ROOT.glob("*.js"))


def test_no_build_step_artifacts() -> None:
    present = [
        str(path.relative_to(WEB_ROOT))
        for path in WEB_ROOT.rglob("*")
        if path.name in BUILD_ARTIFACTS or path.suffix in BUILD_SUFFIXES
    ]
    assert present == []
    assert (STATIC_ROOT / "index.html").is_file()


def test_no_remote_script_sources() -> None:
    """Every asset is local: a CDN import is a runtime dependency (D51)."""
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    sources = _SCRIPT_SRC.findall(markup) + _LINK_HREF.findall(markup)
    assert sources != []
    for source in sources:
        assert not source.startswith(REMOTE_PREFIXES), source
        assert source.startswith("/static/"), source
        assert (STATIC_ROOT / source[len("/static/") :]).is_file(), source

    for path in js_files():
        for target in _BARE_IMPORT.findall(path.read_text(encoding="utf-8")):
            assert not target.startswith(REMOTE_PREFIXES), f"{path.name} -> {target}"
            assert target.startswith("./"), f"{path.name} -> {target}"


def test_the_page_is_plain_es_modules() -> None:
    markup = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in markup


def test_no_polling_in_the_ui() -> None:
    """§12: "No polling anywhere in the UI" — a hard requirement (T15/T16)."""
    offenders: list[str] = []
    for path in js_files():
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.name} uses {shape}" for shape in POLLING_SHAPES if shape in source
        )
    assert offenders == []
    joined = "".join(path.read_text(encoding="utf-8") for path in js_files())
    assert "new EventSource" in joined
