#!/usr/bin/env python3
"""Dependency-free source checks; never imports application code or opens services."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    "README.md", "README.zh-CN.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md",
    "THIRD_PARTY_NOTICES.md", "docs/README.md", "docs/getting-started.md",
    "docs/current-architecture.md", "docs/portfolio-walkthrough.md", "docs/quality-roadmap.md",
)
RUNTIME = "services/agent-workflow-runtime/src/"
FORBIDDEN = ("a2flow_bside", "a2flow_content")
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


def check() -> int:
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    errors: list[str] = []
    python_count = 0
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_bytes(), filename=name)
        except (SyntaxError, UnicodeError) as error:
            errors.append(f"{name}: {error}")
            continue
        python_count += 1
        if name.startswith(RUNTIME):
            for node in ast.walk(tree):
                modules = ([part.name for part in node.names] if isinstance(node, ast.Import)
                           else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for module in modules:
                    if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN):
                        errors.append(f"{name}:{node.lineno}: Runtime imports product domain {module}")
    link_count = 0
    for name in DOCS:
        path = ROOT / name
        if not path.is_file():
            errors.append(f"missing contributor entry: {name}")
            continue
        for match in LINK.finditer(path.read_text()):
            raw = match.group(1).strip()
            target = raw[1:raw.index(">") ] if raw.startswith("<") and ">" in raw else raw.split()[0]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                errors.append(f"{name}: missing or out-of-repository link {target}")
            link_count += 1
    for directory in ("apps/digital-employee/web", "services/management-java/frontend"):
        for filename in ("package.json", "package-lock.json"):
            try:
                json.loads((ROOT / directory / filename).read_text())
            except (OSError, ValueError) as error:
                errors.append(f"{directory}/{filename}: {error}")
    if not (ROOT / "LICENSE").is_file():
        errors.append("missing root LICENSE")
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"PASS: {python_count} Python files parsed, {link_count} local entry-doc links, "
          "Runtime direct-import boundary and current frontend manifests checked.")
    print("Scope: syntax/static boundaries only; no application execution, model or database calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
