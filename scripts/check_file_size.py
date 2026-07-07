#!/usr/bin/env python3
"""Fail if any tracked code file exceeds the line limit.

Enforces the spot convention of <=500 lines/file. A file opts out with a
comment line containing ``spot: allow-large-file`` (add a reason after it).
Only git-tracked files with a code extension are checked, so lockfiles,
generated code, data, and vendored deps are excluded by construction.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAX_LINES = 500
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sh"}
OPT_OUT = "spot: allow-large-file"


def tracked_code_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout
    return [Path(p) for p in out.splitlines() if Path(p).suffix in CODE_EXTS]


def line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def has_opt_out(path: Path) -> bool:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return any(OPT_OUT in line for line in fh)


def check(files: list[Path], max_lines: int = MAX_LINES) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    exemptions: list[str] = []
    for path in files:
        n = line_count(path)
        if n <= max_lines:
            continue
        if has_opt_out(path):
            exemptions.append(f"{path}: {n} lines (opted out)")
        else:
            violations.append(f"{path}: {n} lines (> {max_lines})")
    return violations, exemptions


def main() -> int:
    violations, exemptions = check(tracked_code_files())
    for entry in exemptions:
        print(f"exempt: {entry}")
    for entry in violations:
        print(f"TOO LARGE: {entry}")
    if violations:
        print(
            f"\n{len(violations)} file(s) exceed {MAX_LINES} lines. "
            f"Split them, or add a '{OPT_OUT} <reason>' comment."
        )
        return 1
    print(f"file-size guard: all tracked code files <= {MAX_LINES} lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
