#!/usr/bin/env python3
"""Check that relative links in Markdown files resolve.

Runs in CI without third-party dependencies. External URLs are not fetched:
network checks are slow, flaky, and fail for reasons unrelated to the change.
What is checked is the thing a code review usually misses — a relative path
that stopped existing when a file was renamed.

Usage:
    python .github/scripts/check_docs_links.py [--root .]

Exit code 0 when every relative link resolves, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# Directories that never contain documentation we own.
SKIP_DIRS = {
    ".git",
    ".workbuddy",
    ".pytest_cache",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "test-results",
    "playwright-report",
    "htmlcov",
}

# `[text](target)` and `![alt](target)`, ignoring an optional title.
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")

# Schemes and prefixes that are not local paths.
SKIP_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "ftp://",
    "#",
    "<",
    "data:",
)


def iter_markdown(root: Path):
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def check_file(path: Path, root: Path) -> list[tuple[int, str]]:
    problems: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in LINK_RE.finditer(line):
            target = match.group(1).strip()
            if not target or target.lower().startswith(SKIP_PREFIXES):
                continue
            # Drop fragment and query string; only the file path is verifiable here.
            local = target.split("#", 1)[0].split("?", 1)[0]
            if not local:
                continue
            local = unquote(local)
            resolved = (root / local.lstrip("/")) if local.startswith("/") else (path.parent / local)
            if not resolved.exists():
                problems.append((lineno, target))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = list(iter_markdown(root))
    broken = 0
    for path in files:
        problems = check_file(path, root)
        for lineno, target in problems:
            broken += 1
            print(f"BROKEN {path.relative_to(root)}:{lineno} -> {target}")

    print(f"checked {len(files)} markdown files, {broken} broken relative link(s)")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
