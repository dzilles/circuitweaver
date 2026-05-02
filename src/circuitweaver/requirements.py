"""Requirement traceability helpers."""

from __future__ import annotations

import re
from pathlib import Path

REQUIREMENT_RE = re.compile(r"`([A-Z]+-\d{3})`")


def requirement_ids(requirement_file: Path) -> set[str]:
    """Return requirement IDs from a markdown requirement file."""
    return set(REQUIREMENT_RE.findall(requirement_file.read_text(encoding="utf-8")))


def test_ids(test_file: Path) -> set[str]:
    """Return requirement IDs represented by test function names."""
    ids: set[str] = set()
    for match in re.finditer(r"def test_([a-z]+)_(\d{3})_", test_file.read_text(encoding="utf-8")):
        ids.add(f"{match.group(1).upper()}-{match.group(2)}")
    return ids


def traceability_report(requirement_file: Path, test_file: Path) -> dict[str, object]:
    """Report requirement IDs without matching tests."""
    requirements = requirement_ids(requirement_file)
    tests = test_ids(test_file)
    missing = sorted(requirements - tests)
    return {
        "ok": not missing,
        "requirements": sorted(requirements),
        "tests": sorted(tests),
        "missing": missing,
    }
