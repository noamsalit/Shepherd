"""The fleet page's HTTP lane (T15, T16). A package so its `conftest` does not
shadow another test directory's top-level `conftest` module (prepend import
mode) — the same fix T12-1 applied to `tests/golden/`. Without it,
`pytest tests/web tests/toolsurface` fails at collection: whichever `conftest`
is imported first wins the name, and `from conftest import Client` then reaches
into the wrong directory's fixtures."""
