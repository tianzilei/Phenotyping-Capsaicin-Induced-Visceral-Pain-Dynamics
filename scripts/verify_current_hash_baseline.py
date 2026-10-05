"""Verify current baseline files; --full rereads all signal bytes."""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from build_hash_baseline import ROOT, sha, write


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    cfg = json.loads((ROOT / "config/hash_baseline_active.json").read_text())
    path = Path(cfg["files_index"])
    assert sha(path) == cfg["files_index_sha256"]
    assert sha(Path(cfg["historical_ledger"])) == cfg["historical_ledger_sha256"]
    entries = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    hashed = 0
    sized = 0
    for row in entries.values():
        p = Path(row["path"])
        if not p.is_file():
            problems.append(dict(path=str(p), status="missing"))
            continue
        if p.stat().st_size != row["bytes"]:
            problems.append(dict(path=str(p), status="size_changed"))
            continue
        sized += 1
        # Full scan was performed on baseline creation. Default checks all small
        # files; large signal hashes require explicit --full, never implied.
        if args.full or row["bytes"] < 1024 * 1024:
            hashed += 1
            if sha(p) != row["sha256"]:
                problems.append(dict(path=str(p), status="hash_changed"))
    out = Path(cfg["directory"]) / (
        "verification_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
        + ".json"
    )
    result = dict(
        status="passed" if not problems else "failed",
        files=len(entries),
        size_checks=sized,
        sha256_checks=hashed,
        full_signal_rehash=args.full,
        problems=problems,
        baseline_index_sha256=sha(path),
        verification_code_sha256=sha(Path(__file__)),
    )
    write(out, result)
    print(json.dumps({k: v for k, v in result.items() if k != "problems"}, indent=2))
    print(out)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
