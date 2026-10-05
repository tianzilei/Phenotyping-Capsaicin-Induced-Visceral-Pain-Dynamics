"""Development-only RR threshold and scan-direction sensitivity audit."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from capsaicin.ecg_rr_candidates_v2 import classify_rr_values, enforce_refractory
from run_rest_waveform_qc import channel_indices, read_acq

CFG = ROOT / "config/ecg_rr_sensitivity_v1.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    source = ROOT / cfg["input_run"]
    ep, rp, mp = (
        source / "ecg_events_private.csv",
        source / "development_diagnostics_private.csv",
        source / "run_manifest.json",
    )
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    for p in (ep, rp):
        if sha(p) != manifest["output_sha256"][p.name]:
            raise ValueError(f"source hash mismatch: {p}")
    with ep.open(encoding="utf-8-sig", newline="") as f:
        events = list(csv.DictReader(f))
    with rp.open(encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    grouped = defaultdict(list)
    for row in events:
        grouped[(row["subject_id"], row["recording_stem"], row["stage"])].append(
            (int(row["aligned_lead_ii_sample"]), int(row["distinct_lead_votes"]))
        )
    rows = []
    input_hashes = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            CFG,
            Path(__file__),
            ROOT / "src/capsaicin/ecg_rr_candidates_v2.py",
            ep,
            rp,
            mp,
        )
    }
    for record in records:
        if record["pool"] != cfg["pool"]:
            raise ValueError("non-development record")
        key = (record["subject_id"], record["recording_stem"], record["stage"])
        path = Path(record["source_path"])
        if sha(path) != manifest["input_sha256"].get(str(path)):
            raise ValueError("ACQ hash mismatch")
        arr, fs, names = read_acq(path)
        ecg, _ = channel_indices(names)
        if not ecg:
            raise ValueError("ECG channels missing")
        kept = enforce_refractory(grouped[key], fs, cfg["refractory_seconds"])
        values = [(kept[i][0] - kept[i - 1][0]) / fs for i in range(1, len(kept))]
        for threshold in cfg["jump_fractions"]:
            forward = classify_rr_values(
                values, *cfg["rr_bounds_seconds"], threshold, False
            )
            reverse = classify_rr_values(
                values, *cfg["rr_bounds_seconds"], threshold, True
            )
            fset = {
                i
                for i, x in enumerate(forward)
                if x["status"] == "RR_CANDIDATE_FLAGGED"
            }
            rset = {
                i
                for i, x in enumerate(reverse)
                if x["status"] == "RR_CANDIDATE_FLAGGED"
            }
            denom = len(fset) + len(rset)
            dice = (2 * len(fset & rset) / denom) if denom else 1.0
            rows.append(
                {
                    "subject_id": key[0],
                    "recording_stem": key[1],
                    "stage": key[2],
                    "jump_fraction": threshold,
                    "rr_candidates": len(values),
                    "forward_flagged": len(fset),
                    "reverse_flagged": len(rset),
                    "flag_union": len(fset | rset),
                    "flag_intersection": len(fset & rset),
                    "direction_dice": dice,
                    "forward_relocks": sum(x["relock_boundary"] for x in forward),
                    "reverse_relocks": sum(x["relock_boundary"] for x in reverse),
                }
            )
    out = (
        ROOT
        / "08_outputs"
        / (
            "ecg_rr_sensitivity_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "_"
            + uuid.uuid4().hex[:8]
        )
    )
    out.mkdir()
    with (out / "record_sensitivity_private.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "development_records": len(records),
        "thresholds": cfg["jump_fractions"],
        "rows": len(rows),
        "threshold_selection_performed": False,
        "normal_beat_or_nn_reference_available": False,
        "application_or_sealed_records_read": False,
        "by_threshold": {
            str(t): {
                "forward_flagged": sum(
                    r["forward_flagged"] for r in rows if r["jump_fraction"] == t
                ),
                "reverse_flagged": sum(
                    r["reverse_flagged"] for r in rows if r["jump_fraction"] == t
                ),
                "median_direction_dice": float(
                    __import__("numpy").median(
                        [r["direction_dice"] for r in rows if r["jump_fraction"] == t]
                    )
                ),
            }
            for t in cfg["jump_fractions"]
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rev = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    run = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": input_hashes,
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
