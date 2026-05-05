#!/usr/bin/env python3
"""Fail CI when shipped InferGuard production paths contain incomplete-code markers."""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

ALLOWLIST_RULE = "scan-no-stubs"
ALLOWLIST_RE = re.compile(r"#\s*noqa:\s*scan-no-stubs\s+(.+)$")
BLOCKED_COMMENT_WORDS = ("TODO", "FIXME", "XXX", "NotImplementedError", "placeholder")
BLOCKED_CODE_NAMES = {"NotImplementedError", "placeholder", "mock", "stub"}
PURE_REEXPORT_RE = re.compile(r"from\s+\.[A-Za-z_][\w.]*\s+import\s+.+")


@dataclass(frozen=True)
class Violation:
    """One scanner violation with enough location detail for CI output."""

    path: Path
    line: int
    rule: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


def scan_for_stubs(paths: list[str | Path]) -> list[Violation]:
    """Scan production Python files under paths and return blocking violations."""
    violations: list[Violation] = []
    for root in paths:
        path = Path(root)
        if path.is_file():
            candidates = [path]
        else:
            candidates = sorted(path.rglob("*.py")) if path.exists() else []
        for candidate in candidates:
            if _excluded(candidate):
                continue
            violations.extend(_scan_file(candidate))
    return violations


def _excluded(path: Path) -> bool:
    parts = set(path.parts)
    if {"tests", "fixtures", "docs", "release_proofs"} & parts:
        return True
    return _pure_reexport_init(path)


def _pure_reexport_init(path: Path) -> bool:
    if path.name != "__init__.py":
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return False
    if len(lines) >= 50:
        return False
    code_lines = [
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]
    if not code_lines:
        return False
    return all(PURE_REEXPORT_RE.fullmatch(line) for line in code_lines)


def _scan_file(path: Path) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[Violation] = []
    violations.extend(_scan_tokens(path, text, lines))
    violations.extend(_scan_function_body_pass(path, text, lines))
    return violations


def _scan_tokens(path: Path, text: str, lines: list[str]) -> list[Violation]:
    violations: list[Violation] = []
    reader = io.StringIO(text).readline
    for token in tokenize.generate_tokens(reader):
        token_type = token.type
        token_text = token.string
        line_no = token.start[0]
        source_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if _allowlisted(source_line):
            continue
        if token_type == tokenize.COMMENT:
            for word in BLOCKED_COMMENT_WORDS:
                if word in token_text:
                    violations.append(Violation(path, line_no, word, f"blocked marker {word!r}"))
        elif token_type == tokenize.NAME and token_text in BLOCKED_CODE_NAMES:
            violations.append(
                Violation(path, line_no, token_text, f"blocked code name {token_text!r}")
            )
    return violations


def _scan_function_body_pass(path: Path, text: str, lines: list[str]) -> list[Violation]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [Violation(path, line, "syntax", f"could not parse Python file: {exc.msg}")]
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = _body_without_docstring(node.body)
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            line_no = body[0].lineno
            source_line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            if not _allowlisted(source_line):
                violations.append(
                    Violation(path, line_no, "pass", f"function {node.name!r} has pass as its body")
                )
    return violations


def _body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return body[1:]
    return body


def _allowlisted(source_line: str) -> bool:
    match = ALLOWLIST_RE.search(source_line)
    if not match:
        return False
    return len(match.group(1).strip()) > 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    args = parser.parse_args(argv)
    violations = scan_for_stubs(args.paths)
    if violations:
        print("scan_no_stubs: blocking production markers found", file=sys.stderr)
        for violation in violations:
            print(violation.format(), file=sys.stderr)
        return 1
    print("scan_no_stubs: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
