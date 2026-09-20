"""Taint analysis for the two field-level boundary rules (r6).

Split out of `_imports.py` to keep both files inside principle 6's ~600-line
budget. Nothing here imports the modules under test.

Both rules this module serves were written at r5 as *syntactic forms* and a
one-line idiom defeated each: `signal.fields.get("tool_input")` is not a
Subscript, and `rk = signal.raw_kind; rk == "Stop"` puts a Name where the rule
looked for an Attribute. A rule about a value has to follow the value.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from _parse import parsed


def _name_targets(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _name_targets(element)]
    return []


def _tainted_locals(tree: ast.Module, attr: str) -> frozenset[str]:
    """Local names holding `<expr>.<attr>`, to a fixpoint (r6 alias tainting).

    `f = signal.fields` taints `f`; `a, b = signal.fields, other` taints `a`;
    `g = f` taints `g`. Without this the whole rule is one assignment wide.
    """
    tainted: set[str] = set()
    for _ in range(4):  # a fixpoint; nesting deeper than this is not idiomatic
        before = set(tainted)

        def is_tainted(node: ast.expr) -> bool:
            if isinstance(node, ast.Attribute) and node.attr == attr:
                return True
            return isinstance(node, ast.Name) and node.id in tainted

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    for target in node.targets:
                        if isinstance(target, (ast.Tuple, ast.List)) and len(target.elts) == len(
                            node.value.elts
                        ):
                            for slot, value in zip(target.elts, node.value.elts):
                                if is_tainted(value):
                                    tainted.update(_name_targets(slot))
                            continue
                        if is_tainted(node.value):
                            tainted.update(_name_targets(target))
                else:
                    for target in node.targets:
                        if is_tainted(node.value):
                            tainted.update(_name_targets(target))
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                if is_tainted(node.value):
                    tainted.update(_name_targets(node.target))
            elif isinstance(node, ast.NamedExpr):
                if is_tainted(node.value):
                    tainted.update(_name_targets(node.target))
        if tainted == before:
            break
    return frozenset(tainted)


def _taint_test(tree: ast.Module, attr: str) -> Callable[[ast.expr | None], bool]:
    tainted = _tainted_locals(tree, attr)

    def is_tainted(node: ast.expr | None) -> bool:
        if isinstance(node, ast.Attribute) and node.attr == attr:
            return True
        return isinstance(node, ast.Name) and node.id in tainted

    return is_tainted


_WHOLE_MAPPING_METHODS = frozenset({"keys", "items", "values"})
_KEYED_METHODS = frozenset({"get", "pop", "setdefault"})


def mapping_read_keys(path: Path, attr: str) -> frozenset[str | None]:
    """Every key by which `<expr>.<attr>` is read, following local aliases (r6).

    Covers subscript, `.get`/`.pop`/`.setdefault`, `in`/`not in`, `**` unpacking,
    `.keys()`/`.items()`/`.values()`, iteration, and passing the mapping to a
    call. `None` marks a read whose key is not a string literal — a computed key,
    or a whole-mapping escape that leaks every key at once — and is **always** a
    failure: fail closed, because a key a test cannot see is a key a test cannot
    check. If a dynamic key is ever genuinely needed it arrives as a named plan
    change, not as a silent hole.

    Revision 5 read only literal `[...]` subscripts, which is near-vacuous:
    `Signal.fields` is a `Mapping` whose every key is per-payload optional, so
    `[...]` raises `KeyError` and `.get(...)` is the idiom the rule table will
    actually be written in.
    """
    tree = parsed(path)
    is_tainted = _taint_test(tree, attr)
    keys: set[str | None] = set()

    def literal_or_none(node: ast.expr | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and is_tainted(node.value):
            keys.add(literal_or_none(node.slice))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and is_tainted(func.value):
                if func.attr in _KEYED_METHODS:
                    keys.add(literal_or_none(node.args[0]) if node.args else None)
                elif func.attr in _WHOLE_MAPPING_METHODS:
                    keys.add(None)
                else:
                    keys.add(None)
            if any(is_tainted(argument) for argument in node.args):
                keys.add(None)  # the whole mapping escapes into a callee
            if any(is_tainted(keyword.value) for keyword in node.keywords):
                keys.add(None)
        elif isinstance(node, ast.Compare):
            if any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) and any(
                is_tainted(operand) for operand in node.comparators
            ):
                keys.add(literal_or_none(node.left))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is None and is_tainted(value):
                    keys.add(None)  # {**mapping}
        elif isinstance(node, (ast.For, ast.AsyncFor)) and is_tainted(node.iter):
            keys.add(None)
        elif isinstance(node, ast.comprehension) and is_tainted(node.iter):
            keys.add(None)
    return frozenset(keys)


def tainted_attribute_uses(path: Path, attr: str) -> frozenset[str]:
    """How `<expr>.<attr>` is used once bound to a local (r6).

    `"compare" | "match" | "method:<name>" | "contains" | "index" |
    "passthrough"`. Everything but `passthrough` is control flow by some route:
    a string method on an engine event name is branching, and `RULES[raw_kind]`
    is dispatch.
    """
    tree = parsed(path)
    is_tainted = _taint_test(tree, attr)
    uses: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(is_tainted(operand) for operand in operands):
                membership = any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
                uses.add("contains" if membership else "compare")
        elif isinstance(node, ast.Match) and is_tainted(node.subject):
            uses.add("match")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and is_tainted(func.value):
                uses.add(f"method:{func.attr}")
        elif isinstance(node, ast.Subscript) and is_tainted(node.slice):
            uses.add("index")
        elif isinstance(node, ast.Attribute) and node.attr == attr:
            uses.add("passthrough")
        elif isinstance(node, ast.Name) and is_tainted(node):
            uses.add("passthrough")
    return frozenset(uses)
