"""Check the current publication tree for restricted files and individual records."""

import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PERSONAL_FIELDS = {
    "id",
    "subject_id",
    "participant_id",
    "person_id",
    "source_subject",
    "source_id",
    "pseudonym",
    "acq_cnp_files",
}
PRIVATE_SUFFIXES = {
    ".acq",
    ".snirf",
    ".nirs",
    ".omm",
    ".cnp",
    ".doc",
    ".docx",
    ".bundle",
}
SECRET = re.compile(
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)
LOCATION = re.compile(
    r"(?:/Users/[A-Za-z0-9_. -]+/|[A-Z]:[/\\]Users[/\\][A-Za-z0-9_. -]+[/\\])"
)


def issue(name, data):
    path = Path(name)
    if path.suffix.lower() in PRIVATE_SUFFIXES or path.name.startswith("._"):
        return "Restricted artifact"
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
        return "Controlled directory"
    if re.search(
        r"baselineData.*\.csv$|identity_mapping|pseudonymized.*\.csv$", path.name, re.I
    ):
        return "Individual-record filename"
    if path.name in {".env", ".netrc", "hosts.yml", "hosts.yaml"}:
        return "Local credential file"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if SECRET.search(text):
        return "Credential material"
    if LOCATION.search(text):
        return "Personal source location"
    if path.suffix.lower() in {".csv", ".tsv"}:
        rows = list(
            csv.reader(
                io.StringIO(text), delimiter="\t" if path.suffix == ".tsv" else ","
            )
        )
        fields = rows[0] if rows else []
        if PERSONAL_FIELDS & {field.casefold() for field in fields}:
            synthetic = (
                name == "tests/fixtures/synthetic_vas.csv"
                and fields[0] == "ID"
                and all(row and row[0].startswith("SYN") for row in rows[1:])
            )
            blank_schema = name.startswith("schemas/") and len(rows) <= 1
            if not (synthetic or blank_schema):
                return "Individual-level columns"
    return None


def verify(root=ROOT):
    root = Path(root).resolve()
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
        )
        .decode()
        .strip("\0")
        .split("\0")
    )
    failures = []
    checked = 0
    for name in sorted(set(names)):
        path = root / name
        if not name or not path.exists():
            continue
        if path.is_symlink():
            failures.append({"file": name, "reason": "Symlink excluded"})
            continue
        if not path.is_file():
            continue
        checked += 1
        reason = issue(name, path.read_bytes())
        if reason:
            failures.append({"file": name, "reason": reason})
    return {
        "status": "PASS" if not failures else "FAIL",
        "scope": "current working files",
        "checked_files": checked,
        "failures": failures,
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)
