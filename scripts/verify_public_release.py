"""Audit current public content and approved aggregate bytes, not Git history."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PERSONAL_HEADERS = {
    "id",
    "subject_id",
    "person_id",
    "participant_id",
    "source_subject",
    "source_id",
    "pseudonym",
    "acq_cnp_files",
}
PRIVATE_NAME = re.compile(
    r"baselineData.*\.csv$|(?:_private|_PRIVATE)\.|identity_mapping|pseudonymized.*\.csv$",
    re.I,
)
REAL_ID = re.compile(r"(?<![A-Za-z_])SUBJECT\d{3}\b")
RAW_EXTENSIONS = {".acq", ".snirf", ".nirs", ".omm", ".cnp", ".bundle"}
SECRET_PATTERN = re.compile(
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|https?://[^\s/:]+:[^\s/@]+@"
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def content_issue(name, data, approved_aggregates, approved_csv):
    """Reject common leaks and every CSV outside the explicit release inventory."""
    path = Path(name)
    if path.name.startswith("._") or path.name == ".DS_Store":
        return "AppleDouble/system file included"
    if PRIVATE_NAME.search(path.name) or path.suffix.lower() in RAW_EXTENSIONS:
        return "Restricted participant artifact included"
    if path.name in {".env", ".netrc", "hosts.yml", "hosts.yaml"}:
        return "Local credential/configuration file included"
    if any(
        part
        in {
            "private",
            "private_inputs",
            "restricted_data",
            "01_data",
            "02_quality_control",
            "08_outputs",
        }
        for part in path.parts
    ):
        return "Private/run directory included"
    if path.suffix.lower() in {".csv", ".tsv"}:
        if name not in approved_csv:
            return "CSV is outside the explicit public inventory"
        try:
            reader = csv.reader(
                io.StringIO(data.decode("utf-8-sig")),
                delimiter="\t" if path.suffix == ".tsv" else ",",
            )
            fields = next(reader, [])
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error):
            return "Unreadable CSV"
        if PERSONAL_HEADERS & {field.casefold() for field in fields}:
            synthetic = (
                name == "tests/fixtures/synthetic_vas.csv"
                and fields
                and fields[0] == "ID"
                and all(row and row[0].startswith("SYN") for row in rows)
            )
            template = name.startswith("schemas/") and not rows
            if not (synthetic or template):
                return "Individual identifiers or source links in a non-synthetic table"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        if path.suffix in {
            ".py",
            ".R",
            ".json",
            ".csv",
            ".md",
            ".html",
            ".svg",
            ".toml",
            ".txt",
            ".in",
            ".yaml",
            ".yml",
            ".sh",
        }:
            return "Unreadable text artifact"
    else:
        if SECRET_PATTERN.search(text):
            return "Credential/token/private key found"
        if REAL_ID.search(text):
            return "Original research-ID namespace found"
        if re.search(
            r"(?:/Users/[A-Za-z0-9_. -]+/|/"
            + r"Volumes/[^\[\]\s]+|[A-Z]:[/\\]Users[/\\][A-Za-z0-9_. -]+[/\\])",
            text,
        ):
            return "Personal absolute source location found"
    if (
        name in approved_aggregates
        and sha(data) != approved_aggregates[name]["published_sha256"]
    ):
        return "Approved aggregate hash mismatch"
    return None


def verify(root=ROOT, index=False):
    root = Path(root).resolve()
    inventory = json.loads((root / "docs/release_inventory.json").read_text())
    aggregates = inventory["aggregate_files"]
    source_files = inventory["source_snapshot"]
    approved_csv = set(aggregates) | {
        name for name in source_files if name.endswith(".csv")
    }
    # Git supplies candidate paths, including untracked files, while respecting ignore rules.
    args = (
        ["git", "ls-files", "-z"]
        if index
        else ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    )
    names = sorted(
        set(subprocess.check_output(args, cwd=root).decode().strip("\0").split("\0"))
    )
    failures = []
    checked = 0
    for name in names:
        if not name:
            continue
        path = root / name
        if index:
            data = subprocess.check_output(["git", "show", ":" + name], cwd=root)
        else:
            if not path.is_file():
                continue  # A removed worktree file is not released from the worktree.
            if path.is_symlink():
                failures.append(
                    dict(file=name, reason="Symlink excluded from public release")
                )
                continue
            data = path.read_bytes()
        checked += 1
        issue = content_issue(name, data, aggregates, approved_csv)
        if issue:
            failures.append(dict(file=name, reason=issue))
    for name, record in aggregates.items():
        path = root / name
        if not path.is_file() or sha(path.read_bytes()) != record["published_sha256"]:
            failures.append(
                dict(file=name, reason="Missing/modified approved aggregate")
            )
    for name, record in source_files.items():
        path = root / name
        if not path.is_file() or sha(path.read_bytes()) != record["published_sha256"]:
            failures.append(
                dict(file=name, reason="Missing/modified published source snapshot")
            )
    result = dict(
        status="PASS" if not failures else "FAIL",
        scope="current index" if index else "current worktree",
        checked_files=checked,
        approved_aggregate_files=len(aggregates),
        source_snapshot_files=len(source_files),
        failures=failures,
        individual_data_allowed=False,
        history_checked=False,
        history_cleanup_assessed=False,
        disclosure_risk_certified=False,
        scientific_validation=False,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        action="store_true",
        help="Also read every staged/index blob, including deletions not yet staged",
    )
    args = parser.parse_args()
    result = verify(index=args.index)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "PASS" else 2)
