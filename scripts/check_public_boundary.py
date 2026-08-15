#!/usr/bin/env python3
"""Boundary guard for this public repository.

Everything here is published — to GitHub and to PyPI. This script fails
(exit 1) if a change would carry something across that line which should not
cross it. It runs in CI on every push and pull request.

It exists because of an asymmetry: the maintainers know which names belong to
the private platform, and contributors have no way to know. A pull request can
mention a private module in a docstring or a doc page in complete good faith.
Review catches that only if a reviewer happens to recognise the name. This does
not depend on anyone recognising anything.

Checks, over the whole repository:
  1. Imports — every import under a package's src/ must resolve to stdlib,
     `visvoai.*`, a relative import, or a dependency DECLARED in that package's
     pyproject.toml. Anything else is either a leak of private code or, more
     commonly, a dependency that works locally and breaks for whoever installs
     the wheel.
  2. No symlinks — they can point outside the tree and travel unnoticed.
  3. No secret-bearing file types (.env, .pem, .key, credentials, …).
  4. No private path/name tokens in shipped text (backend/, VisvoRuntime, …).

Rule 1 was originally about keeping private source out of a subtree that was
mirrored here. That mirror is gone and this repo is now the source of truth, so
the rule survives for its second purpose: an undeclared import is a real bug for
users, whoever wrote it.

Run: python scripts/check_public_boundary.py
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKGS = ROOT  # the whole repository is public

# Names that are always allowed as a top-level import inside a public package.
_ALWAYS_OK = set(sys.stdlib_module_names) | {"visvoai"}

# Dist name → top-level import module(s), for packages whose import name isn't just
# the dist name with hyphens swapped for underscores. google-genai is a PEP-420
# namespace package: the dist is `google-genai` but it imports as `google.genai`.
_DIST_MODULE_ALIASES = {
    "google-genai": ["google"],
    "python-dotenv": ["dotenv"],
}

# Files we will never allow under packages/ (extension or name match).
_FORBIDDEN_FILE_RE = re.compile(
    r"(^|/)(\.env(\.|$)|.*\.(pem|key|p12|pfx)$|.*secret.*|.*credential.*|id_rsa)",
    re.IGNORECASE,
)

# Private tokens that must never appear in shipped text (code, docstrings, docs).
_PRIVATE_TOKEN_RE = re.compile(
    r"\b(VisvoRuntime|BackendContext|HistoryManager(?:LLM)?Persistence)\b"
    r"|(^|[^\w/])backend/"            # backend/ as a path
    r"|/app/backend",
)

_TEXT_SUFFIXES = {".py", ".md", ".toml", ".cfg", ".txt", ".rst"}

# Vendored / build / VCS dirs that are never authored package source. The wheel ships
# only src/; these hold installed deps and build artifacts, so scanning them produces
# false positives (e.g. a dependency's credentials.py). Pruning them is a correctness
# fix, not a relaxation of the boundary rules — authored source is still fully checked.
_PRUNE_DIRS = {".venv", "venv", "site-packages", "node_modules", "__pycache__",
               ".git", ".mypy_cache", ".pytest_cache", "build", "dist"}


def _walk(root: Path):
    """Yield files under `root`, skipping vendored/build dirs (see _PRUNE_DIRS)."""
    for p in root.rglob("*"):
        if any(part in _PRUNE_DIRS or part.endswith(".egg-info") for part in p.parts):
            continue
        yield p


def _dep_dist_names(pyproject: Path) -> tuple[str, list[str]]:
    """Return (this package's dist name, its declared dependency dist names)."""
    data = tomllib.loads(pyproject.read_text())
    proj = data.get("project", {})
    specs: list[str] = list(proj.get("dependencies", []))
    for group in (proj.get("optional-dependencies", {}) or {}).values():
        specs.extend(group)
    deps: list[str] = []
    for spec in specs:
        # strip extras and version specifiers: "visvoai-ai[gemini]>=0.1" -> "visvoai-ai"
        name = re.split(r"[<>=!~\[ ;]", spec.strip(), maxsplit=1)[0]
        if name:
            deps.append(name)
    return proj.get("name", pyproject.parent.name), deps


def _allowed_modules(dist: str, dep_graph: dict[str, list[str]], _seen: set[str] | None = None) -> set[str]:
    """Top-level import names a package may use — its deps plus, transitively, the
    deps of any sibling visvoai-* package it depends on (those resolve at runtime)."""
    _seen = _seen or set()
    if dist in _seen:
        return set()
    _seen.add(dist)
    names: set[str] = set()
    for dep in dep_graph.get(dist, []):
        if dep.startswith("visvoai"):
            names.add("visvoai")
            names |= _allowed_modules(dep, dep_graph, _seen)  # transitive
        elif dep in _DIST_MODULE_ALIASES:
            names.update(_DIST_MODULE_ALIASES[dep])
        else:
            names.add(dep.replace("-", "_"))
    return names


def _check_imports(pkg_dir: Path, allowed: set[str], errors: list[str]) -> None:
    src = pkg_dir / "src"
    if not src.is_dir():
        return
    ok = _ALWAYS_OK | allowed
    for py in _walk(src):
        if py.suffix != ".py":
            continue
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError as e:
            errors.append(f"{py.relative_to(ROOT)}: syntax error ({e})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in ok:
                        errors.append(
                            f"{py.relative_to(ROOT)}:{node.lineno}: "
                            f"forbidden import '{alias.name}' "
                            f"(not stdlib / visvoai / declared dep)"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative import — fine
                top = (node.module or "").split(".")[0]
                if top and top not in ok:
                    errors.append(
                        f"{py.relative_to(ROOT)}:{node.lineno}: "
                        f"forbidden import 'from {node.module}' "
                        f"(not stdlib / visvoai / declared dep)"
                    )


def main() -> int:

    errors: list[str] = []

    # 2. symlinks
    for p in _walk(PKGS):
        if p.is_symlink():
            errors.append(f"{p.relative_to(ROOT)}: symlink not allowed in a published repo")

    # 3. forbidden file types
    for p in _walk(PKGS):
        if p.is_file() and _FORBIDDEN_FILE_RE.search(str(p.relative_to(ROOT))):
            errors.append(f"{p.relative_to(ROOT)}: private/secret file type not allowed")

    # 1. imports (per package, against its declared deps + transitive visvoai siblings)
    pyprojects = list(PKGS.glob("*/pyproject.toml"))
    dep_graph: dict[str, list[str]] = {}
    dist_to_dir: dict[str, Path] = {}
    for pp in pyprojects:
        dist, deps = _dep_dist_names(pp)
        dep_graph[dist] = deps
        dist_to_dir[dist] = pp.parent
    for dist, pkg_dir in dist_to_dir.items():
        _check_imports(pkg_dir, _allowed_modules(dist, dep_graph), errors)

    # 4. private tokens in shipped text
    self_path = Path(__file__).resolve()
    for p in _walk(PKGS):
        if not (p.is_file() and p.suffix in _TEXT_SUFFIXES):
            continue
        # This file defines the patterns, so it necessarily contains them.
        if p.resolve() == self_path:
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if _PRIVATE_TOKEN_RE.search(line):
                errors.append(
                    f"{p.relative_to(ROOT)}:{i}: private token leaked into public text "
                    f"→ {line.strip()[:80]}"
                )

    if errors:
        print("✗ boundary violations — this repository is public:\n")
        for e in errors:
            print(f"  {e}")
        print(
            f"\n{len(errors)} violation(s). Public packages must not import private "
            "platform code, carry secrets, or name private internals."
        )
        return 1

    print("✓ boundary clean — no private leakage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
