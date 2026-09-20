"""The `shepherd` command's lane (T17). A package for the same reason
`tests/golden/` is one (T12-1): two sibling test directories cannot both own
the top-level module name `conftest`, and `pytest tests/cli tests/signals`
fails at collection when they try."""
