"""Time-reversal-invariant RR candidate continuity audit."""

from __future__ import annotations
import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capsaicin.ecg_rr_candidates_v2 import symmetric_rr_continuity

CFG = ROOT / "config/ecg_rr_symmetric_v1.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["input_run"]
    ip = source / "rr_intervals_private.csv"
    sp = source / "record_summary_private.csv"
    mp = source / "run_manifest.json"
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    for p in (ip, sp):
        if sha(p) != manifest["output_sha256"][p.name]:
            raise ValueError(f"source hash mismatch: {p}")
    with ip.open(encoding="utf-8-sig", newline="") as f:
        intervals = list(csv.DictReader(f))
    grouped = defaultdict(list)
    for row in intervals:
        grouped[(row["subject_id"], row["recording_stem"], row["stage"])].append(row)
    detail = []
    records = []
    for key, source_rows in sorted(grouped.items()):
        source_rows.sort(key=lambda r: int(r["interval_index"]))
        values = [float(r["rr_seconds"]) for r in source_rows]
        result = symmetric_rr_continuity(
            values, *cfg["rr_bounds_seconds"], cfg["adjacent_log_ratio_jump_fraction"]
        )
        reverse = symmetric_rr_continuity(
            values[::-1],
            *cfg["rr_bounds_seconds"],
            cfg["adjacent_log_ratio_jump_fraction"],
        )
        if (
            result["range_valid"].tolist() != reverse["range_valid"][::-1].tolist()
            or result["edge_continuous"].tolist()
            != reverse["edge_continuous"][::-1].tolist()
        ):
            raise AssertionError("time reversal invariance failed")
        block_values = defaultdict(list)
        for i, (row, valid, block) in enumerate(
            zip(source_rows, result["range_valid"], result["block_ids"])
        ):
            if valid:
                block_values[int(block)].append(float(row["rr_seconds"]))
            detail.append(
                {
                    "subject_id": key[0],
                    "recording_stem": key[1],
                    "stage": key[2],
                    "interval_index": i,
                    "rr_seconds": row["rr_seconds"],
                    "range_valid": bool(valid),
                    "symmetric_block_id": int(block),
                    "left_edge_continuous": None
                    if i == 0
                    else bool(result["edge_continuous"][i - 1]),
                    "right_edge_continuous": None
                    if i == len(values) - 1
                    else bool(result["edge_continuous"][i]),
                }
            )
        diffs = [
            b - a
            for vals in block_values.values()
            if len(vals) >= cfg["minimum_intervals_per_block"]
            for a, b in zip(vals[:-1], vals[1:])
        ]
        records.append(
            {
                "subject_id": key[0],
                "recording_stem": key[1],
                "stage": key[2],
                "rr_candidates": len(values),
                "range_invalid": int((~result["range_valid"]).sum()),
                "discontinuous_edges": int((~result["edge_continuous"]).sum()),
                "symmetric_blocks": len(block_values),
                "candidate_rmssd_seconds": float(np.sqrt(np.mean(np.square(diffs))))
                if diffs
                else None,
                "direction_invariance_dice": 1.0,
            }
        )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_rr_symmetric_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    for name, rows in (
        ("interval_continuity_private.csv", detail),
        ("record_summary_private.csv", records),
    ):
        with (out / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    vals = [
        r["candidate_rmssd_seconds"]
        for r in records
        if r["candidate_rmssd_seconds"] is not None
    ]
    summary = {
        "development_records": len(records),
        "rr_candidates": sum(r["rr_candidates"] for r in records),
        "range_invalid": sum(r["range_invalid"] for r in records),
        "discontinuous_edges": sum(r["discontinuous_edges"] for r in records),
        "symmetric_blocks": sum(r["symmetric_blocks"] for r in records),
        "records_with_candidate_rmssd": len(vals),
        "median_candidate_rmssd_ms": float(np.median(vals) * 1000) if vals else None,
        "direction_invariance_dice": 1.0,
        "parameter_selection_from_current_data": False,
        "normal_beat_or_nn_reference_available": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    inputs = (
        CFG,
        Path(__file__),
        ROOT / "src/capsaicin/ecg_rr_candidates_v2.py",
        ip,
        sp,
        mp,
    )
    run = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": rev.stdout.strip() if rev.returncode == 0 else None,
        "output_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()},
    }
    (out / "run_manifest.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
