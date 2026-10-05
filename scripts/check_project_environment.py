"""Inspect the versioned project runtime; do not read participant data or start Dask."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys


def inspect_environment(lock: Path) -> dict:
    from packaging.requirements import Requirement

    packages = {}
    issues = []
    for raw in lock.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removesuffix("\\").strip()
        if not line or line.startswith(("#", "--")):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            actual = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        okay = actual is not None and requirement.specifier.contains(actual)
        packages[requirement.name] = {
            "expected": str(requirement.specifier),
            "actual": actual,
            "matches": okay,
        }
        if not okay:
            issues.append(requirement.name)
    python_okay = platform.python_version() == "3.12.13"
    if not python_okay:
        issues.append("python")
    return {
        "python": platform.python_version(),
        "expected_python": "3.12.13",
        "executable": sys.executable,
        "platform": platform.platform(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "packages": packages,
        "issues": issues,
        "status": "PASS" if not issues else "ENVIRONMENT_MISMATCH",
        "participant_data_read": False,
        "dask_workers_started": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "dependencies/project-python312-20261003-v2.lock.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional new JSON output; an existing file is never overwritten",
    )
    args = parser.parse_args()
    result = inspect_environment(args.lock)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
    print(serialized, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
