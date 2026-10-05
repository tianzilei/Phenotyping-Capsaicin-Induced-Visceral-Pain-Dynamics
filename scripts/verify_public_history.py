"""Audit every reachable commit and require a complete, reachable-only object store."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from verify_public_release import ROOT, content_issue, sha


def verify_history(root=ROOT):
    root = Path(root).resolve()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root)

    failures = []
    gitdir = Path(git("rev-parse", "--absolute-git-dir").decode().strip())
    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        failures.append({"reason": "Shallow history cannot be audited completely"})
    if git("replace", "-l").strip():
        failures.append({"reason": "Replace refs can conceal original commits"})
    for name in (
        "info/grafts",
        "objects/info/alternates",
        "objects/info/http-alternates",
    ):
        if (gitdir / name).exists():
            failures.append(
                {"reason": "History/object indirection excluded", "file": name}
            )
    partial = subprocess.run(
        [
            "git",
            "config",
            "--get-regexp",
            r"^(extensions\.partialclone|remote\..*\.promisor)$",
        ],
        cwd=root,
        capture_output=True,
    )
    if partial.stdout.strip():
        failures.append(
            {"reason": "Partial clone cannot establish full object coverage"}
        )
    if failures:
        return {
            "status": "FAIL",
            "scope": "all reachable history and object store",
            "failures": failures,
        }

    def ref_snapshot():
        return (
            git("for-each-ref", "--format=%(refname) %(objectname)"),
            git("rev-parse", "HEAD"),
        )

    initial_refs = ref_snapshot()
    for line in initial_refs[0].decode().splitlines():
        name, oid = line.split()
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", oid + "^{commit}"],
            cwd=root,
            capture_output=True,
        )
        if resolved.returncode:
            failures.append(
                {"ref": name, "reason": "Ref does not resolve to an auditable commit"}
            )
    commits = git("rev-list", "--all", "HEAD").decode().splitlines()
    if not commits:
        failures.append({"reason": "No referenced commits to audit"})
    checked = 0
    for commit in commits:
        entries = []
        for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if not entry:
                continue
            metadata, name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            entries.append((mode, kind, oid, name.decode()))
        try:
            inventory = json.loads(git("show", commit + ":docs/release_inventory.json"))
            aggregates = inventory["aggregate_files"]
            sources = inventory["source_snapshot"]
        except (subprocess.CalledProcessError, ValueError, KeyError):
            failures.append(
                {"commit": commit, "reason": "Missing/invalid public inventory"}
            )
            aggregates, sources = {}, {}
        approved_csv = set(aggregates) | {
            name for name in sources if name.endswith(".csv")
        }
        present = set()
        for mode, kind, oid, name in entries:
            present.add(name)
            if kind != "blob" or mode not in {"100644", "100755"}:
                failures.append(
                    {
                        "commit": commit,
                        "file": name,
                        "reason": "Symlink/submodule/non-regular entry excluded",
                    }
                )
                continue
            data = git("cat-file", "blob", oid)
            checked += 1
            issue = content_issue(name, data, aggregates, approved_csv)
            record = sources.get(name)
            if not issue and record and sha(data) != record["published_sha256"]:
                issue = "Historical source snapshot hash mismatch"
            if issue:
                failures.append({"commit": commit, "file": name, "reason": issue})
        for name in set(aggregates) | set(sources):
            if name not in present:
                failures.append(
                    {
                        "commit": commit,
                        "file": name,
                        "reason": "Inventory file missing from commit",
                    }
                )

    reachable = {
        line.split()[0]
        for line in git("rev-list", "--objects", "--all", "HEAD").decode().splitlines()
    }
    stored = set(
        git("cat-file", "--batch-all-objects", "--batch-check=%(objectname)")
        .decode()
        .splitlines()
    )
    unreachable = stored - reachable
    if unreachable:
        failures.append(
            {
                "reason": "Unreachable objects remain in Git storage",
                "count": len(unreachable),
            }
        )
    fsck = subprocess.run(
        ["git", "fsck", "--full", "--strict", "--no-reflogs"],
        cwd=root,
        capture_output=True,
    )
    if fsck.returncode:
        failures.append(
            {
                "reason": "Git object integrity check failed",
                "exit_code": fsck.returncode,
            }
        )
    if ref_snapshot() != initial_refs:
        failures.append(
            {
                "reason": "Git references changed during audit; stop background fetch and rerun"
            }
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "scope": "all reachable history and object store",
        "commits": len(commits),
        "checked_file_versions": checked,
        "stored_objects": len(stored),
        "reachable_objects": len(reachable),
        "unreachable_objects": len(unreachable),
        "failures": failures,
        "remote_history_checked": False,
        "disclosure_risk_certified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify_history(args.root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 2)
