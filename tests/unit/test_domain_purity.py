"""Enforce the domain import allowlist and ban impure names and builtins."""

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

ALLOWED_STDLIB = {
    "__future__",
    "abc",
    "collections",
    "collections.abc",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "itertools",
    "re",
    "types",
    "typing",
}
FORBIDDEN_NAMES = {
    "now",
    "utcnow",
    "today",
    "uuid4",
    "getenv",
    "environ",
    "getcontext",
    "setcontext",
    "localcontext",
    "lru_cache",
    "cache",
}
FORBIDDEN_BUILTINS = {
    "open",
    "print",
    "input",
    "__import__",
    "eval",
    "exec",
    "compile",
    "breakpoint",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "hash",
    "id",
}
DOMAIN_PACKAGE = "actraforge.domain"
DOMAIN_DIR = Path(__file__).resolve().parents[2] / "src" / "actraforge" / "domain"


def _imported_modules(node: ast.Import | ast.ImportFrom, package: str) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    module = resolve_name("." * node.level + (node.module or ""), package)
    if module == "actraforge":
        return [f"{module}.{alias.name}" for alias in node.names]
    return [module]


def _purity_violations(source: str, package: str = DOMAIN_PACKAGE) -> list[str]:
    violations = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in _imported_modules(node, package):
                if (
                    module not in ALLOWED_STDLIB
                    and module != DOMAIN_PACKAGE
                    and not module.startswith(f"{DOMAIN_PACKAGE}.")
                ):
                    violations.append(f"line {node.lineno}: forbidden import {module}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                violations.append(f"line {node.lineno}: forbidden dunder attribute {node.attr}")
            elif isinstance(node.value, ast.Name) and node.value.id == "builtins":
                violations.append(f"line {node.lineno}: forbidden attribute builtins.{node.attr}")
            elif node.attr in FORBIDDEN_NAMES:
                violations.append(f"line {node.lineno}: forbidden attribute {node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_BUILTINS:
                violations.append(f"line {node.lineno}: forbidden builtin {node.id}")
            elif node.id in FORBIDDEN_NAMES:
                violations.append(f"line {node.lineno}: forbidden name {node.id}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "astimezone"
            and not node.args
            and not node.keywords
        ):
            violations.append(f"line {node.lineno}: forbidden astimezone without tz")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            violations.append(f"line {node.lineno}: forbidden global statement")
    return violations


def test_domain_modules_remain_pure() -> None:
    paths = sorted(DOMAIN_DIR.rglob("*.py"))
    assert paths, f"No domain modules found under {DOMAIN_DIR}"
    violations: list[str] = []
    for path in paths:
        package = ".".join((DOMAIN_PACKAGE, *path.parent.relative_to(DOMAIN_DIR).parts))
        violations.extend(
            f"{path.relative_to(DOMAIN_DIR)}:{violation}"
            for violation in _purity_violations(path.read_text(encoding="utf-8"), package)
        )
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    ("source", "violation"),
    [
        ("import os", "forbidden import os"),
        ("import enum.zzz", "forbidden import enum.zzz"),
        ("from .. import infrastructure", "forbidden import actraforge.infrastructure"),
        (
            "from actraforge.domain_extra import recovery",
            "forbidden import actraforge.domain_extra",
        ),
        ("datetime.now()", "forbidden attribute now"),
        ("getenv('HOME')", "forbidden name getenv"),
        ("open('x')", "forbidden builtin open"),
        ("reader = open", "forbidden builtin open"),
        ("print(1)", "forbidden builtin print"),
        ("input()", "forbidden builtin input"),
        ("__import__('os')", "forbidden builtin __import__"),
        ("eval('x')", "forbidden builtin eval"),
        ("exec('x')", "forbidden builtin exec"),
        ("compile('x', '<string>', 'eval')", "forbidden builtin compile"),
        ("breakpoint()", "forbidden builtin breakpoint"),
        ("globals()", "forbidden builtin globals"),
        ("locals()", "forbidden builtin locals"),
        ("vars()", "forbidden builtin vars"),
        ("import builtins", "forbidden import builtins"),
        ("builtins.len", "forbidden attribute builtins.len"),
        ("getattr(x, 'field')", "forbidden builtin getattr"),
        ("setattr(x, 'field', 1)", "forbidden builtin setattr"),
        ("delattr(x, 'field')", "forbidden builtin delattr"),
        ("hash(x)", "forbidden builtin hash"),
        ("id(x)", "forbidden builtin id"),
        ("object.__subclasses__()", "forbidden dunder attribute __subclasses__"),
        ("x.__class__", "forbidden dunder attribute __class__"),
        ("decimal.getcontext()", "forbidden attribute getcontext"),
        ("setcontext(value)", "forbidden name setcontext"),
        ("localcontext()", "forbidden name localcontext"),
        ("functools.lru_cache", "forbidden attribute lru_cache"),
        ("cache(function)", "forbidden name cache"),
        ("x.astimezone()", "forbidden astimezone without tz"),
        ("global value", "forbidden global statement"),
        ("nonlocal value", "forbidden global statement"),
    ],
)
def test_purity_checker_rejects_forbidden_source(source: str, violation: str) -> None:
    assert _purity_violations(source) == [f"line 1: {violation}"]


@pytest.mark.parametrize(
    "source",
    [
        "from .recovery import RecoveryContext\nfrom .. import domain",
        "import collections.abc",
        "x.astimezone(tz)",
        "x.astimezone(tz=tz)",
    ],
)
def test_purity_checker_accepts_pure_source(source: str) -> None:
    assert _purity_violations(source) == []
